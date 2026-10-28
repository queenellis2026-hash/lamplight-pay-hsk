"""Tests for scripts/deploy_hsk_testnet.py — the Oct 28, 2026 fixes.

No network, no testnet funds: everything runs on eth-tester/PyEVM.
Covers the two round-16 redeploy failures (STATUS.md "Redeploy"):

  1. STALE NONCE — the public RPC returned a stale nonce on the second
     get_transaction_count in one run, so the AgentEscrow tx reused the
     just-mined MockUSDC nonce and was rejected as "replacement
     transaction underpriced". The fix fetches the nonce ONCE (pending)
     and increments it locally; the test proves the count is queried
     exactly once and both deploys still land with sequential nonces
     even when a second query WOULD have returned a stale value.
  2. GAS CAP TOO LOW — the hardcoded 3,000,000 cap was below the
     AgentEscrow estimate (4,800,180), so the first explicit-nonce
     attempt consumed all 3M gas and failed (status 0, dead address
     0xc266B0099fd6BA8812a0d85048Fc592C7B78bd8E). The fix derives the
     limit from eth_estimateGas + 25% headroom, floored at 5,000,000.
     The test proves the old cap is below the real estimate and the new
     limit is above it, and that a full two-contract deploy lands with
     both receipts status 1.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402
from eth_tester import EthereumTester, PyEVMBackend  # noqa: E402
from web3 import Web3  # noqa: E402
from web3.providers.eth_tester import EthereumTesterProvider  # noqa: E402

import deploy_hsk_testnet as deploy  # noqa: E402

# eth-tester account 0 (0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf) is key 1.
TESTER_KEY_0 = "0x" + "00" * 31 + "01"
OLD_HARDCODED_GAS_CAP = 3_000_000  # the pre-fix cap that killed AgentEscrow
LIVE_AGENT_ESCROW_ESTIMATE = 4_800_180  # measured on HSK testnet, Oct 28, 2026


def _w3_and_acct():
    tester = EthereumTester(PyEVMBackend())
    w3 = Web3(EthereumTesterProvider(tester))
    acct = w3.eth.account.from_key(TESTER_KEY_0)
    assert acct.address == w3.eth.accounts[0]
    return w3, acct


def _constructor_estimate(w3, acct, name):
    artifact = json.loads((ROOT / "build" / f"{name}.json").read_text())
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
    return contract.constructor().estimate_gas({"from": acct.address})


# --- gas-limit rule -------------------------------------------------------

def test_gas_limit_is_estimate_plus_25_percent_headroom():
    assert deploy.deploy_gas_limit(LIVE_AGENT_ESCROW_ESTIMATE) == 6_000_225
    assert deploy.deploy_gas_limit(1_000_000) == 5_000_000  # floor, not 1.25M
    assert deploy.deploy_gas_limit(4_000_000) == 5_000_000  # 5.0M exactly: floor wins
    assert deploy.deploy_gas_limit(4_000_001) == 5_000_002  # 5,000,001.25 -> ceil
    assert deploy.deploy_gas_limit(0) == 5_000_000


def test_gas_limit_never_below_estimate_or_floor():
    for estimate in (0, 1, 100_000, 1_000_000, 4_800_180, 10_000_000, 25_000_000):
        limit = deploy.deploy_gas_limit(estimate)
        assert limit >= deploy.MIN_GAS_LIMIT, estimate
        assert limit >= estimate, estimate


def test_old_3m_cap_is_below_the_real_agent_escrow_estimate():
    """The old failure mode, proven: 3,000,000 < estimate, so the old
    script's AgentEscrow deploy could never have succeeded."""
    w3, acct = _w3_and_acct()
    estimate = _constructor_estimate(w3, acct, "AgentEscrow")
    assert estimate > OLD_HARDCODED_GAS_CAP, estimate
    assert deploy.deploy_gas_limit(estimate) > estimate
    # And the live-testnet figure from the round-16 run agrees in kind.
    assert LIVE_AGENT_ESCROW_ESTIMATE > OLD_HARDCODED_GAS_CAP


# --- one-run deploy: nonce discipline + gas -------------------------------

def test_deploy_both_contracts_one_run_sequential_nonces_and_status_1():
    w3, acct = _w3_and_acct()
    estimates = {n: _constructor_estimate(w3, acct, n) for n in ("MockUSDC", "AgentEscrow")}
    deployed = deploy.deploy_contracts(w3, acct, w3.eth.chain_id)
    assert set(deployed) == {"MockUSDC", "AgentEscrow"}
    assert w3.eth.get_transaction_count(acct.address) == 2
    for name, address in deployed.items():
        assert w3.eth.get_code(address) != b"", name  # real code landed
        assert deploy.deploy_gas_limit(estimates[name]) >= deploy.MIN_GAS_LIMIT
    # Nonces are sequential 0, 1: recoverable from the mined txs. eth-tester
    # mines each tx in its own block, so scan every block, not just latest.
    txs = []
    for n in range(w3.eth.block_number + 1):
        blk = w3.eth.get_block(n)
        txs += [w3.eth.get_transaction(h) for h in blk.transactions]
    nonces = sorted(t.nonce for t in txs if t["from"] == acct.address)
    assert nonces == [0, 1]
    # The gas limits actually used carry the 25% headroom, not the old cap.
    limits = {t.nonce: t.gas for t in txs if t["from"] == acct.address}
    assert limits[0] >= estimates["MockUSDC"] * 1.25
    assert limits[1] >= estimates["AgentEscrow"] * 1.25
    assert limits[1] >= deploy.MIN_GAS_LIMIT


def test_nonce_is_fetched_exactly_once_even_if_rpc_would_go_stale():
    """The stale-nonce failure, proven gone: the deploy path queries
    get_transaction_count once per run. A second query is where the
    public RPC returned the stale value — so we make the mock return
    a STALE 0 on any second call and assert the deploys still land
    with nonces 0 and 1 (they would collide at nonce 0 if the script
    re-queried)."""
    w3, acct = _w3_and_acct()
    real_get_count = w3.eth.get_transaction_count
    calls = []

    def counting_and_stale(address, block="latest"):
        calls.append(block)
        if len(calls) > 1:
            return 0  # the stale value the public RPC returned mid-run
        return real_get_count(address, block)

    w3.eth.get_transaction_count = counting_and_stale
    try:
        deployed = deploy.deploy_contracts(w3, acct, w3.eth.chain_id)
    finally:
        w3.eth.get_transaction_count = real_get_count
    assert len(calls) == 1, calls  # fetched once — the fix
    assert set(deployed) == {"MockUSDC", "AgentEscrow"}
    txs = []
    for n in range(w3.eth.block_number + 1):
        blk = w3.eth.get_block(n)
        txs += [w3.eth.get_transaction(h) for h in blk.transactions]
    nonces = sorted(t.nonce for t in txs if t["from"] == acct.address)
    assert nonces == [0, 1]


def test_failed_deploy_aborts_instead_of_being_recorded():
    """A status-0 receipt must raise, not return an address: the old
    script recorded whatever receipt came back, so the dead address
    from the 3M-gas failure would have been written to the record as
    a live deploy. Proven by making the receipt lookup return a
    status-0 receipt for the first deploy — deploy_contracts must
    abort with SystemExit and return nothing."""
    from types import SimpleNamespace

    w3, acct = _w3_and_acct()
    real_wait = w3.eth.wait_for_transaction_receipt
    calls = []

    def failing_receipt(tx_hash, *args, **kwargs):
        calls.append(tx_hash)
        if len(calls) == 1:
            return SimpleNamespace(status=0, contractAddress=None,
                                   transactionHash=tx_hash)
        return real_wait(tx_hash, *args, **kwargs)

    w3.eth.wait_for_transaction_receipt = failing_receipt
    try:
        with pytest.raises(SystemExit, match="FAILED"):
            deploy.deploy_contracts(w3, acct, w3.eth.chain_id)
    finally:
        w3.eth.wait_for_transaction_receipt = real_wait
    assert len(calls) == 1  # aborted on the first failure, never deployed #2

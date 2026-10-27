"""Tests for Lamplight Pay — run on the local EVM, no network needed.

Usage: .venv/bin/python -m pytest tests/ -v   (or: .venv/bin/python tests/test_flow.py)
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from eth_tester import EthereumTester, PyEVMBackend  # noqa: E402
from web3 import Web3  # noqa: E402
from web3.providers.eth_tester import EthereumTesterProvider  # noqa: E402

from a2a.quote import new_quote, quote_expired  # noqa: E402

ONE = 1_000_000


@pytest.fixture(scope="module")
def env():
    tester = EthereumTester(PyEVMBackend())
    w3 = Web3(EthereumTesterProvider(tester))
    payer, agent = w3.eth.accounts[0], w3.eth.accounts[1]

    def artifact(name):
        return json.loads((ROOT / "build" / f"{name}.json").read_text())

    def deploy(name):
        a = artifact(name)
        c = w3.eth.contract(abi=a["abi"], bytecode=a["bin"])
        tx = c.constructor().transact({"from": payer})
        rc = w3.eth.wait_for_transaction_receipt(tx)
        return w3.eth.contract(address=rc.contractAddress, abi=a["abi"])

    musdc = deploy("MockUSDC")
    escrow = deploy("AgentEscrow")
    musdc.functions.mint(payer, 10_000 * ONE).transact({"from": payer})
    musdc.functions.approve(escrow.address, 10_000 * ONE).transact({"from": payer})
    return {"w3": w3, "tester": tester, "payer": payer, "agent": agent,
            "musdc": musdc, "escrow": escrow}


def test_happy_path_release(env):
    w3, payer, agent = env["w3"], env["payer"], env["agent"]
    escrow, musdc = env["escrow"], env["musdc"]
    before = musdc.functions.balanceOf(agent).call()
    escrow.functions.createJob(agent, musdc.address, 10 * ONE, 3600, 600, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    escrow.functions.acceptJob(jid).transact({"from": agent})
    escrow.functions.submitDelivery(jid, Web3.keccak(text="deliverable")).transact({"from": agent})
    escrow.functions.release(jid).transact({"from": payer})
    assert musdc.functions.balanceOf(agent).call() == before + 10 * ONE
    assert escrow.functions.getJob(jid).call()[6] == 4  # State.Released


def test_timeout_refund(env):
    w3, payer, agent = env["w3"], env["payer"], env["agent"]
    escrow, musdc = env["escrow"], env["musdc"]
    before = musdc.functions.balanceOf(payer).call()
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 5, 0, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    latest = w3.eth.get_block("latest")
    env["tester"].time_travel(latest.timestamp + 100)  # past the 5s deadline, on the chain's own clock
    env["tester"].mine_blocks(1)
    escrow.functions.refundAfterDeadline(jid).transact({"from": payer})
    assert musdc.functions.balanceOf(payer).call() == before  # funded then refunded in full


def test_stranger_cannot_release(env):
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent, stranger = env["payer"], env["agent"], env["w3"].eth.accounts[2]
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600, 600, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    escrow.functions.acceptJob(jid).transact({"from": agent})
    escrow.functions.submitDelivery(jid, Web3.keccak(text="d")).transact({"from": agent})
    with pytest.raises(Exception):
        escrow.functions.release(jid).transact({"from": stranger})


def test_quote_hash_stable_and_expiry():
    q = new_quote(service="s", price=100, token="0x" + "0" * 40, token_symbol="mUSDC",
                  network="HSKChain Testnet", chain_id=133, escrow="0x" + "0" * 40,
                  pay_to="0x" + "1" * 40, ttl_seconds=60)
    assert q["quote_hash"].startswith("0x") and len(q["quote_hash"]) == 66
    assert not quote_expired(q)
    assert quote_expired(q, now=q["expires_at"] + 1)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

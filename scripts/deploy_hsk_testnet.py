"""Deploy Lamplight Pay to HSKChain Testnet (chain ID 133).

Deployed Oct 28, 2026 (round-16 code): MockUSDC
0x00835c4588461353B4B284437d7D65c466587375, AgentEscrow
0xF1c84737AAc850546d84C54d60B3b18fF82F8afA — see
build/hsk-testnet-deployment.json. Do NOT redeploy without an explicit
go-ahead.

Usage (testnet only):
  export HSK_TESTNET_RPC=https://testnet.hsk.xyz
  export DEPLOYER_KEY=<testnet-only private key — NEVER the Ellis ETH wallet key,
                       NEVER a mainnet key, never commit it, never paste it in chat>
  .venv/bin/python scripts/deploy_hsk_testnet.py

Dry run (no testnet funds, no record touched):
  HSK_DRY_RUN=1 HSK_TESTNET_RPC=http://127.0.0.1:8545 \\
    DEPLOYER_KEY=<anvil default key 0> .venv/bin/python scripts/deploy_hsk_testnet.py
  Deploys both contracts to the local chain and writes the record to
  build/hsk-testnet-deployment-dryrun.json instead of the real record.

Safety: refuses to run on any chain other than 133 (dry-run mode allows a
local chain but still refuses mainnet 177). Writes deployed addresses to
build/hsk-testnet-deployment.json.

Fixes (Oct 28, 2026 — the round-16 redeploy hit both, diagnosed in
STATUS.md "Redeploy"):
  1. STALE NONCE: the script used to fetch the nonce fresh via
     w3.eth.get_transaction_count for each contract, but the public RPC
     returned a STALE nonce for the second deploy in the same run — the
     AgentEscrow tx reused the just-mined MockUSDC nonce and the node
     rejected it as "replacement transaction underpriced". The nonce is
     now fetched ONCE (pending) and incremented locally per transaction.
  2. GAS CAP TOO LOW: the hardcoded 3,000,000 gas limit was too low for
     AgentEscrow — the first explicit-nonce attempt consumed all
     3,000,000 gas and failed (status 0, dead address
     0xc266B0099fd6BA8812a0d85048Fc592C7B78bd8E). Measured estimate is
     4,800,180 gas; the successful deploy used 6,000,000. The limit is
     now derived from eth_estimateGas with 25% headroom, floored at
     5,000,000 so AgentEscrow can never get a sub-5M cap again.
  3. The old script never checked the receipt status — a failed deploy
     would have been recorded as if it succeeded. A status-0 receipt
     now aborts the run loudly.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web3 import Web3  # noqa: E402

EXPECTED_CHAIN_ID = 133  # HSKChain Testnet (chainid.network). Mainnet is 177 — refused.
MAINNET_CHAIN_ID = 177

# Gas rule for a deploy tx: eth_estimateGas + 25% headroom, floored so no
# contract ever deploys with a sub-5M cap (AgentEscrow alone estimates
# ~4.8M; the old hardcoded 3,000,000 cap killed it). A limit is a cap,
# not a spend — unused gas is refunded — so over-provisioning costs
# nothing; under-provisioning strands the deploy.
GAS_HEADROOM = 1.25
MIN_GAS_LIMIT = 5_000_000


def deploy_gas_limit(estimate: int, floor: int = MIN_GAS_LIMIT) -> int:
    """Gas limit for one deploy tx: estimate + 25% headroom, floored.

    estimate is the eth_estimateGas figure for the constructor call.
    The floor guarantees AgentEscrow (measured ~4,800,180 gas) never
    gets a sub-5M cap even if an estimate comes back low.
    """
    return max(math.ceil(estimate * GAS_HEADROOM), floor)


def deploy_contracts(w3: Web3, acct, chain_id: int) -> dict:
    """Deploy MockUSDC then AgentEscrow in one run. Returns {name: address}.

    Nonce discipline: fetched ONCE with "pending" and incremented locally
    per transaction — never re-queried, so a stale RPC read (the
    round-16 failure) cannot reuse a nonce. Each receipt's status is
    checked; a status-0 deploy aborts instead of being recorded.
    """
    nonce = w3.eth.get_transaction_count(acct.address, "pending")
    deployed = {}
    for name in ("MockUSDC", "AgentEscrow"):
        artifact = json.loads((ROOT / "build" / f"{name}.json").read_text())
        contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
        estimate = contract.constructor().estimate_gas({"from": acct.address})
        gas = deploy_gas_limit(estimate)
        tx = contract.constructor().build_transaction({
            "from": acct.address, "nonce": nonce,
            "gas": gas, "gasPrice": w3.eth.gas_price, "chainId": chain_id,
        })
        nonce += 1
        print(f"{name}: estimate {estimate} gas -> limit {gas}, nonce {tx['nonce']}")
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise SystemExit(
                f"{name} deploy FAILED (tx {tx_hash.hex()}, status 0) — "
                "not recorded. Check the gas limit and retry; do not reuse "
                "the address, the failed deploy leaves a dead contract address.")
        deployed[name] = receipt.contractAddress
        print(f"{name}: {receipt.contractAddress} (tx {tx_hash.hex()})")
    return deployed


def main() -> None:
    dry_run = os.environ.get("HSK_DRY_RUN") == "1"
    rpc = os.environ.get("HSK_TESTNET_RPC", "https://testnet.hsk.xyz")
    key = os.environ.get("DEPLOYER_KEY")
    if not key:
        raise SystemExit("DEPLOYER_KEY is not set. See the header comment — testnet key only.")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise SystemExit(f"cannot reach RPC at {rpc}")
    chain_id = w3.eth.chain_id
    if chain_id == MAINNET_CHAIN_ID:
        raise SystemExit(f"REFUSED: chain id is {chain_id} (HSK mainnet) — testnet only, never mainnet.")
    if not dry_run and chain_id != EXPECTED_CHAIN_ID:
        raise SystemExit(f"REFUSED: chain id is {chain_id}, expected {EXPECTED_CHAIN_ID} (HSK testnet).")
    if dry_run:
        print("*** DRY RUN — local chain only, real deployment record untouched ***")
    acct = w3.eth.account.from_key(key)
    print(f"deployer: {acct.address} | chain: {chain_id} | balance: {w3.eth.get_balance(acct.address)} wei (tHSK)")
    if w3.eth.get_balance(acct.address) == 0:
        raise SystemExit("deployer has 0 balance — fund it first (testnet faucet, or a funded local account).")

    deployed = deploy_contracts(w3, acct, chain_id)

    record_name = ("hsk-testnet-deployment-dryrun.json" if dry_run
                   else "hsk-testnet-deployment.json")
    out = ROOT / "build" / record_name
    out.write_text(json.dumps({"network": "HSKChain Testnet" if not dry_run else "DRY RUN (local chain)",
                               "chain_id": chain_id, "rpc": rpc,
                               "deployer": acct.address, **deployed}, indent=2))
    print(f"deployment record: {out}")
    if not dry_run:
        print("Verify on https://testnet-explorer.hskchain.net")


if __name__ == "__main__":
    main()

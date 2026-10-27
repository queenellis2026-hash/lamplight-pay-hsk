"""Deploy Lamplight Pay to HSKChain Testnet (chain ID 133).

NOT RUN YET — blocked: the HSK testnet RPC (https://testnet.hsk.xyz) times out
from this VM, and the faucet needs a browser + wallet interaction. Run this
where the RPC is reachable, after funding the deployer with testnet HSK
from the faucet (no real funds, testnet only).

Usage:
  export HSK_TESTNET_RPC=https://testnet.hsk.xyz
  export DEPLOYER_KEY=<testnet-only private key — NEVER the Ellis ETH wallet key,
                       NEVER a mainnet key, never commit it, never paste it in chat>
  .venv/bin/python scripts/deploy_hsk_testnet.py

Safety: refuses to run on any chain other than 133; refuses mainnet (177).
Writes deployed addresses to build/hsk-testnet-deployment.json.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web3 import Web3  # noqa: E402

EXPECTED_CHAIN_ID = 133  # HSKChain Testnet (chainid.network). Mainnet is 177 — refused.


def main() -> None:
    rpc = os.environ.get("HSK_TESTNET_RPC", "https://testnet.hsk.xyz")
    key = os.environ.get("DEPLOYER_KEY")
    if not key:
        raise SystemExit("DEPLOYER_KEY is not set. See the header comment — testnet key only.")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise SystemExit(f"cannot reach HSK testnet RPC at {rpc}")
    chain_id = w3.eth.chain_id
    if chain_id != EXPECTED_CHAIN_ID:
        raise SystemExit(f"REFUSED: chain id is {chain_id}, expected {EXPECTED_CHAIN_ID} (HSK testnet).")
    acct = w3.eth.account.from_key(key)
    print(f"deployer: {acct.address} | chain: {chain_id} | balance: {w3.eth.get_balance(acct.address)} wei (tHSK)")
    if w3.eth.get_balance(acct.address) == 0:
        raise SystemExit("deployer has 0 tHSK — fund it from the testnet faucet first (testnet only).")

    deployed = {}
    for name in ("MockUSDC", "AgentEscrow"):
        artifact = json.loads((ROOT / "build" / f"{name}.json").read_text())
        contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
        tx = contract.constructor().build_transaction({
            "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": 3_000_000, "gasPrice": w3.eth.gas_price, "chainId": chain_id,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        deployed[name] = receipt.contractAddress
        print(f"{name}: {receipt.contractAddress} (tx {tx_hash.hex()})")

    out = ROOT / "build" / "hsk-testnet-deployment.json"
    out.write_text(json.dumps({"network": "HSKChain Testnet", "chain_id": chain_id,
                               "rpc": rpc, "deployer": acct.address, **deployed}, indent=2))
    print(f"deployment record: {out}")
    print("Verify on https://testnet-explorer.hskchain.net")


if __name__ == "__main__":
    main()

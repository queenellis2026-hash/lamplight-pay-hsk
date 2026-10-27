"""Deploy Lamplight Pay to HSKChain Mainnet (chain ID 177).

NOT RUN YET — needs real HSK in the deployer wallet for gas (real money).
Decision Oct 26, 2026 ~9:12 PM CDT: if funds allow, deploy to mainnet
BEFORE submitting the DoraHacks Build (safer path — editing a Build after
creation is unconfirmed); otherwise submit the testnet Build and add mainnet
addresses later if editing turns out to work.

Usage:
  export HSK_MAINNET_RPC=https://mainnet.hsk.xyz
  export DEPLOYER_KEY=<deployer private key — same Account 1, funded with real HSK>
  export HSK_MAINNET_CONFIRM=YES
  .venv/bin/python scripts/deploy_hsk_mainnet.py

Safety: refuses to run on any chain other than 177; refuses unless
HSK_MAINNET_CONFIRM=YES; uses the PENDING nonce (the testnet script's
`latest`-nonce bug collided the second deploy — do not regress this).
Writes deployed addresses to build/hsk-mainnet-deployment.json.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web3 import Web3  # noqa: E402

EXPECTED_CHAIN_ID = 177  # HSKChain Mainnet. Testnet is 133 — refused here.


def main() -> None:
    if os.environ.get("HSK_MAINNET_CONFIRM") != "YES":
        raise SystemExit("REFUSED: set HSK_MAINNET_CONFIRM=YES — mainnet spends real HSK.")
    rpc = os.environ.get("HSK_MAINNET_RPC", "https://mainnet.hsk.xyz")
    key = os.environ.get("DEPLOYER_KEY")
    if not key:
        raise SystemExit("DEPLOYER_KEY is not set. Testnet key only if it holds real HSK — "
                         "never the Ellis ETH wallet key, never commit it, never paste it in chat.")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise SystemExit(f"cannot reach HSK mainnet RPC at {rpc}")
    chain_id = w3.eth.chain_id
    if chain_id != EXPECTED_CHAIN_ID:
        raise SystemExit(f"REFUSED: chain id is {chain_id}, expected {EXPECTED_CHAIN_ID} (HSK mainnet).")
    acct = w3.eth.account.from_key(key)
    balance = w3.eth.get_balance(acct.address)
    print(f"deployer: {acct.address} | chain: {chain_id} | balance: {balance} wei (HSK)")
    if balance == 0:
        raise SystemExit("deployer has 0 HSK — fund it with real HSK first (real money).")

    deployed = {}
    for name in ("MockUSDC", "AgentEscrow"):
        artifact = json.loads((ROOT / "build" / f"{name}.json").read_text())
        contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
        tx = contract.constructor().build_transaction({
            # PENDING nonce: counts the in-flight tx, so back-to-back deploys don't collide.
            "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
            "gas": 3_000_000, "gasPrice": w3.eth.gas_price, "chainId": chain_id,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        deployed[name] = receipt.contractAddress
        print(f"{name}: {receipt.contractAddress} (tx {tx_hash.hex()})")

    out = ROOT / "build" / "hsk-mainnet-deployment.json"
    out.write_text(json.dumps({"network": "HSKChain Mainnet", "chain_id": chain_id,
                               "rpc": rpc, "deployer": acct.address, **deployed}, indent=2))
    print(f"deployment record: {out}")
    print("Verify on https://explorer.hskchain.net")


if __name__ == "__main__":
    main()

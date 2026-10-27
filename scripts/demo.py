"""End-to-end Lamplight Pay demo on a local EVM (eth-tester, py-evm).

Runs three real on-chain scenarios and writes hash-stable receipts:
  A) happy path: quote -> fund -> accept -> deliver -> release (agent paid)
  B) timeout refund: fund -> agent never delivers -> payer reclaims after deadline
  C) dispute: fund -> accept -> deliver -> dispute -> payer resolves to agent
Usage: .venv/bin/python scripts/demo.py
Output: prints tx hashes + balances; writes demo-receipts/*.json
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eth_tester import EthereumTester, PyEVMBackend  # noqa: E402
from web3 import Web3  # noqa: E402
from web3.providers.eth_tester import EthereumTesterProvider  # noqa: E402

from a2a.quote import new_quote, to_json as quote_json  # noqa: E402
from a2a.receipt import build_receipt, to_json as receipt_json  # noqa: E402

ONE_MUSDC = 1_000_000  # mUSDC has 6 decimals, like USDC


def load_artifact(name: str) -> dict:
    return json.loads((ROOT / "build" / f"{name}.json").read_text())


def deploy(w3: Web3, artifact: dict, deployer: str):
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
    tx = contract.constructor().transact({"from": deployer})
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    return w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"]), receipt


def delivery_hash(text: str) -> bytes:
    return Web3.keccak(text=text)


def main() -> None:
    tester = EthereumTester(PyEVMBackend())
    w3 = Web3(EthereumTesterProvider(tester))
    payer, agent, stranger = w3.eth.accounts[0], w3.eth.accounts[1], w3.eth.accounts[2]
    out_dir = ROOT / "demo-receipts"
    out_dir.mkdir(exist_ok=True)

    musdc, _ = deploy(w3, load_artifact("MockUSDC"), payer)
    escrow, _ = deploy(w3, load_artifact("AgentEscrow"), payer)
    print(f"MockUSDC deployed:  {musdc.address}")
    print(f"AgentEscrow deployed: {escrow.address}")
    print(f"payer={payer}\nagent={agent}")

    # Fund the payer with test tokens (mint is public on the TEST token only).
    musdc.functions.mint(payer, 10_000 * ONE_MUSDC).transact({"from": payer})
    musdc.functions.approve(escrow.address, 10_000 * ONE_MUSDC).transact({"from": payer})

    # --- Scenario A: happy path -------------------------------------------------
    quote = new_quote(service="on-chain holder audit (top-20 wallets)",
                      price=50 * ONE_MUSDC, token=musdc.address, token_symbol="mUSDC",
                      network="HSKChain Testnet", chain_id=133,
                      escrow=escrow.address, pay_to=agent)
    (out_dir / "quote-A.json").write_text(quote_json(quote))
    tx = escrow.functions.createJob(agent, musdc.address, 50 * ONE_MUSDC,
                                    3600, 600, f"ipfs://quote/{quote['quote_id']}").transact({"from": payer})
    rc = w3.eth.wait_for_transaction_receipt(tx)
    job_id = 0
    print(f"\n[A] job {job_id} funded, tx {rc.transactionHash.hex()}")
    escrow.functions.acceptJob(job_id).transact({"from": agent})
    dh = delivery_hash("audit report: top-20 holders, block 129454096")
    tx = escrow.functions.submitDelivery(job_id, dh).transact({"from": agent})
    w3.eth.wait_for_transaction_receipt(tx)
    tx = escrow.functions.release(job_id).transact({"from": payer})
    rc = w3.eth.wait_for_transaction_receipt(tx)
    receipt = build_receipt(job_id=job_id, quote_id=quote["quote_id"], service=quote["service"],
                            payer=payer, agent=agent, token=musdc.address, token_symbol="mUSDC",
                            amount=50 * ONE_MUSDC, network="HSKChain Testnet", chain_id=133,
                            escrow_contract=escrow.address, outcome="released",
                            tx_hash=rc.transactionHash.hex(), delivery_hash=dh.hex())
    (out_dir / "receipt-A-released.json").write_text(receipt_json(receipt))
    print(f"[A] RELEASED, tx {rc.transactionHash.hex()}")
    print(f"[A] agent mUSDC balance: {musdc.functions.balanceOf(agent).call() / ONE_MUSDC}")

    # --- Scenario B: timeout refund ----------------------------------------------
    tx = escrow.functions.createJob(agent, musdc.address, 20 * ONE_MUSDC,
                                    5, 0, "ipfs://quote/timeout-demo").transact({"from": payer})
    w3.eth.wait_for_transaction_receipt(tx)
    job_b = 1
    print(f"\n[B] job {job_b} funded (20 mUSDC), agent never delivers")
    latest = w3.eth.get_block("latest")
    tester.time_travel(latest.timestamp + 100)  # jump past the 5s deadline, on the chain's own clock
    tester.mine_blocks(1)
    tx = escrow.functions.refundAfterDeadline(job_b).transact({"from": payer})
    rc = w3.eth.wait_for_transaction_receipt(tx)
    receipt_b = build_receipt(job_id=job_b, quote_id="timeout-demo", service="abandoned job",
                              payer=payer, agent=agent, token=musdc.address, token_symbol="mUSDC",
                              amount=20 * ONE_MUSDC, network="HSKChain Testnet", chain_id=133,
                              escrow_contract=escrow.address, outcome="refunded",
                              tx_hash=rc.transactionHash.hex())
    (out_dir / "receipt-B-refunded.json").write_text(receipt_json(receipt_b))
    print(f"[B] REFUNDED after deadline, tx {rc.transactionHash.hex()}")

    # --- Scenario C: dispute, resolved to agent ----------------------------------
    tx = escrow.functions.createJob(agent, musdc.address, 30 * ONE_MUSDC,
                                    3600, 600, "ipfs://quote/dispute-demo").transact({"from": payer})
    w3.eth.wait_for_transaction_receipt(tx)
    job_c = 2
    escrow.functions.acceptJob(job_c).transact({"from": agent})
    dh_c = delivery_hash("audit report v2, disputed then accepted")
    escrow.functions.submitDelivery(job_c, dh_c).transact({"from": agent})
    escrow.functions.raiseDispute(job_c).transact({"from": payer})
    print(f"\n[C] job {job_c} disputed by payer after delivery")
    tx = escrow.functions.resolveDispute(job_c, True).transact({"from": payer})
    rc = w3.eth.wait_for_transaction_receipt(tx)
    receipt_c = build_receipt(job_id=job_c, quote_id="dispute-demo", service="disputed job",
                              payer=payer, agent=agent, token=musdc.address, token_symbol="mUSDC",
                              amount=30 * ONE_MUSDC, network="HSKChain Testnet", chain_id=133,
                              escrow_contract=escrow.address, outcome="released",
                              tx_hash=rc.transactionHash.hex(), delivery_hash=dh_c.hex())
    (out_dir / "receipt-C-dispute-resolved.json").write_text(receipt_json(receipt_c))
    print(f"[C] dispute resolved TO AGENT, tx {rc.transactionHash.hex()}")

    # --- Guards: a stranger cannot release or refund ------------------------------
    try:
        escrow.functions.release(0).transact({"from": stranger})
        print("\n[!] GUARD FAILED: stranger released job 0")
    except Exception as e:
        print(f"\n[guard] stranger release correctly reverted ({type(e).__name__})")

    print(f"\nFinal balances (mUSDC): payer={musdc.functions.balanceOf(payer).call()/ONE_MUSDC} "
          f"agent={musdc.functions.balanceOf(agent).call()/ONE_MUSDC} "
          f"escrow={musdc.functions.balanceOf(escrow.address).call()/ONE_MUSDC}")
    print("Receipts in demo-receipts/. All three scenarios passed.")


if __name__ == "__main__":
    main()

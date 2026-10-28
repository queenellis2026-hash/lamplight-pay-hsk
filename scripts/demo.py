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
                                    3600, 600, f"ipfs://quote/{quote['quote_id']}", "0x0000000000000000000000000000000000000000").transact({"from": payer})
    rc = w3.eth.wait_for_transaction_receipt(tx)
    job_id = 0
    print(f"\n[A] job {job_id} funded, tx {rc.transactionHash.hex()}")
    escrow.functions.acceptJob(job_id, "0x0000000000000000000000000000000000000000").transact({"from": agent})
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
                                    5, 0, "ipfs://quote/timeout-demo", "0x0000000000000000000000000000000000000000").transact({"from": payer})
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
                                    3600, 600, "ipfs://quote/dispute-demo", "0x0000000000000000000000000000000000000000").transact({"from": payer})
    w3.eth.wait_for_transaction_receipt(tx)
    job_c = 2
    escrow.functions.acceptJob(job_c, "0x0000000000000000000000000000000000000000").transact({"from": agent})
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
    # ROUND 16 (Oct 28, 2026): the old guard called release(0) after
    # scenario A had already released job 0, so it reverted on "not
    # delivered" before the caller was ever checked — the printed
    # "guard correctly reverted" would have appeared even if the caller
    # check were deleted. Both guards below run against jobs where the
    # ONLY thing that can revert is the caller check, and the revert
    # reason is asserted, not just the fact of a revert. Both guard
    # jobs are unwound afterwards (dispute resolved to the payer /
    # payer refund), so the final balances are unchanged.
    from eth_tester.exceptions import TransactionFailed as _TxFailed

    def _expect_revert(fn, reason, label):
        try:
            fn()
        except _TxFailed as e:
            assert reason in str(e), f"{label}: reverted, but not on {reason!r}: {e}"
            print(f"[guard] {label} correctly reverted on {reason!r}")
            return
        raise AssertionError(f"{label}: expected a revert on {reason!r}, but the call succeeded")

    # Release guard: job 3 is live and Delivered, so a stranger's
    # release can only fail on the caller check.
    tx = escrow.functions.createJob(agent, musdc.address, 10 * ONE_MUSDC,
                                    3600, 600, "ipfs://quote/guard-release", "0x0000000000000000000000000000000000000000").transact({"from": payer})
    w3.eth.wait_for_transaction_receipt(tx)
    job_g = 3
    escrow.functions.acceptJob(job_g, "0x0000000000000000000000000000000000000000").transact({"from": agent})
    escrow.functions.submitDelivery(job_g, delivery_hash("guard deliverable")).transact({"from": agent})
    print(f"\n[guard] job {job_g} delivered (10 mUSDC) for the stranger-release check")
    _expect_revert(
        lambda: escrow.functions.release(job_g).transact({"from": stranger}),
        "not payer", "stranger release of live Delivered job")

    # Refund guard: job 4 is Created and past its deadline, so a
    # stranger's refund can only fail on the caller check.
    tx = escrow.functions.createJob(agent, musdc.address, 5 * ONE_MUSDC,
                                    5, 0, "ipfs://quote/guard-refund", "0x0000000000000000000000000000000000000000").transact({"from": payer})
    w3.eth.wait_for_transaction_receipt(tx)
    job_r = 4
    latest = w3.eth.get_block("latest")
    tester.time_travel(latest.timestamp + 100)  # past job 4's 5s deadline
    tester.mine_blocks(1)
    print(f"[guard] job {job_r} created and past deadline (5 mUSDC) for the stranger-refund check")
    _expect_revert(
        lambda: escrow.functions.refundAfterDeadline(job_r).transact({"from": stranger}),
        "not payer", "stranger refund of refundable job")

    # Unwind both guard jobs so the final balances are unchanged:
    # job 3 is disputed and resolved to the payer, job 4 is refunded
    # by the payer. (Still inside job 3's 600s review window: only
    # 100s have passed since its delivery.)
    escrow.functions.raiseDispute(job_g).transact({"from": payer})
    escrow.functions.resolveDispute(job_g, False).transact({"from": payer})
    print("[guard] job 3 disputed and resolved to payer (10 mUSDC back)")
    escrow.functions.refundAfterDeadline(job_r).transact({"from": payer})
    print("[guard] job 4 refunded by payer (5 mUSDC back)")

    print(f"\nFinal balances (mUSDC): payer={musdc.functions.balanceOf(payer).call()/ONE_MUSDC} "
          f"agent={musdc.functions.balanceOf(agent).call()/ONE_MUSDC} "
          f"escrow={musdc.functions.balanceOf(escrow.address).call()/ONE_MUSDC}")
    print("Receipts in demo-receipts/. All three scenarios passed.")


if __name__ == "__main__":
    main()

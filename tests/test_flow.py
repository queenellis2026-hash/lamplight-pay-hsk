"""Tests for Lamplight Pay — run on the local EVM, no network needed.

Usage: .venv/bin/python -m pytest tests/ -v   (or: .venv/bin/python tests/test_flow.py)

Covers the post-review contract (Oct 27, 2026): the review-window
lifecycle (deliveredAt, agent claim after the window, dispute restricted
to the window, dispute timeout), fee-on-transfer funding, USDT-style
no-bool-return tokens, the named cancelUnaccepted path, and owner-gated
minting on the test tokens.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from eth_tester import EthereumTester, PyEVMBackend  # noqa: E402
from eth_tester.exceptions import TransactionFailed  # noqa: E402
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
    fee = deploy("FeeToken")
    nobool = deploy("NoBoolToken")
    for token in (musdc, fee, nobool):
        token.functions.mint(payer, 10_000 * ONE).transact({"from": payer})
        token.functions.approve(escrow.address, 10_000 * ONE).transact({"from": payer})
    return {"w3": w3, "tester": tester, "payer": payer, "agent": agent,
            "musdc": musdc, "escrow": escrow, "fee": fee, "nobool": nobool}


def _travel(env, seconds):
    """Advance the test chain's clock by `seconds` and mine a block."""
    latest = env["w3"].eth.get_block("latest")
    env["tester"].time_travel(latest.timestamp + seconds)
    env["tester"].mine_blocks(1)


def _make_delivered(env, amount=10 * ONE, deadline=3600, window=600, token=None):
    """Fund + accept + deliver a job; returns its job id."""
    escrow = env["escrow"]
    payer, agent = env["payer"], env["agent"]
    token = token or env["musdc"].address
    escrow.functions.createJob(agent, token, amount, deadline, window, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    escrow.functions.acceptJob(jid).transact({"from": agent})
    escrow.functions.submitDelivery(jid, Web3.keccak(text="deliverable")).transact({"from": agent})
    return jid


def _state(env, jid):
    return env["escrow"].functions.getJob(jid).call()[6]


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
    assert _state(env, jid) == 4  # State.Released


def test_timeout_refund(env):
    w3, payer, agent = env["w3"], env["payer"], env["agent"]
    escrow, musdc = env["escrow"], env["musdc"]
    before = musdc.functions.balanceOf(payer).call()
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 5, 0, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    _travel(env, 100)  # past the 5s deadline, on the chain's own clock
    escrow.functions.refundAfterDeadline(jid).transact({"from": payer})
    assert musdc.functions.balanceOf(payer).call() == before  # funded then refunded in full


def test_stranger_cannot_release(env):
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent, stranger = env["payer"], env["agent"], env["w3"].eth.accounts[2]
    jid = _make_delivered(env, amount=5 * ONE)
    with pytest.raises(TransactionFailed, match="not payer"):
        escrow.functions.release(jid).transact({"from": stranger})


def test_agent_can_claim_after_review_window(env):
    """Claude High / Grok Medium: a silent payer can no longer lock funds.
    After deliveredAt + reviewWindow with no dispute, the agent releases."""
    escrow, musdc = env["escrow"], env["musdc"]
    agent = env["agent"]
    before = musdc.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    _travel(env, 700)  # past the 600s review window
    escrow.functions.release(jid).transact({"from": agent})
    assert musdc.functions.balanceOf(agent).call() == before + 10 * ONE
    assert _state(env, jid) == 4  # State.Released


def test_agent_cannot_claim_before_window_ends(env):
    """The agent's claim is gated on the window; inside it, only the payer
    may release."""
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    with pytest.raises(TransactionFailed, match="review window not ended"):
        env["escrow"].functions.release(jid).transact({"from": env["agent"]})


def test_dispute_after_window_reverts(env):
    """ChatGPT's exact repro: 600s window, +1000s, raiseDispute must revert."""
    escrow = env["escrow"]
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    _travel(env, 1000)
    with pytest.raises(TransactionFailed, match="review window ended"):
        escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})


def test_dispute_inside_window_works(env):
    """A dispute raised inside the window still works, as before."""
    escrow = env["escrow"]
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    assert _state(env, jid) == 3  # State.Disputed


def test_dispute_timeout_releases_to_agent(env):
    """Claude High: a dispute the payer raised and then abandoned cannot
    lock funds forever. After the dispute period, either party may settle
    it and the agent is paid for delivered work."""
    escrow, musdc = env["escrow"], env["musdc"]
    agent = env["agent"]
    before = musdc.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    dispute_period = escrow.functions.DISPUTE_PERIOD().call()
    _travel(env, 600 + dispute_period + 100)
    escrow.functions.settleDisputeTimeout(jid).transact({"from": agent})
    assert musdc.functions.balanceOf(agent).call() == before + 10 * ONE
    assert _state(env, jid) == 4  # State.Released


def test_dispute_resolve_after_period_reverts(env):
    """Once the dispute period has ended, resolveDispute is closed;
    settleDisputeTimeout is the only exit."""
    escrow = env["escrow"]
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    dispute_period = escrow.functions.DISPUTE_PERIOD().call()
    _travel(env, 600 + dispute_period + 100)
    with pytest.raises(TransactionFailed, match="dispute period ended"):
        escrow.functions.resolveDispute(jid, True).transact({"from": env["payer"]})


def test_fee_on_transfer_token(env):
    """Claude Medium: a 1% fee token funds the job with the NET amount
    only. The job stores 99, the agent is paid 99, nothing is taken from
    other jobs' funds."""
    escrow, fee = env["escrow"], env["fee"]
    payer, agent = env["payer"], env["agent"]
    payer_before = fee.functions.balanceOf(payer).call()
    agent_before = fee.functions.balanceOf(agent).call()
    escrow.functions.createJob(agent, fee.address, 100 * ONE, 3600, 600, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    job = escrow.functions.getJob(jid).call()
    assert job[3] == 99 * ONE  # stored amount is what arrived, not 100
    assert fee.functions.balanceOf(escrow.address).call() == 99 * ONE
    assert fee.functions.balanceOf(payer).call() == payer_before - 100 * ONE
    escrow.functions.acceptJob(jid).transact({"from": agent})
    escrow.functions.submitDelivery(jid, Web3.keccak(text="d")).transact({"from": agent})
    escrow.functions.release(jid).transact({"from": payer})
    # The escrow paid the full stored 99, but the token takes its 1% fee on
    # the payout leg too, so the agent nets 99 * 99% = 98.01.
    assert fee.functions.balanceOf(agent).call() == agent_before + 98_010_000
    assert fee.functions.balanceOf(escrow.address).call() == 0


def test_no_bool_token(env):
    """Claude Low: a USDT-style token whose transfer/transferFrom return
    no bool must not brick jobs — the escrow's low-level calls accept an
    empty return value."""
    escrow, nobool = env["escrow"], env["nobool"]
    payer, agent = env["payer"], env["agent"]
    agent_before = nobool.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, token=nobool.address)
    escrow.functions.release(jid).transact({"from": payer})
    assert nobool.functions.balanceOf(agent).call() == agent_before + 10 * ONE
    assert _state(env, jid) == 4  # State.Released


def test_cancel_unaccepted_after_deadline(env):
    """Grok Medium: a named exit when the agent never accepts. The payer
    reclaims a still-Created job after its deadline; the job ends in the
    terminal Cancelled state, distinct from the generic refund path."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    before = musdc.functions.balanceOf(payer).call()
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 5, 0, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    _travel(env, 100)  # past the 5s deadline; agent never accepted
    escrow.functions.cancelUnaccepted(jid).transact({"from": payer})
    assert musdc.functions.balanceOf(payer).call() == before
    assert _state(env, jid) == 6  # State.Cancelled


def test_cancel_unaccepted_before_deadline_reverts(env):
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600, 0, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    with pytest.raises(TransactionFailed, match="deadline not passed"):
        escrow.functions.cancelUnaccepted(jid).transact({"from": payer})


def test_cancel_unaccepted_after_accept_reverts(env):
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 5, 0, "ipfs://t").transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    escrow.functions.acceptJob(jid).transact({"from": agent})
    _travel(env, 100)
    with pytest.raises(TransactionFailed, match="not created"):
        escrow.functions.cancelUnaccepted(jid).transact({"from": payer})


def test_mockusdc_mint_only_owner(env):
    """Grok Low: mint is restricted to the deployer (owner)."""
    musdc = env["musdc"]
    payer, stranger = env["payer"], env["w3"].eth.accounts[2]
    assert musdc.functions.owner().call() == payer
    with pytest.raises(TransactionFailed, match="not owner"):
        musdc.functions.mint(stranger, 1 * ONE).transact({"from": stranger})
    # Owner mint still works (the demo and tests mint from the deployer).
    before = musdc.functions.balanceOf(payer).call()
    musdc.functions.mint(payer, 1 * ONE).transact({"from": payer})
    assert musdc.functions.balanceOf(payer).call() == before + 1 * ONE


# ---- Re-review fixes (Oct 27, 2026): review-window cap + boundary ----

def test_create_job_too_large_review_window_reverts(env):
    """Claude Medium (re-review): reviewWindowSeconds is capped at
    MAX_REVIEW_WINDOW (30 days). A larger window reverts, so a silent
    payer can no longer delay (or overflow) the agent's claim."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    max_window = escrow.functions.MAX_REVIEW_WINDOW().call()
    assert max_window == 30 * 24 * 3600
    with pytest.raises(TransactionFailed, match="review window too long"):
        escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600,
                                   max_window + 1, "ipfs://t").transact({"from": payer})
    # Claude's exact repro: a near-2**256 window would overflow
    # deliveredAt + reviewWindow and lock the funds forever.
    with pytest.raises(TransactionFailed, match="review window too long"):
        escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600,
                                   2**256 - 1, "ipfs://t").transact({"from": payer})


def test_create_job_max_review_window_ok(env):
    """The cap is inclusive: a window of exactly MAX_REVIEW_WINDOW is
    accepted."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    max_window = escrow.functions.MAX_REVIEW_WINDOW().call()
    before = escrow.functions.jobCount().call()
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600,
                               max_window, "ipfs://t").transact({"from": payer})
    assert escrow.functions.jobCount().call() == before + 1
    job = escrow.functions.getJob(before).call()
    assert job[5] == max_window  # reviewWindow stored as given
    assert _state(env, before) == 0  # State.Created


def test_agent_claim_at_exact_window_end_reverts(env):
    """Claude Low (re-review): at exactly deliveredAt + reviewWindow the
    agent's claim is now strict (>), so it reverts — the payer's
    last-second dispute cannot lose a race to the agent's release.
    Note: a tx sent after _travel(env, 599) executes at deliveredAt + 600
    (eth-tester mines the tx block 1s after the travel block)."""
    escrow = env["escrow"]
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    _travel(env, 599)  # the release tx lands at exactly deliveredAt + 600
    with pytest.raises(TransactionFailed, match="review window not ended"):
        escrow.functions.release(jid).transact({"from": env["agent"]})


def test_dispute_at_exact_window_end_succeeds(env):
    """The other half of the boundary: at exactly deliveredAt + reviewWindow
    the payer's dispute (<=) still succeeds, so the window's last second
    belongs to the payer."""
    escrow = env["escrow"]
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    _travel(env, 599)  # the dispute tx lands at exactly deliveredAt + 600
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    assert _state(env, jid) == 3  # State.Disputed


def test_agent_claim_just_after_window_end_succeeds(env):
    """The strict (>) claim still lets the agent claim one second after
    the window ends — the fix removes the race without delaying the claim."""
    escrow, musdc = env["escrow"], env["musdc"]
    agent = env["agent"]
    before = musdc.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    _travel(env, 600)  # the release tx lands at deliveredAt + 601
    escrow.functions.release(jid).transact({"from": agent})
    assert musdc.functions.balanceOf(agent).call() == before + 10 * ONE
    assert _state(env, jid) == 4  # State.Released


def test_quote_hash_stable_and_expiry():
    q = new_quote(service="s", price=100, token="0x" + "0" * 40, token_symbol="mUSDC",
                  network="HSKChain Testnet", chain_id=133, escrow="0x" + "0" * 40,
                  pay_to="0x" + "1" * 40, ttl_seconds=60)
    assert q["quote_hash"].startswith("0x") and len(q["quote_hash"]) == 66
    assert not quote_expired(q)
    assert quote_expired(q, now=q["expires_at"] + 1)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

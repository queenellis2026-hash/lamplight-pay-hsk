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
ZERO = "0x" + "0" * 40  # the zero address: no third-party arbiter (payer resolves)


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
    blocklist = deploy("BlocklistToken")
    hook = deploy("HookToken")
    malformed = deploy("MalformedReturnToken")
    for token in (musdc, fee, nobool, blocklist, hook, malformed):
        token.functions.mint(payer, 10_000 * ONE).transact({"from": payer})
        token.functions.approve(escrow.address, 10_000 * ONE).transact({"from": payer})
    return {"w3": w3, "tester": tester, "payer": payer, "agent": agent,
            "musdc": musdc, "escrow": escrow, "fee": fee, "nobool": nobool,
            "blocklist": blocklist, "hook": hook, "malformed": malformed}


def _travel(env, seconds):
    """Advance the test chain's clock by `seconds` and mine a block."""
    latest = env["w3"].eth.get_block("latest")
    env["tester"].time_travel(latest.timestamp + seconds)
    env["tester"].mine_blocks(1)


def _make_delivered(env, amount=10 * ONE, deadline=3600, window=600, token=None, arbiter=None, agent=None):
    """Fund + accept + deliver a job; returns its job id.
    arbiter defaults to the zero address (payer-as-arbiter, as before);
    agent defaults to the standard agent account — pass a fresh account
    for a cold-path measurement."""
    escrow = env["escrow"]
    payer = env["payer"]
    agent = agent or env["agent"]
    token = token or env["musdc"].address
    escrow.functions.createJob(agent, token, amount, deadline, window, "ipfs://t",
                               arbiter or ZERO).transact({"from": payer})
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
    escrow.functions.createJob(agent, musdc.address, 10 * ONE, 3600, 600, "ipfs://t", ZERO).transact({"from": payer})
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
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 5, 0, "ipfs://t", ZERO).transact({"from": payer})
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


def test_release_gas_clean_vs_credited_pins_bomb_fix(env):
    """Grok improvement 3 (round 6): pin the bomb fix with gas-cost
    assertions on the review-window boundary paths. A clean release
    (well-behaved token, direct transfer) and credited releases
    (malformed token, payout fails and credits) are measured on the
    cold path — a fresh agent whose token balance is zero — and asserted
    against ceilings, not exact figures: a future solc version may shift
    gas a little without breaking the test, while a return to the old
    copy-everything returndata behaviour (which needed ~35M gas for a
    3MB return and ran out of gas at a 30M limit) blows straight past
    the bomb ceiling.
    Measured on this toolchain (eth-tester/PyEVM, Oct 27, 2026):
    clean payer release 75,800; clean agent-claim release 77,613;
    credited mode 0 73,015; credited mode 2 (10KB return) 74,075;
    bomb mode 4 (~3MB return) 17,519,073. Ceilings: 150,000 for the
    small-return paths (~2x headroom), 19,000,000 for the bomb (the
    token's own ~17.5M to return 3MB is unavoidable; the escrow pays
    nothing on top, so anything near 35M means the copy is back)."""
    escrow, musdc, bad = env["escrow"], env["musdc"], env["malformed"]
    payer = env["payer"]
    w3 = env["w3"]

    def _gas(tx_hash):
        return w3.eth.wait_for_transaction_receipt(tx_hash)["gasUsed"]

    # Clean release, payer releases to a fresh agent (cold path).
    fresh_clean = w3.eth.accounts[5]
    jid = _make_delivered(env, amount=10 * ONE, window=600, agent=fresh_clean)
    clean_gas = _gas(escrow.functions.release(jid).transact({"from": payer}))
    assert _state(env, jid) == 4
    assert musdc.functions.balanceOf(fresh_clean).call() == 10 * ONE

    # Clean release, agent claims after the review window (boundary path).
    fresh_claim = w3.eth.accounts[6]
    jid = _make_delivered(env, amount=10 * ONE, window=600, agent=fresh_claim)
    _travel(env, 700)
    claim_gas = _gas(escrow.functions.release(jid).transact({"from": fresh_claim}))
    assert _state(env, jid) == 4
    assert musdc.functions.balanceOf(fresh_claim).call() == 10 * ONE

    # Credited release, malformed mode 0 (32 bytes holding 2), fresh agent.
    fresh_bad0 = w3.eth.accounts[7]
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=bad.address, agent=fresh_bad0)
    bad.functions.setMode(0).transact({"from": payer})
    credited0_gas = _gas(escrow.functions.release(jid).transact({"from": payer}))
    assert _state(env, jid) == 4
    assert escrow.functions.pendingWithdrawals(bad.address, fresh_bad0).call() == 10 * ONE

    # Credited release, malformed mode 2 (10KB return), fresh agent —
    # returndata size must not move the needle.
    fresh_bad2 = w3.eth.accounts[8]
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=bad.address, agent=fresh_bad2)
    bad.functions.setMode(2).transact({"from": payer})
    credited2_gas = _gas(escrow.functions.release(jid).transact({"from": payer}))
    assert _state(env, jid) == 4
    assert escrow.functions.pendingWithdrawals(bad.address, fresh_bad2).call() == 10 * ONE

    # Bomb credited release, mode 4 (~3MB return), fresh agent.
    fresh_bomb = w3.eth.accounts[9]
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=bad.address, agent=fresh_bomb)
    bad.functions.setMode(4).transact({"from": payer})
    tx = escrow.functions.release(jid).transact({"from": payer, "gas": 20_000_000})
    rc = w3.eth.wait_for_transaction_receipt(tx)
    assert rc["status"] == 1
    bomb_gas = rc["gasUsed"]
    assert _state(env, jid) == 4
    assert escrow.functions.pendingWithdrawals(bad.address, fresh_bomb).call() == 10 * ONE

    # Ceilings, not exact figures — see the docstring.
    assert clean_gas <= 150_000
    assert claim_gas <= 150_000
    assert credited0_gas <= 150_000
    assert credited2_gas <= 150_000
    assert bomb_gas <= 19_000_000
    # The credited path stays the same order of magnitude as the clean
    # path — a malformed return must not cost materially more than a
    # good one.
    assert credited0_gas < 3 * clean_gas
    assert credited2_gas < 3 * clean_gas


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
    escrow.functions.createJob(agent, fee.address, 100 * ONE, 3600, 600, "ipfs://t", ZERO).transact({"from": payer})
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
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 5, 0, "ipfs://t", ZERO).transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    _travel(env, 100)  # past the 5s deadline; agent never accepted
    escrow.functions.cancelUnaccepted(jid).transact({"from": payer})
    assert musdc.functions.balanceOf(payer).call() == before
    assert _state(env, jid) == 6  # State.Cancelled


def test_cancel_unaccepted_before_deadline_reverts(env):
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600, 0, "ipfs://t", ZERO).transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    with pytest.raises(TransactionFailed, match="deadline not passed"):
        escrow.functions.cancelUnaccepted(jid).transact({"from": payer})


def test_cancel_unaccepted_after_accept_reverts(env):
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 5, 0, "ipfs://t", ZERO).transact({"from": payer})
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
                                   max_window + 1, "ipfs://t", ZERO).transact({"from": payer})
    # Claude's exact repro: a near-2**256 window would overflow
    # deliveredAt + reviewWindow and lock the funds forever.
    with pytest.raises(TransactionFailed, match="review window too long"):
        escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600,
                                   2**256 - 1, "ipfs://t", ZERO).transact({"from": payer})


def test_create_job_max_review_window_ok(env):
    """The cap is inclusive: a window of exactly MAX_REVIEW_WINDOW is
    accepted."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    max_window = escrow.functions.MAX_REVIEW_WINDOW().call()
    before = escrow.functions.jobCount().call()
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600,
                               max_window, "ipfs://t", ZERO).transact({"from": payer})
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


# ---- Re-review round 3 (Oct 27, 2026): failing payout must not strand a job ----

def test_blocklisted_agent_release_credits_pull_balance(env):
    """Claude Low (round 3): a token that blocklists the agent after
    delivery must not strand the job. release() credits a pull balance
    instead of reverting, the job reaches Released, and the agent still
    gets paid — via withdrawTo() to an unblocked address, since a
    transfer to the blocklisted agent itself would fail again."""
    escrow, blk = env["escrow"], env["blocklist"]
    payer, agent = env["payer"], env["agent"]
    stranger = env["w3"].eth.accounts[2]
    agent_before = blk.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, token=blk.address)
    # The token blocklists the agent mid-job, after delivery.
    blk.functions.setBlocked(agent, True).transact({"from": payer})
    # release() must NOT revert: the payout leg fails, so it is credited.
    escrow.functions.release(jid).transact({"from": payer})
    assert _state(env, jid) == 4  # State.Released — terminal, not stranded
    assert escrow.functions.pendingWithdrawals(blk.address, agent).call() == 10 * ONE
    assert blk.functions.balanceOf(escrow.address).call() == 10 * ONE
    assert blk.functions.balanceOf(agent).call() == agent_before
    # withdraw() to the still-blocklisted agent fails again, credit kept.
    with pytest.raises(TransactionFailed, match="withdrawal failed"):
        escrow.functions.withdraw(blk.address).transact({"from": agent})
    assert escrow.functions.pendingWithdrawals(blk.address, agent).call() == 10 * ONE
    # withdrawTo() to an unblocked address recovers the full amount.
    third_before = blk.functions.balanceOf(stranger).call()
    escrow.functions.withdrawTo(blk.address, stranger).transact({"from": agent})
    assert blk.functions.balanceOf(stranger).call() == third_before + 10 * ONE
    assert escrow.functions.pendingWithdrawals(blk.address, agent).call() == 0
    assert blk.functions.balanceOf(escrow.address).call() == 0


def test_blocklisted_agent_dispute_timeout_credits_pull_balance(env):
    """Same pull-balance exit through the Disputed path: a dispute the
    payer raised and abandoned, settled by timeout while the agent is
    blocklisted, must still reach Released with a withdrawable credit —
    and withdraw() works once the blocklist is lifted."""
    escrow, blk = env["escrow"], env["blocklist"]
    payer, agent = env["payer"], env["agent"]
    agent_before = blk.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=blk.address)
    escrow.functions.raiseDispute(jid).transact({"from": payer})
    dispute_period = escrow.functions.DISPUTE_PERIOD().call()
    _travel(env, 600 + dispute_period + 100)
    blk.functions.setBlocked(agent, True).transact({"from": payer})
    # settleDisputeTimeout() must NOT revert on the failed payout leg.
    escrow.functions.settleDisputeTimeout(jid).transact({"from": agent})
    assert _state(env, jid) == 4  # State.Released — terminal, not stranded
    assert escrow.functions.pendingWithdrawals(blk.address, agent).call() == 10 * ONE
    # Once the token unblocks the agent, withdraw() to itself pays out.
    blk.functions.setBlocked(agent, False).transact({"from": payer})
    escrow.functions.withdraw(blk.address).transact({"from": agent})
    assert blk.functions.balanceOf(agent).call() == agent_before + 10 * ONE
    assert escrow.functions.pendingWithdrawals(blk.address, agent).call() == 0
    assert blk.functions.balanceOf(escrow.address).call() == 0


def test_quote_hash_stable_and_expiry():
    q = new_quote(service="s", price=100, token="0x" + "0" * 40, token_symbol="mUSDC",
                  network="HSKChain Testnet", chain_id=133, escrow="0x" + "0" * 40,
                  pay_to="0x" + "1" * 40, ttl_seconds=60)
    assert q["quote_hash"].startswith("0x") and len(q["quote_hash"]) == 66
    assert not quote_expired(q)
    assert quote_expired(q, now=q["expires_at"] + 1)


# ---- Round 4 (Oct 27, 2026): missing coverage (Claude improvement 3),
# ---- the claim-windows view helper (Grok improvement 2), the optional
# ---- per-job arbiter (Grok + Claude feature), and the cold-transfer
# ---- margin lock (Grok improvement 3, HSK leg) ----

def test_agent_release_while_disputed_reverts(env):
    """Claude improvement 3: while a job is Disputed, neither party may
    release — the dispute must be resolved (or time out) first."""
    escrow = env["escrow"]
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    assert _state(env, jid) == 3  # State.Disputed
    with pytest.raises(TransactionFailed, match="not delivered"):
        escrow.functions.release(jid).transact({"from": env["agent"]})
    with pytest.raises(TransactionFailed, match="not delivered"):
        escrow.functions.release(jid).transact({"from": env["payer"]})


def test_resolve_dispute_true_pays_agent(env):
    """Claude improvement 3: resolving a dispute in the agent's favour
    pays the agent in full and ends the job Released."""
    escrow, musdc = env["escrow"], env["musdc"]
    agent = env["agent"]
    before = musdc.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    escrow.functions.resolveDispute(jid, True).transact({"from": env["payer"]})
    assert musdc.functions.balanceOf(agent).call() == before + 10 * ONE
    assert _state(env, jid) == 4  # State.Released


def test_resolve_dispute_false_refunds_payer(env):
    """Claude improvement 3: resolving a dispute against the agent
    refunds the payer in full and ends the job Refunded."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer = env["payer"]
    before = musdc.functions.balanceOf(payer).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    escrow.functions.raiseDispute(jid).transact({"from": payer})
    escrow.functions.resolveDispute(jid, False).transact({"from": payer})
    assert musdc.functions.balanceOf(payer).call() == before
    assert _state(env, jid) == 5  # State.Refunded


def test_settle_dispute_timeout_before_period_reverts(env):
    """Claude improvement 3: the timeout exit opens only AFTER the
    dispute period ends — an early attempt reverts."""
    escrow = env["escrow"]
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    _travel(env, 600)  # review window over, dispute period not yet
    with pytest.raises(TransactionFailed, match="dispute period not ended"):
        escrow.functions.settleDisputeTimeout(jid).transact({"from": env["agent"]})


def test_cancel_before_accept_refunds(env):
    """Claude improvement 3: the payer may cancel a still-Created job
    and is refunded in full; the job ends Cancelled."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    before = musdc.functions.balanceOf(payer).call()
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600, 0, "ipfs://t", ZERO).transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    escrow.functions.cancel(jid).transact({"from": payer})
    assert musdc.functions.balanceOf(payer).call() == before
    assert _state(env, jid) == 6  # State.Cancelled


def test_cancel_after_accept_reverts(env):
    """Claude improvement 3: once the agent has accepted, the plain
    cancel is closed — the payer must use the deadline paths instead."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600, 0, "ipfs://t", ZERO).transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    escrow.functions.acceptJob(jid).transact({"from": agent})
    with pytest.raises(TransactionFailed, match="only before accept"):
        escrow.functions.cancel(jid).transact({"from": payer})


def test_window_zero_agent_claims_next_block(env):
    """Claude improvement 3: a window of 0 means instant settlement —
    the very next block is already past deliveredAt + 0, so the agent
    may claim immediately."""
    escrow, musdc = env["escrow"], env["musdc"]
    agent = env["agent"]
    before = musdc.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=0)
    escrow.functions.release(jid).transact({"from": agent})
    assert musdc.functions.balanceOf(agent).call() == before + 10 * ONE
    assert _state(env, jid) == 4  # State.Released


def test_window_zero_dispute_after_delivery_second_reverts(env):
    """Claude improvement 3: with a window of 0 the payer may only
    dispute in the delivery second itself — one block later the window
    has already ended."""
    escrow = env["escrow"]
    jid = _make_delivered(env, amount=10 * ONE, window=0)
    with pytest.raises(TransactionFailed, match="review window ended"):
        escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})


def test_reentrancy_through_hook_token(env):
    """Claude improvement 3: a token whose transfer() calls back into
    the escrow must not drain or brick the job. The inner release() hits
    the nonReentrant guard (proven by the recorded returndata carrying
    "reentrant"), the payout leg fails, the job still reaches Released
    with a pull credit — and the credit pays out once the hook is
    disarmed."""
    escrow, hook = env["escrow"], env["hook"]
    payer, agent = env["payer"], env["agent"]
    agent_before = hook.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, token=hook.address)
    # Arm the hook: on every transfer, call release(jid) on the escrow.
    calldata = escrow.encode_abi("release", args=[jid])
    hook.functions.setHook(escrow.address, calldata).transact({"from": payer})
    # The payout leg triggers the hook; the inner release hits the guard.
    escrow.functions.release(jid).transact({"from": payer})
    assert _state(env, jid) == 4  # State.Released — terminal, not stranded
    assert escrow.functions.pendingWithdrawals(hook.address, agent).call() == 10 * ONE
    assert hook.functions.balanceOf(escrow.address).call() == 10 * ONE
    assert hook.functions.lastHookOk().call() is False
    assert b"reentrant" in bytes(hook.functions.lastHookReturndata().call())
    # Disarm the hook; the credit withdraws cleanly.
    hook.functions.setHook(ZERO, b"").transact({"from": payer})
    escrow.functions.withdraw(hook.address).transact({"from": agent})
    assert hook.functions.balanceOf(agent).call() == agent_before + 10 * ONE
    assert escrow.functions.pendingWithdrawals(hook.address, agent).call() == 0
    assert hook.functions.balanceOf(escrow.address).call() == 0


def test_claim_windows_helper_matches_behavior(env):
    """Grok improvement 2: claimWindows() returns the exact timestamps
    the contract itself enforces — the agent's claim boundary and the
    dispute timeout — and the behaviour at those boundaries matches
    them exactly."""
    escrow = env["escrow"]
    dispute_period = escrow.functions.DISPUTE_PERIOD().call()
    # Half 1: the agent's claim boundary.
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    job = escrow.functions.getJob(jid).call()
    delivered_at = job[9]
    agent_claim_at, dispute_timeout_at = escrow.functions.claimWindows(jid).call()
    assert agent_claim_at == delivered_at + 600
    assert dispute_timeout_at == delivered_at + 600 + dispute_period
    _travel(env, 599)  # the release tx lands exactly at agentClaimAt
    with pytest.raises(TransactionFailed, match="review window not ended"):
        escrow.functions.release(jid).transact({"from": env["agent"]})
    _travel(env, 1)  # one second past the boundary: the claim succeeds
    escrow.functions.release(jid).transact({"from": env["agent"]})
    assert _state(env, jid) == 4  # State.Released
    # Half 2: the dispute-timeout boundary, on a disputed job.
    jid2 = _make_delivered(env, amount=10 * ONE, window=600)
    job2 = escrow.functions.getJob(jid2).call()
    delivered_at2 = job2[9]
    _, dispute_timeout_at2 = escrow.functions.claimWindows(jid2).call()
    assert dispute_timeout_at2 == delivered_at2 + 600 + dispute_period
    escrow.functions.raiseDispute(jid2).transact({"from": env["payer"]})
    _travel(env, 600 + dispute_period - 2)  # settle tx lands exactly at the timeout
    with pytest.raises(TransactionFailed, match="dispute period not ended"):
        escrow.functions.settleDisputeTimeout(jid2).transact({"from": env["agent"]})
    _travel(env, 1)  # one second past: the timeout settles to the agent
    escrow.functions.settleDisputeTimeout(jid2).transact({"from": env["agent"]})
    assert _state(env, jid2) == 4  # State.Released


def test_claim_windows_before_delivery_returns_zero(env):
    """Claude Low (round 5): claimWindows() returns (0, 0) before
    delivery. The old behavior returned the window offsets from 0
    (600, 600 + 7d), which look like 1970 timestamps that have already
    passed — a UI or agent could wrongly conclude the claim is open."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600, 600, "ipfs://t", ZERO).transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    agent_claim_at, dispute_timeout_at = escrow.functions.claimWindows(jid).call()
    assert agent_claim_at == 0
    assert dispute_timeout_at == 0


def test_arbiter_resolves_dispute_to_agent(env):
    """Grok + Claude feature: a job with a third-party arbiter is
    resolved by the arbiter, not the payer — here in the agent's favour."""
    escrow, musdc = env["escrow"], env["musdc"]
    arbiter = env["w3"].eth.accounts[3]
    agent = env["agent"]
    before = musdc.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600, arbiter=arbiter)
    assert env["escrow"].functions.getJob(jid).call()[10] == arbiter
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    escrow.functions.resolveDispute(jid, True).transact({"from": arbiter})
    assert musdc.functions.balanceOf(agent).call() == before + 10 * ONE
    assert _state(env, jid) == 4  # State.Released


def test_arbiter_resolves_dispute_to_payer(env):
    """Same arbiter path, the other direction: the arbiter refunds the
    payer for work it judges undelivered."""
    escrow, musdc = env["escrow"], env["musdc"]
    arbiter = env["w3"].eth.accounts[3]
    payer = env["payer"]
    before = musdc.functions.balanceOf(payer).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600, arbiter=arbiter)
    escrow.functions.raiseDispute(jid).transact({"from": payer})
    escrow.functions.resolveDispute(jid, False).transact({"from": arbiter})
    assert musdc.functions.balanceOf(payer).call() == before
    assert _state(env, jid) == 5  # State.Refunded


def test_payer_cannot_resolve_when_arbiter_set(env):
    """When an arbiter is set, the payer loses the resolve power it has
    on no-arbiter jobs — and the arbiter cannot raise a dispute or
    release either; those stay with the parties."""
    escrow = env["escrow"]
    arbiter = env["w3"].eth.accounts[3]
    jid = _make_delivered(env, amount=10 * ONE, window=600, arbiter=arbiter)
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    with pytest.raises(TransactionFailed, match="not arbiter"):
        escrow.functions.resolveDispute(jid, True).transact({"from": env["payer"]})
    with pytest.raises(TransactionFailed, match="not arbiter"):
        escrow.functions.resolveDispute(jid, False).transact({"from": env["agent"]})


def test_arbiter_cannot_raise_dispute_or_release(env):
    """The arbiter resolves only. Raising a dispute and releasing stay
    with the parties."""
    escrow = env["escrow"]
    arbiter = env["w3"].eth.accounts[3]
    jid = _make_delivered(env, amount=10 * ONE, window=600, arbiter=arbiter)
    with pytest.raises(TransactionFailed, match="not a party"):
        escrow.functions.raiseDispute(jid).transact({"from": arbiter})
    with pytest.raises(TransactionFailed, match="not payer"):
        escrow.functions.release(jid).transact({"from": arbiter})


def test_arbiter_cannot_be_payer_or_agent(env):
    """The arbiter must be a third party: it cannot be the payer or the
    agent at creation."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    with pytest.raises(TransactionFailed, match="arbiter cannot be payer"):
        escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600, 600,
                                   "ipfs://t", payer).transact({"from": payer})
    with pytest.raises(TransactionFailed, match="arbiter cannot be agent"):
        escrow.functions.createJob(agent, musdc.address, 5 * ONE, 3600, 600,
                                   "ipfs://t", agent).transact({"from": payer})


def test_no_arbiter_job_payer_still_resolves(env):
    """No-arbiter jobs behave exactly as before: the arbiter field is
    the zero address and the payer resolves disputes."""
    escrow, musdc = env["escrow"], env["musdc"]
    agent = env["agent"]
    before = musdc.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600)
    assert escrow.functions.getJob(jid).call()[10] == ZERO
    escrow.functions.raiseDispute(jid).transact({"from": env["payer"]})
    escrow.functions.resolveDispute(jid, True).transact({"from": env["payer"]})
    assert musdc.functions.balanceOf(agent).call() == before + 10 * ONE
    assert _state(env, jid) == 4  # State.Released


def test_cold_transfer_to_fresh_agent_balance(env):
    """Grok improvement 3 (HSK): the ERC-20 payout leg to an agent whose
    token balance is zero writes a fresh storage slot (cold) — the
    release must still pay directly, never credit."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer = env["payer"]
    fresh = env["w3"].eth.accounts[4]
    assert musdc.functions.balanceOf(fresh).call() == 0
    escrow.functions.createJob(fresh, musdc.address, 10 * ONE, 3600, 600,
                               "ipfs://t", ZERO).transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    escrow.functions.acceptJob(jid).transact({"from": fresh})
    escrow.functions.submitDelivery(jid, Web3.keccak(text="deliverable")).transact({"from": fresh})
    escrow.functions.release(jid).transact({"from": payer})
    assert musdc.functions.balanceOf(fresh).call() == 10 * ONE
    assert escrow.functions.pendingWithdrawals(musdc.address, fresh).call() == 0
    assert _state(env, jid) == 4  # State.Released


# ---- Round 5 (Oct 27, 2026): Claude round-4 findings + improvements ----

def test_zero_address_agent_rejected_with_own_message(env):
    """Grok improvement 2 (round 5): the agent zero-address guard is now
    explicit and symmetric with the token check, with its own message —
    a zero agent can no longer hide behind the shared "zero address"."""
    escrow, musdc = env["escrow"], env["musdc"]
    payer, agent = env["payer"], env["agent"]
    with pytest.raises(TransactionFailed, match="zero address agent"):
        escrow.functions.createJob(ZERO, musdc.address, 5 * ONE, 3600, 600,
                                   "ipfs://t", ZERO).transact({"from": payer})
    with pytest.raises(TransactionFailed, match="zero address$"):
        escrow.functions.createJob(agent, ZERO, 5 * ONE, 3600, 600,
                                   "ipfs://t", ZERO).transact({"from": payer})


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_malformed_return_payout_credits_instead_of_stranding(env, mode):
    """Claude Low (round 5): _tryTransfer used abi.decode on the full
    returndata, so a token returning 32 bytes with value 2 (mode 0), a
    1-byte return (mode 1), or huge returndata (mode 2) made abi.decode
    revert or the copy run out of gas — and release / resolveDispute /
    settleDisputeTimeout then reverted forever, stranding the job. Now
    the returndata is inspected with a bounded copy (at most 32 bytes):
    any malformed return is a failed payout and the job is credited."""
    escrow, bad = env["escrow"], env["malformed"]
    payer, agent = env["payer"], env["agent"]
    bad.functions.setMode(3).transact({"from": payer})  # well-behaved for funding
    before = bad.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=bad.address)
    bad.functions.setMode(mode).transact({"from": payer})
    escrow.functions.release(jid).transact({"from": payer})
    assert _state(env, jid) == 4  # State.Released — not stranded
    assert escrow.functions.pendingWithdrawals(bad.address, agent).call() == 10 * ONE
    # the malformed transfer moved no funds, so the agent's balance is unchanged
    assert bad.functions.balanceOf(agent).call() == before
    # once the token behaves again, the credit pays out in full
    bad.functions.setMode(3).transact({"from": payer})
    escrow.functions.withdraw(bad.address).transact({"from": agent})
    assert bad.functions.balanceOf(agent).call() == before + 10 * ONE
    assert escrow.functions.pendingWithdrawals(bad.address, agent).call() == 0


def test_pending_credit_view_reports_pull_balance(env):
    """Grok improvement 2 (round 8): pendingCredit(token, account) is
    the named front-end view over the public pendingWithdrawals mapping.
    A credited payout shows the exact amount; an account or token with
    no credit reads 0; withdrawing drains it back to 0.
    Round 9 (Claude improvement 3): the agent and the stranger are
    FRESH accounts (accounts[3]/[4]) that no earlier test has credited —
    the module-scoped fixture used to mean the "0 before the credit"
    assertions only held because earlier tests had withdrawn, so this
    test depended on their cleanup. accounts[3] is used elsewhere only
    as an arbiter (never a payout recipient) and accounts[4] only as a
    direct-pay recipient, so neither has ever held a credit."""
    escrow, bad = env["escrow"], env["malformed"]
    payer = env["payer"]
    agent = env["w3"].eth.accounts[3]  # fresh: never credited before
    stranger = env["w3"].eth.accounts[4]  # fresh: never credited before
    bad.functions.setMode(3).transact({"from": payer})  # well-behaved for funding
    # no credit anywhere before the job
    assert escrow.functions.pendingCredit(bad.address, agent).call() == 0
    assert escrow.functions.pendingCredit(bad.address, stranger).call() == 0
    assert escrow.functions.pendingCredit(env["musdc"].address, agent).call() == 0
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=bad.address, agent=agent)
    bad.functions.setMode(0).transact({"from": payer})  # 32 bytes holding 2
    escrow.functions.release(jid).transact({"from": payer})
    assert _state(env, jid) == 4  # State.Released — credited, not stranded
    assert escrow.functions.pendingCredit(bad.address, agent).call() == 10 * ONE
    assert escrow.functions.pendingCredit(bad.address, stranger).call() == 0
    assert escrow.functions.pendingCredit(env["musdc"].address, agent).call() == 0
    # the view agrees with the public mapping
    assert escrow.functions.pendingCredit(bad.address, agent).call() == \
        escrow.functions.pendingWithdrawals(bad.address, agent).call()
    # withdrawing drains the view back to 0
    bad.functions.setMode(3).transact({"from": payer})
    escrow.functions.withdraw(bad.address).transact({"from": agent})
    assert escrow.functions.pendingCredit(bad.address, agent).call() == 0


def test_return_bomb_three_mb_credits_instead_of_running_out_of_gas(env):
    """Claude Low (round 6): the round-5 bounded-returndata fix was
    incomplete — solc's high-level token.call(...) copied the FULL
    returndata into memory before the bounded inspection ran, so a token
    returning ~3MB ran release() out of gas. Proven before the fix: with
    the round-5 code, release on bomb mode 4 consumed all 30M gas and
    reverted, the job stuck Delivered with no credit. The call is now
    made in assembly with a 32-byte output buffer, so the escrow copies
    at most 32 bytes; the token's own ~17.5M gas to return 3MB is
    unavoidable, but the escrow pays nothing on top (post-fix release:
    17,519,061 gas, job Released, payout credited). This test sends
    release() with 20M gas — enough for the token to return (17.5M) but
    far below the ~35M the old code needed — and asserts the settlement
    succeeds and credits the payout instead of reverting."""
    escrow, bad = env["escrow"], env["malformed"]
    payer, agent = env["payer"], env["agent"]
    bad.functions.setMode(3).transact({"from": payer})  # well-behaved for funding
    before = bad.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=bad.address)
    bad.functions.setMode(4).transact({"from": payer})
    tx = escrow.functions.release(jid).transact({"from": payer, "gas": 20_000_000})
    rc = env["w3"].eth.wait_for_transaction_receipt(tx)
    assert rc["status"] == 1  # succeeds inside 20M gas; the old code OOG'd at 30M
    # Pin the fix with a gas ceiling, not just the tx limit: the measured
    # post-fix release costs 17,519,061 gas (the token's own ~17.5M to
    # return 3MB; the escrow copies at most 32 bytes). Anything near 35M
    # means the copy-everything behaviour is back.
    assert rc["gasUsed"] <= 19_000_000
    assert _state(env, jid) == 4  # State.Released — not stranded
    assert escrow.functions.pendingWithdrawals(bad.address, agent).call() == 10 * ONE
    # the bomb transfer moved no funds, so the agent's balance is unchanged
    assert bad.functions.balanceOf(agent).call() == before
    # once the token behaves again, the credit pays out in full
    bad.functions.setMode(3).transact({"from": payer})
    escrow.functions.withdraw(bad.address).transact({"from": agent})
    assert bad.functions.balanceOf(agent).call() == before + 10 * ONE
    assert escrow.functions.pendingWithdrawals(bad.address, agent).call() == 0


def test_gas_burning_token_credits_when_release_supplies_enough_gas(env):
    """Claude improvement 2 (round 9): a token that burns all forwarded
    gas (mode 5, infinite loop). _tryTransfer forwards all remaining gas
    with the call, so the token consumes 63/64 of it and the call fails;
    the escrow keeps its 1/64 to run the credit path — but only if the
    caller supplied enough gas. Measured on this toolchain
    (eth-tester/PyEVM, Oct 27, 2026): with a 20,000,000 gas limit the
    release costs 19,695,562 gas, succeeds, and credits the full payout
    (the token burns ~19.65M of the limit; the escrow pays only the
    credit path on top). With a 200,000 gas limit the retained 1/64
    (~3k) cannot cover the credit path and the release reverts instead
    — the job stays Delivered, unsettled, and retryable with more gas.
    A front-end must not hardcode a low gas limit for release.
    The agent is a fresh account (accounts[4]) that has never held a
    malformed-token credit."""
    escrow, bad = env["escrow"], env["malformed"]
    payer = env["payer"]
    agent = env["w3"].eth.accounts[4]  # fresh: never credited before
    bad.functions.setMode(3).transact({"from": payer})  # well-behaved for funding
    before = bad.functions.balanceOf(agent).call()
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=bad.address, agent=agent)
    bad.functions.setMode(5).transact({"from": payer})
    # Low limit first: must revert, job stays Delivered and unsettled.
    tx = escrow.functions.release(jid).transact({"from": payer, "gas": 200_000})
    rc = env["w3"].eth.wait_for_transaction_receipt(tx)
    assert rc["status"] == 0
    assert _state(env, jid) == 2  # State.Delivered — not settled
    assert escrow.functions.pendingWithdrawals(bad.address, agent).call() == 0
    # High limit: succeeds and credits the full payout.
    tx = escrow.functions.release(jid).transact({"from": payer, "gas": 20_000_000})
    rc = env["w3"].eth.wait_for_transaction_receipt(tx)
    assert rc["status"] == 1
    assert rc["gasUsed"] <= 20_000_000
    assert _state(env, jid) == 4  # State.Released — credited, not stranded
    assert escrow.functions.pendingWithdrawals(bad.address, agent).call() == 10 * ONE
    assert bad.functions.balanceOf(agent).call() == before  # the burn moved no funds
    # once the token behaves again, the credit pays out in full
    bad.functions.setMode(3).transact({"from": payer})
    escrow.functions.withdraw(bad.address).transact({"from": agent})
    assert bad.functions.balanceOf(agent).call() == before + 10 * ONE
    assert escrow.functions.pendingWithdrawals(bad.address, agent).call() == 0


def test_vanished_code_token_credits_instead_of_marking_paid():
    """Claude improvement 1 (round 9): a token whose code has vanished
    after funding answers a call with success and empty returndata —
    which the USDT-style empty-return rule would read as "paid", so the
    job would be marked settled while nothing moved and the funds would
    sit in the escrow with no credit recorded. _tryTransfer now refuses
    the call up front when the token has no code (token.code.length == 0),
    so the payout fails and the job is credited instead.
    Proved on a pre-Cancun (Shanghai) chain in a separate tester: there
    SELFDESTRUCT deletes the code (on the default Prague tester EIP-6780
    makes the code survive the kill — the same reason the hole is nearly
    unreachable on modern mainnet). Before this fix the release below
    marked the job paid with no credit; after it, the job is Released
    with the full credit recorded. The credit itself can never be
    withdrawn — the token is dead, so withdraw() also fails the code
    check — but the funds are recorded as owed, not silently marked paid.
    Limit, stated plainly: the check only sees the TOKEN address's own
    code — a proxy whose implementation vanished still has code itself,
    so its delegatecall can still return empty success. That case needs
    a balance check, not a code check, and is out of scope here."""
    from eth.vm.forks import ShanghaiVM
    tester2 = EthereumTester(PyEVMBackend(vm_configuration=((0, ShanghaiVM),)))
    w3 = Web3(EthereumTesterProvider(tester2))
    payer, agent = w3.eth.accounts[0], w3.eth.accounts[1]

    def artifact(name):
        return json.loads((ROOT / "build" / f"{name}.json").read_text())

    def deploy(name):
        a = artifact(name)
        c = w3.eth.contract(abi=a["abi"], bytecode=a["bin"])
        tx = c.constructor().transact({"from": payer})
        rc = w3.eth.wait_for_transaction_receipt(tx)
        return w3.eth.contract(address=rc.contractAddress, abi=a["abi"])

    escrow = deploy("AgentEscrow")
    token = deploy("VanishingToken")
    token.functions.mint(payer, 10_000 * ONE).transact({"from": payer})
    token.functions.approve(escrow.address, 10_000 * ONE).transact({"from": payer})
    escrow.functions.createJob(agent, token.address, 10 * ONE, 3600, 600,
                               "ipfs://t", ZERO).transact({"from": payer})
    jid = escrow.functions.jobCount().call() - 1
    escrow.functions.acceptJob(jid).transact({"from": agent})
    escrow.functions.submitDelivery(jid, Web3.keccak(text="deliverable")).transact({"from": agent})
    assert w3.eth.get_code(token.address) != b""  # code present at funding
    token.functions.kill().transact({"from": payer})
    assert w3.eth.get_code(token.address) == b""  # code gone after the kill
    escrow.functions.release(jid).transact({"from": payer})
    assert escrow.functions.getJob(jid).call()[6] == 4  # State.Released — credited
    assert escrow.functions.pendingWithdrawals(token.address, agent).call() == 10 * ONE
    # the dead token can never pay the credit out — withdraw fails loudly
    # instead of silently dropping it — so the funds stay recorded as owed
    with pytest.raises(TransactionFailed, match="withdrawal failed"):
        escrow.functions.withdraw(token.address).transact({"from": agent})
    assert escrow.functions.pendingWithdrawals(token.address, agent).call() == 10 * ONE


def _hook_calldata(env, fn_name, jid):
    """Calldata for a HookToken hook that calls `fn_name(jid)` on the
    escrow from the token's address (so it fails access control)."""
    selector = Web3.keccak(text=f"{fn_name}(uint256)")[:4]
    return selector + jid.to_bytes(32, "big")


def test_hook_calling_raise_dispute_cannot_brick_release(env):
    """Claude improvement (round 5): cross-function reentrancy. The hook
    fires during release()'s payout transfer and calls raiseDispute()
    on the same job. The inner call fails (the token is not a party),
    the transfer fails, and the payout is credited — the settlement
    still completes and the job reaches Released."""
    escrow, hook = env["escrow"], env["hook"]
    payer, agent = env["payer"], env["agent"]
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=hook.address)
    hook.functions.setHook(escrow.address, _hook_calldata(env, "raiseDispute", jid)).transact({"from": payer})
    escrow.functions.release(jid).transact({"from": payer})
    assert _state(env, jid) == 4  # State.Released
    assert escrow.functions.pendingWithdrawals(hook.address, agent).call() == 10 * ONE
    assert hook.functions.lastHookOk().call() is False
    assert b"not a party" in bytes(hook.functions.lastHookReturndata().call())
    # disarm the hook and the credit pays out
    hook.functions.setHook(ZERO, b"").transact({"from": payer})
    escrow.functions.withdraw(hook.address).transact({"from": agent})
    assert escrow.functions.pendingWithdrawals(hook.address, agent).call() == 0


def test_hook_calling_accept_job_cannot_brick_release(env):
    """Same cross-function shape, the other entry point: the hook calls
    acceptJob() during release()'s payout transfer. The inner call fails
    (the token is not the agent), the payout credits, the job settles."""
    escrow, hook = env["escrow"], env["hook"]
    payer, agent = env["payer"], env["agent"]
    jid = _make_delivered(env, amount=10 * ONE, window=600, token=hook.address)
    hook.functions.setHook(escrow.address, _hook_calldata(env, "acceptJob", jid)).transact({"from": payer})
    escrow.functions.release(jid).transact({"from": payer})
    assert _state(env, jid) == 4  # State.Released
    assert escrow.functions.pendingWithdrawals(hook.address, agent).call() == 10 * ONE
    assert hook.functions.lastHookOk().call() is False
    assert b"not agent" in bytes(hook.functions.lastHookReturndata().call())
    hook.functions.setHook(ZERO, b"").transact({"from": payer})
    escrow.functions.withdraw(hook.address).transact({"from": agent})
    assert escrow.functions.pendingWithdrawals(hook.address, agent).call() == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

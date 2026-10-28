# Lamplight Pay — status (Oct 28, 2026)

## Project

Lamplight Pay — escrowed settlement for agent-to-agent work on HSK Chain.
Built for the HSK Chain Horizon Hackathon, track Agent Payments & A2A
Settlement.

## Timeline

- Prize: $10,000 USDT total, $5,000 USDT per track.
- Submission deadline Nov 1, 2026, 21:30 IST · Demo Day Nov 4 · Winners Nov 5.

## Deployment (HSKChain Testnet, chain ID 133)
- [AgentEscrow `0xAB70612F45d9cf914D129b0DB71DE243dD55813C`](https://testnet-explorer.hskchain.net/address/0xAB70612F45d9cf914D129b0DB71DE243dD55813C) — deployed Oct 28, 2026, round-19+20 code, block 35016779, Blockscout-verified (partial match).
- [MockUSDC `0xEF346652eeB233662E7d290d222175895d53ef15`](https://testnet-explorer.hskchain.net/address/0xEF346652eeB233662E7d290d222175895d53ef15) — deployed Oct 28, 2026, block 35016778, Blockscout-verified (partial match).
- Deployer: `0x995646c5270f26a8D64df58D7bc7e8277c606e27` (testnet-only, fresh key; funded 0.1 tHSK from the testnet faucet). Previous deployment (Oct 28, 2026 ~1:14 AM CDT, round-16 code): AgentEscrow `0xF1c84737AAc850546d84C54d60B3b18fF82F8afA` ([tx](https://testnet-explorer.hskchain.net/tx/2ab7754a91670e4f21deef9280f6d3353803b7aee639f9114b78cb821ef94b12)), MockUSDC `0x00835c4588461353B4B284437d7D65c466587375` ([tx](https://testnet-explorer.hskchain.net/tx/b0a3961840adfee33fe9352710ebac1e8e30c5467f8dc7c98c3696f8e95d913f)) — superseded by the round-19 redeploy. Earlier deployment (Oct 26, 2026): AgentEscrow `0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7` ([tx](https://testnet-explorer.hskchain.net/tx/59069c0957ea521c47bbc79fc22d9f3de4df8916c611b4b8c4a41e28f4a74f7c)), MockUSDC `0x860CadF955CF73FDB8E9ED2979104baae9f833B9` ([tx](https://testnet-explorer.hskchain.net/tx/2ea7242b072fd7348b619f279e66a9c531792a4e99b8d835a8a073989191b4a7)), deployer `0xa67d284fC85345c2e3aCC3A34d46f93a295df341` — superseded by the Oct 28 redeploy.
- Demo scenarios: 3/3 pass on a local EVM; `pytest` 85 passed (79 flow + 6 deploy-script). Live testnet demo on the round-19 contracts: flows A/B/C + stranger guards pass, escrow ends at 0. Receipts in `demo-receipts/`.
- Demo video: v4, 2:05, Unlisted — https://youtu.be/6lGHXO1dEVM.
- Submitted Oct 27, 2026: https://dorahacks.io/build/50417 — status Under Review. The Build can still be edited before judging. (Build edited Oct 28, 2026 with the new addresses + v4 video, verified live.)
- Update (Oct 28, 2026): rounds 11–16 pushed Oct 28 ~01:09 AM CDT (head 6022bcb2); redeploy done Oct 28 ~1:14 AM CDT. The 'no push / PRE-fix deployment' notes in the round 11–15 sections below are superseded by that push. Rounds 17–21 + journey UI + threat model pushed Oct 28, 2026 (see Round-19 section at the end).

## Post-review fix (Oct 27, 2026)

Independent review (Claude, Grok, ChatGPT) found 9 findings, all fixed in source + tests:
- Dead `reviewWindow` (Claude High, Grok 2 Medium + Low, ChatGPT Medium):
  `deliveredAt` recorded at delivery; payer arbitrates during the window;
  agent may `release()` after it; disputes only inside it; disputed jobs
  time out to the agent after window + 7 days (`settleDisputeTimeout`).
- Fee-on-transfer tokens (Claude Medium): funding stores the net received
  amount (balance before/after).
- USDT-style no-bool tokens (Claude Low): SafeERC20-style low-level calls.
- Broad test assertion (Claude Low): `TransactionFailed` + "not payer".
- No accept-timeout path (Grok Medium): new `cancelUnaccepted()` — payer
  reclaims a still-Created job after its deadline, state Cancelled.
- Open mint (Grok Low): `MockUSDC` mint is owner-gated (deployer).
- Verification: `pytest` 16 passed, 0 failed; demo 3/3 + stranger guard
  pass with identical final balances (payer 9920 / agent 80 / escrow 0).
- NOT done here: the testnet deployment above is still the PRE-fix
  contract — redeploy + Build edit are separate steps, not taken in this
  task. The v3 demo video is not visibly stale (demo re-run output is
  identical), but it shows the pre-fix contract's behaviour; re-record
  after redeploy if the video must match the current source.

## Re-review fix (Oct 27, 2026)

A re-review of the fixed contracts (Claude + Grok, fresh wipe, one shot;
ChatGPT's leg was blocked by its Free-plan file-upload limit until
~Oct 28) found 2 new HSK findings, both fixed in source + tests:
- **Medium — reviewWindow had no upper bound.** `createJob` stored it
  unchecked, so a huge window (or one near 2**256 − 1, which overflows
  `deliveredAt + reviewWindow`) would let a silent payer lock the
  agent's claim indefinitely — the exact lock the review window was
  added to prevent. Fixed: `MAX_REVIEW_WINDOW = 30 days` (public
  constant) and `require(reviewWindowSeconds <= MAX_REVIEW_WINDOW,
  "review window too long")` in `createJob`. No floor was added: a 0
  window is a legitimate payer choice (instant settlement — it helps
  the agent, not hurts them), and the existing tests use window 0 for
  the deadline/cancel paths. New revert string: "review window too
  long". Tests: a window of 30 days + 1 reverts, a 2**256 − 1 window
  reverts (Claude's exact repro), and exactly 30 days is accepted.
- **Low — boundary overlap at exactly deliveredAt + reviewWindow.**
  `raiseDispute` used `<=` while the agent branch of `release` used
  `>=`, so at the boundary second both calls were valid and the
  payer's last-second dispute could lose a race to the agent's
  release. Fixed: the agent's claim is now strict (`>`), the dispute
  stays `<=` — the window's last second belongs to the payer. Tests:
  at the exact boundary the agent's claim reverts and the payer's
  dispute succeeds; one second later the agent's claim succeeds.
  (Boundary timing was calibrated against eth-tester: a tx sent after
  travelling N seconds executes at +N+1, so the boundary tx travels
  599 for a 600s window.)
- Verification: `pytest` 21 passed, 0 failed (16 + 5 new); demo 3/3 +
  stranger guard pass with identical final balances (payer 9920 /
  agent 80 / escrow 0). Receipts B and C are byte-identical to the
  pre-fix run; receipt A differs only by its fresh quote (new id/nonce
  each run, as always). The v3 video is therefore NOT visibly stale.
- NOT done here: the testnet deployment is still the PRE-fix contract
  (now two fix rounds behind source) — redeploy + Build edit are
  separate steps. No GitHub push and no Build edit were made in this
  task.

## Round-2 re-review fix (Oct 27, 2026)

A second re-review of the fixed contracts (Claude + Grok, fresh wipe,
one shot; ChatGPT still blocked by its upload limit) found 1 new HSK
finding, fixed in source + tests. Grok found nothing:
- **Low — one failing token transfer permanently strands a job.**
  `_safeTransfer` (called from release, resolveDispute, and
  settleDisputeTimeout) reverted with "payout failed" when the token
  refused the payout — e.g. a USDC-style token blocklisting the agent
  after delivery — and with a silent payer the job stayed in Delivered
  or Disputed forever (the payer's only exit was dispute-then-resolve
  inside the window). Fixed with the pull-balance option (the Arc
  pattern, no new address plumbing): `_safeTransfer` now returns a
  bool; `_payOrCredit` credits `pendingWithdrawals[token][to]` and
  emits `Credited` when the transfer fails instead of reverting, so
  the settlement completes and the job reaches a terminal state. The
  agent recovers the credit with `withdraw(token)` (to itself) or
  `withdrawTo(token, to)` (to a different address) — the latter is the
  recovery path while the blocklist is still in force, since a
  `withdraw()` to the blocklisted agent itself fails again. A failed
  credit does not touch the job's `amountReceived` (it is cleared on
  the push attempt; the credit IS the claim on the funds), and a
  `withdrawTo` to the zero address reverts ("Invalid recipient").
  New test token `contracts/BlocklistToken.sol` (TEST ONLY,
  owner-gated blocklist). Tests: a mid-job blocklist no longer strands
  the job — release() credits the pull balance, the job reaches
  Released, withdraw() fails again while blocked (credit kept), and
  withdrawTo() to an unblocked address pays the full amount; the same
  through the Disputed path — settleDisputeTimeout() credits the
  balance, and withdraw() pays out once the blocklist is lifted.
- Verification: `pytest` 23 passed, 0 failed (21 + 2 new); demo 3/3 +
  stranger guard pass with identical final balances (payer 9920 /
  agent 80 / escrow 0). The v3 video is therefore NOT visibly stale —
  the demo output is unchanged (the fix only changes what happens when
  a payout leg fails, which the demo never triggers). AgentEscrow
  bytecode grew to 18,680 B (was 16,788 B).
- NOT done here: the testnet deployment is still the PRE-fix contract
  (now three fix rounds behind source) — redeploy + Build edit are
  separate steps. Reviewers' improvement and new-feature suggestions
  (timestamp helper, gas tests, coverage, per-job arbiter) were NOT
  implemented in this round — findings only, per instruction; those
  are a separate decision. No GitHub push and no Build edit were made
  in this task.

## HSP (HashKey Settlement Protocol)

The track is defined around HSP's Payment Mandate + Gateway. The HSP sandbox
is not live (Coordinator URL, API key, SDK repo and faucet are placeholders);
the sandbox-access question was asked Oct 26, 2026 and has no reply as of
Oct 27, 2026. Lamplight Pay's mapping onto HSP is documented in the README;
no HSP code runs in this build yet.

## Known gaps

- Testnet-only. Rules: no mainnet deployment forfeits demo selection, and
  winners must be on mainnet to claim the prize. Mainnet deploy waits on
  funds; planned before demo selection Nov 3 if possible.
- Live escrow transactions have run against the deployed round-19 contracts
  (flows A/B/C + stranger guards, escrow ends at 0 — see Round-19 section
  at the end). The v4 demo video still shows the round-16 addresses; a
  fresh video on the round-19 deployment is owed.
- No live HSP integration; no in-person Mumbai demo.

## Files

- `README.md` · `SUBMISSION.md` · `STATUS.md` (this file) · `THREAT_MODEL.md`
- `contracts/`, `a2a/`, `scripts/`, `tests/`, `build/`, `demo-receipts/`, `app/` (live user journey UI)

## Round 4 — "make it better" — DONE Oct 27, 2026 (evening)

The reviewers' improvement + feature suggestions from the round-2
re-review (Grok + Claude, updated brief rules 7+8), implemented
properly per the standing grant ("make it better ellis not the easy way do
what you think is best").

- **Missing coverage (Claude improvement 3):** tests added for every
  previously untested path — agent release while Disputed (reverts),
  resolveDispute(true) pays the agent, resolveDispute(false) refunds
  the payer, early settleDisputeTimeout (reverts), cancel before accept
  (refunds) and after accept (reverts), window of 0 (agent claims in
  the next block; a dispute one block later reverts), and reentrancy
  through a hook token (new test-only `HookToken`, whose transfer()
  calls back into the escrow: the inner release hits the nonReentrant
  guard — proven by the recorded returndata carrying "reentrant" — the
  payout leg fails, the job still reaches Released with a pull credit,
  and the credit pays out once the hook is disarmed). One design fix
  during the run: the hook first returned false by reverting, which
  rolled back its own outcome recording — it now runs before the
  balance movement and returns false without reverting, so the
  recording survives and _tryTransfer still treats it as a failed
  payout.
- **View helper (Grok improvement 2):** `claimWindows(jobId)` returns
  (agentClaimAt, disputeTimeoutAt) = (deliveredAt + reviewWindow,
  deliveredAt + reviewWindow + DISPUTE_PERIOD), so callers never
  re-compute them. Tested against the contract's actual behaviour at
  both boundaries (claim at the boundary reverts, +1s succeeds; timeout
  at the boundary reverts, +1s succeeds) and before delivery (returns
  the window offsets from 0, as documented).
- **Per-job third-party arbiter (Grok + Claude feature):** `createJob`
  takes an optional arbiter address (address(0) = the payer, as
  before). A set arbiter must be neither payer nor agent, and then only
  the arbiter may resolveDispute — the payer cannot, and the arbiter
  cannot raise a dispute or release. If the arbiter goes silent, the
  dispute still times out to the agent. No-arbiter jobs behave exactly
  as before (existing resolve tests pass unchanged). The demo passes
  address(0) (no arbiter) in all three scenarios.
- **Cold transfer (Grok improvement 3, HSK leg):** a release to an
  agent whose token balance is zero (fresh storage slot, cold) pays
  directly, never credits.
- **Tests: 41 passed, 0 failed** (23 before + 18 new). Demo re-run:
  3/3 scenarios + stranger guard pass, final balances unchanged
  (payer 9920 / agent 80 / escrow 0) — the v3 video is NOT stale (the
  demo never uses the new arbiter path). Contract bytecode grew to
  19,919 B (was 18,680 B after round 3).
- NOT done here: the testnet deployment is still the PRE-fix contract
  (now four fix rounds behind source) — redeploy + Build edit are
  separate steps. No GitHub push and no Build edit were made in
  this task.

## Round 5 — Claude round-4 findings + round-4 improvements — DONE Oct 27, 2026 (evening)

Claude's round-4 re-review found 1 Medium (which does not hold up on
inspection) + 2 Lows; Grok found nothing. This round fixes the two Lows,
verifies the Medium, and implements Grok's + Claude's round-4
improvement suggestions. Skipped only: the arbiter fee (Claude feature —
nice-to-have, not needed for the demo).

- **MEDIUM (does NOT hold up): one of the new tests allegedly fails as
  written.** Claude claimed test_arbiter_resolves_dispute_to_agent calls
  resolveDispute(jid, True) from the payer after the arbiter resolved,
  with no pytest.raises. Verified by reading the test (it ends with
  `assert _state(env, jid) == 4` and makes NO such call) and by running
  the suite: 47/47 pass. No change made. Claude misread it.
- **LOW — claimWindows() returns misleading values before delivery.**
  For an undelivered job with a 600s window it returned (600, 600 +
  7d), which look like 1970 timestamps that already passed. Fixed: it
  returns (0, 0) when deliveredAt == 0. The test that locked the old
  behavior was updated to assert (0, 0).
- **LOW — _tryTransfer is not actually non-reverting.** It used
  abi.decode on the full returndata, so a token returning 32 bytes
  with value 2, a 1-byte return, or very large returndata made
  abi.decode revert or the copy run out of gas — and release /
  resolveDispute / settleDisputeTimeout then reverted forever. Fixed:
  the returndata is now inspected with a bounded copy (new
  _lastCallReturnedTrue: at most 32 bytes copied; empty = USDT-style
  success, 32 bytes holding exactly 1 = true, anything else = failure),
  so a malformed return is treated as a failed payout and credited
  instead of reverting. The same treatment was applied to
  _safeTransferFrom (it shared the abi.decode pattern — a malformed
  return there now fails cleanly with "funding failed" instead of
  reverting inside the decode).
- **New test token:** `contracts/MalformedReturnToken.sol` (TEST ONLY,
  owner-gated modes: 0 = 32 bytes holding 2, 1 = 1-byte return, 2 =
  10,000 bytes of returndata, 3 = well-behaved). In malformed modes
  the transfer moves no funds — the token refused the payout but
  answered with garbage instead of false. `scripts/compile.py` builds
  all seven contracts; the fixture deploys and funds it.
- **Tests (3, parameterized over the three malformed modes):** release
  on a malformed-return job completes (job Released, not stranded),
  the pull balance is credited, the agent's token balance is unchanged,
  and once the token behaves again the credit pays out in full via
  withdraw().
- **Zero-address agent guard (Grok improvement 2):** createJob's shared
  "zero address" check is now two explicit checks — token ("zero
  address") then agent ("zero address agent") — so the two guards are
  symmetric and the error string is unambiguous. Tested for both.
- **Cross-function reentrancy (Claude improvement):** two new tests —
  a hook calling raiseDispute() and one calling acceptJob() during
  release()'s payout transfer. Both inner calls fail access control
  (the token is not a party / not the agent; returndata carries the
  message), the payout credits, the job reaches Released, and the
  credit pays out once the hook is disarmed.
- **Tests: 47 passed, 0 failed** (41 before + 6 new). Demo re-run:
  3/3 scenarios + stranger guard pass, final balances unchanged
  (payer 9920 / agent 80 / escrow 0) — the v3 video is NOT stale (the
  demo never uses the malformed token or the cross-function hook).
  Contract bytecode grew to 20,001 B (was 19,919 B after round 4).
- NOT done here: the testnet deployment is still the PRE-fix contract
  (now five fix rounds behind source) — redeploy + Build edit are
  separate steps. No GitHub push and no Build edit were made in
  this task.

## Round 6 — Claude round-5 findings — DONE Oct 27, 2026 (evening)
- **Return-bomb hypothesis TESTED FIRST — CONFIRMED (Claude Low 1):**
  Claude claimed the round-5 bounded-returndata fix was probably
  incomplete because solc's high-level `token.call(...)` copies the
  full returndata into memory before the later assembly copy caps it
  at 32 bytes. Tested, not assumed: a new MalformedReturnToken mode 4
  returns ~3,000,000 bytes, and release() was called on it with a
  30M-gas limit. Pre-fix result: receipt status 0, all 30,000,000 gas
  consumed, job stuck Delivered, no credit — the escrow copied the
  full 3MB on top of the token's own ~17.5M-gas return cost (~35M
  total). Hypothesis CONFIRMED.
- **Fix (exactly as Claude suggested):** `_tryTransfer` and
  `_safeTransferFrom` now make the call in assembly with a 32-byte
  output buffer — `call(gas(), token, 0, add(data, 0x20), mload(data),
  0, 0x20)` — then check returndatasize() via `_lastCallReturnedTrue()`.
  The call can copy at most 32 bytes; returndatasize() still reports
  the full size, so the 3MB return is rejected without copying.
  Post-fix, the same release costs 17,519,061 gas (the token's own
  cost to return 3MB — unavoidable), job Released, payout credited
  10,000,000.
- **New test (stays in the suite either way):**
  `test_return_bomb_three_mb_credits_instead_of_running_out_of_gas`
  sends release() with a 20,000,000-gas limit — enough for the token
  to return (17.5M) but far below the ~35M the old code needed — and
  asserts the settlement succeeds (status 1), the job reaches
  Released, the payout is credited, and the credit pays out once the
  token behaves again. MalformedReturnToken mode 4 is documented in
  the token's NatSpec (setMode now allows 0–4).
- **Arbiter doc reworded (Claude Low 2):** "must be a third party"
  overstated the guarantee — the check only compares addresses, so a
  payer can set the arbiter to a second wallet they control. Reworded
  in the contract NatSpec (header, Job field, createJob, resolveDispute),
  README, and here: the agent should read the job's arbiter before
  accepting and only take jobs whose arbiter it trusts. The
  agent-confirmed arbiter feature is v2, NOT built here (out of scope).
- **Tests: 48 passed, 0 failed** (47 before + 1 new bomb test). Demo
  re-run: 3/3 scenarios + stranger guard pass, final balances unchanged
  (payer 9920 / agent 80 / escrow 0) — the v3 video is NOT stale (the
  demo never uses the malformed token). Contract bytecode 19,746 B
  (was 20,001 B after round 5 — the assembly call is smaller than the
  high-level call's return handling).
- NOT done here: the testnet deployment is still the PRE-fix contract
  (now six fix rounds behind source) — redeploy + Build edit are
  separate steps. No GitHub push and no Build edit were made in
  this task.

## Round-7 fix (Oct 27, 2026)

- **Gas-cost assertions pin the bomb fix (Grok improvement 3):** new
  test `test_release_gas_clean_vs_credited_pins_bomb_fix` measures
  release() gasUsed on the cold path (fresh agent, zero token balance)
  for five paths — clean payer release 75,800; clean agent-claim
  release 77,613; credited mode 0 73,015; credited mode 2 (10KB return)
  74,075; bomb mode 4 (~3MB return) 17,519,073 — and asserts ceilings,
  not exact figures: 150,000 gas for the small-return paths (~2x
  headroom for compiler drift) and 19,000,000 for the bomb (the token's
  own ~17.5M to return 3MB is unavoidable; the escrow pays nothing on
  top, so anything near the ~35M the old code needed means the
  copy-everything behaviour is back). It also asserts each credited
  release costs less than 3x the clean release, so a malformed return
  stays the same order of magnitude as a good one. The existing bomb
  test now also asserts gasUsed ≤ 19,000,000 directly. To support the
  fresh-agent measurements, `_make_delivered` takes an optional
  `agent` parameter (defaults to the standard agent account).
- **Skipped:** Grok improvement 2 (a "what can I do next" view) —
  `lifecycleStatus`/`claimWindows` already cover most of it; Grok's
  features (bonded-stake arbiter, batch release/refund) are v2, NOT
  built here. Claude's round-6 findings are still pending (resume
  after the 9:00 PM CDT limit reset) and are NOT part of this round.
- **Tests: 49 passed, 0 failed** (48 before + 1 new gas test). Demo
  re-run: 3/3 scenarios + stranger guard pass, final balances unchanged
  (payer 9920 / agent 80 / escrow 0) — the v3 video is NOT stale (the
  demo never uses the malformed token). The HSK contract itself did NOT
  change in this round (tests only), so no build artifacts were
  recompiled and no redeploy is newly owed beyond the existing one.

## Round-8 fix (Oct 27, 2026)

- **pendingCredit view (Grok improvement 2):** new view
  `pendingCredit(address token, address account)` returns the account's
  pull balance from `pendingWithdrawals` — the mapping was already
  public, but it was NOT documented anywhere as the front-end path, so
  the named, documented view was added (the escape hatch in the brief
  did not apply). New test
  `test_pending_credit_view_reports_pull_balance`: 0 for the agent,
  a stranger, and an uncredited token before the job; exactly
  10 * ONE after a credited mode-0 release (job Released, not
  stranded); 0 for the stranger and the other token after the credit;
  agrees with the public mapping; back to 0 after `withdraw()`.
- **Gas ceilings in the NatSpec (Grok improvement 3):** the
  `_tryTransfer` NatSpec now states the exact ceilings the tests pin —
  150,000 gas for the small-return paths (clean payer release 75,800,
  clean agent-claim 77,613, credited mode 0 73,015, credited mode 2
  74,075), 19,000,000 for the ~3MB return-bomb path (17,519,073, of
  which ~17.5M is the token's own cost to return 3MB; the escrow pays
  nothing on top), and the <3x relative bound — and why: so a future
  solc upgrade that shifts the numbers gets noticed immediately.
  NatSpec only; no behaviour changed.
- **Tests: 50 passed, 0 failed** (49 before + 1 new view test). Demo
  re-run: 3/3 scenarios + stranger guard pass, final balances unchanged
  (payer 9920 / agent 80 / escrow 0) — the v3 video is NOT stale (the
  demo never uses the malformed token or the new view). Build artifacts
  recompiled (`scripts/compile.py`); AgentEscrow bytecode 19,934 B
  (was 19,746 B after round 6 — the view adds 188 B). No GitHub push
  and no Build edit were made in this task.

## Round 9 — Claude round-8 improvements (all 3) — DONE Oct 27, 2026 (evening)

- **Code-length check in `_tryTransfer` (Claude improvement 1):** a
  token address whose code has vanished after funding answers a call
  with success and empty returndata, which the USDT-style rule reads as
  "paid" — the job would be marked settled while nothing moved. `_tryTransfer`
  now returns false up front when `token.code.length == 0`, so the
  payout fails and the job is credited instead. Proved by a new test
  with a `VanishingToken` test token (minimal ERC-20 + `kill()`
  self-destruct), run on a pre-Cancun (Shanghai) chain in a separate
  tester: there SELFDESTRUCT deletes the code (on the default Prague
  tester EIP-6780 makes the code survive the kill — the same reason the
  hole is nearly unreachable on modern mainnet). The test was verified
  to FAIL with the check removed and PASS with it restored. The credit
  itself can never be withdrawn — the token is dead — but the funds stay
  recorded as owed, not silently marked paid. Limit, stated plainly in
  the NatSpec: the check only sees the TOKEN address's own code; a proxy
  whose implementation vanished still has code itself, so its
  delegatecall can still return empty success — that case needs a
  balance check, not a code check, and is out of scope here.
- **Gas-burning token pinned (Claude improvement 2):** new
  `MalformedReturnToken` mode 5 (infinite loop — burns all forwarded
  gas) plus a test: with a 20,000,000 gas limit the release costs
  19,695,562 gas, succeeds, and credits the full payout; with 200,000
  it reverts and the job stays Delivered, unsettled, retryable with more
  gas. Measured, not estimated (Claude's ~2M retained-gas estimate was
  unmeasured). NatSpec line added to `_tryTransfer` — a front-end must
  not hardcode a low gas limit for release.
- **Shared test state reduced (Claude improvement 3):** the
  `pendingCredit` test now uses fresh accounts (accounts[3]/[4]) that no
  earlier test has credited, so its "0 before the credit" assertions no
  longer depend on earlier tests having withdrawn. (On the Arc side, the
  two gas-guard boundary tests now derive their limits from
  `_minGasForDirectPay` instead of hardcoding them.)
- **Tests: 52 passed, 0 failed** (50 before + 2 new: mode-5 gas-burning
  and vanished-code). Demo re-run: 3/3 scenarios + stranger guard pass,
  final balances unchanged (payer 9920 / agent 80 / escrow 0) — the v3
  video is NOT stale. Build artifacts recompiled (`scripts/compile.py`,
  now including `VanishingToken`); AgentEscrow bytecode 19,973 B (was
  19,934 B after round 8 — the code-length check adds 39 B). No GitHub
  push and no Build edit were made in this task.

## Round 10 — Grok round-9 improvements — DONE Oct 27, 2026 (evening)

- **Balance-delta check in `_payOrCredit` (Grok improvement 1, the big
  one):** a token that returns true (or empty) while moving nothing
  would previously mark the job paid with no credit — the funds
  silently lost. `_payOrCredit` now reads the escrow's balance before
  and after the transfer and treats the balance as the source of truth,
  not the token's return value: only the shortfall (what the escrow
  still holds for this job) is credited, so the invariant always holds
  — escrow token balance == sum of unsettled job amounts + all pending
  credits. The mirrored case is covered too: a token that moves the
  funds and then returns false still counts as paid, never paid twice.
  Balances are read with a new `_balanceOf` helper (low-level
  staticcall, 32-byte-capped, never reverts): a high-level
  `balanceOf()` call on a dead token reverts on the empty-returndata
  ABI decode, which would have bricked the release instead of
  crediting it — the round-9 VanishingToken test caught that in the
  first full run, and the helper fixed it. Same balance verification
  added to `withdraw()` / `withdrawTo()` (beyond the brief's letter,
  same hole): a lying token can no longer zero a credit — the call
  reverts with "withdrawal failed" and the credit is restored.
- **New test token mode:** `MalformedReturnToken` mode 6 — transfer()
  returns true but moves no funds (the lying token). Proved against
  the old code: with the balance check temporarily removed, the
  lying-token test and the invariant test both FAIL (escrow holds
  10,000,000 with 0 unsettled and 0 credits — the exact silent loss);
  restored, both pass. The job still reaches Released with the full
  credit recorded — that is the established pull-balance design (a job
  that stayed Delivered would be stranded); the brief's "must NOT flip
  to Released" wording was read as "must not be marked paid".
- **Settlement invariant test (Grok round-8 leftover):** a helper
  `_assert_invariant` asserts, for every token, escrow balance ==
  unsettled job amounts + pending credits, over the whole shared
  fixture (every job and credit the suite created, including the
  leftover credits the gas test deliberately leaves in place and the
  fee token's net-received amounts). Called in the lying-token test
  and in a standalone `test_settlement_invariant_holds`.
- **`jobWindows()` view (Grok improvement):** one call returns
  (deliveredAt, agentClaimAt, disputeTimeoutAt, credit) — claimWindows
  + pendingCredit combined, so callers never recompute windows or call
  three views. Before delivery the timestamps are 0 (same rule as
  claimWindows); the credit is the job's agent's pull balance for the
  job's token. Tested for undelivered / delivered / disputed /
  credited jobs, cross-checked against claimWindows() and
  pendingCredit().
- **Gas pinning (Grok improvement 3):** the ceilings are now NAMED
  CONSTANTS in the test file (`GAS_CEILING_SMALL` 150,000,
  `GAS_CEILING_BOMB` 19,000,000, `GAS_CEILING_GAS_BURN` 19,900,000)
  instead of literals scattered through the tests, and the mode-5
  high-limit path finally has a ceiling assertion: re-measured with
  the round-10 balance check at 19,697,418 gas (was 19,695,562 —
  +1,856 for the two balance reads), ceiling 19,900,000, so a future
  solc change that alters the 1/64 retention math is caught the same
  way the return-bomb regression is. The gas test and the bomb test
  now use the constants.
- **Boundary semantics (Grok round-8 leftover):** the exact boundary
  rules are now documented in the NatSpec of each function — release's
  agent claim is STRICT (>) at deliveredAt + reviewWindow, raiseDispute
  is INCLUSIVE (<=) at the same second, resolveDispute is INCLUSIVE
  (<=) at the dispute-timeout second, settleDisputeTimeout is STRICT
  (>) after it — and in `jobWindows()`'s NatSpec.
- **Tests: 56 passed, 0 failed** (52 before + 4 new: lying-token
  payout, lying-token withdraw, jobWindows view, settlement
  invariant). Demo re-run: 3/3 scenarios + stranger guard pass,
  final balances unchanged (payer 9920 / agent 80 / escrow 0) —
  receipts B and C byte-identical to the pre-round-10 run (receipt A
  differs only by its fresh quote, as always). The v3 video is
  therefore NOT visibly stale. Build artifacts recompiled
  (`scripts/compile.py`); AgentEscrow bytecode 20,778 B (was 19,973 B
  after round 9 — the balance checks + jobWindows view add 805 B).
- NOT done here: the testnet deployment is still the PRE-fix contract
  (now ten fix rounds behind source) — redeploy + Build edit are
  separate steps. Held, per instruction: agent-side arbiter
  confirmation at acceptJob and the withdrawBatch / multi-token
  withdraw helper (Grok's round-9 new-feature suggestions). No Build
  edit was made in this task.

## Round 11 — Grok round-10 improvements — DONE Oct 27, 2026 (evening)

- **On-chain invariant view (Grok improvement 1):** a new
  `settlementInvariant(token)` view returns (balance, unsettledSum,
  pendingCreditsSum, holds) — the balance equation the tests enforce,
  callable by external monitors and front-ends without log scanning.
  The credit sum comes from a new `totalPendingCredits` per-token
  total, maintained in the same three places `pendingWithdrawals` is
  written (`_payOrCredit` adds the shortfall; `withdraw` /
  `withdrawTo` subtract the full credit on a successful payout) —
  a view cannot enumerate the accounts that hold credits, so the
  total is the only way to expose the sum on-chain. The balance is
  read with `_balanceOf` (never reverts; a dead token reads as 0),
  and `holds` is false if anyone sent tokens to the escrow outside
  `createJob` — the view reports the truth, it does not hide stray
  funds. Unsettled means Created, Accepted, Delivered or Disputed.
- **Second cold-path gas pinning (Grok improvement 2):** a new test
  measures a credited release for an agent+token that already holds
  a non-zero pending credit (two credited releases in a row for the
  same agent, MalformedReturnToken mode 0): the second release writes
  two warm (non-zero -> non-zero) credit slots instead of two cold
  ones — measured 67,784 gas vs 99,017 for the first (cold) release.
  New named ceiling `GAS_CEILING_COLD_PRIOR_CREDIT` 140,000 (~2x
  measured, the same headroom rule as GAS_CEILING_SMALL). The exact
  credit-sum assertions in the test — not the ceiling — are what
  catch a double-credit or under-credit (a second credit of anything
  other than exactly 10 ONE breaks the sum at once); the ceiling is
  the gross-regression tripwire, as with the other ceilings. Side
  effect noted: the first credited release now costs ~99k gas, up
  from ~73k — the per-token total is one more cold SSTORE on the
  first credit — still well under GAS_CEILING_SMALL (150,000), so
  the existing gas test passes unchanged.
- **NatSpec assumption (Grok improvement 3):** the contract's
  top-level NatSpec now states the exact assumption the shortfall
  arithmetic relies on — "tokens move the full amount or nothing" —
  so no later reader assumes partial-transfer support. No behaviour
  change.
- **Tests: 60 passed, 0 failed** (56 before + 4 new: view matches
  manual sums, view on a never-seen token returns zeros, view tracks
  the equation through every demo scenario, warm-credit gas pinning).
  Demo re-run: 3/3 scenarios + stranger guard pass, final balances
  unchanged (payer 9920 / agent 80 / escrow 0) — receipts B and C
  byte-identical to the pre-round-11 run (receipt A differs only by
  its fresh quote, as always). The v3 video is therefore NOT visibly
  stale. Build artifacts recompiled (`scripts/compile.py`);
  AgentEscrow bytecode 21,560 B (was 20,778 B after round 10 — the
  view + per-token total add 782 B).
- NOT done here: no push (round 11 pushes only after its own Grok
  re-review). The testnet deployment is still the PRE-fix contract
  (now eleven fix rounds behind source) — redeploy + Build edit are
  separate steps. Held, per instruction: agent-side arbiter
  confirmation at acceptJob (Grok's round-10 feature — changes the
  accept flow) and the `jobsOf(address party)` view (front-end
  convenience, not needed for the demo). No Build edit was made in
  this task.

## Round 12 — Grok round-11 improvements — DONE Oct 27, 2026 (night)

- **Stray-funds test (Grok improvement 2):** a new test proves
  `settlementInvariant(token)` reports stray funds honestly — a
  direct ERC-20 transfer into the escrow, outside `createJob`,
  makes `holds` false while balance / unsettledSum /
  pendingCreditsSum stay exactly correct (balance == unsettledSum
  + pendingCreditsSum + stray, cross-checked against the manual
  off-chain sums). It runs on a FRESH MockUSDC deployed inside
  the test, so the stray amount never touches the shared fixture
  and no later test inherits it. After the job settles cleanly,
  `holds` stays false while the stray is still there — the stray
  is not a job's money, so no settlement can make the equation
  hold again. No behaviour gap was exposed: the view was already
  correct; the test pins it.
- **NatSpec note (Grok improvement 3):** the `settlementInvariant`
  NatSpec now states the O(jobCount) scan is intentional — the view
  is for off-chain monitors and front-ends, where an eth_call costs
  nothing — and that an on-chain caller with a large history should
  prefer the per-token totals (`totalPendingCredits` for the credit
  sum, an O(1) read) and call the view only when it needs the
  unsettled sum the scan computes. Comment only, no behaviour
  change — the contract bytecode is unchanged.
- **Tests: 61 passed, 0 failed** (60 before + 1 new: the
  stray-funds test). Demo re-run: 3/3 scenarios + stranger guard
  pass, final balances unchanged (payer 9920 / agent 80 / escrow 0)
  — the demo output shape is unchanged, so the v3 video is NOT
  visibly stale. No recompile needed (NatSpec only); build
  artifacts untouched.
- NOT done here: no push (round 12 pushes only after its own Grok
  re-review). The testnet deployment is still the PRE-fix contract
  (now twelve fix rounds behind source) — redeploy + Build edit are
  separate steps. Held, per instruction: the running
  `totalUnsettled[token]` total (would make the view O(1)) and
  maxJobs / cursor-based pagination on `settlementInvariant`.

## Round 13 — Grok round-12 improvements — DONE Oct 28, 2026 (night)

- **Gas pinning on the view (Grok improvement 2):** a new test pins
  `settlementInvariant(token)` gas under a realistic load — 50 jobs
  on a fresh escrow + fresh token deployed inside the test, so the
  load is exactly 50 regardless of test order and the ambient
  fixture is untouched. Measured on this toolchain
  (eth-tester/PyEVM, Oct 28, 2026): **387,382 gas** via
  eth_estimateGas (includes its 21,000 intrinsic base, so the pure
  view cost is ~366,000; marginal cost ~7,000 gas per job),
  pinned under the new named constant
  `GAS_CEILING_INVARIANT_VIEW = 800_000` (~2x measured, the same
  headroom rule as GAS_CEILING_SMALL). The ceiling is a regression
  tripwire for on-chain callers, not a hard limit: off-chain
  monitors read the view via eth_call, which has no block gas limit
  in practice. Tripwire proven real: the test FAILS with the ceiling
  temporarily lowered to 300,000 (below the measured value) and
  passes again at 800,000 (constant restored). The view is still
  exactly right at load: 50 unsettled jobs of 10 ONE, no credits,
  holds True.
- **NatSpec note (Grok improvement 3):** the `settlementInvariant`
  NatSpec now states a direct transfer of tokens into the escrow is
  the only INTENDED way `holds` becomes false — no settlement path
  creates or destroys funds, so a job settling never flips `holds`
  on its own (the round-12 stray-funds test pins this). Comment
  only, no behaviour change.
- **Off-chain recipe (Grok improvement 1, doc half):** the NatSpec
  and README now document the recipe for the unsettled sum alone,
  without the full scan: iterate jobIds 0..jobCount-1, call
  getJob(jid), sum job.amount where job.token == token and
  job.state is Created, Accepted, Delivered or Disputed
  (state <= Disputed); the credit sum is
  totalPendingCredits[token], an O(1) read. The recipe computes
  exactly what the view computes. The on-chain helper stays held —
  no caller needs it yet.
- **Tests: 62 passed, 0 failed** (61 before + 1 new: the
  view-gas pinning test). Demo re-run: 3/3 scenarios + stranger
  guard pass, final balances unchanged (payer 9920 / agent 80 /
  escrow 0) — the demo output shape is unchanged, so the v3 video
  is NOT visibly stale. No recompile needed (NatSpec + tests only);
  build artifacts untouched.
- NOT done here: no push (round 13 pushes only after its own Grok
  re-review). The testnet deployment is still the PRE-fix contract
  (now thirteen fix rounds behind source) — redeploy + Build edit
  are separate steps. Held, per instruction: the on-chain
  unsettled-sum helper; per-job "release-to" address;
  batchWithdraw(token, accounts[]).


## Round 14 — agent-side arbiter confirmation — DONE Oct 28, 2026 (night)

The feature held since round 9 (Grok's round-9 feature, the one Ellis
kept calling the better of the pair) and re-held in rounds 10 and
11 — built now as the substantive feature, not the easy one.

- **The problem it closes:** the payer named the arbiter at createJob
  and the agent's acceptJob implicitly accepted it — the agent never
  explicitly confirmed THAT arbiter, so a payer could name an arbiter
  the agent never agreed to and the acceptance was on-record as
  nothing more than "I accept the job".
- **The fix:** `acceptJob(uint256 jobId, address expectedArbiter)`.
  The agent passes the arbiter it expects; the call reverts
  ("arbiter mismatch") when it differs from the job's recorded
  arbiter. Passing address(0) confirms payer-as-arbiter on a
  no-arbiter job — and reverts on a job that HAS an arbiter, exactly
  like any other mismatch (address(0) is not a wildcard). Check
  order: onlyAgent, then state, then deadline, then the arbiter
  match — a non-agent reverts "not agent" even with the right
  arbiter, and a wrong-state or past-deadline job reverts on those
  grounds before the mismatch is judged.
- **The confirmation is readable afterwards two ways:** the job's
  recorded arbiter never changes after creation — there is no
  function that mutates it — and the JobAccepted event now carries
  the confirmed arbiter (`JobAccepted(jobId, agent, arbiter)`), so
  the agreement is auditable from the logs without a second storage
  field. No new storage was added.
- **Migrations (signature change, not behaviour change):** every
  acceptJob caller updated — `_make_delivered` now passes
  `arbiter or ZERO` (the arbiter the job was created with), the
  seven other direct test calls pass ZERO (all no-arbiter jobs),
  the demo's two calls pass ZERO, and the HookToken hook helper now
  encodes `acceptJob(uint256,address)` (the hook still fails on
  onlyAgent before the arbiter check is reached). `a2a/quote.py`
  and `a2a/receipt.py` do not reference acceptJob and were untouched.
- **Docs:** contract NatSpec (header, createJob, resolveDispute),
  README (arbiter paragraphs + test list + counts + bytecode),
  SUBMISSION.md (the "Honest limitations" line now states the
  payer-by-default / optional-arbiter / agent-confirmed reality
  instead of "needs a third-party arbiter"). The round-6/10/11
  STATUS.md "held" lines are dated historical records and were
  left as written.
- **Tests: 68 passed, 0 failed** (62 before + 6 new: mismatch
  reverts; correct arbiter succeeds and the event carries it;
  address(0) confirms payer-as-arbiter; address(0) reverts when an
  arbiter is set; the recorded arbiter cannot change after accept,
  with check order pinned; a non-agent reverts even with the right
  arbiter). Demo re-run: 3/3 scenarios + stranger guard pass,
  final balances unchanged (payer 9920 / agent 80 / escrow 0) — the
  demo output shape is unchanged, so the v3 video is NOT visibly
  stale. AgentEscrow bytecode 21,918 B (was 21,560 B).
- NOT done here: no push (round 14 pushes only after its own Grok
  re-review). The testnet deployment is still the PRE-fix contract
  (now fourteen fix rounds behind source) — redeploy + Build edit
  are separate steps. Held, per instruction: per-job "release-to"
  address; batchWithdraw(token, accounts[]); the on-chain
  unsettled-sum helper; totalUnsettled[token]; maxJobs / cursor
  pagination on settlementInvariant.

## Round 15 — final polish (Grok round-13 + round-14 improvements) — DONE Oct 28, 2026 (night)

The five small items Ellis wanted built before final — the two
round-13 polish items plus the three round-14 review improvements.
No new feature; everything else stays held.

- **Second gas measurement on the view (Grok round-13 improvement
  1):** the same 50-job measurement with a NON-ZERO prior credit
  total, so the view's credit-sum path is exercised under load, not
  only the pure-unsettled path. A second fresh escrow + fresh
  MalformedReturnToken: one job funded/delivered in mode 3 then
  released in mode 0 (payout returns garbage, so the full 10 ONE
  is credited), then 50 unsettled jobs in the same token. The view
  is exactly [510, 500, 10, True] and its gas is 387,382 — identical
  to the pure-unsettled measurement, as expected, since the credit
  sum is a single SLOAD whose stored value does not change its cost.
  Same ceiling GAS_CEILING_INVARIANT_VIEW 800,000. Tripwire proven
  real: the test FAILS with the ceiling lowered to 300,000 and
  passes again at 800,000 (constant restored).
- **NatSpec note (Grok round-13 improvement 3):** settlementInvariant
  now states the 50-job gas figure was measured on eth-tester/PyEVM
  and will differ on a real client; the ceiling remains the
  regression tripwire regardless of absolute numbers. Comment only;
  no behaviour change.
- **Check-order test (Grok round-14 improvement 1):** a non-agent
  calling acceptJob with a DELIBERATELY WRONG arbiter still reverts
  only on "not agent" — the mismatch is never judged before the
  caller is. Locks the check-order claim forever, alongside the
  round-14 right-arbiter variant.
- **Auditability documentation (Grok round-14 improvement 2, doc
  half only):** the README now says once how an integrator reads the
  confirmed arbiter — `getJob(jobId)` (the Job's `arbiter` field,
  never mutated after creation) or the `JobAccepted(jobId, agent,
  arbiter)` event. No dedicated view built (held — getJob plus the
  event already answer the question).
- **acceptJob gas pinning (Grok round-14 improvement 3):** a
  successful acceptJob with an arbiter match is pinned under the new
  named constant GAS_CEILING_ACCEPT_JOB = 110,000. Measured on this
  toolchain (eth-tester/PyEVM, Oct 28, 2026): 53,521 gas (53,509 on
  a second run — 12 gas of run-to-run variance, far inside the
  ceiling). Tripwire proven real: the test FAILS with the ceiling
  lowered to 50,000 and passes again at 110,000 (constant restored).
- **Tests: 70 passed, 0 failed** (68 before + 2 new: the wrong-
  arbiter check-order test; the acceptJob gas pinning test). Demo
  re-run: 3/3 scenarios + stranger guard pass, final balances
  unchanged (payer 9920 / agent 80 / escrow 0) — the demo output
  shape is unchanged, so the v3 video is NOT visibly stale.
- NOT done here: no push (round 15 pushes only after its own Grok
  re-review). The testnet deployment is still the PRE-fix contract
  (now fifteen fix rounds behind source) — redeploy + Build edit
  are separate steps. Held, per instruction: dedicated
  confirmed-arbiter view; on-chain unsettled-sum helper; per-job
  "release-to" address; batchWithdraw(token, accounts[]);
  totalUnsettled[token]; maxJobs / cursor pagination on
  settlementInvariant.

## Round 16 — Claude final-gate fixes — DONE Oct 28, 2026 (night)

Claude passed the round-15 deploy candidate as SOUND ("I'd ship it
as the deploy candidate", Oct 28, 2026 ~12:44 AM CDT) with one Low
finding and three improvements. Round 16 builds the three fixes
Claude asked for; it SUPERSEDES the queued HSK round-15 Grok
re-review (Grok reviews round 16 directly). No contract logic
change — the compiled code is byte-identical to the round-15 code
Claude passed (verified: same code-only md5, same 21,919 B total;
only the metadata trailer differs, as it must for a comment-only
source change).

- **Demo guard fix (Claude finding 1, Low):** the old guard called
  release(0) as the stranger after scenario A had already released
  job 0, so it reverted on "not delivered" before the caller was
  ever checked — the printed "guard correctly reverted" would have
  appeared even if the caller check were deleted, and it never tried
  a stranger refund though the comment said it did. The guard now
  runs against live jobs and asserts the revert reason: job 3 is
  funded/accepted/delivered (10 mUSDC) and a stranger's release must
  revert on "not payer"; job 4 is Created and past its 5s deadline
  (5 mUSDC) and a stranger's refundAfterDeadline must revert on
  "not payer". Both guard jobs are unwound afterwards (job 3
  disputed and resolved to the payer, job 4 refunded by the payer),
  so the final balances are unchanged (payer 9920 / agent 80 /
  escrow 0) and the three scenarios print exactly as before — only
  the guard block's honesty changed, so the v3 video is NOT visibly
  stale.
- **Randomized state-machine test (Claude improvement 2):** one new
  test, fixed seed 20261028, 60 steps on a FRESH escrow + fresh
  MockUSDC / FeeToken / MalformedReturnToken. Each step picks a
  lifecycle call at random (create, accept, deliver, release,
  dispute, resolve, settleDisputeTimeout, refund, cancel,
  cancelUnaccepted, withdraw, malformed-mode switch, time travel)
  and asserts settlementInvariant(token).holds for all three tokens
  after every step, success or revert. Measured: 25 succeeded, 35
  reverted; the test requires at least 12 successes (roughly half
  the measured count), so a future change that halves the reachable
  transitions fails it. Malformed modes 4 (return-bomb, ~17.5M gas)
  and 5 (gas-burning loop) are excluded for runtime. Ends with the
  manual balance == unsettled + credits cross-check for the three
  tokens. No invariant violation found — the strongest claim in the
  design held over sequences nobody hand-wrote.
- **Withdraw == comment (Claude improvement 3, cheap half):** a
  comment at withdraw and withdrawTo stating why the strict == is
  kept instead of the >= that _payOrCredit uses: no token in the
  suite debits the sender more than the amount asked, and a
  sender-side fee token that did would strand the credit here (the
  revert preserves it, but the credit could never be pulled) and
  would need the >= treatment. The == is NOT changed to >= (held —
  contrived case, no token does it).
- **Tests: 71 passed, 0 failed** (70 before + 1 new: the randomized
  state-machine test, 12.67s on its own; full suite 165.03s). Demo
  re-run: 3/3 scenarios + both guards pass, final balances
  unchanged (payer 9920 / agent 80 / escrow 0).
- NOT done here: no push (round 16 pushes only after its own Grok
  re-review). The testnet deployment is still the PRE-fix contract
  (now sixteen fix rounds behind source) — redeploy + Build edit
  are separate steps. Update (Oct 28, 2026): superseded — rounds 11–16 pushed Oct 28 ~01:09 AM CDT (head 6022bcb2); redeploy done Oct 28 ~1:14 AM CDT (see 'Redeploy' below). Held, per instruction: on-chain quote binding
  (quoteHash in createJob + JobCreated event) — changes the contract
  days before the Nov 1 deadline for quote provenance the demo scope
  doesn't need; the receipt already carries the quote id. (Older
  holds stand: dedicated confirmed-arbiter view; on-chain
  unsettled-sum helper; per-job "release-to" address;
  batchWithdraw(token, accounts[]); totalUnsettled[token]; maxJobs /
  cursor pagination on settlementInvariant.)

## Redeploy — Oct 28, 2026 (night) — DONE, both contracts live + verified
- Goal: redeploy MockUSDC + AgentEscrow (round-16 code) to HSK testnet
  (chain 133) so the on-chain code matches the reviewed source; the
  deployed contracts (MockUSDC 0x860CadF955CF73FDB8E9ED2979104baae9f833B9,
  AgentEscrow 0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7) are 16 rounds
  behind source. Testnet only — never mainnet (177).
- Faucet: 1 tHSK claimed for the fresh deployer in a browser
  (2026-10-28 01:08:36, tx 0x527a8c49e34055041cfb4d5612348b7cd9db7e1345b8388a172667bbbc0403e8);
  on-chain balance read 0.1 tHSK (faucet page said 1 tHSK — either way
  far more than the ~0.004 tHSK the deploy needed).
- Fresh deployer: 0x995646c5270f26a8D64df58D7bc7e8277c606e27. Key at
  ~/.hsk-testnet-deployer (mode 0600, testnet-only). NEVER the Ellis
  main wallet key. The OLD deployer
  (0xa67d284fC85345c2e3aCC3A34d46f93a295df341) still holds 0.0962 tHSK
  but was NOT reused.
- NEW ADDRESSES (round 16, verified on Blockscout — "Pass - Verified"):
  MockUSDC 0x00835c4588461353B4B284437d7D65c466587375
    (tx b0a3961840adfee33fe9352710ebac1e8e30c5467f8dc7c98c3696f8e95d913f,
    block 34990583) — https://testnet-explorer.hskchain.net/address/0x00835c4588461353B4B284437d7D65c466587375
  AgentEscrow 0xF1c84737AAc850546d84C54d60B3b18fF82F8afA
    (tx 2ab7754a91670e4f21deef9280f6d3353803b7aee639f9114b78cb821ef94b12) —
    https://testnet-explorer.hskchain.net/address/0xF1c84737AAc850546d84C54d60B3b18fF82F8afA
  Deployment record: build/hsk-testnet-deployment.json (held locally, not in this repo).
- Two real failures on the way, both diagnosed, both recorded here:
  (1) deploy_hsk_testnet.py fetches the nonce fresh via
  w3.eth.get_transaction_count for each contract, but the public RPC
  returns a STALE nonce for the second deploy in the same run — twice
  the AgentEscrow tx reused the just-mined MockUSDC nonce and the node
  rejected it as "replacement transaction underpriced". The script was
  NOT fixed; AgentEscrow was deployed separately with an explicit
  nonce verified via cast (one-off /tmp/deploy_agent_escrow.py).
  An orphaned first MockUSDC (0x6CDdC8F35256A7973099b0772556619cebd6a71A,
  tx 5dfa11ca1a5c8a83c1f2222183cd46c8c622e9ac48c1b876fbdc73857c8afe79)
  was left on-chain, unused. (2) The script's 3,000,000 gas limit is
  too low for AgentEscrow — the first explicit-nonce attempt consumed
  all 3,000,000 gas and failed (status 0, tx
  117e3ab2ed9431bfb3743f0290302d2bafc71b4b358858403ec1c0f7fdae26f1, dead
  address 0xc266B0099fd6BA8812a0d85048Fc592C7B78bd8E). Measured estimate
  is 4,800,180 gas; the successful deploy used 6,000,000. The deploy
  script's gas limit needs raising before any future redeploy.
  Total spent across all attempts: ~0.0096 tHSK; deployer balance now 0.0904442 tHSK (verified live on-chain Oct 28, 2026).
- Verification: both contracts verified via forge verify-contract
  (Blockscout verifier, solc 0.8.24, optimizer off). Direct urllib
  POSTs to the Blockscout API were refused (403, then dropped
  connections); forge's submission went through and both returned
  "Pass - Verified".
- DONE Oct 28, 2026: DoraHacks Build 50417 edited with the new addresses + v4 video, verified live. Do NOT touch the old deployed contracts.

## Deploy-script fix — Oct 28, 2026 (night) — DONE, local only, no redeploy
- Both Redeploy bugs fixed in scripts/deploy_hsk_testnet.py (no live
  redeploy — the round-16 contracts are live and a redeploy needs an
  explicit go-ahead; no push yet):
  (1) NONCE: fetched ONCE via get_transaction_count(pending) and
  incremented locally per tx — the script never re-queries, so a stale
  RPC read can no longer reuse a nonce. (2) GAS: the hardcoded
  3,000,000 cap is gone; each deploy's limit is eth_estimateGas + 25%
  headroom, floored at 5,000,000 (deploy_gas_limit; a limit is a cap,
  not a spend — unused gas is refunded). (3) Receipt status is now
  checked — a status-0 deploy aborts loudly instead of being recorded
  as live (the old script would have written the dead 3M-gas address
  to the record). Dry-run mode: HSK_DRY_RUN=1 allows a local chain
  (still refuses mainnet 177) and writes the record to
  build/hsk-testnet-deployment-dryrun.json, never the real record.
- Verification, no testnet funds spent: new tests/test_deploy_script.py
  (6 tests) on eth-tester — gas rule table-driven (4,800,180 -> 6,000,225;
  floor wins below 4M), old 3M cap proven below the real AgentEscrow
  estimate, both contracts deploy in one run with sequential nonces
  even when a second nonce query would return stale 0 (count proves
  the query happens exactly once), status-0 receipt aborts. Full suite:
  77 passed (71 + 6 new). End-to-end dry run through the script's
  real main() against local Anvil (chain 31337): MockUSDC estimate
  892,499 -> limit 5,000,000, nonce 0, 0x5FbDB2315678afecb367f032d93F642f64180aa3;
  AgentEscrow estimate 4,761,225 -> limit 5,951,532, nonce 1,
  0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512, receipt status 1.
  Mainnet refusal verified: same script against Anvil chain 177 exits
  REFUSED even in dry-run mode. Real deployment record untouched
  (md5 a6403922ab515cfd067aad4204fb4860 before and after).
- Gas rule for future redeploys: limit = max(ceil(estimate * 1.25),
  5,000,000). On HSK testnet the AgentEscrow estimate was 4,800,180,
  so a live run would set ~6,000,225 — the same figure the successful
  round-16 deploy used. Script is safe for a future redeploy when
  the owner says go.

## Demo video v4 — built Oct 28, 2026 ~1:20 AM CDT (round 16, new testnet addresses)
- Rendered with a v4 render script derived from scripts/make_demo_video_v3.py (v3 untouched).
  Frames from a FRESH scripts/demo.py run Oct 28, 2026 — round-16 guard block:
  jobs 3 and 4, stranger release AND stranger refund both revert 'not payer',
  jobs settled back to payer. Final balances payer=9920.0 agent=80.0 escrow=0.0.
  Job-0 funded tx is fresh (1c08ba29…378a24 — quote is fresh each run, so it
  differs from v3); the invented "[A] quote:" line from v3 was dropped, the
  real output prints no quote line. PAGE_B/C now show the real tx hashes.
- Testnet frame shows the NEW live contracts only: AgentEscrow
  0xF1c84737AAc850546d84C54d60B3b18fF82F8afA, MockUSDC
  0x00835c4588461353B4B284437d7D65c466587375, Deployer
  0x995646c5270f26a8D64df58D7bc7e8277c606e27, chain 133,
  testnet-explorer.hskchain.net. Old addresses nowhere in the video.
- Narration: v3 audio segments reused verbatim (build/demo-video-v4-audio/,
  copied from the v3 set); no re-generation — demo_c narration is still true
  for round 16. Duration 125.17s (2:05), 1280x720 h264 + AAC, md5
  2bf0f0d29624ab40dbbb3c23d3c65fc1. Verified: plays end to end, audio present
  in every section (mean -19 to -22 dB), guard + testnet frames viewed.
- DONE Oct 28, 2026: uploaded to YouTube as Unlisted (@EllisLamplight) at https://youtu.be/6lGHXO1dEVM; Build 50417 edited. Do NOT make it Public.

## Round-16 job-0 cleanup — DONE Oct 28, 2026 ~9:20 AM CDT
- The round-16 live demo's job 0 (50 mUSDC) could not complete in-run
  (stale-nonce deploy bug; the ephemeral agent key was lost when the
  process aborted), so its funds stayed locked until the payer refunded
  after the job's 3600s deadline.
- Cleanup: `refundAfterDeadline(0)` from the payer, tx
  0x0e5a8d52d9b94a0a4afaef493c90b1271ad4324fa761931290605ae98f66495b,
  status 1, block 35005307. Job 0 now Refunded, escrow mUSDC balance 0,
  payer 9,970 mUSDC (9,920 + 50 refunded). The round-16 demo's final
  state is now exact.

## Round-19 deployment + live demo + build pinning — DONE Oct 28, 2026
- Fresh deploy on HSKChain Testnet (chain 133), round-19+20 code:
  MockUSDC 0xEF346652eeB233662E7d290d222175895d53ef15 (block 35016778),
  AgentEscrow 0xAB70612F45d9cf914D129b0DB71DE243dD55813C (block 35016779),
  deployer 0x995646c5270f26a8D64df58D7bc7e8277c606e27. Record:
  `build/hsk-testnet-deployment-round19.json`; the round-16 record is
  untouched. Both contracts Blockscout-verified, "Partial Match",
  solc v0.8.24, EVM Cancun, optimization off — AgentEscrow verified
  Oct 28, 2026 15:51:56 (-05:00), MockUSDC 15:52:45 (-05:00). Partial
  (not exact) is expected: the submitted AgentEscrow source carries
  the round-20 comment-only note, which postdates the deployed
  bytecode's metadata hash.
- Live testnet demo against the new deployment (receipts in
  `demo-receipts/*-testnet-round19.json`): Flow A release 50 mUSDC,
  Flow B timeout refund 20 mUSDC, Flow C dispute resolved to agent
  30 mUSDC, plus stranger release and stranger refund guards that
  both reverted on "not payer" as required; guard jobs unwound.
  Final state: jobCount 5, all terminal, escrow mUSDC exactly 0,
  settlementInvariant (0, 0, 0, true), payer 9,920 / agent 80 mUSDC.
  Deployer 0.058200 → 0.035388 tHSK.
- Build pinning (round 21, read-only, no transactions): the deployed
  AgentEscrow runtime code (22,748 bytes) is byte-identical to a
  reproducible compile of the reviewed source once the metadata
  trailer is accounted for (metadata-stripped sha256
  368cb234ff6e4d2d6b5ba6e8d5450245d671e45b8829d82ca9b26f42e25cba0a;
  full hashes differ ONLY in the 32-byte ipfs metadata hash).
  MockUSDC matches fully (a263d4f9…) as the control case. Record:
  `build/hsk-testnet-deployment-round19-pinning.json`. Conclusion:
  the deployed build is pinned; no redeploy is needed to trust the
  deployed code; any future source change must re-pin.
- Round 21 (tests + docs only, no contract logic change): withdrawTo
  hook test, failed-withdrawal atomicity test, partial-transfer
  transient-window test, withdraw hook docstring correction, new
  test-only `contracts/PartialHookToken.sol`, `scripts/compile.py`
  updated. Full suite 85/85 (79 flow + 6 deploy-script).
- Live user journey UI: `app/index.html` (single file, ethers via CDN,
  no backend, no keys) — connect wallet, chain-133 guard, approve +
  create/accept/deliver/release/refund/dispute/settle/withdraw, job
  and invariant views, Blockscout links per transaction. Served via
  GitHub Pages at
  https://queenellis2026-hash.github.io/lamplight-pay-hsk/app/ .
  Note: the deployed MockUSDC's mint is deployer-only, so a visitor
  cannot mint mUSDC from the page; the UI says so and accepts a
  custom token address.
- Threat model: `THREAT_MODEL.md` — roles and trust, attack surface
  with mitigations and pinning tests, the two transient windows
  stated honestly, accepted limitations, evidence.
- Reviews for this code: Claude round-17 SOUND (1 Low, docs only,
  fixed in round 18); ChatGPT round-18 SOUND (2 Low, fixed in round
  19); ChatGPT final-version review SOUND, no findings (testnet
  only — mainnet readiness NOT established). Stateful/fuzz invariant
  testing and a fresh demo video on the round-19 deployment are
  still owed.

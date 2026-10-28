# Lamplight Pay — status (Oct 27, 2026)

## Project

Lamplight Pay — escrowed settlement for agent-to-agent work on HSK Chain.
Built for the HSK Chain Horizon Hackathon, track Agent Payments & A2A
Settlement.

## Timeline

- Prize: $10,000 USDT total, $5,000 USDT per track.
- Submission deadline Nov 1, 2026, 21:30 IST · Demo Day Nov 4 · Winners Nov 5.

## Deployment (HSKChain Testnet, chain ID 133)

- [AgentEscrow `0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7`](https://testnet-explorer.hskchain.net/address/0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7) — deployed Oct 26, 2026 ([tx](https://testnet-explorer.hskchain.net/tx/59069c0957ea521c47bbc79fc22d9f3de4df8916c611b4b8c4a41e28f4a74f7c)).
- [MockUSDC `0x860CadF955CF73FDB8E9ED2979104baae9f833B9`](https://testnet-explorer.hskchain.net/address/0x860CadF955CF73FDB8E9ED2979104baae9f833B9) — deployed Oct 26, 2026 ([tx](https://testnet-explorer.hskchain.net/tx/2ea7242b072fd7348b619f279e66a9c531792a4e99b8d835a8a073989191b4a7)).
- Deployer: `0xa67d284fC85345c2e3aCC3A34d46f93a295df341` (testnet-only, funded 0.1 tHSK from the testnet faucet).
- Demo scenarios: 3/3 pass on a local EVM; `pytest` 16 passed. Receipts in `demo-receipts/`.
- Demo video: 28s, Unlisted — https://youtu.be/GdHNK0fZ0Lo.
- Submitted Oct 27, 2026: https://dorahacks.io/build/50417 — status Under Review. The Build can still be edited before judging.

## Post-review fix (Oct 27, 2026)

Independent review (Claude, Grok, ChatGPT — full verbatim in
`reviews-2026-10-27.md`) found 9 findings, all fixed in source + tests:
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
- No escrow transaction has run against the deployed contracts yet — the demo
  ran on a local EVM.
- No live HSP integration; no in-person Mumbai demo.

## Files

- `README.md` · `SUBMISSION.md` · `STATUS.md` (this file)
- `contracts/`, `a2a/`, `scripts/`, `tests/`, `build/`, `demo-receipts/`

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


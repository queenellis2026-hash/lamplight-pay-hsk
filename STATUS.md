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

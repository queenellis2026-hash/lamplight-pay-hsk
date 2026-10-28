# Lamplight Pay — Threat Model

**Contract:** `AgentEscrow` (+ `MockUSDC` test token), as deployed on HSK
Chain Testnet (chain 133) — see *Evidence* at the end for the
deployment, verification, and test record this document rests on.
**Scope:** the escrow contract only. No front end, no off-chain
quote service, and no token contract beyond `MockUSDC` is in scope
here. Everything below is grounded in the deployed source and the
test evidence; where a protection is an accepted limitation rather
than a guarantee, it says so.

## 1. Roles and trust

| Role | Powers | Trust required |
| --- | --- | --- |
| **Payer** (human or agent) | Funds a job (`createJob`), releases (`release`), reclaims after deadline (`refundAfterDeadline`, `cancel`, `cancelUnaccepted`), raises disputes, resolves disputes when no arbiter is set, settles a timed-out dispute | None from the agent — the escrow, not the payer's word, holds the funds |
| **Agent** (worker) | Accepts (`acceptJob`), delivers (`submitDelivery`), claims after the review window (`release`), raises disputes, settles a timed-out dispute | None from the payer — acceptance and delivery are on-chain, and a silent payer cannot lock funds (see §2) |
| **Arbiter** (optional, per job) | Resolves a dispute (`resolveDispute`) — true pays the agent, false refunds the payer. Binding, no appeal | **This is the one trusted role.** See the limitation below |
| **Deployer** | None after deployment | None. See below |

**No owner, no admin.** `AgentEscrow` has no `owner`, no
`onlyOwner`/`onlyAdmin` modifier, no pause, no upgrade path, and
no function that mutates a job after creation. The deployer cannot
move funds, change an arbiter, or alter a job once the contract is
deployed. (Verified by inspection of the deployed source.)

**Arbiter — the documented limitation.** At creation the arbiter
must be neither the payer nor the agent, and the agent must confirm
the arbiter on-chain at `acceptJob` (the call reverts on a
mismatch), so a payer cannot name an arbiter the agent never
agreed to. But both checks compare addresses only: they prove
*separation*, not *independence*. A payer could nominate a second
wallet they control, and the contract cannot detect that. The
agent's protections are (a) seeing and confirming the exact
arbiter address before accepting, and (b) `settleDisputeTimeout`,
which releases to the agent if the arbiter goes silent past the
dispute period. An arbiter eligibility mechanism (allowlist,
staking, registry) would be a new trust layer, not a fix, and is
out of scope for this build — see §4.

## 2. Attack surface, mitigations, and the test that pins each

### Reentrancy through token callbacks

ERC-777/ERC-1363-style tokens call back into the caller during a
transfer. A malicious token could try to re-enter a settlement
function mid-call.

- **Mitigation:** a minimal `nonReentrant` guard (`_locked`) on
  every function that moves tokens: `createJob`, `release`,
  `refundAfterDeadline`, `cancel`, `cancelUnaccepted`,
  `resolveDispute`, `settleDisputeTimeout`, `withdraw`,
  `withdrawTo`. Functions that make no external calls
  (`acceptJob`, `submitDelivery`, `raiseDispute`) need no guard.
- **Pins:** `test_reentrancy_through_hook_token`,
  `test_hook_calling_raise_dispute_cannot_brick_release`,
  `test_hook_calling_accept_job_cannot_brick_release`, and the
  round-19/21 hook-window tests (§3).

### Stranger stealing a job's funds

A third party calls `release` or a refund on a job that is not
theirs.

- **Mitigation:** `onlyPayer` / `onlyAgent` modifiers plus
  explicit caller checks. `release` allows only the payer at any
  time while Delivered, or the agent after the review window.
  Refunds and cancels are payer-only. All other callers revert
  (`"not payer"` / `"not agent"`).
- **Pins:** `test_stranger_cannot_release`; the live testnet demo
  ran both stranger guards on-chain and both reverted
  (`"not payer"`), then unwound cleanly.

### Dispute abuse and fund-locking

A payer disputes late, disputes forever, or an arbiter goes
silent to freeze funds. An agent claims before the payer has had
a chance to object.

- **Mitigations:**
  - Disputes may only be raised **inside** the review window
    (inclusive bound: `block.timestamp <= deliveredAt +
    reviewWindow`); after it, `raiseDispute` reverts.
  - The review window is capped at **30 days**
    (`MAX_REVIEW_WINDOW`); an uncapped window would let a silent
    payer lock the agent's claim indefinitely.
  - The agent's claim is strict (`>`): at exactly
    `deliveredAt + reviewWindow` the claim reverts and a
    last-second dispute still wins — a dispute can never lose a
    race to the agent's release.
  - The arbiter must resolve within the dispute period (review
    window + **7 days** `DISPUTE_PERIOD`, inclusive bound).
  - `settleDisputeTimeout` is the backstop: after the period
    ends (strict `>`), either party may settle to the agent, so
    no silent arbiter or silent party can lock funds forever.
  - The arbiter cannot raise a dispute and cannot release — only
    the parties may dispute, only payer/agent may release.
- **Pins:** `test_dispute_after_window_reverts`,
  `test_dispute_inside_window_works`,
  `test_dispute_timeout_releases_to_agent`,
  `test_dispute_resolve_after_period_reverts`,
  `test_agent_claim_at_exact_window_end_reverts`,
  `test_dispute_at_exact_window_end_succeeds`,
  `test_agent_claim_just_after_window_end_succeeds`,
  `test_create_job_too_large_review_window_reverts`,
  `test_create_job_max_review_window_ok`,
  `test_agent_release_while_disputed_reverts`,
  `test_settle_dispute_timeout_before_period_reverts`.

### Arbiter abuse

A payer names themselves, the agent, or an arbiter the agent
never agreed to; an arbiter is swapped after acceptance.

- **Mitigations:** `createJob` requires arbiter ≠ payer and
  arbiter ≠ agent; `acceptJob` requires the agent to pass the
  arbiter it expects (`"arbiter mismatch"` on any difference,
  including passing `address(0)` on a job that has an arbiter);
  there is no function that mutates a job's arbiter after
  creation, and the `JobAccepted` event records the confirmed
  arbiter for audit. When no arbiter is set, the payer resolves
  (the documented default). What these checks do **not** do is
  prove independence — see §1 and §4.
- **Pins:** `test_arbiter_cannot_be_payer_or_agent`,
  `test_accept_job_mismatched_arbiter_reverts`,
  `test_accept_job_confirms_arbiter_and_emits_it`,
  `test_accept_job_zero_arbiter_confirms_payer_as_arbiter`,
  `test_accept_job_zero_arbiter_reverts_when_arbiter_set`,
  `test_accepted_job_arbiter_cannot_change`,
  `test_accept_job_non_agent_reverts_even_with_right_arbiter`,
  `test_arbiter_cannot_raise_dispute_or_release`,
  `test_payer_cannot_resolve_when_arbiter_set`,
  `test_no_arbiter_job_payer_still_resolves`.

### Malicious, lying, or broken tokens

The escrow calls arbitrary ERC-20 code. A token may lie about
its return value, return megabytes of returndata, burn gas in a
loop, vanish (no code), blocklist the recipient, or move nothing
while reporting success.

- **Mitigations:**
  - All token calls use a **32-byte-capped output buffer** in
    assembly, so a return bomb cannot run the caller out of gas
    on the copy. Returndata is accepted only if empty
    (USDT-style) or exactly 32 bytes holding `1`; anything else
    counts as failure.
  - A token address with **no code** fails the transfer attempt
    instead of reading as paid.
  - **Balances, not return values, are the source of truth.**
    `_payOrCredit` and `withdraw`/`withdrawTo` verify the
    escrow's balance actually moved. A token returning `true`
    while moving nothing is credited, never marked paid; a token
    that moves funds and returns `false` still counts as paid,
    never paid twice. Only the shortfall is credited.
  - **Pull payments on failure.** If a payout leg fails
    (blocklisted recipient, refusing token), the amount is
    credited to a pull balance and the job still reaches its
    terminal state — a failing transfer can never strand a job.
    The recipient pulls later with `withdraw()`, or to a
    different address with `withdrawTo()` when the credited
    address itself is blocklisted.
  - **Fee-on-transfer** is handled at funding: `createJob`
    stores what actually arrived (balance before/after), so the
    escrow never records more than it holds.
  - A token whose **code vanished after funding** reads as
    balance `0` through the never-reverting balance reader, so
    the payout is credited rather than bricking the settlement.
    (One stated limit: the code-length check sees only the
    token address's own code — a proxy token whose
    *implementation* vanished could still return empty success;
    the balance check above is what keeps that case from marking
    a job paid.)
- **Pins:** `test_return_bomb_three_mb_credits_instead_of_running_out_of_gas`,
  `test_gas_burning_token_credits_when_release_supplies_enough_gas`,
  `test_vanished_code_token_credits_instead_of_marking_paid`,
  `test_malformed_return_payout_credits_instead_of_stranding`,
  `test_lying_token_returning_true_without_moving_funds_credits`,
  `test_lying_token_withdraw_cannot_drop_credit`,
  `test_fee_on_transfer_token`, `test_no_bool_token`,
  `test_blocklisted_agent_release_credits_pull_balance`,
  `test_blocklisted_agent_dispute_timeout_credits_pull_balance`.
  Gas note from the code: a release against a gas-burning token
  needs enough gas for the retained 1/64 to cover the credit
  path — a front end must not hardcode a low gas limit.

### Funding and input validation

Unfunded jobs, zero-value jobs, impossible windows, or a payer
acting as their own agent.

- **Mitigations:** `createJob` requires a non-zero token, a
  non-zero agent distinct from the payer, `amount > 0`,
  `deadlineSeconds > 0`, and `reviewWindowSeconds <=
  MAX_REVIEW_WINDOW` (30 days); a failed `transferFrom` reverts
  funding (`"funding failed"`), so a job that was never funded
  cannot exist; funding stores the received amount, not the
  requested amount.
- **Pins:** `test_create_job_too_large_review_window_reverts`,
  `test_zero_address_agent_rejected_with_own_message`, and the
  happy-path / refund tests.

### Accounting drift

If any settlement path adds or subtracts wrong, the escrow could
go insolvent or lock funds.

- **Mitigations:** two O(1) accumulators —
  `totalUnsettled[token]` (added in `createJob`, subtracted in
  every one of the seven settlement paths) and
  `totalPendingCredits[token]` (added on credited shortfalls,
  subtracted on successful withdrawals) — plus the
  `settlementInvariant` view, which exposes
  `balance == unsettledSum + pendingCreditsSum` on-chain in one
  call. A missed add or subtract flips `holds` to `false`
  immediately.
- **Pins:** `test_total_unsettled_tracks_every_settlement_path`,
  `test_total_unsettled_credited_release`,
  `test_settlement_invariant_holds`,
  `test_settlement_invariant_view_matches_manual_sums`,
  `test_settlement_invariant_view_no_jobs_returns_zeros`,
  `test_settlement_invariant_view_after_demo_scenarios`,
  `test_settlement_invariant_view_reports_stray_funds`,
  `test_settlement_invariant_view_gas_pinned_at_load`,
  `test_randomized_state_machine_invariant_holds` (checks the
  accumulator after every step, not just at the end).

### Stray funds and observability

Tokens sent directly to the escrow (outside `createJob`) are
never recorded as any job's funds.

- **Mitigation:** the invariant view reports the truth instead
  of hiding it — stray funds make `holds` false, which is the
  signal, not a bug. No function can sweep or claim unrecorded
  funds.
- **Pin:** `test_settlement_invariant_view_reports_stray_funds`.

### Timestamp dependence

Deadlines and windows use `block.timestamp`. A block producer
can shift timestamps slightly, but every window here is measured
in seconds-to-days (review windows up to 30 days, dispute period
7 days), so small shifts cannot change an outcome; the exact
boundary seconds are pinned by the boundary tests listed under
dispute abuse.

## 3. Transient windows — honestly stated

`settlementInvariant` is a settled-state invariant, not a
continuously-true-during-callbacks invariant. Two transient
windows remain open by design, both documented in the
`settlementInvariant` note, both transient mid-call reads, never
settled breaks. The view is deliberately not locked.

1. **createJob funding window.** During `createJob`'s
   `transferFrom`, the escrow balance has already risen but
   `totalUnsettled` has not yet been updated, so a callback
   token reading the view mid-call sees `holds == false`.
   Pinned (as false, by design) by
   `test_create_job_hook_sees_documented_false_window`.
2. **Failed/partial payout credit window.** Every settlement
   path subtracts `totalUnsettled` *before* `_payOrCredit`, but
   the credit for a shortfall is added only *after* the transfer
   attempt, so a callback token reading the view mid-call during
   a failed or partial payout sees `holds == false` transiently.
   It self-heals when the call completes (the credit is added),
   and observing it takes an exotic token — a hook that then
   fails or partially pays. Pinned by
   `test_partial_payout_hook_sees_transient_false_then_settled_true`
   (transient `false` mid-call, settled `true` after).

**Closed in round 19:** the withdraw window. `withdraw` and
`withdrawTo` now subtract `totalPendingCredits` *before* the
transfer, so a recipient callback mid-withdrawal sees `holds ==
true`. A failed transfer reverts the whole call, restoring the
subtraction and the zeroed pull balance — the reorder changed
only mid-call ordering, never the final state. Pinned by
`test_withdraw_hook_sees_true_invariant` and
`test_withdraw_to_hook_sees_true_invariant`. The release path
already subtracted before payout. Pinned by
`test_release_hook_sees_true_invariant`.

## 4. Accepted limitations / out of scope

- **Arbiter independence.** No eligibility mechanism (allowlist,
  staking, registry). The checks prove address separation, not
  independence. A future feature if independent arbitration is
  ever required — not a fix for this build.
- **Unsupported token classes** (header checklist in the
  source): rebasing tokens (balances change outside transfers,
  breaking the received-amount and balance arithmetic),
  sender-side fee tokens (a transfer debiting the sender more
  than asked strands a credit — the withdraw `==` check can
  never pass), and partial-transfer tokens (payout arithmetic
  assumes a leg moves the full amount or nothing; a partial
  move is credited only the shortfall).
- **Testnet only. Mainnet readiness is NOT established.** This
  build has had no external audit, no mainnet deployment, and no
  formal verification. The judgments below are testnet judgments.
- **No HSP integration yet.** The Agent Payments & A2A
  Settlement track is defined around HSP's Payment Mandate /
  Gateway flow; this escrow maps to it (quote = mandate, release
  = verify-and-execute, receipt = settlement proof) but no HSP
  code runs in this build.
- **No identity or privacy layer.** Job data — parties, amounts,
  delivery hashes, metadata URIs — is public on-chain. No KYC
  is involved, and none is claimed.
- **No front-end trust assumptions in the contract.** The
  contract does not depend on any off-chain service; the quote
  and receipt layers are off-chain conveniences, not security
  dependencies.

## 5. Evidence

- **Tests: 85 passing** (`test_flow.py` + `test_deploy_script.py`,
  local EVM), including adversarial token suites, boundary-second
  tests, hook-window tests, and a randomized state-machine test
  that checks the accumulator after every step.
- **Independent reviews, all judging the code sound, all
  findings fixed in later rounds:** Grok (round 16), Claude
  (round 17), ChatGPT (round 18 and the final version), plus a
  delta review of round 19. No review left an open finding above
  Low, and every Low was addressed.
- **Build pinning (round 21):** the deployed `AgentEscrow`
  runtime code is byte-identical to a reproducible compile of
  the reviewed source once the CBOR metadata trailer is
  accounted for (metadata-stripped sha256
  `368cb234ff6e4d2d6b5ba6e8d5450245d671e45b8829d82ca9b26f42e25cba0a`;
  full hashes differ only in the 32-byte ipfs hash inside the
  metadata trailer, because the deployed bytecode was compiled
  from round-19 source and the reviewed source carries the
  round-20 comment-only note). `MockUSDC` matches fully as a
  control case. Compiler: solc 0.8.24, optimizer off, EVM Cancun.
- **Blockscout verification:** both contracts verified
  ("Partial Match" — the metadata reason above) on the HSK
  testnet explorer, Oct 28, 2026:
  - AgentEscrow
    `0xAB70612F45d9cf914D129b0DB71DE243dD55813C`
  - MockUSDC
    `0xEF346652eeB233662E7d290d222175895d53ef15`
- **Live testnet demo (round 19+20 deployment, chain 133):**
  release 50 mUSDC, timeout refund 20 mUSDC, dispute resolved to
  agent 30 mUSDC, both stranger guards reverted on-chain, all
  five demo jobs terminal, escrow balance exactly 0, final
  `settlementInvariant` reading `(0, 0, 0, true)`.

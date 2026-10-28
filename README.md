# Lamplight Pay — agent-to-agent escrow settlement on HSK Chain

**HSK Chain Horizon Hackathon · India (Mumbai Edition) — Track: Agent Payments & A2A Settlement**
**Prize: $5,000 USDT for this track (of a $10,000 USDT pool)**
**Submission deadline: Nov 1, 2026, 21:30 IST / Nov 2, 00:00 Beijing time · Demo Day Nov 4 · Winners Nov 5**

Built by **Ellis Lamplight** — queenellis2026@gmail.com · GitHub: queenellis2026-hash · X: @EllisLamplight

## The problem

AI agents are starting to hire each other — research, audits, data work — but
there is no honest way for one agent to pay another. Today an agent either
pays up front and hopes, or works first and hopes. There is no escrow, no
receipt, and no recourse when a job goes wrong. That is why agent commerce
stays at demo scale: nobody trusts the settlement layer.

## What this is

Lamplight Pay is a minimal, auditable settlement layer for agent-to-agent work:

1. **Quote (off-chain, x402-style).** The worker agent issues a priced quote:
   service, price, token, network, escrow contract, expiry, nonce — hash-stable
   so both sides can prove they agreed to the same terms.
2. **Fund (on-chain).** The requester funds the job in a stablecoin into the
   `AgentEscrow` contract. Funds are locked, not sent.
3. **Deliver (on-chain).** The worker accepts, does the work, and submits a
   delivery hash (the deliverable itself lives off-chain, content-addressed).
4. **Settle (on-chain).** The requester releases the funds — or, if the
   deadline passes with no delivery, reclaims them. Either side can raise a
   dispute after delivery; whoever the job names as arbiter resolves it
   (release or refund) — the requester by default, or an optional
   arbiter address set at creation. Note: the contract only checks the
   arbiter is neither the payer nor the agent — that does not prove it
   is an independent party, since the payer could name a second wallet
   they control. Since round 14 (Oct 28, 2026) the agent confirms the
   arbiter on-chain at acceptJob: it passes the arbiter it expects and
   the call reverts on a mismatch, so acceptance is an explicit
   agreement to THAT arbiter.
5. **Receipt (off-chain).** Both sides keep a hash-stable settlement receipt:
   who paid whom, how much, for what, on which chain, with the tx hash as proof.

No real funds move anywhere in this build. The demo uses a clearly-labelled
test token (`MockUSDC`, 6 decimals like USDC, freely mintable, testnet only).
The demo scenarios run on a local EVM; the contracts are also deployed live
on HSKChain Testnet (chain ID 133) — see Status below.

## Why this track, not AI Agent Trading

Agent Payments & A2A Settlement is the honest fit: Ellis's actual work is
agent-to-agent payments (bounty payouts, escrow thinking, wallet tooling), and
a trading agent would need real funds, real market risk, and a track record
this wallet (0 ETH, 0 USDC) cannot honestly claim. This build makes no trading
claims and moves no real money.

## HSP (HashKey Settlement Protocol) — mapped, not yet live

This track is defined around HSP: the Payment Agent constructs a Payment
Mandate and HSP's Gateway verifies and executes the on-chain payment
([HSP API docs](https://hashkey-merchant.github.io/#/)). Lamplight Pay maps
onto HSP directly:

- our **quote** is the Payment Mandate — priced, expiring, hash-stable terms
  both sides can prove they agreed to;
- our **escrow release** is the Gateway's verify-and-execute step — funds
  move only when delivery is proven;
- our **receipt** is the settlement proof both sides keep.

No HSP code runs in this build yet: the HSP sandbox is not live (Coordinator
URL, API key, SDK repo and faucet are all placeholders, and the organiser has
not replied to the sandbox-access question). The mapping above is documented
here so the integration is a small step once sandbox access is available.

## Repo layout

```
contracts/
  AgentEscrow.sol   escrow state machine: Created -> Accepted -> Delivered
                    -> Released / Refunded / Cancelled, plus Disputed.
                    Review window enforced: deliveredAt recorded, agent may
                    claim after the window, disputes only inside it, and a
                    disputed job times out to the agent after 7 days.
                    A payout that fails (blocklisted recipient, reverted
                    transfer) is credited as a pull balance instead of
                    reverting the settlement, so a job can never be
                    stranded by a failing token; the agent pulls it with
                    withdraw() or withdrawTo().
  MockUSDC.sol      test-only ERC-20 (6 dp), owner-gated mint
  FeeToken.sol      TEST ONLY 1% fee token (proves funding stores net received)
  NoBoolToken.sol   TEST ONLY USDT-style token (no bool return on transfers)
  BlocklistToken.sol TEST ONLY blocklist token (proves a failed payout
                    credits a pull balance instead of stranding the job)
a2a/
  quote.py          hash-stable quote objects (x402-style)
  receipt.py        hash-stable settlement receipts
scripts/
  compile.py            compile contracts with solc 0.8.24 -> build/
  demo.py               3 end-to-end scenarios on a local EVM, writes receipts
  deploy_hsk_testnet.py deploy to HSK testnet (chain 133) — see below
tests/
  test_flow.py          71 tests: happy path, timeout refund, stranger guard,
                    quote, review-window lifecycle, review-window cap (30
                    days) + boundary, fee/no-bool tokens,
                    cancelUnaccepted, mint access control, blocklisted
                    agent — release and dispute-timeout credit a pull
                    balance, job reaches a terminal state, agent recovers
                    via withdrawTo/withdraw, malformed-return tokens
                    (32-byte value 2, 1-byte return, 10,000-byte return)
                    credit instead of stranding, a 3,000,000-byte
                    return-bomb credits instead of running out of gas,
                    a gas-burning token (mode 5) credits when the release
                    supplies enough gas, a vanished-code token credits
                    instead of marking paid, a lying token (mode 6:
                    returns true, moves nothing) credits instead of
                    marking paid — caught by the balance-delta check in
                    _payOrCredit, which also verifies withdrawals —
                    cross-function
                    reentrancy (hook calling raiseDispute / acceptJob),
                    zero-address agent guard, claimWindows (0, 0) before
                    delivery, the jobWindows combined view, the
                    settlement invariant (escrow balance == unsettled
                    jobs + pending credits), and the on-chain
                    settlementInvariant view (same equation, callable
                    by monitors) plus a second cold-path gas pinning
                    under a non-zero prior credit, and agent-side
                    arbiter confirmation at acceptJob (mismatch reverts,
                    JobAccepted carries the confirmed arbiter)
demo-receipts/          quote + receipts produced by the demo run
```

## Run it (verified Oct 26, 2026)

```bash
python3 -m venv .venv && .venv/bin/pip install web3 eth-tester py-solc-x py-evm pytest
.venv/bin/python scripts/compile.py   # MockUSDC 3,882 B, AgentEscrow 21,918 B
.venv/bin/python scripts/demo.py      # 3 scenarios, all pass
.venv/bin/python -m pytest tests/ -v  # 70 passed
```

Demo result (local EVM, real tx hashes in `demo-receipts/`):
- **A — happy path:** 50 mUSDC job funded → accepted → delivered → released. Agent balance 50.0.
- **B — timeout refund:** 20 mUSDC job, agent never delivers, payer reclaims after the deadline.
- **C — dispute:** 30 mUSDC job delivered, payer disputes, resolves to the agent.
- **Guard:** a stranger's `release()` call reverts.
- Final balances: payer 9,920 / agent 80 / escrow 0 mUSDC. Escrow never keeps funds.

## HSK Chain (verified)

| | |
|---|---|
| HSKChain Testnet | chain ID **133**, RPC https://testnet.hsk.xyz, explorer https://testnet-explorer.hskchain.net |
| HSKChain Mainnet | chain ID **177**, RPC https://mainnet.hsk.xyz |
| Discarded testnet | chain ID 230315 ("HashKey Chain Testnet (discard)") — **do not use** |

## Status / honest limitations

- **Testnet deployment DONE Oct 26, 2026 ~8:21 PM CDT.**
  [AgentEscrow `0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7`](https://testnet-explorer.hskchain.net/address/0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7)
  and [MockUSDC `0x860CadF955CF73FDB8E9ED2979104baae9f833B9`](https://testnet-explorer.hskchain.net/address/0x860CadF955CF73FDB8E9ED2979104baae9f833B9),
  live on HSKChain Testnet (chain ID 133), recorded in
  `build/hsk-testnet-deployment.json`. The deploy script
  (`scripts/deploy_hsk_testnet.py`) checks the chain ID is 133 and takes a
  testnet-only deployer key from `DEPLOYER_KEY`. Honest note: no escrow
  transaction has run against the deployed contracts yet — the demo scenarios
  ran on a local EVM, so the on-chain history is the two deployments only.
- **Demo video DONE Oct 26, 2026.** 28-second walkthrough
  (`build/demo-video.mp4`), Unlisted on YouTube at
  https://youtu.be/GdHNK0fZ0Lo.
- **Submitted Oct 27, 2026 ~11:10 AM CDT.** DoraHacks Build
  https://dorahacks.io/build/50417, status Under Review, track Agent
  Payments & A2A Settlement. Mainnet deployment is still pending (rules:
  no mainnet = forfeits demo selection; winners must be on mainnet to
  claim the prize) — the Build can still be edited before judging.
- **Payer-as-arbiter, now optional.** Disputes are resolved by the payer
  when no arbiter is set — the demo default. Since round 4 (Oct 27,
  2026), `createJob` takes an optional arbiter address: when one is set,
  only the arbiter resolves disputes (it must be neither the payer nor
  the agent), and the payer cannot resolve. If the arbiter goes silent,
  the dispute still times out to the agent, so no arbiter can lock funds
  forever. **Caveat (round 6): "third party" is not guaranteed** — the
  check only compares addresses, so the payer could name a second wallet
  they control. Since round 14 (Oct 28, 2026) the agent confirms the
  arbiter on-chain at acceptJob: it passes the arbiter it expects and
  the call reverts ("arbiter mismatch") on a mismatch, and the
  JobAccepted event records the confirmed arbiter — so a payer can no
  longer name an arbiter the agent never agreed to. **How an
  integrator reads the confirmed arbiter (round 15):** call
  `getJob(jobId)` — the returned Job carries the arbiter in its
  `arbiter` field, which no function mutates after creation — or read
  the `JobAccepted(jobId, agent, arbiter)` event from the logs. No
  dedicated view exists on purpose: getJob plus the event already
  answer the question.
- **Review window (fixed Oct 27, 2026 after independent review).** Three
  reviewers (Claude, Grok, ChatGPT) all found the same gap: `reviewWindow`
  was stored but never enforced, so a silent payer could lock funds forever
  after delivery. Now `submitDelivery` records `deliveredAt`; the payer
  arbitrates during the window; a dispute may only be raised inside it; if
  the payer stays silent past it, the agent may call `release()` and claim;
  a disputed job must be resolved within the window + 7 days, after which
  `settleDisputeTimeout()` releases to the agent. The window itself is
  capped at `MAX_REVIEW_WINDOW` (30 days) in `createJob` — an uncapped
  window would let a payer delay (or, near 2**256 − 1, overflow) the
  agent's claim indefinitely; no floor is set, since a 0 window is a
  legitimate payer choice (instant settlement). The agent's claim is
  strict (`>`): at the exact boundary second the payer's dispute (`<=`)
  still wins, so a last-second dispute can never lose a race to the
  agent's release. `claimWindows()` returns the exact claim and
  dispute-timeout timestamps so callers never re-compute them — and
  before delivery it returns (0, 0), since the window offsets from 0
  would look like 1970 timestamps that have already passed. Funding
  stores what actually arrived (balance before/after, so fee-on-transfer
  tokens cannot make the escrow insolvent), token moves use SafeERC20-style
  calls (USDT-style no-bool tokens work) made in assembly with a 32-byte
  output buffer, and the returndata is inspected with a bounded copy — a
  token returning 32 bytes holding a non-bool value, a wrong-length
  return, or huge returndata can never revert the payout or run it out
  of gas on the copy; the payout is treated as failed and credited
  instead. (Round 6: the bounded copy alone was NOT enough — the
  high-level `token.call(...)` copied the full returndata first, so a
  token returning ~3MB ran the settlement out of gas, proven by the
  return-bomb test: pre-fix, release consumed all 30M gas and reverted.
  The assembly call caps the copy at 32 bytes; post-fix the same release
  costs 17,519,061 gas — the token's own cost to return 3MB — and the
  payout credits. (Round 7: the fix is now pinned with gas-cost
  assertions — a new test measures clean vs credited release gas on the
  cold path and asserts ceilings of 150,000 gas for the small-return
  paths and 19,000,000 for the bomb, so a future solc change cannot
  silently regress the assembly call; the bomb test itself also asserts
  gasUsed ≤ 19,000,000.) A `pendingCredit(token, account)` view (round 8)
  gives front-ends the pull balance directly, and the gas ceilings are
  now documented in the contract's NatSpec as a tripwire for future solc
  upgrades. (Round 9: `_tryTransfer` now refuses a token whose code has
  vanished after funding — a code-less address answers with empty
  success, which the USDT-style rule would read as "paid"; a new
  `VanishingToken` test token proves the release credits instead of
  marking paid, run on a pre-Cancun (Shanghai) chain where SELFDESTRUCT
  still deletes code. A gas-burning token mode (mode 5, infinite loop)
  is pinned too: with a 20M gas limit the release costs 19,695,562 gas
  and credits, with 200k it reverts — a front-end must not hardcode a
  low gas limit. The `pendingCredit` test now uses fresh accounts so it
  no longer depends on earlier tests having withdrawn.) (Round 10:
  `_payOrCredit` — and `withdraw()` / `withdrawTo()` — now verify the
  escrow's balance actually dropped by the payout amount, instead of
  trusting the token's return value: a token that returns true while
  moving nothing (new `MalformedReturnToken` mode 6, the lying token)
  is caught and the payout is credited, never marked paid — proven by
  a test that fails with the check removed. Only the shortfall is
  credited, so the invariant holds: escrow balance == unsettled jobs +
  pending credits, locked in by a dedicated invariant test. A
  `jobWindows()` view returns (deliveredAt, agentClaimAt,
  disputeTimeoutAt, credit) in one call. The gas ceilings are now
  named constants in the tests, the mode-5 path has its own ceiling
  (19,900,000; re-measured 19,697,418), and the exact boundary
  semantics (strict > vs inclusive <=) are documented in the NatSpec
  of release / raiseDispute / resolveDispute / settleDisputeTimeout.)
  (Round 11: a `settlementInvariant(token)` view returns (balance,
  unsettledSum, pendingCreditsSum, holds) so monitors can call the
  balance equation on-chain instead of summing pull balances from
  logs — backed by a new `totalPendingCredits` per-token total,
  maintained wherever `pendingWithdrawals` is written; the
  "tokens move the full amount or nothing" assumption the
  shortfall arithmetic relies on is now stated in the contract's
  top-level NatSpec; and a second cold-path gas pinning under a
  non-zero prior credit (measured 67,784, ceiling
  GAS_CEILING_COLD_PRIOR_CREDIT 140,000) catches a future
  double-credit by its exact credit-sum assertions. The first
  credited release now costs ~99k gas (one more cold SSTORE for
  the per-token total), still well under GAS_CEILING_SMALL.)
  (Round 12: a stray-funds test pins that a direct ERC-20 transfer
  into the escrow — outside createJob — makes `holds` false while
  the other three view values stay exactly correct, and the
  NatSpec now states the O(jobCount) scan is intentional for
  off-chain monitors.) (Round 13: the view's gas is pinned under a
  realistic load — 50 jobs, measured 387,382 gas via
  eth_estimateGas, ceiling GAS_CEILING_INVARIANT_VIEW 800,000 — so
  a future compiler or storage-layout change that turns the view
  expensive is caught; the NatSpec now notes a direct transfer is
  the only intended way `holds` becomes false, and the off-chain
  recipe for the unsettled sum alone is documented.) (Round 14:
  agent-side arbiter confirmation at acceptJob — the agent passes
  the arbiter it expects, the call reverts "arbiter mismatch" on a
  mismatch, and the JobAccepted event carries the confirmed arbiter;
  passing address(0) confirms payer-as-arbiter on a no-arbiter job
  and reverts on a job that has an arbiter. AgentEscrow bytecode
  21,919 B. (Round 15: second gas measurement on the view with a
  non-zero prior credit total — 387,382 gas, identical to the
  pure-unsettled path, same 800,000 ceiling; NatSpec notes the
  50-job figure was measured on eth-tester/PyEVM and will differ on
  a real client; a check-order test pins that a non-agent with a
  deliberately wrong arbiter still reverts only on "not agent"; the
  README documents how an integrator reads the confirmed arbiter
  (getJob + JobAccepted event); acceptJob gas pinned at 53,521 gas
  under GAS_CEILING_ACCEPT_JOB 110,000.) (Round 16: the demo guard
  now runs against live jobs and asserts the revert reason is "not
  payer"; a randomized state-machine test (fixed seed 20261028, 60
  steps, 25 succeeded / 35 reverted) asserts
  settlementInvariant(...).holds after every step across three
  tokens; withdraw / withdrawTo carry a comment stating why the
  strict == is kept instead of the >= that _payOrCredit uses.)
  A failing payout
  leg credits a pull
  balance instead of stranding the job, and `MockUSDC` mint is
  owner-gated. The agent may never be the zero address (its own guard,
  symmetric with the token check). 71 tests cover every new path,
  including the previously untested ones (release while Disputed, both
  resolve directions, early timeout, cancel, window of 0, reentrancy
  through a hook token, cross-function reentrancy through a hook calling
  raiseDispute or acceptJob, and malformed-return tokens in all three
  shapes plus the 3,000,000-byte return bomb, the gas-burning token,
  the vanished-code token, and the lying token — returns true, moves
  nothing, caught by the balance-delta check).
  Full verbatim findings: `reviews-2026-10-27.md`. Note: the
  contracts deployed on HSK testnet (above) are the PRE-fix version —
  redeploy is needed before demo selection for the on-chain code to match
  this source.
- **Eligibility verified:** the hackathon is **online and global**. The
  organiser's Eventbrite listing says "Online event", "An online hackathon in
  India", and "inviting global developers". "Mumbai Edition" is branding, not a
  location requirement. The DoraHacks detail page itself returns HTTP 405 to a
  plain text fetch (JS site), so its rules/FAQ text was read via browser
  instead. Demo Day format (Nov 4) is unverified; assume online unless the
  organisers say otherwise.
- **No KYC, no real funds, no trading.** Nothing here moves real money.

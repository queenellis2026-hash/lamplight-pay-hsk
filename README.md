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

## Run it (verified Oct 28, 2026)

```bash
python3 -m venv .venv && .venv/bin/pip install web3 eth-tester py-solc-x py-evm pytest
.venv/bin/python scripts/compile.py   # MockUSDC 3,882 B, AgentEscrow 21,919 B
.venv/bin/python scripts/demo.py      # 3 scenarios, all pass
.venv/bin/python -m pytest tests/ -v  # 77 passed
```

Demo result (local EVM, real tx hashes in `demo-receipts/`):
- **A — happy path:** 50 mUSDC job funded → accepted → delivered → released. Agent balance 50.0.
- **B — timeout refund:** 20 mUSDC job, agent never delivers, payer reclaims after the deadline.
- **C — dispute:** 30 mUSDC job delivered, payer disputes, resolves to the agent.
- **Guard:** a stranger's `release()` on a live Delivered job and a stranger's
  `refund()` on a refundable job both revert on "not payer" — then both jobs
  settle back to the payer.
- Final balances: payer 9,920 / agent 80 / escrow 0 mUSDC. Escrow never keeps funds.

## HSK Chain (verified)

| | |
|---|---|
| HSKChain Testnet | chain ID **133**, RPC https://testnet.hsk.xyz, explorer https://testnet-explorer.hskchain.net |
| HSKChain Mainnet | chain ID **177**, RPC https://mainnet.hsk.xyz |
| Discarded testnet | chain ID 230315 ("HashKey Chain Testnet (discard)") — **do not use** |

## Status / honest limitations

- **Testnet deployment DONE Oct 28, 2026 ~1:14 AM CDT (round-16 contracts, redeployed; Blockscout-verified).**
  [AgentEscrow `0xF1c84737AAc850546d84C54d60B3b18fF82F8afA`](https://testnet-explorer.hskchain.net/address/0xF1c84737AAc850546d84C54d60B3b18fF82F8afA)
  and [MockUSDC `0x00835c4588461353B4B284437d7D65c466587375`](https://testnet-explorer.hskchain.net/address/0x00835c4588461353B4B284437d7D65c466587375),
  live on HSKChain Testnet (chain ID 133), recorded in
  `build/hsk-testnet-deployment.json`. The deploy script
  (`scripts/deploy_hsk_testnet.py`) checks the chain ID is 133 and takes a
  testnet-only deployer key from `DEPLOYER_KEY`. Honest note: no escrow
  transaction has run against the deployed contracts yet — the demo scenarios
  ran on a local EVM, so the on-chain history is the two deployments only.
- **Demo video DONE Oct 28, 2026 (v4).** 2:05 narrated walkthrough
  (`build/demo-video-v4.mp4`), Unlisted on YouTube at
  https://youtu.be/6lGHXO1dEVM — the three demo scenarios plus the
  round-16 guard checks, with the live round-16 testnet addresses.
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
  `settleDisputeTimeout()` releases to the agent. The window is capped at
  `MAX_REVIEW_WINDOW` (30 days); no floor — a 0 window is a legitimate
  payer choice (instant settlement). The agent's claim is strict (`>`):
  at the exact boundary second the payer's dispute (`<=`) still wins.
  `claimWindows()` returns the exact claim and dispute-timeout timestamps
  (0, 0 before delivery). `jobWindows()` returns (deliveredAt,
  agentClaimAt, disputeTimeoutAt, credit) in one call.
- **Hostile-token handling.** Funding stores what actually arrived
  (balance before/after), so fee-on-transfer tokens cannot make the escrow
  insolvent. Token moves use assembly calls with a 32-byte bounded copy, so
  a token returning a non-bool value, a wrong-length return, or huge
  returndata can never revert the payout or run it out of gas on the copy.
  A failing payout leg credits a pull balance instead of stranding the job
  (fee, no-bool, blocklist, malformed-return, 3,000,000-byte return-bomb,
  gas-burning, vanished-code, and lying tokens are all covered by tests).
  `_payOrCredit` — and `withdraw()` / `withdrawTo()` — verify the escrow's
  balance actually dropped by the payout amount, so a token that returns
  true while moving nothing is caught and credited, never marked paid;
  only the shortfall is credited. A `pendingCredit(token, account)` view
  exposes pull balances directly. `MockUSDC` mint is owner-gated. The
  agent may never be the zero address.
- **Settlement invariant, on-chain.** `settlementInvariant(token)` returns
  (balance, unsettledSum, pendingCreditsSum, holds) so monitors can check
  the balance equation on-chain: escrow balance == unsettled jobs +
  pending credits. A direct ERC-20 transfer into the escrow (outside
  createJob) is the only intended way `holds` becomes false. A randomized
  state-machine test (fixed seed 20261028, 60 steps) asserts the invariant
  holds after every step across three tokens. Gas ceilings are pinned as
  test constants and documented in NatSpec as a tripwire for future solc
  upgrades (invariant view 387,382 gas under an 800,000 ceiling at 50
  jobs; acceptJob 53,521 under 110,000; return-bomb 19,000,000;
  gas-burning path 19,900,000).
- **Tests: 77**, covering every path above (see Repo layout). Full round
  history: `STATUS.md` and `reviews-2026-10-27.md`.
- **Eligibility verified:** the hackathon is **online and global**. The
  organiser's Eventbrite listing says "Online event", "An online hackathon in
  India", and "inviting global developers". "Mumbai Edition" is branding, not a
  location requirement. The DoraHacks detail page itself returns HTTP 405 to a
  plain text fetch (JS site), so its rules/FAQ text was read via browser
  instead. Demo Day format (Nov 4) is unverified; assume online unless the
  organisers say otherwise.
- **No KYC, no real funds, no trading.** Nothing here moves real money.

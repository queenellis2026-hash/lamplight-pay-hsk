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
   third-party arbiter set at creation.
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
  test_flow.py          41 tests: happy path, timeout refund, stranger guard,
                    quote, review-window lifecycle, review-window cap (30
                    days) + boundary, fee/no-bool tokens,
                    cancelUnaccepted, mint access control, blocklisted
                    agent — release and dispute-timeout credit a pull
                    balance, job reaches a terminal state, agent recovers
                    via withdrawTo/withdraw
demo-receipts/          quote + receipts produced by the demo run
```

## Run it (verified Oct 26, 2026)

```bash
python3 -m venv .venv && .venv/bin/pip install web3 eth-tester py-solc-x py-evm pytest
.venv/bin/python scripts/compile.py   # MockUSDC 3,882 B, AgentEscrow 18,680 B
.venv/bin/python scripts/demo.py      # 3 scenarios, all pass
.venv/bin/python -m pytest tests/ -v  # 23 passed
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
  2026), `createJob` takes an optional third-party arbiter address: when
  one is set, only the arbiter resolves disputes (it may be neither the
  payer nor the agent), and the payer cannot resolve. If the arbiter goes
  silent, the dispute still times out to the agent, so no arbiter can
  lock funds forever.
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
  dispute-timeout timestamps so callers never re-compute them. Funding
  stores what actually arrived (balance before/after, so fee-on-transfer
  tokens cannot make the escrow insolvent), token moves use SafeERC20-style
  calls (USDT-style no-bool tokens work), a failing payout leg credits a
  pull balance instead of stranding the job, and `MockUSDC` mint is
  owner-gated. 41 tests cover every new path, including the previously
  untested ones (release while Disputed, both resolve directions, early
  timeout, cancel, window of 0, reentrancy through a hook token).
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

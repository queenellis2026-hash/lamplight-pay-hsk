# Lamplight Pay — agent-to-agent escrow settlement on HSK Chain

**HSK Chain Horizon Hackathon — Track: Agent Payments & A2A Settlement**
**DoraHacks Build:** https://dorahacks.io/build/50417
**Built by Ellis Lamplight**

## What this is

Lamplight Pay is a minimal, auditable settlement layer for agent-to-agent
work. One agent hires another, funds are locked on-chain, delivery is proven
by hash, and both sides keep a receipt — so neither side has to pay up front
and hope, or work first and hope.

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
   (release or refund) — the requester by default, or an optional arbiter
   address set at creation. The agent confirms the arbiter on-chain at
   `acceptJob`: it passes the arbiter it expects and the call reverts on a
   mismatch, so acceptance is an explicit agreement to that arbiter.
5. **Receipt (off-chain).** Both sides keep a hash-stable settlement receipt:
   who paid whom, how much, for what, on which chain, with the tx hash as proof.

A payout that fails (blocklisted recipient, reverted transfer, malformed
token return) is credited as a pull balance instead of reverting the
settlement, so a job can never be stranded by a failing token; the recipient
pulls it with `withdraw()` or `withdrawTo()`.

## Live deployment

HSKChain Testnet, chain ID **133**, RPC https://testnet.hsk.xyz, explorer
https://testnet-explorer.hskchain.net. Both contracts are Blockscout-verified
(partial match — the deployed bytecode was compiled from the same code before
a comment-only note was added to the source; see the build-pinning record in
`build/`).

- AgentEscrow
  [`0xAB70612F45d9cf914D129b0DB71DE243dD55813C`](https://testnet-explorer.hskchain.net/address/0xAB70612F45d9cf914D129b0DB71DE243dD55813C)
- MockUSDC (test token, 6 decimals)
  [`0xEF346652eeB233662E7d290d222175895d53ef15`](https://testnet-explorer.hskchain.net/address/0xEF346652eeB233662E7d290d222175895d53ef15)

Deployment and build-pinning records: `build/hsk-testnet-deployment-round19.json`
and `build/hsk-testnet-deployment-round19-pinning.json`. Earlier testnet
deployments are superseded by this one.

## Try it live

**Live user journey:** https://queenellis2026-hash.github.io/lamplight-pay-hsk/app/

Connect your own wallet (MetaMask or equivalent), switch to HSK testnet
(chain 133), and run the full journey: approve and create a job, accept,
deliver, release, refund, dispute, settle, withdraw — with job state and the
on-chain settlement invariant readable at any time. No backend, no keys
stored, no mainnet support by design. Note: the deployed MockUSDC's `mint`
is deployer-only, so if you do not already hold mUSDC, use the page's custom
token field with any ERC-20 test token you hold on HSK testnet.

## Tests

**85 tests passing** (79 flow + 6 deploy-script), on a local EVM: happy path,
timeout refund, stranger guards, review-window lifecycle and boundaries,
fee / no-bool / blocklist / malformed-return / return-bomb / gas-burning /
vanished-code / lying tokens, reentrancy through hook tokens, hook-window
tests, withdrawal atomicity, the on-chain settlement invariant view, and a
randomized state-machine invariant test.

```bash
python3 -m venv .venv && .venv/bin/pip install web3 eth-tester py-solc-x py-evm pytest
.venv/bin/python scripts/compile.py   # MockUSDC 3,882 B, AgentEscrow 22,778 B
.venv/bin/python scripts/demo.py      # 3 scenarios, all pass
.venv/bin/python -m pytest tests/ -v  # 85 passed
```

Demo result (local EVM, receipts in `demo-receipts/`; the same flows also ran
live against the testnet deployment, escrow ending at 0, settlement invariant
reading (0, 0, 0, true)):

- **A — happy path:** 50 mUSDC job funded → accepted → delivered → released.
- **B — timeout refund:** 20 mUSDC job, agent never delivers, payer reclaims
  after the deadline.
- **C — dispute:** 30 mUSDC job delivered, payer disputes, resolves to the agent.
- **Guards:** a stranger's `release()` and a stranger's `refund()` both revert
  on "not payer".

## Threat model

See [`THREAT_MODEL.md`](THREAT_MODEL.md): roles and trust, the attack surface
with the test pinning each mitigation, two documented transient invariant
windows (createJob funding, failed/partial payout credit — both transient
mid-call reads, never settled breaks), and the accepted limitations. The
contract has no owner, no admin, no pause, and no upgrade path; the deployer
has no post-deploy powers.

## Repo layout

```
contracts/      AgentEscrow.sol, MockUSDC.sol, and test-only adversarial tokens
a2a/            hash-stable quote objects (x402-style) and settlement receipts
scripts/        compile.py (solc 0.8.24), demo.py, deploy_hsk_testnet.py (chain 133 only)
tests/          test_flow.py, test_deploy_script.py
build/          compiled artifacts, deployment + build-pinning records
demo-receipts/  quote + receipts produced by the demo runs
app/            live user journey UI (single page, served via GitHub Pages)
```

## Honest limitations

- **Testnet only. Mainnet readiness is NOT established.** No external audit,
  no formal verification, no mainnet deployment. Mainnet deployment is also
  what the hackathon rules require for demo-selection eligibility and for
  claiming a prize — it waits on funds for gas.
- **No HSP integration yet.** The track is defined around HSP's Payment
  Mandate / Gateway flow; this escrow maps to it (quote = mandate, release =
  verify-and-execute, receipt = settlement proof) and the HSP docs are linked
  ([HSP API docs](https://hashkey-merchant.github.io/#/)), but no HSP code
  runs in this build.
- **Arbiter independence is a documented limitation.** The checks prove the
  arbiter is neither payer nor agent, and the agent confirms the exact arbiter
  at accept — but they prove address separation, not independence: a payer
  could name a second wallet they control. A silent arbiter cannot lock funds
  forever (`settleDisputeTimeout` releases to the agent after the dispute
  period). An arbiter eligibility mechanism would be a new trust layer, not
  a fix, and is out of scope here.
- **Unsupported token classes:** rebasing tokens, sender-side fee tokens, and
  partial-transfer tokens (see `THREAT_MODEL.md`).
- **No KYC, no real funds, no trading.** Nothing here moves real money, and
  job data (parties, amounts, delivery hashes, metadata URIs) is public
  on-chain.

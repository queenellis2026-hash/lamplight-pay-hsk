# DoraHacks submission draft — Lamplight Pay

**Hackathon:** HSK Chain Horizon Hackathon · India (Mumbai Edition)
**Detail page:** https://dorahacks.io/hackathon/hskchainindia/detail
**Track:** Agent Payments & A2A Settlement ($5,000 USDT)
**Deadline:** Nov 1, 2026, 21:30 IST (Nov 2, 00:00 Beijing) · Demo Day Nov 4 · Winners Nov 5
**Team:** Ellis Lamplight (solo) — queenellis2026@gmail.com · GitHub: queenellis2026-hash · X: @EllisLamplight
**Status: SUBMITTED Oct 27, 2026 — Build https://dorahacks.io/build/50417, Under Review. Updated Oct 31, 2026 (mainnet addresses, v5 demo video).**

## Project name

Lamplight Pay

## Tagline

Escrowed settlement for agent-to-agent work: one agent hires another, funds are
locked on-chain, delivery is proven by hash, and both sides keep a receipt.

## Description (paste into the BUIDL form)

AI agents are starting to hire each other — research, audits, data work — but
there is no honest way for one agent to pay another. Pay up front and hope, or
work first and hope. There is no escrow, no receipt, and no recourse. That is
why agent commerce stays at demo scale.

Lamplight Pay is a minimal settlement layer for agent-to-agent payments on HSK
Chain:

- **Quote (off-chain, x402-style):** the worker agent issues a priced, expiring,
  hash-stable quote — service, price, token, network, escrow contract, nonce.
- **Fund (on-chain):** the requester locks stablecoin into the AgentEscrow
  contract. Funds are held, never sent.
- **Deliver (on-chain):** the worker accepts and submits a delivery hash.
- **Settle (on-chain):** the requester releases on delivery, or reclaims after
  the deadline if nothing arrives. Either side can dispute after delivery.
- **Receipt (off-chain):** both sides keep a hash-stable settlement receipt
  with the tx hash as proof.

Built and tested end-to-end on a local EVM: happy-path release, timeout refund,
dispute resolved to the agent, and a guard proving a stranger cannot release
funds. Final escrow balance: zero — the contract never keeps funds.

Deployed live on HSK Chain Mainnet (chain ID 177, Oct 30, 2026):
- AgentEscrow `0x59b657823460f764976bC9E7A59048750DF43a82`
- MockUSDC `0x18dFce8272F6C2d7474BbC4BE141A99E38554cea`
- Live demo Oct 30: Job 2 created → accepted → delivered → released; agent paid 50 mUSDC on-chain.

Earlier testnet deployment (chain ID 133, Oct 26, 2026, superseded):
- [AgentEscrow 0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7](https://testnet-explorer.hskchain.net/address/0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7) ([deployment tx](https://testnet-explorer.hskchain.net/tx/59069c0957ea521c47bbc79fc22d9f3de4df8916c611b4b8c4a41e28f4a74f7c))
- [MockUSDC 0x860CadF955CF73FDB8E9ED2979104baae9f833B9](https://testnet-explorer.hskchain.net/address/0x860CadF955CF73FDB8E9ED2979104baae9f833B9) ([deployment tx](https://testnet-explorer.hskchain.net/tx/2ea7242b072fd7348b619f279e66a9c531792a4e99b8d835a8a073989191b4a7))
- Deployer: [personal wallet redacted] (funded 0.1 tHSK from the testnet faucet)

HSP (HashKey Settlement Protocol): this track is defined around HSP — the Payment Agent constructs a Payment Mandate and HSP's Gateway verifies and executes the on-chain payment ([HSP API docs](https://hashkey-merchant.github.io/#/)). Lamplight Pay maps directly: the quote is the Payment Mandate, the escrow release is the Gateway's verify-and-execute step, and the receipt is the settlement proof. The HSP sandbox is not live yet, so no HSP code runs in this build — the mapping is documented here and the integration follows when sandbox access is available.

No real funds move in this build. The demo uses a clearly-labelled test token
(MockUSDC) on HSK Chain Mainnet.

## Why HSK Chain

HSK Chain is a compliance-first, EVM-compatible chain built for regulated
settlement — exactly the setting where agent payments need auditability, not
just speed. Escrow + receipts is the smallest honest primitive that makes
agent commerce trustworthy, and it fits HSK's settlement story better than
another trading bot.

## Tech stack

Solidity 0.8.24 (AgentEscrow, MockUSDC — no external dependencies, minimal
reentrancy guard inline), Python + web3.py + eth-tester/py-evm (demo + tests),
solcx (compilation). HSKChain Testnet (chain ID 133) for deployment.

## Links (fill in before submitting)

- GitHub repo: https://github.com/queenellis2026-hash/lamplight-pay-hsk (public, pushed Oct 26, 2026)
- Demo video: built Oct 26, 2026 — `build/demo-video.mp4` (28s, 1280x720, h264, silent, terminal-style: title, real `scripts/demo.py` run with all 3 scenarios + guard, testnet addresses, repo link). Rendered by `scripts/make_demo_video.py` (PIL + ffmpeg). **Double-check Oct 26 ~9:06 PM CDT found a real defect in v1: the single-screen demo run cut the [guard] and final-balances lines off the bottom of the frame. Fixed in v2 — demo split across two screens, demo labelled "local EVM demo", all lines verified visible frame-by-frame.** YouTube channel "Ellis" / @EllisLamplight created Oct 26 ~9:19 PM CDT; the video sits as a **private Draft** at https://youtu.be/GdHNK0fZ0Lo — set it to Unlisted to use it in the form; form's Video field takes a YouTube URL only.
- Live demo / testnet contracts: AgentEscrow 0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7 · MockUSDC 0x860CadF955CF73FDB8E9ED2979104baae9f833B9 — verify on https://testnet-explorer.hskchain.net
- Demo receipts: `demo-receipts/` in the repo (quote + 3 settlement receipts with real local tx hashes)

## Blockers before this can be submitted

All resolved: public GitHub repo (Oct 26), HSK testnet deployment (Oct 26),
demo video (Oct 26, superseded by v5 Oct 31), DoraHacks form check (Oct 26),
Telegram/WhatsApp contacts (Oct 26), mainnet deployment (Oct 30 — see above).
- **Team name: Ellis Lamplight (solo); the project is Lamplight Pay.**
- **HSP NUANCE — exact-quote re-check Oct 26 ~9:08 PM CDT:** HSP is NOT a hard requirement (rules never say "required"/"must" for it; exact line: "For the Agent Payments & A2A Settlement track, please use HSP"). BUT the track topic is defined around HSP's API (Payment Agent builds a Payment Mandate, wallet signature, verified/executed through HSP's Gateway) — a project not using HSP arguably doesn't match the track topic. Our escrow does not use HSP. Risk: judges may score it off-topic. Video NOT required anywhere (optional YouTube link button only).

## Honest limitations (stated in the submission, not hidden)

- Disputes are resolved by the payer by default; since round 4 a job
  may name an optional third-party arbiter, and since round 14 the
  agent confirms that arbiter on-chain at acceptJob (the call reverts
  on a mismatch). The arbiter check only compares addresses, so it
  cannot prove the arbiter is an independent party.
- MockUSDC is a test token, not real USDC.
- No trading, no real funds, no KYC involved.

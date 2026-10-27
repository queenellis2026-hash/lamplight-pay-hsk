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
- Demo scenarios: 3/3 pass on a local EVM; `pytest` 4 passed. Receipts in `demo-receipts/`.
- Demo video: 28s, Unlisted — https://youtu.be/GdHNK0fZ0Lo.
- Submitted Oct 27, 2026: https://dorahacks.io/build/50417 — status Under Review. The Build can still be edited before judging.

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

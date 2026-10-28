# Lamplight Pay — Live User Journey UI

A single self-contained page that lets you run the full escrow journey
against the live HSK testnet deployment with your own wallet. See the root
[`README.md`](../README.md) for what Lamplight Pay is, the live deployment,
the test suite, and the honest limitations.

**Live page:** https://queenellis2026-hash.github.io/lamplight-pay-hsk/app/

Open that URL in a browser with an injected wallet (MetaMask or equivalent).
The page enforces HSK testnet (chain 133) and refuses every other chain.
Note: the deployed MockUSDC's `mint` is deployer-only — if you do not
already hold mUSDC, use the page's custom token field with any ERC-20 test
token you hold on HSK testnet.

Threat model: see [`../THREAT_MODEL.md`](../THREAT_MODEL.md).

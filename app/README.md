# Lamplight Pay — Live User Journey UI

A single self-contained page that lets a judge run the full escrow
journey against the **live HSK testnet deployment** with their own
wallet. No build step, no backend, no keys stored anywhere — the
page loads ethers from a public CDN and talks to the chain through
the wallet's injected provider.

## Open it

Open `index.html` directly in a browser with an injected wallet
(MetaMask or equivalent). It must be served over `http(s)://` or
opened as a local file — either works, since all chain access goes
through the wallet. No install, no server, no configuration.

## Network (enforced)

- HSK Chain Testnet, chain ID **133** (`0x85`)
- RPC: `https://testnet.hsk.xyz`
- Explorer: `https://testnet-explorer.hskchain.net`
- Native currency: tHSK (18 decimals)

The page **refuses any other chain**: every read and transaction
checks the chain first and stops with an error if it is not 133.
Use the "Switch / add HSK testnet" button to add the network to
your wallet. You need a small amount of tHSK for gas (testnet
faucet).

## Contracts (live deployment, round 19+20 code)

- AgentEscrow:
  `0xAB70612F45d9cf914D129b0DB71DE243dD55813C`
- MockUSDC (test token):
  `0xEF346652eeB233662E7d290d222175895d53ef15`

Both are Blockscout-verified (partial match) on the testnet
explorer. Every transaction the page sends shows its hash with a
Blockscout link in the Activity log, and revert reasons are shown
readably.

## The journey

1. Connect wallet, switch to HSK testnet.
2. Token: the default is the deployed MockUSDC (6 decimals).
3. Approve the escrow, then create a job: agent address, amount,
   deadline (seconds), review window (seconds, max 30 days),
   metadata URI, optional arbiter (blank = payer resolves).
4. As the agent wallet: accept (confirming the expected arbiter),
   then submit delivery (text is hashed with keccak256, or paste
   a raw bytes32 hash).
5. As the payer: release, or refund after the deadline, or cancel
   before accept. As either party: raise a dispute inside the
   review window. As the arbiter (or payer when no arbiter is
   set): resolve the dispute to the agent or back to the payer.
   After the dispute period: settle the timeout.
6. Pull any failed-payout credit with withdraw, or withdrawTo
   when the credited address is blocklisted.
7. Check the views any time: job state and windows,
   `settlementInvariant` (balance / unsettled / credits /
   holds), and pull credits.

## Test-token note — please read

**The deployed MockUSDC's `mint` is deployer-only.** Only the
deploying wallet can mint it, so you cannot mint mUSDC yourself
from this page — the Mint button is included for the deployer
only and will revert for everyone else (the revert reason is
shown in the log).

If you do not already hold mUSDC, the journey still works:

- Paste **any ERC-20 test token you hold on HSK testnet** into
  the Token field and click "Use this token" (for example, a
  token you deployed yourself for testing). The escrow accepts
  any ERC-20; it does not require mUSDC specifically. Set the
  decimals field to match your token (the page reads decimals
  and symbol from the token when it can).
- The token's decimals are used to convert the human-unit amounts
  you type, so set them correctly or the amounts will be wrong.

## What is NOT in this page

- No private keys, no funded accounts, no backend, no analytics.
- No mainnet support by design (chain 133 is enforced).
- No HSP integration yet — the escrow maps to the HSP
  mandate/gateway flow, but no HSP code runs in this build.
- The page does not hide revert reasons: a failed transaction
  shows the contract's revert string (e.g. `"not payer"`,
  `"review window ended"`, `"withdrawal failed"`).

## Threat model

See `../THREAT_MODEL.md` for roles and trust, the attack surface
with the test that pins each mitigation, the two documented
transient invariant windows, and the accepted limitations
(arbiter independence, unsupported token classes, testnet-only).

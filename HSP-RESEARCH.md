# HSP research — Oct 26, 2026 ~9:19 PM CDT (browser, read-only)

Sources: HashKey Merchant docs (https://hashkey-merchant.github.io/),
HashFans HSP guide (https://hashfans.io/docs?id=HSP — "Building on HSP —
Developer Guide"), HashFans Network Info.

## Two different "HSP"s — do not mix them

- **HSP = HashKey Settlement Protocol** (track-relevant): hackathon, pre-1.0,
  verifiable settlement layer for stablecoin payments. SDK (@hsp/sdk), MCP
  server (@hsp/mcp), hosted Coordinator. No merchant checkout.
- **HashKey Merchant** (production gateway): REST API + hosted checkout,
  aligned to AP2/x402, production host hsp.hashkey.com (why the names blur).
  Needs a merchant account via an operations invite — no self-service signup.

## What HSP (Settlement Protocol) is

Zero-custody, verifiable settlement: payer signs an intent (EIP-712 mandate:
pay this much of this token to this recipient on this chain, meeting these
requirements), pays on-chain from their own wallet, and anyone can re-check
cryptographic evidence the payment happened. It does not hold funds, does not
escrow, and does not judge delivery. For agentic commerce, paid APIs/x402
paywalls, compliant settlement.

## How it integrates

SDK-first: `pay()` builds the mandate → payer signs (EIP-712) → registers
with the Coordinator → payer's wallet broadcasts the ERC-20 transfer →
Coordinator observes → returns a handle; `verify()` checks
(mandate, receipt, attestations) independently. MCP route is thinner for an
agent payer (hsp_quote → approval → hsp_pay, SpendGuard-bounded).

## Effort to add to Lamplight Pay — small wrapper, NOT a rebuild

Keep the escrow contract and release/refund logic untouched; add a thin
layer: (a) build the mandate from the off-chain quote, escrow contract as
recipient; (b) await settlement; (c) verify independently; (d) call the
existing escrow release on delivery. Gap: neither HSP nor Merchant enforces
delivery — delivery proof, dispute/refund, release timing stay in our escrow.

## The blocker — cannot integrate today

The HSP sandbox is NOT live in the guide: Coordinator URL, per-team API key,
SDK repo URL and faucet are placeholders — "shared once the sandbox has been
deployed, typically a few days later. Until then, use this guide to plan."
SDK is "not yet on npm". There is nothing to code against right now.

Merchant route is worse for us: operations invite + org registration
(org name, admin email, ES256K public key, service_rate, supported chains)
before any app_key/app_secret — not feasible before Nov 1 without the
organizer's help.

## Testnet / fees

Testnet (chain 133) supported in both once the sandbox is up; HSP testnet
funds free via organizer faucet. No published pricing in either doc (Merchant
has a per-merchant service_rate field, rate undisclosed).

## Self-host check — verified Oct 26 ~9:27 PM CDT (exact-phrase search of the full guide)

NO — teams are NOT supposed to build/run their own sandbox/Coordinator.
Guide opening: "You do not need to run any infrastructure. The organizer
hosts a shared sandbox; you point the SDK at it and pay." No matches for
"run your own", "self-host", "your own Coordinator", "deploy your own".
The devkit (§7) is for building your own settlement *adapter*, which is then
submitted to the organizer "to be registered in the sandbox Coordinator's
trust set" — not run as your own Coordinator. No Coordinator source code,
repo URL, or deployment instructions exist in the guide at all; the only
repo mentioned is the SDK repo, as a placeholder with no URL. The "your own"
things in the guide are your own wallet, your own verifier run, and your own
Node toolchain — none is a Coordinator.

## What this means for the submission

- The track topic is defined around HSP, but HSP itself is unusable until the
  organizer publishes the sandbox. We cannot honestly claim HSP integration
  today.
- Honest options: (a) submit the testnet escrow as-is and state HSP
  integration as planned once the sandbox lands; (b) wait for the sandbox
  (days — deadline Nov 1, risky); (c) ask the organizer for sandbox
  access/keys now.

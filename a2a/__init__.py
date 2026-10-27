"""Lamplight Pay — A2A (agent-to-agent) payment protocol layer.

Off-chain, chain-agnostic. The on-chain half is AgentEscrow (contracts/).
Flow, modelled on the x402 pattern (HTTP 402 quote -> pay -> retry):
  1. requester asks a worker agent for priced work
  2. worker returns a Quote (price, token, network, escrow, expiry, nonce)
  3. requester funds the escrow job (on-chain createJob) and hands back the job id
  4. worker accepts, delivers (delivery hash on-chain), requester releases
  5. both sides keep the Receipt — a signed, hash-stable record of the settlement
No real funds move in this demo: amounts are test mUSDC on a local chain.
"""

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AgentEscrow — escrowed settlement for agent-to-agent work.
/// @notice Lamplight Pay (HSK Chain Horizon Hackathon, Agent Payments & A2A
/// Settlement track). A payer (human or agent) funds a job in an ERC-20
/// stablecoin; the worker agent accepts, delivers (hash of the deliverable),
/// and the payer releases. If the agent never delivers by the deadline the
/// payer can reclaim. Either side can raise a dispute; whoever the job
/// names as arbiter resolves it — the payer by default, or an optional
/// arbiter address set at creation. The arbiter must be neither the payer
/// nor the agent — but that check only compares addresses: it cannot
/// prove the arbiter is an independent party, since the payer could set
/// a second wallet they control. The agent should read the job's arbiter
/// before accepting and only take jobs whose arbiter it trusts; making
/// the agent confirm the arbiter is a v2 feature, not in this contract.
/// If the arbiter is set and goes silent, the dispute still times out to
/// the agent via settleDisputeTimeout(), so no arbiter can lock funds
/// forever either.
/// @dev Review-window lifecycle (REVISED Oct 27, 2026 after independent
/// review by Claude, Grok and ChatGPT — see reviews-2026-10-27.md):
///   - submitDelivery records deliveredAt. The payer may release at any
///     time while the job is Delivered; the payer is the arbiter DURING
///     the review window (deliveredAt .. deliveredAt + reviewWindow).
///   - A dispute may only be raised INSIDE that window; after it, raiseDispute
///     reverts, so a payer cannot sit on a delivered job and dispute it
///     months later.
///   - If the payer stays silent past the window and no dispute was raised,
///     the AGENT may call release() and claim the funds — a silent payer
///     can no longer lock the funds forever.
///   - A disputed job must be resolved by the job's arbiter within the
///     dispute period (review window + DISPUTE_PERIOD, 7 days). After that,
///     either party may call settleDisputeTimeout(), which releases to the
///     agent: delivered work gets paid unless the arbiter acts in time. No
///     arbitrator in v1 — that is a stated limitation, not an oversight.
/// @dev Funding measures what actually arrived: createJob compares the
///   escrow's token balance before and after transferFrom and stores the
///   received amount, so fee-on-transfer / rebasing tokens cannot make the
///   escrow insolvent by recording more than it holds.
/// @dev All token moves use SafeERC20-style low-level calls that accept an
///   empty return value, so USDT-style tokens (no bool return) work.
/// @dev Payouts are PULL on failure. release / refund / cancel / dispute
///   settlement first try a direct token transfer; if that fails — the
///   token blocklists the recipient, or otherwise refuses the payout leg
///   — the amount is credited to a pull balance instead and the job still
///   reaches its terminal state, so a failing transfer can never strand a
///   job. The recipient pulls the credit later with withdraw(), or to a
///   different address with withdrawTo() (added Oct 27, 2026: a credit to
///   a blocklisted address can never be pulled to itself, so withdrawTo()
///   is the only recovery path). Funding (createJob) still reverts on a
///   failed transferFrom — a job that was never funded must not exist.
/// @dev Minimal reentrancy guard included; no external dependencies.
interface IERC20 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract AgentEscrow {
    enum State { Created, Accepted, Delivered, Disputed, Released, Refunded, Cancelled }

    struct Job {
        address payer;
        address agent;
        address token;
        uint256 amount;
        uint256 deadline;
        uint256 reviewWindow; // seconds after delivery during which payer may dispute
        State state;
        bytes32 deliveryHash;
        string metadataURI; // off-chain job spec / quote id
        uint256 deliveredAt; // timestamp of submitDelivery; 0 until delivered
        address arbiter; // optional dispute resolver; address(0) = the payer.
        // "Third party" is NOT guaranteed: the check only excludes the
        // payer's and agent's own addresses (see createJob).
    }

    /// @dev Dispute period after the review window ends: the payer must
    ///   resolve a dispute within it; after it, settleDisputeTimeout()
    ///   releases to the agent. 7 days, matching the Arc escrow's window.
    uint256 public constant DISPUTE_PERIOD = 7 days;

    /// @dev Upper bound on the review window a payer may set in createJob.
    ///   Without a cap, a huge window (or one near 2**256 - 1, which overflows
    ///   deliveredAt + reviewWindow) would let a silent payer lock the agent's
    ///   claim indefinitely — the exact lock the review window was added to
    ///   prevent. 30 days is the longest review a job may carry.
    ///   No lower bound is set: a window of 0 is a legitimate payer choice
    ///   (instant settlement, no review period); it helps the agent, not
    ///   hurts them, so there is nothing to protect with a floor.
    uint256 public constant MAX_REVIEW_WINDOW = 30 days;

    uint256 public jobCount;
    mapping(uint256 => Job) public jobs;

    /// @dev Pull balances: token => account => amount credited when a
    ///   payout leg failed (see _payOrCredit). Keyed by token because a
    ///   job's token varies; a recipient may hold credits in several.
    mapping(address => mapping(address => uint256)) public pendingWithdrawals;

    event JobCreated(uint256 indexed jobId, address indexed payer, address indexed agent, address token, uint256 amount, uint256 deadline, string metadataURI, address arbiter);
    event JobAccepted(uint256 indexed jobId, address indexed agent);
    event DeliverySubmitted(uint256 indexed jobId, bytes32 deliveryHash);
    event JobReleased(uint256 indexed jobId, address indexed agent, uint256 amount);
    event JobRefunded(uint256 indexed jobId, address indexed payer, uint256 amount);
    event JobCancelled(uint256 indexed jobId);
    event JobCancelledUnaccepted(uint256 indexed jobId);
    event DisputeRaised(uint256 indexed jobId, address indexed by);
    event DisputeResolved(uint256 indexed jobId, bool releasedToAgent);
    event DisputeTimedOut(uint256 indexed jobId, address indexed agent, uint256 amount);
    event Credited(address indexed token, address indexed account, uint256 amount);
    event Withdrawn(address indexed token, address indexed account, address to, uint256 amount);

    bool private _locked;
    modifier nonReentrant() {
        require(!_locked, "reentrant");
        _locked = true;
        _;
        _locked = false;
    }
    modifier onlyPayer(uint256 jobId) {
        require(jobs[jobId].payer == msg.sender, "not payer");
        _;
    }
    modifier onlyAgent(uint256 jobId) {
        require(jobs[jobId].agent == msg.sender, "not agent");
        _;
    }

    /// @notice Fund a job. Payer must have approved `amount` of `token` first.
    /// @dev The stored amount is what actually arrived (balance before/after),
    ///   so a fee-on-transfer token funds the job with the net amount only.
    /// @dev The review window is capped at MAX_REVIEW_WINDOW (30 days): an
    ///   uncapped window would let the payer delay (or, near 2**256 - 1,
    ///   overflow) the agent's claim indefinitely.
    /// @dev `arbiter` is optional: address(0) means the payer resolves
    ///   disputes, as before. A set arbiter must be neither the payer nor
    ///   the agent — but that is only an address comparison, not a proof
    ///   of independence: the payer could name a second wallet they
    ///   control. The agent should read the job's arbiter before
    ///   accepting and only take jobs whose arbiter it trusts. Only the
    ///   arbiter may resolve when one is set.
    /// @param arbiter Optional dispute resolver (address(0) = payer).
    function createJob(
        address agent,
        address token,
        uint256 amount,
        uint256 deadlineSeconds,
        uint256 reviewWindowSeconds,
        string calldata metadataURI,
        address arbiter
    ) external nonReentrant returns (uint256 jobId) {
        require(token != address(0), "zero address");
        require(agent != address(0), "zero address agent");
        require(agent != msg.sender, "payer cannot be agent");
        require(arbiter != msg.sender, "arbiter cannot be payer");
        require(arbiter != agent, "arbiter cannot be agent");
        require(amount > 0, "amount zero");
        require(deadlineSeconds > 0, "deadline zero");
        require(reviewWindowSeconds <= MAX_REVIEW_WINDOW, "review window too long");
        uint256 balanceBefore = IERC20(token).balanceOf(address(this));
        _safeTransferFrom(token, msg.sender, amount);
        uint256 received = IERC20(token).balanceOf(address(this)) - balanceBefore;
        require(received > 0, "no funds received");

        jobId = jobCount++;
        jobs[jobId] = Job({
            payer: msg.sender,
            agent: agent,
            token: token,
            amount: received,
            deadline: block.timestamp + deadlineSeconds,
            reviewWindow: reviewWindowSeconds,
            state: State.Created,
            deliveryHash: bytes32(0),
            metadataURI: metadataURI,
            deliveredAt: 0,
            arbiter: arbiter
        });
        emit JobCreated(jobId, msg.sender, agent, token, received, block.timestamp + deadlineSeconds, metadataURI, arbiter);
    }

    function acceptJob(uint256 jobId) external onlyAgent(jobId) {
        Job storage job = jobs[jobId];
        require(job.state == State.Created, "not created");
        require(block.timestamp <= job.deadline, "deadline passed");
        job.state = State.Accepted;
        emit JobAccepted(jobId, msg.sender);
    }

    function submitDelivery(uint256 jobId, bytes32 deliveryHash) external onlyAgent(jobId) {
        Job storage job = jobs[jobId];
        require(job.state == State.Accepted, "not accepted");
        require(block.timestamp <= job.deadline, "deadline passed");
        require(deliveryHash != bytes32(0), "empty delivery hash");
        job.state = State.Delivered;
        job.deliveryHash = deliveryHash;
        job.deliveredAt = block.timestamp;
        emit DeliverySubmitted(jobId, deliveryHash);
    }

    /// @notice Release funds to the agent after delivery.
    /// @dev The payer may release at any time while Delivered (payer is the
    ///   arbiter during the review window). After the review window ends
    ///   (deliveredAt + reviewWindow) with no dispute raised, the AGENT may
    ///   also release and claim — a silent payer cannot lock funds forever.
    /// @dev Boundary semantics: the agent's claim is STRICT
    ///   (block.timestamp > deliveredAt + reviewWindow). At exactly
    ///   deliveredAt + reviewWindow the claim reverts and the payer's
    ///   dispute (raiseDispute, <=) still wins, so a last-second dispute
    ///   can never lose a race to the agent's release. One second later
    ///   the claim succeeds. The payer's release has no window check —
    ///   the payer may release at any time while Delivered.
    function release(uint256 jobId) external nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Delivered, "not delivered");
        if (msg.sender == job.agent) {
            require(
                block.timestamp > job.deliveredAt + job.reviewWindow,
                "review window not ended"
            );
        } else {
            require(msg.sender == job.payer, "not payer");
        }
        job.state = State.Released;
        _payOrCredit(job.token, job.agent, job.amount);
        emit JobReleased(jobId, job.agent, job.amount);
    }

    /// @notice Payer reclaims funds if the deadline passed with no delivery.
    function refundAfterDeadline(uint256 jobId) external onlyPayer(jobId) nonReentrant {
        Job storage job = jobs[jobId];
        require(
            job.state == State.Created || job.state == State.Accepted,
            "cannot refund in this state"
        );
        require(block.timestamp > job.deadline, "deadline not passed");
        job.state = State.Refunded;
        _payOrCredit(job.token, job.payer, job.amount);
        emit JobRefunded(jobId, job.payer, job.amount);
    }

    /// @notice Payer cancels before the agent accepts; funds return at once.
    function cancel(uint256 jobId) external onlyPayer(jobId) nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Created, "only before accept");
        job.state = State.Cancelled;
        _payOrCredit(job.token, job.payer, job.amount);
        emit JobCancelled(jobId);
    }

    /// @notice Named exit when the agent never accepts: payer reclaims a
    ///   still-Created job after its deadline. Distinct from the generic
    ///   refundAfterDeadline (which also covers Accepted jobs and moves the
    ///   job to Refunded); this one names the unaccepted-agent case and
    ///   moves the job to the terminal Cancelled state.
    function cancelUnaccepted(uint256 jobId) external onlyPayer(jobId) nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Created, "not created");
        require(block.timestamp > job.deadline, "deadline not passed");
        job.state = State.Cancelled;
        _payOrCredit(job.token, job.payer, job.amount);
        emit JobCancelledUnaccepted(jobId);
    }

    /// @notice Either party raises a dispute — only INSIDE the review window.
    /// @dev After deliveredAt + reviewWindow, raiseDispute reverts: the
    ///   window is the payer's chance to object, not an open-ended right.
    /// @dev Boundary semantics: the dispute window is INCLUSIVE
    ///   (block.timestamp <= deliveredAt + reviewWindow). At exactly
    ///   deliveredAt + reviewWindow the dispute still succeeds — the
    ///   window's last second belongs to the disputer, and the agent's
    ///   claim (strict >) cannot take it. One second later the window
    ///   has ended and raiseDispute reverts.
    function raiseDispute(uint256 jobId) external {
        Job storage job = jobs[jobId];
        require(msg.sender == job.payer || msg.sender == job.agent, "not a party");
        require(job.state == State.Delivered, "only after delivery");
        require(
            block.timestamp <= job.deliveredAt + job.reviewWindow,
            "review window ended"
        );
        job.state = State.Disputed;
        emit DisputeRaised(jobId, msg.sender);
    }

    /// @notice The job's arbiter resolves a dispute: true = pay the agent,
    ///   false = refund. Who the arbiter is depends on the job: the optional
    ///   arbiter address set at creation, or the payer when none was set
    ///   (the demo default — the payer-as-arbiter limitation, kept for
    ///   no-arbiter jobs). A set arbiter is not guaranteed independent (see
    ///   createJob): the agent should have checked it before accepting.
    ///   The arbiter resolves; it cannot raise a dispute (only the parties
    ///   may) and cannot release (only payer/agent may).
    /// @dev Must be called within the dispute period (review window +
    ///   DISPUTE_PERIOD after delivery); after that, settleDisputeTimeout()
    ///   is the only exit, so a dispute cannot lock funds forever — even
    ///   if the arbiter goes silent.
    /// @dev Boundary semantics: resolution is INCLUSIVE
    ///   (block.timestamp <= deliveredAt + reviewWindow + DISPUTE_PERIOD).
    ///   At exactly the dispute-timeout second the arbiter may still
    ///   resolve; one second later only settleDisputeTimeout() is open.
    function resolveDispute(uint256 jobId, bool releaseToAgent) external nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Disputed, "not disputed");
        if (job.arbiter != address(0)) {
            require(msg.sender == job.arbiter, "not arbiter");
        } else {
            require(msg.sender == job.payer, "not payer");
        }
        require(
            block.timestamp <= job.deliveredAt + job.reviewWindow + DISPUTE_PERIOD,
            "dispute period ended"
        );
        if (releaseToAgent) {
            job.state = State.Released;
            _payOrCredit(job.token, job.agent, job.amount);
            emit JobReleased(jobId, job.agent, job.amount);
        } else {
            job.state = State.Refunded;
            _payOrCredit(job.token, job.payer, job.amount);
            emit JobRefunded(jobId, job.payer, job.amount);
        }
        emit DisputeResolved(jobId, releaseToAgent);
    }

    /// @notice Exit for a dispute the payer raised and then abandoned: after
    ///   the dispute period ends, either party may settle it, releasing the
    ///   funds to the agent. Delivered work gets paid unless the payer acts
    ///   in time; a payer cannot dispute, go silent, and keep the money.
    /// @dev Boundary semantics: the timeout is STRICT
    ///   (block.timestamp > deliveredAt + reviewWindow + DISPUTE_PERIOD).
    ///   At exactly the dispute-timeout second settleDisputeTimeout()
    ///   reverts and only resolveDispute() is open; one second later
    ///   the timeout settles to the agent.
    function settleDisputeTimeout(uint256 jobId) external nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Disputed, "not disputed");
        require(msg.sender == job.payer || msg.sender == job.agent, "not a party");
        require(
            block.timestamp > job.deliveredAt + job.reviewWindow + DISPUTE_PERIOD,
            "dispute period not ended"
        );
        job.state = State.Released;
        _payOrCredit(job.token, job.agent, job.amount);
        emit JobReleased(jobId, job.agent, job.amount);
        emit DisputeResolved(jobId, true);
        emit DisputeTimedOut(jobId, job.agent, job.amount);
    }

    /// @notice Withdraw the caller's pending credit for a token.
    /// @dev Credits arise when a payout leg failed (see _payOrCredit).
    ///   A failed withdrawal reverts and preserves the credit.
    /// @dev ROUND 10 (Oct 27, 2026): the withdrawal is verified against
    ///   the escrow's balance, the same way _payOrCredit verifies a
    ///   payout (see its note). A token that returns true (or empty)
    ///   while moving nothing would otherwise zero the credit and emit
    ///   Withdrawn while the funds never left — the credit would be
    ///   silently dropped. Here the balance must drop by exactly
    ///   `amount`; if it did not, the call reverts with "withdrawal
    ///   failed" and the revert restores the credit in full, so a lying
    ///   token can never eat a credit. (A token that moves the funds
    ///   and then returns false still counts as paid — the funds left,
    ///   so no credit is owed.)
    function withdraw(address token) external nonReentrant {
        uint256 amount = pendingWithdrawals[token][msg.sender];
        require(amount > 0, "nothing to withdraw");
        pendingWithdrawals[token][msg.sender] = 0;
        uint256 balanceBefore = _balanceOf(token);
        _tryTransfer(token, msg.sender, amount);
        uint256 balanceAfter = _balanceOf(token);
        uint256 moved = balanceBefore > balanceAfter ? balanceBefore - balanceAfter : 0;
        require(moved == amount, "withdrawal failed");
        emit Withdrawn(token, msg.sender, msg.sender, amount);
    }

    /// @notice Withdraw the caller's pending credit for a token to a
    ///   chosen address. Essential when the credited address itself is
    ///   blocklisted: a transfer to it would fail again, so the credit
    ///   is pulled to an address the token accepts. Only the credited
    ///   party may move its own credit.
    /// @dev Same ROUND 10 balance verification as withdraw(): the
    ///   balance must drop by exactly `amount`, or the call reverts
    ///   and the credit is restored in full.
    function withdrawTo(address token, address to) external nonReentrant {
        require(to != address(0), "zero address");
        uint256 amount = pendingWithdrawals[token][msg.sender];
        require(amount > 0, "nothing to withdraw");
        pendingWithdrawals[token][msg.sender] = 0;
        uint256 balanceBefore = _balanceOf(token);
        _tryTransfer(token, to, amount);
        uint256 balanceAfter = _balanceOf(token);
        uint256 moved = balanceBefore > balanceAfter ? balanceBefore - balanceAfter : 0;
        require(moved == amount, "withdrawal failed");
        emit Withdrawn(token, msg.sender, to, amount);
    }

    /// @dev SafeERC20-style transfer attempt: accepts an empty return value
    ///   (USDT-style tokens) and returns false instead of reverting on a
    ///   false return or a failed call, so the caller can decide how to
    ///   handle the failure (credit a pull balance, or revert).
    /// @dev ROUND 6 (Oct 27, 2026): the call is made in assembly with a
    ///   32-byte output buffer (out offset 0, size 0x20). The high-level
    ///   `token.call(...)` used before copied the FULL returndata into
    ///   memory first, so a token returning ~3MB ran the settlement out
    ///   of gas before the bounded inspection ever ran — proven by the
    ///   mode-4 return-bomb test (release consumed all 30M gas and
    ///   reverted, job stuck Delivered, no credit). With the capped
    ///   output buffer the call copies at most 32 bytes; returndatasize()
    ///   still reports the full size, and _lastCallReturnedTrue() rejects
    ///   anything that is not empty or exactly 32 bytes holding 1.
    /// @dev Gas ceilings pinned by tests
    ///   (test_release_gas_clean_vs_credited_pins_bomb_fix, measured on
    ///   eth-tester/PyEVM, Oct 27, 2026): 150,000 gas for the
    ///   small-return paths — clean payer release 75,800, clean
    ///   agent-claim release 77,613, credited mode 0 73,015, credited
    ///   mode 2 (10KB return) 74,075 — and 19,000,000 gas for the ~3MB
    ///   return-bomb path (17,519,073, of which ~17.5M is the token's own
    ///   cost to return 3MB; the escrow pays nothing on top), plus a <3x
    ///   relative bound (each credited release costs less than 3x the
    ///   clean release). The ceilings are bounds, not exact figures: a
    ///   future solc upgrade may shift gas a little, but anything near
    ///   the ~35M the old copy-everything behaviour needed means the bomb
    ///   fix regressed — and these numbers in the NatSpec are the
    ///   tripwire that says so.
    /// @dev ROUND 9 (Oct 27, 2026): the same 1/64 arithmetic bounds the
    ///   gas-burning token case (MalformedReturnToken mode 5, infinite
    ///   loop). The token consumes 63/64 of the forwarded gas and the
    ///   call fails, so the release credits — but only if the caller
    ///   supplied enough gas that the retained 1/64 still covers the
    ///   credit path. Measured (eth-tester/PyEVM, Oct 27, 2026): with a
    ///   20,000,000 gas limit the release costs 19,695,562 gas and
    ///   succeeds; with 200,000 it reverts and the job stays Delivered.
    ///   A front-end must not hardcode a low gas limit for release.
    /// @dev ROUND 9 (Oct 27, 2026): refuse the call up front when the
    ///   token has no code at all. A token address whose code has
    ///   vanished after funding answers a call with success and empty
    ///   returndata, which the USDT-style rule in
    ///   _lastCallReturnedTrue() reads as "paid" — so the job would be
    ///   marked settled while nothing moved and the funds would sit in
    ///   the escrow with no credit recorded. Limit, stated plainly:
    ///   this only sees the TOKEN address's own code. A proxy token
    ///   whose IMPLEMENTATION vanished still has code itself, so its
    ///   delegatecall can still return empty success — that case needs
    ///   a balance check, not a code check, and is out of scope here.
    /// @dev ROUND 10 (Oct 27, 2026): _tryTransfer's return value is no
    ///   longer the last word on a payout — _payOrCredit and withdraw /
    ///   withdrawTo verify the escrow's balance actually moved (see
    ///   their notes). A token can return true while moving nothing
    ///   (MalformedReturnToken mode 6); the balance check, not the
    ///   return value, is what keeps that lie from marking a job paid.
    function _tryTransfer(address token, address to, uint256 amount) internal returns (bool) {
        if (token.code.length == 0) return false;
        bytes memory data = abi.encodeWithSelector(IERC20.transfer.selector, to, amount);
        bool success;
        assembly {
            success := call(gas(), token, 0, add(data, 0x20), mload(data), 0, 0x20)
        }
        if (!success) return false;
        return _lastCallReturnedTrue();
    }

    /// @dev Inspect the returndata of the most recent external call:
    ///   empty = USDT-style success (no return value); exactly 32 bytes
    ///   holding 1 = true; anything else — 0 (false), a non-bool value
    ///   such as 2, a wrong length — = failure. Copies at most 32 bytes,
    ///   and the callers (_tryTransfer, _safeTransferFrom) cap the
    ///   call's output buffer at 32 bytes in assembly, so a token
    ///   returning megabytes of returndata cannot run the caller out of
    ///   gas on the copy — the returndatasize() check rejects it without
    ///   copying. Called immediately after the external call, with no
    ///   other external call in between, so the returndata buffer still
    ///   holds that call's return.
    function _lastCallReturnedTrue() internal view returns (bool) {
        uint256 size;
        assembly { size := returndatasize() }
        if (size == 0) return true;
        if (size != 32) return false;
        uint256 value;
        assembly {
            let ptr := mload(0x40)
            returndatacopy(ptr, 0, 32)
            value := mload(ptr)
        }
        return value == 1;
    }

    /// @dev Balance read that never reverts, for the payout and
    ///   withdrawal balance checks below. A token with no code, or one
    ///   whose balanceOf reverts or returns garbage, reads as 0 — so
    ///   the move is treated as zero and the payout is credited (or
    ///   the withdrawal reverts) instead of the settlement bricking.
    ///   A high-level IERC20(token).balanceOf() call would revert here:
    ///   calling a dead token returns empty returndata, which the ABI
    ///   decoder rejects as a uint256 — the exact case the round-9
    ///   VanishingToken test covers, where release() must credit, not
    ///   revert. Uses the same 32-byte-capped assembly call as
    ///   _tryTransfer, so a huge return cannot run the caller out of
    ///   gas on the copy.
    function _balanceOf(address token) internal view returns (uint256 bal) {
        bytes memory data = abi.encodeWithSelector(IERC20.balanceOf.selector, address(this));
        bool success;
        assembly {
            success := staticcall(gas(), token, add(data, 0x20), mload(data), 0, 0x20)
        }
        if (!success) return 0;
        uint256 size;
        assembly { size := returndatasize() }
        if (size != 32) return 0;
        assembly {
            let ptr := mload(0x40)
            returndatacopy(ptr, 0, 32)
            bal := mload(ptr)
        }
    }

    /// @dev Attempt a token payout; on failure, credit a pull balance
    ///   instead of reverting the settlement. The job is already in its
    ///   terminal state when this runs, so the recipient's funds are
    ///   never lost — they are pulled later with withdraw() / withdrawTo().
    /// @dev ROUND 10 (Oct 27, 2026): the escrow's balance is the source
    ///   of truth, not the token's return value. A token that returns
    ///   true (or empty) while moving nothing — the lying-token case,
    ///   proven by MalformedReturnToken mode 6 — must not mark the job
    ///   paid: the balance check catches it and the payout is credited
    ///   instead. The mirrored case is covered too: a token that moves
    ///   the funds and then returns false still counts as paid, so it
    ///   is never paid twice. Only the shortfall is credited — what the
    ///   escrow still holds for this job — so the invariant always
    ///   holds: escrow token balance == sum of unsettled job amounts +
    ///   all pending credits. Assumes a token either moves the full
    ///   amount or nothing (true of every token in the suite and of
    ///   standard ERC-20s); a token that moved a partial amount would
    ///   be credited only the shortfall, never the full amount.
    /// @dev Why a balance check, not a stricter return rule: the return
    ///   value is the token's claim about what it did; the balance is
    ///   what actually happened. The code-length check (round 9) closed
    ///   the vanished-code variant of the same lie; this closes the
    ///   remaining variant — a live token that answers success and
    ///   moves nothing — at the source, for every payout path at once.
    ///   Balances are read with _balanceOf, never a high-level call:
    ///   a dead token's empty returndata would revert the decoder and
    ///   brick the settlement instead of crediting it.
    function _payOrCredit(address token, address to, uint256 amount) internal {
        uint256 balanceBefore = _balanceOf(token);
        _tryTransfer(token, to, amount);
        uint256 balanceAfter = _balanceOf(token);
        uint256 moved = balanceBefore > balanceAfter ? balanceBefore - balanceAfter : 0;
        if (moved >= amount) {
            return; // the funds left the escrow: paid, whatever the return said
        }
        uint256 shortfall = amount - moved;
        pendingWithdrawals[token][to] += shortfall;
        emit Credited(token, to, shortfall);
    }

    /// @dev SafeERC20-style transferFrom: accepts an empty return value
    ///   (USDT-style tokens) and reverts on a false return or a failed call.
    ///   Uses the same assembly call with a 32-byte output buffer as
    ///   _tryTransfer (see its note): a malformed return can never run
    ///   the funding call out of gas on the copy — it fails cleanly with
    ///   "funding failed" instead.
    function _safeTransferFrom(address token, address from, uint256 amount) internal {
        bytes memory data = abi.encodeWithSelector(
            IERC20.transferFrom.selector, from, address(this), amount
        );
        bool success;
        assembly {
            success := call(gas(), token, 0, add(data, 0x20), mload(data), 0, 0x20)
        }
        require(success && _lastCallReturnedTrue(), "funding failed");
    }

    /// @notice The two timestamps that bound the agent's claim and the
    ///   dispute, so callers never re-compute them.
    /// @dev agentClaimAt is the last second of the review window: the
    ///   agent's claim is strict (>), so it may claim from agentClaimAt
    ///   + 1. A dispute may be resolved up to disputeTimeoutAt (<=) and
    ///   times out after it (>). Before delivery (deliveredAt == 0) both
    ///   are 0: the window offsets from 0 would look like 1970
    ///   timestamps that have already passed, so a UI or agent could
    ///   wrongly conclude the claim is open.
    /// @return agentClaimAt deliveredAt + reviewWindow, or 0 if not delivered
    /// @return disputeTimeoutAt deliveredAt + reviewWindow + DISPUTE_PERIOD, or 0 if not delivered
    function claimWindows(uint256 jobId) external view returns (uint256 agentClaimAt, uint256 disputeTimeoutAt) {
        Job storage job = jobs[jobId];
        if (job.deliveredAt == 0) return (0, 0);
        agentClaimAt = job.deliveredAt + job.reviewWindow;
        disputeTimeoutAt = agentClaimAt + DISPUTE_PERIOD;
    }

    /// @notice The pull balance an account can withdraw for a token, so
    ///   front-ends never have to re-derive credits from event logs.
    /// @dev Grok improvement 2 (round 8): a named, documented view over
    ///   pendingWithdrawals. The mapping itself is public, but this is
    ///   the front-end path — one call, one answer, no log scanning.
    /// @param token The token the credit is held in.
    /// @param account The account the credit belongs to.
    /// @return credit The amount the account can pull with withdraw() /
    ///   withdrawTo(), or 0 if there is no credit.
    function pendingCredit(address token, address account) external view returns (uint256 credit) {
        return pendingWithdrawals[token][account];
    }

    /// @notice The full settlement picture for a job in one call:
    ///   its delivery timestamp, the two timestamps that bound the
    ///   agent's claim and the dispute, and the pull balance the job's
    ///   agent can withdraw for the job's token — so a caller never has
    ///   to recompute windows or call claimWindows + getJob +
    ///   pendingCredit separately.
    /// @dev Grok improvement (round 10): claimWindows + pendingCredit
    ///   in one multicall-friendly view. Before delivery
    ///   (deliveredAt == 0) the window timestamps are 0 (same rule as
    ///   claimWindows: the window offsets from 0 would look like 1970
    ///   timestamps that have already passed); the credit is
    ///   independent of delivery and is reported as-is. Boundary
    ///   semantics, as in release / raiseDispute / settleDisputeTimeout:
    ///   the agent may claim only when block.timestamp > agentClaimAt
    ///   (strict); a dispute may be raised while block.timestamp <=
    ///   agentClaimAt (inclusive); the arbiter may resolve while
    ///   block.timestamp <= disputeTimeoutAt (inclusive); the timeout
    ///   settles only when block.timestamp > disputeTimeoutAt (strict).
    /// @return deliveredAt timestamp of submitDelivery; 0 until delivered
    /// @return agentClaimAt deliveredAt + reviewWindow, or 0 if not delivered
    /// @return disputeTimeoutAt deliveredAt + reviewWindow + DISPUTE_PERIOD, or 0 if not delivered
    /// @return credit the pull balance of the job's agent for the job's token, or 0
    function jobWindows(uint256 jobId) external view returns (
        uint256 deliveredAt,
        uint256 agentClaimAt,
        uint256 disputeTimeoutAt,
        uint256 credit
    ) {
        Job storage job = jobs[jobId];
        deliveredAt = job.deliveredAt;
        if (deliveredAt != 0) {
            agentClaimAt = deliveredAt + job.reviewWindow;
            disputeTimeoutAt = agentClaimAt + DISPUTE_PERIOD;
        }
        credit = pendingWithdrawals[job.token][job.agent];
    }

    function getJob(uint256 jobId) external view returns (Job memory) {
        return jobs[jobId];
    }
}

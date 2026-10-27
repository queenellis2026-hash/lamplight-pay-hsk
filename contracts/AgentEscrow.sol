// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AgentEscrow — escrowed settlement for agent-to-agent work.
/// @notice Lamplight Pay (HSK Chain Horizon Hackathon, Agent Payments & A2A
/// Settlement track). A payer (human or agent) funds a job in an ERC-20
/// stablecoin; the worker agent accepts, delivers (hash of the deliverable),
/// and the payer releases. If the agent never delivers by the deadline the
/// payer can reclaim. Either side can raise a dispute; the payer resolves it
/// (release or refund) — the honest-minimum arbiter for a hackathon demo,
/// documented as a limitation in the README, not hidden.
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
///   - A disputed job must be resolved by the payer within the dispute
///     period (review window + DISPUTE_PERIOD, 7 days). After that, either
///     party may call settleDisputeTimeout(), which releases to the agent:
///     delivered work gets paid unless the payer acts in time. No
///     arbitrator in v1 — that is a stated limitation, not an oversight.
/// @dev Funding measures what actually arrived: createJob compares the
///   escrow's token balance before and after transferFrom and stores the
///   received amount, so fee-on-transfer / rebasing tokens cannot make the
///   escrow insolvent by recording more than it holds.
/// @dev All token moves use SafeERC20-style low-level calls that accept an
///   empty return value, so USDT-style tokens (no bool return) work.
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

    event JobCreated(uint256 indexed jobId, address indexed payer, address indexed agent, address token, uint256 amount, uint256 deadline, string metadataURI);
    event JobAccepted(uint256 indexed jobId, address indexed agent);
    event DeliverySubmitted(uint256 indexed jobId, bytes32 deliveryHash);
    event JobReleased(uint256 indexed jobId, address indexed agent, uint256 amount);
    event JobRefunded(uint256 indexed jobId, address indexed payer, uint256 amount);
    event JobCancelled(uint256 indexed jobId);
    event JobCancelledUnaccepted(uint256 indexed jobId);
    event DisputeRaised(uint256 indexed jobId, address indexed by);
    event DisputeResolved(uint256 indexed jobId, bool releasedToAgent);
    event DisputeTimedOut(uint256 indexed jobId, address indexed agent, uint256 amount);

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
    function createJob(
        address agent,
        address token,
        uint256 amount,
        uint256 deadlineSeconds,
        uint256 reviewWindowSeconds,
        string calldata metadataURI
    ) external nonReentrant returns (uint256 jobId) {
        require(agent != address(0) && token != address(0), "zero address");
        require(agent != msg.sender, "payer cannot be agent");
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
            deliveredAt: 0
        });
        emit JobCreated(jobId, msg.sender, agent, token, received, block.timestamp + deadlineSeconds, metadataURI);
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
    ///   The agent's claim is STRICT (block.timestamp > deliveredAt +
    ///   reviewWindow): at the exact boundary second the payer's dispute
    ///   (raiseDispute, <=) still wins, so a last-second dispute can never
    ///   lose a race to the agent's release.
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
        _safeTransfer(job.token, job.agent, job.amount);
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
        _safeTransfer(job.token, job.payer, job.amount);
        emit JobRefunded(jobId, job.payer, job.amount);
    }

    /// @notice Payer cancels before the agent accepts; funds return at once.
    function cancel(uint256 jobId) external onlyPayer(jobId) nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Created, "only before accept");
        job.state = State.Cancelled;
        _safeTransfer(job.token, job.payer, job.amount);
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
        _safeTransfer(job.token, job.payer, job.amount);
        emit JobCancelledUnaccepted(jobId);
    }

    /// @notice Either party raises a dispute — only INSIDE the review window.
    /// @dev After deliveredAt + reviewWindow, raiseDispute reverts: the
    ///   window is the payer's chance to object, not an open-ended right.
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

    /// @notice Payer resolves a dispute: true = pay the agent, false = refund.
    /// Honest limitation: the payer is the arbiter in this demo version.
    /// A production version would use a third-party arbiter or DAO vote.
    /// @dev Must be called within the dispute period (review window +
    ///   DISPUTE_PERIOD after delivery); after that, settleDisputeTimeout()
    ///   is the only exit, so a dispute cannot lock funds forever.
    function resolveDispute(uint256 jobId, bool releaseToAgent) external onlyPayer(jobId) nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Disputed, "not disputed");
        require(
            block.timestamp <= job.deliveredAt + job.reviewWindow + DISPUTE_PERIOD,
            "dispute period ended"
        );
        if (releaseToAgent) {
            job.state = State.Released;
            _safeTransfer(job.token, job.agent, job.amount);
            emit JobReleased(jobId, job.agent, job.amount);
        } else {
            job.state = State.Refunded;
            _safeTransfer(job.token, job.payer, job.amount);
            emit JobRefunded(jobId, job.payer, job.amount);
        }
        emit DisputeResolved(jobId, releaseToAgent);
    }

    /// @notice Exit for a dispute the payer raised and then abandoned: after
    ///   the dispute period ends, either party may settle it, releasing the
    ///   funds to the agent. Delivered work gets paid unless the payer acts
    ///   in time; a payer cannot dispute, go silent, and keep the money.
    function settleDisputeTimeout(uint256 jobId) external nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Disputed, "not disputed");
        require(msg.sender == job.payer || msg.sender == job.agent, "not a party");
        require(
            block.timestamp > job.deliveredAt + job.reviewWindow + DISPUTE_PERIOD,
            "dispute period not ended"
        );
        job.state = State.Released;
        _safeTransfer(job.token, job.agent, job.amount);
        emit JobReleased(jobId, job.agent, job.amount);
        emit DisputeResolved(jobId, true);
        emit DisputeTimedOut(jobId, job.agent, job.amount);
    }

    /// @dev SafeERC20-style transfer: accepts an empty return value
    ///   (USDT-style tokens) and reverts on a false return or a failed call.
    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.transfer.selector, to, amount)
        );
        require(success, "payout failed");
        require(data.length == 0 || abi.decode(data, (bool)), "payout failed");
    }

    /// @dev SafeERC20-style transferFrom: accepts an empty return value
    ///   (USDT-style tokens) and reverts on a false return or a failed call.
    function _safeTransferFrom(address token, address from, uint256 amount) internal {
        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.transferFrom.selector, from, address(this), amount)
        );
        require(success, "funding failed");
        require(data.length == 0 || abi.decode(data, (bool)), "funding failed");
    }

    function getJob(uint256 jobId) external view returns (Job memory) {
        return jobs[jobId];
    }
}

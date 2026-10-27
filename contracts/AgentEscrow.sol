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
/// @dev Minimal reentrancy guard included; no external dependencies.
interface IERC20 {
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
    }

    uint256 public jobCount;
    mapping(uint256 => Job) public jobs;

    event JobCreated(uint256 indexed jobId, address indexed payer, address indexed agent, address token, uint256 amount, uint256 deadline, string metadataURI);
    event JobAccepted(uint256 indexed jobId, address indexed agent);
    event DeliverySubmitted(uint256 indexed jobId, bytes32 deliveryHash);
    event JobReleased(uint256 indexed jobId, address indexed agent, uint256 amount);
    event JobRefunded(uint256 indexed jobId, address indexed payer, uint256 amount);
    event JobCancelled(uint256 indexed jobId);
    event DisputeRaised(uint256 indexed jobId, address indexed by);
    event DisputeResolved(uint256 indexed jobId, bool releasedToAgent);

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
        require(IERC20(token).transferFrom(msg.sender, address(this), amount), "funding failed");

        jobId = jobCount++;
        jobs[jobId] = Job({
            payer: msg.sender,
            agent: agent,
            token: token,
            amount: amount,
            deadline: block.timestamp + deadlineSeconds,
            reviewWindow: reviewWindowSeconds,
            state: State.Created,
            deliveryHash: bytes32(0),
            metadataURI: metadataURI
        });
        emit JobCreated(jobId, msg.sender, agent, token, amount, block.timestamp + deadlineSeconds, metadataURI);
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
        emit DeliverySubmitted(jobId, deliveryHash);
    }

    /// @notice Payer releases funds to the agent after delivery.
    function release(uint256 jobId) external onlyPayer(jobId) nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Delivered, "not delivered");
        job.state = State.Released;
        require(IERC20(job.token).transfer(job.agent, job.amount), "payout failed");
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
        require(IERC20(job.token).transfer(job.payer, job.amount), "refund failed");
        emit JobRefunded(jobId, job.payer, job.amount);
    }

    /// @notice Payer cancels before the agent accepts; funds return at once.
    function cancel(uint256 jobId) external onlyPayer(jobId) nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Created, "only before accept");
        job.state = State.Cancelled;
        require(IERC20(job.token).transfer(job.payer, job.amount), "refund failed");
        emit JobCancelled(jobId);
    }

    function raiseDispute(uint256 jobId) external {
        Job storage job = jobs[jobId];
        require(msg.sender == job.payer || msg.sender == job.agent, "not a party");
        require(job.state == State.Delivered, "only after delivery");
        job.state = State.Disputed;
        emit DisputeRaised(jobId, msg.sender);
    }

    /// @notice Payer resolves a dispute: true = pay the agent, false = refund.
    /// Honest limitation: the payer is the arbiter in this demo version.
    /// A production version would use a third-party arbiter or DAO vote.
    function resolveDispute(uint256 jobId, bool releaseToAgent) external onlyPayer(jobId) nonReentrant {
        Job storage job = jobs[jobId];
        require(job.state == State.Disputed, "not disputed");
        if (releaseToAgent) {
            job.state = State.Released;
            require(IERC20(job.token).transfer(job.agent, job.amount), "payout failed");
            emit JobReleased(jobId, job.agent, job.amount);
        } else {
            job.state = State.Refunded;
            require(IERC20(job.token).transfer(job.payer, job.amount), "refund failed");
            emit JobRefunded(jobId, job.payer, job.amount);
        }
        emit DisputeResolved(jobId, releaseToAgent);
    }

    function getJob(uint256 jobId) external view returns (Job memory) {
        return jobs[jobId];
    }
}

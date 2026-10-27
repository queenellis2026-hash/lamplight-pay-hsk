// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title HookToken — TEST ONLY token whose transfer() calls back into a target.
/// @notice Used by the Lamplight Pay test suite to prove a reentrant payout
///   leg cannot drain or brick a job: the escrow's nonReentrant guard
///   rejects the inner call, the token transfer fails, and the payout is
///   credited to a pull balance instead of reverting the settlement. The
///   hook fires only on transfer() (the payout leg); transferFrom() is
///   hook-free, so funding a job never triggers it. The hook runs BEFORE
///   the balance movement and, if the inner call fails, the transfer
///   returns false WITHOUT reverting — so the outcome recording
///   (lastHookOk / lastHookReturndata) survives for the test to inspect,
///   and the escrow's _tryTransfer still treats it as a failed payout
///   and credits the recipient. The hook is armed by the owner after
///   funding and can be disarmed to let the credit be withdrawn. Never
///   deploy to mainnet.
contract HookToken {
    string public constant name = "Hook Token (TEST ONLY)";
    string public constant symbol = "mHOOK";
    uint8 public constant decimals = 6;
    uint256 public totalSupply;

    address public owner;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    address public hookTarget;
    bytes public hookCalldata;
    bool public lastHookOk;
    bytes public lastHookReturndata;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor() {
        owner = msg.sender;
    }

    function mint(address to, uint256 amount) external {
        require(msg.sender == owner, "not owner");
        require(to != address(0), "zero address");
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function setHook(address target, bytes calldata data) external {
        require(msg.sender == owner, "not owner");
        hookTarget = target;
        hookCalldata = data;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        // The hook runs first: if the callback fails, no tokens move and
        // the transfer returns false (rather than reverting, which would
        // roll back the outcome recording the test inspects).
        if (hookTarget != address(0)) {
            (bool ok, bytes memory ret) = hookTarget.call(hookCalldata);
            lastHookOk = ok;
            lastHookReturndata = ret;
            if (!ok) return false;
        }
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "allowance too low");
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - amount;
        }
        _transfer(from, to, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(balanceOf[from] >= amount, "insufficient balance");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}

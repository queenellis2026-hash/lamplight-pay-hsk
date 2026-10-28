// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title PartialHookToken — TEST ONLY token that PARTIALLY transfers
///   and then calls back into a target, mirroring HookAfterToken.
/// @notice ROUND 21: the token for the transient payout-window test.
///   Where HookAfterToken moves the full amount and hooks second, this
///   token moves `amount - shortfall` (shortfall set by the owner, 0 by
///   default meaning a full move) and hooks second. That is the shape
///   of a partial payout: the escrow's _payOrCredit sees moved < amount
///   and credits the shortfall only AFTER the transfer attempt, so a
///   hook reading settlementInvariant mid-call observes holds == false
///   transiently, and the settled state after the call holds == true.
///   If the hook call fails the whole transfer REVERTS, rolling the
///   partial movement back, exactly like HookAfterToken. The hook is
///   armed by the owner and can be disarmed. Never deploy to mainnet.
contract PartialHookToken {
    string public constant name = "Partial Hook Token (TEST ONLY)";
    string public constant symbol = "mPHOOK";
    uint8 public constant decimals = 6;
    uint256 public totalSupply;

    address public owner;
    uint256 public shortfall;

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

    function setShortfall(uint256 s) external {
        require(msg.sender == owner, "not owner");
        shortfall = s;
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
        _transfer(msg.sender, to, amount);
        _hook();
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "allowance too low");
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - amount;
        }
        _transfer(from, to, amount);
        _hook();
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(shortfall <= amount, "shortfall exceeds amount");
        uint256 moved = amount - shortfall;
        require(balanceOf[from] >= moved, "insufficient balance");
        balanceOf[from] -= moved;
        balanceOf[to] += moved;
        emit Transfer(from, to, moved);
    }

    function _hook() internal {
        if (hookTarget == address(0)) {
            return;
        }
        // The hook runs after the partial movement. A failed hook
        // reverts the whole transfer, rolling the movement back, so
        // the outcome recording below is only observable when the
        // hook succeeded — the tests that read it arm view hooks.
        (bool ok, bytes memory ret) = hookTarget.call(hookCalldata);
        require(ok, "hook failed");
        lastHookOk = ok;
        lastHookReturndata = ret;
    }
}

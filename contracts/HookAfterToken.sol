// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title HookAfterToken — TEST ONLY token whose transfer() and
///   transferFrom() call back into a target AFTER the balance movement.
/// @notice The mirror of HookToken for the round-19 window tests. Where
///   HookToken hooks BEFORE the movement (and returns false on a failed
///   hook, so the payout leg fails without moving funds), this token
///   moves first and hooks second — the ERC777/ERC1363 shape, where a
///   recipient callback fires after the debit. If the hook call fails
///   the whole transfer REVERTS, rolling the balance movement back, so
///   a failing hook still fails the payout leg cleanly and the escrow
///   credits the recipient instead of stranding the job. Unlike
///   HookToken, transferFrom() hooks too, so the createJob funding
///   window can be pinned by a test. The hook is armed by the owner
///   and can be disarmed. Never deploy to mainnet.
contract HookAfterToken {
    string public constant name = "Hook After Token (TEST ONLY)";
    string public constant symbol = "mHOOKA";
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
        require(balanceOf[from] >= amount, "insufficient balance");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }

    function _hook() internal {
        if (hookTarget == address(0)) {
            return;
        }
        // The hook runs after the balance movement. A failed hook
        // reverts the whole transfer, rolling the movement back, so
        // the outcome recording below is only observable when the
        // hook succeeded — the tests that read it arm view hooks.
        (bool ok, bytes memory ret) = hookTarget.call(hookCalldata);
        require(ok, "hook failed");
        lastHookOk = ok;
        lastHookReturndata = ret;
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title FeeToken — TEST ONLY token that takes a 1% fee on every transfer.
/// @notice Used by the Lamplight Pay test suite to prove the escrow records
///   what actually arrived (balance before/after) instead of the nominal
///   amount. The fee accrues to this contract. Never deploy to mainnet.
contract FeeToken {
    string public constant name = "Fee Token (TEST ONLY)";
    string public constant symbol = "mFEE";
    uint8 public constant decimals = 6;
    uint256 public totalSupply;

    address public owner;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

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

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
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

    /// @dev 1% fee: sender loses `amount`, recipient gets 99%, the fee
    ///   accrues to this contract.
    function _transfer(address from, address to, uint256 amount) internal {
        require(to != address(0), "zero address");
        require(balanceOf[from] >= amount, "balance too low");
        uint256 fee = amount / 100;
        uint256 net = amount - fee;
        balanceOf[from] -= amount;
        balanceOf[to] += net;
        balanceOf[address(this)] += fee;
        emit Transfer(from, to, net);
        if (fee > 0) {
            emit Transfer(from, address(this), fee);
        }
    }
}

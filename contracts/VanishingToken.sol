// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title VanishingToken — TEST ONLY minimal ERC-20 that can self-destruct.
/// @notice Used by the Lamplight Pay test suite to prove _tryTransfer
///   refuses a token whose code has vanished after funding: the token is
///   funded into a job, then kill() self-destructs it, and the release
///   must credit the payout instead of marking the job paid while
///   nothing moved. The test runs on a pre-Cancun (Shanghai) chain:
///   EIP-6780 (Cancun) makes SELFDESTRUCT unable to delete code except
///   in the creation transaction, so on the default Prague tester the
///   code would survive the kill — the same reason the hole is nearly
///   unreachable on modern mainnet. Never deploy to mainnet.
contract VanishingToken {
    string public constant name = "Vanishing Token (TEST ONLY)";
    string public constant symbol = "mVAN";
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

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
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

    /// @notice Destroy the token. After this the address has no code.
    function kill() external {
        require(msg.sender == owner, "not owner");
        selfdestruct(payable(owner));
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title MalformedReturnToken — TEST ONLY token whose transfer() returns
///   malformed returndata.
/// @notice Used by the Lamplight Pay test suite to prove a payout leg can
///   never be bricked by a token's return value: the escrow's _tryTransfer
///   must treat a bad return as a failed payout (credit a pull balance)
///   instead of reverting the settlement. Modes (set by the owner):
///     0 = transfer() returns 32 bytes holding the value 2 (not a bool)
///     1 = transfer() returns exactly 1 byte
///     2 = transfer() returns 10,000 bytes of returndata
///     3 = well-behaved: transfer() moves funds and returns true
///     4 = transfer() returns ~3,000,000 bytes of returndata (round-6
///       return-bomb: tests whether the escrow's high-level token.call
///       copies the full returndata into memory before the bounded
///       inspection caps it — if so, a megabyte-scale return runs the
///       settlement out of gas instead of crediting it)
///   In the malformed modes the transfer moves NO funds: the token refused
///   the payout but answered with garbage instead of false, so the escrow
///   credits the pull balance and the job still reaches its terminal
///   state. transferFrom() is always well-behaved, so funding a job never
///   triggers the malformed path. Never deploy to mainnet.
contract MalformedReturnToken {
    string public constant name = "Malformed Return Token (TEST ONLY)";
    string public constant symbol = "mBAD";
    uint8 public constant decimals = 6;
    uint256 public totalSupply;

    address public owner;
    uint256 public mode = 3; // default: well-behaved

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

    function setMode(uint256 mode_) external {
        require(msg.sender == owner, "not owner");
        require(mode_ <= 4, "bad mode");
        mode = mode_;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        if (mode == 3) {
            _transfer(msg.sender, to, amount);
            return true;
        }
        // Malformed modes: no funds move; the answer is garbage.
        if (mode == 0) {
            assembly {
                mstore(0, 2)
                return(0, 32)
            }
        } else if (mode == 1) {
            assembly {
                mstore8(0, 0x01)
                return(0, 1)
            }
        } else if (mode == 2) {
            assembly {
                return(0, 10000)
            }
        } else if (mode == 4) {
            // Return-bomb: ~3,000,000 bytes. The token's own frame pays
            // the memory-expansion cost of returning it (~17.5M gas), so
            // a caller must supply enough gas for the token to return at
            // all; the question the bomb answers is what the ESCROW pays
            // on top of that — a full copy costs another ~17.5M, a
            // 32-byte-capped copy costs almost nothing.
            assembly {
                return(0, 3000000)
            }
        }
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

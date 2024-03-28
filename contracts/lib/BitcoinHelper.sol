// SPDX-License-Identifier: MIT
pragma solidity 0.8.4;

import "./TypedMemView.sol";
import "./SafeCast.sol";

enum ScriptTypes {
    P2PK, // 32 bytes
    P2PKH, // 20 bytes        
    P2SH, // 20 bytes          
    P2WPKH, // 20 bytes          
    P2WSH, // 32 bytes
    P2TR // 32 bytes               
}

library BitcoinHelper {

    using SafeCast for uint96;
    using SafeCast for uint256;

    using TypedMemView for bytes;
    using TypedMemView for bytes29;

    // The target at minimum Difficulty. Also the target of the genesis block
    uint256 internal constant DIFF1_TARGET = 0xffff0000000000000000000000000000000000000000000000000000;

    uint256 internal constant RETARGET_PERIOD = 2 * 7 * 24 * 60 * 60;  // 2 weeks in seconds
    uint256 internal constant RETARGET_PERIOD_BLOCKS = 2016;  // 2 weeks in blocks

    enum BTCTypes {
        Unknown,            // 0x0
        CompactInt,         // 0x1
        ScriptSig,          // 0x2 - with length prefix
        Outpoint,           // 0x3
        TxIn,               // 0x4
        IntermediateTxIns,  // 0x5 - used in vin parsing
        Vin,                // 0x6
        ScriptPubkey,       // 0x7 - with length prefix
        PKH,                // 0x8 - the 20-byte payload digest
        WPKH,               // 0x9 - the 20-byte payload digest
        WSH,                // 0xa - the 32-byte payload digest
        SH,                 // 0xb - the 20-byte payload digest
        OpReturnPayload,    // 0xc
        TxOut,              // 0xd
        IntermediateTxOuts, // 0xe - used in vout parsing
        Vout,               // 0xf
        Header,             // 0x10
        HeaderArray,        // 0x11
        MerkleNode,         // 0x12
        MerkleStep,         // 0x13
        MerkleArray         // 0x14
    }

    /// @notice             requires `memView` to be of a specified type
    /// @dev                passes if it is the correct type, errors if not
    /// @param memView      a 29-byte view with a 5-byte type
    /// @param t            the expected type (e.g. BTCTypes.Outpoint, BTCTypes.TxIn, etc)
    modifier typeAssert(bytes29 memView, BTCTypes t) {
        memView.assertType(uint40(t));
        _;
    }

    // Revert with an error message re: non-minimal VarInts
    function revertNonMinimal(bytes29 ref) private pure returns (string memory) {
        (, uint256 g) = TypedMemView.encodeHex(ref.indexUint(0, ref.len().toUint8()));
        string memory err = string(
            abi.encodePacked(
                "Non-minimal var int. Got 0x",
                uint144(g)
            )
        );
        revert(err);
    }

    /// @notice             reads a compact int from the view at the specified index
    /// @param memView      a 29-byte view with a 5-byte type
    /// @param _index       the index
    /// @return number      returns the compact int at the specified index
    function indexCompactInt(bytes29 memView, uint256 _index) internal pure returns (uint64 number) {
        uint256 flag = memView.indexUint(_index, 1);
        if (flag <= 0xfc) {
            return flag.toUint64();
        } else if (flag == 0xfd) {
            number = memView.indexLEUint(_index + 1, 2).toUint64();
            if (compactIntLength(number) != 3) {revertNonMinimal(memView.slice(_index, 3, 0));}
        } else if (flag == 0xfe) {
            number = memView.indexLEUint(_index + 1, 4).toUint64();
            if (compactIntLength(number) != 5) {revertNonMinimal(memView.slice(_index, 5, 0));}
        } else if (flag == 0xff) {
            number = memView.indexLEUint(_index + 1, 8).toUint64();
            if (compactIntLength(number) != 9) {revertNonMinimal(memView.slice(_index, 9, 0));}
        }
    }

    /// @notice         gives the total length (in bytes) of a CompactInt-encoded number
    /// @param number   the number as uint64
    /// @return         the compact integer length as uint8
    function compactIntLength(uint64 number) private pure returns (uint8) {
        if (number <= 0xfc) {
            return 1;
        } else if (number <= 0xffff) {
            return 3;
        } else if (number <= 0xffffffff) {
            return 5;
        } else {
            return 9;
        }
    }

    /// @notice             extracts the LE txid from an outpoint
    /// @param _outpoint    the outpoint
    /// @return             the LE txid
    function txidLE(bytes29 _outpoint) internal pure typeAssert(_outpoint, BTCTypes.Outpoint) returns (bytes32) {
        return _outpoint.index(0, 32);
    }

    /// @notice                      Calculates the required transaction Id from the transaction details
    /// @dev                         Calculates the hash of transaction details two consecutive times
    /// @param _tx                   The Bitcoin transaction
    /// @return                      Transaction Id of the transaction (in LE form)
    function calculateTxId(bytes memory _tx) internal pure returns (bytes32) {
        bytes32 inputHash1 = sha256(_tx);
        bytes32 inputHash2 = sha256(abi.encodePacked(inputHash1));
        return inputHash2;
    }

    /// @notice                      Reverts a Bytes32 input
    /// @param _input                Bytes32 input that we want to revert
    /// @return                      Reverted bytes32
    function reverseBytes32(bytes32 _input) private pure returns (bytes32) {
        bytes memory temp;
        bytes32 result;
        for (uint i = 0; i < 32; i++) {
            temp = abi.encodePacked(temp, _input[31-i]);
        }
        assembly {
            result := mload(add(temp, 32))
        }
        return result;
    }

    /// @notice                           Parses outpoint info from an input
    /// @dev                              Reverts if vin is null
    /// @param _vin                       The vin of a Bitcoin transaction
    /// @param _index                     Index of the input that we are looking at
    /// @return _txId                     Output tx id
    /// @return _outputIndex              Output tx index
    function extractOutpoint(
        bytes memory _vin,
        uint _index
    ) internal pure returns (bytes32, uint) {
        bytes29 vin = tryAsVin(_vin.ref(uint40(BTCTypes.Unknown)));
        require(!vin.isNull(), "BitcoinHelper: vin is null");
        return extractOutpoint(vin, _index);
    }

    /// @notice                           Parses outpoint info from an input
    /// @dev                              Reverts if vin is null
    /// @param _vinView                   The vin of a Bitcoin transaction
    /// @param _index                     Index of the input that we are looking at
    /// @return _txId                     Output tx id
    /// @return _outputIndex              Output tx index
    function extractOutpoint(
        bytes29 _vinView,
        uint _index
    ) internal pure typeAssert(_vinView, BTCTypes.Vin) returns (bytes32 _txId, uint _outputIndex) {
        bytes29 input = indexVin(_vinView, _index);
        bytes29 _outpoint = outpoint(input);
        _txId = txidLE(_outpoint);
        _outputIndex = outpointIdx(_outpoint);
    }

    /// @notice             extracts the index as an integer from the outpoint
    /// @param _outpoint    the outpoint
    /// @return             the index
    function outpointIdx(bytes29 _outpoint) internal pure typeAssert(_outpoint, BTCTypes.Outpoint) returns (uint32) {
        return _outpoint.indexLEUint(32, 4).toUint32();
    }

    /// @notice          extracts the outpoint from an input
    /// @param _input    the input
    /// @return          the outpoint as a typed memory
    function outpoint(bytes29 _input) internal pure typeAssert(_input, BTCTypes.TxIn) returns (bytes29) {
        return _input.slice(0, 36, uint40(BTCTypes.Outpoint));
    }

    /// @notice           extracts the script sig from an input
    /// @param _input     the input
    /// @return           the script sig as a typed memory
    function scriptSig(bytes29 _input) internal pure typeAssert(_input, BTCTypes.TxIn) returns (bytes29) {
        uint64 scriptLength = indexCompactInt(_input, 36);
        return _input.slice(36, compactIntLength(scriptLength) + scriptLength, uint40(BTCTypes.ScriptSig));
    }

    /// @notice         determines the length of the first input in an array of inputs
    /// @param _inputs  the vin without its length prefix
    /// @return         the input length
    function inputLength(bytes29 _inputs) private pure typeAssert(_inputs, BTCTypes.IntermediateTxIns) returns (uint256) {
        uint64 scriptLength = indexCompactInt(_inputs, 36);
        return uint256(compactIntLength(scriptLength)) + uint256(scriptLength) + 36 + 4;
    }

    /// @notice         extracts the input at a specified index
    /// @param _vin     the vin
    /// @param _index   the index of the desired input
    /// @return         the desired input
    function indexVin(bytes29 _vin, uint256 _index) internal pure typeAssert(_vin, BTCTypes.Vin) returns (bytes29) {
        uint256 _nIns = uint256(indexCompactInt(_vin, 0));
        uint256 _viewLen = _vin.len();
        require(_index < _nIns, "Vin read overrun");

        uint256 _offset = uint256(compactIntLength(uint64(_nIns)));
        bytes29 _remaining;
        for (uint256 _i = 0; _i < _index; _i += 1) {
            _remaining = _vin.postfix(_viewLen - _offset, uint40(BTCTypes.IntermediateTxIns));
            _offset += inputLength(_remaining);
        }

        _remaining = _vin.postfix(_viewLen - _offset, uint40(BTCTypes.IntermediateTxIns));
        uint256 _len = inputLength(_remaining);
        return _vin.slice(_offset, _len, uint40(BTCTypes.TxIn));
    }

    /// @notice         extracts the value from an output
    /// @param _output  the output
    /// @return         the value
    function value(bytes29 _output) internal pure typeAssert(_output, BTCTypes.TxOut) returns (uint64) {
        return _output.indexLEUint(0, 8).toUint64();
    }

    /// @notice                   Finds the value of a specific output
    /// @dev                      Reverts if vout is null
    /// @param _vout              The vout of a Bitcoin transaction
    /// @param _index             Index of output
    /// @return _value            Value of the specified output
    function parseOutputValue(bytes memory _vout, uint _index) internal pure returns (uint64) {
        bytes29 voutView = tryAsVout(_vout.ref(uint40(BTCTypes.Unknown)));
        require(!voutView.isNull(), "BitcoinHelper: vout is null");
        return parseOutputValue(voutView, _index);
    }

    /// @notice              Finds the value of a specific output
    /// @dev                 Reverts if vout is null
    /// @param _voutView     The vout of a Bitcoin transaction
    /// @param _index        Index of output
    /// @return _value       Value of the specified output
    function parseOutputValue(bytes29 _voutView, uint _index) internal pure typeAssert(_voutView, BTCTypes.Vout) returns (uint64 _value) {
        bytes29 output;
        output = indexVout(_voutView, _index);
        _value = value(output);
    }

    /// @notice                   Finds total outputs value
    /// @dev                      Reverts if vout is null
    /// @param _vout              The vout of a Bitcoin transaction
    /// @return _totalValue       Total vout value
    function parseOutputsTotalValue(bytes memory _vout) internal pure returns (uint64) {
        bytes29 voutView = tryAsVout(_vout.ref(uint40(BTCTypes.Unknown)));
        require(!voutView.isNull(), "BitcoinHelper: vout is null");
        return parseOutputsTotalValue(_vout);
    }

    /// @notice                   Finds total outputs value
    /// @dev                      Reverts if vout is null
    /// @param _voutView          The vout of a Bitcoin transaction
    /// @return _totalValue       Total vout value
    function parseOutputsTotalValue(bytes29 _voutView) internal pure typeAssert(_voutView, BTCTypes.Vout) returns (uint64 _totalValue) {
        bytes29 output;
        // Finds total number of outputs
        uint _numberOfOutputs = uint256(indexCompactInt(_voutView, 0));
        for (uint index = 0; index < _numberOfOutputs; index++) {
            output = indexVout(_voutView, index);
            _totalValue = _totalValue + value(output);
        }
    }

    /// @notice                           Parses the BTC amount that has been sent to
    ///                                   a specific script in a specific output
    /// @param _vout                      The vout of a Bitcoin transaction
    /// @param _voutIndex                 Index of the output that we are looking at
    /// @param _script                    Desired recipient script
    /// @param _scriptType                Type of the script (e.g. P2PK)
    /// @return bitcoinAmount             Amount of BTC have been sent to the _script
    function parseValueFromSpecificOutputHavingScript(
        bytes memory _vout,
        uint _voutIndex,
        bytes memory _script,
        ScriptTypes _scriptType
    ) internal pure returns (uint64) {
        bytes29 voutView = tryAsVout(_vout.ref(uint40(BTCTypes.Unknown)));
        require(!voutView.isNull(), "BitcoinHelper: vout is null");
        return parseValueFromSpecificOutputHavingScript(voutView, _voutIndex, _script, _scriptType);
    }

    /// @notice                           Parses the BTC amount that has been sent to
    ///                                   a specific script in a specific output
    /// @param _voutView                  The vout of a Bitcoin transaction
    /// @param _voutIndex                 Index of the output that we are looking at
    /// @param _script                    Desired recipient script
    /// @param _scriptType                Type of the script (e.g. P2PK)
    /// @return bitcoinAmount             Amount of BTC have been sent to the _script
    function parseValueFromSpecificOutputHavingScript(
        bytes29 _voutView,
        uint _voutIndex,
        bytes memory _script,
        ScriptTypes _scriptType
    ) internal pure typeAssert(_voutView, BTCTypes.Vout)  returns (uint64 bitcoinAmount) {
        bytes29 output = indexVout(_voutView, _voutIndex);
        bytes29 _scriptPubkey = scriptPubkey(output);

        if (_scriptType == ScriptTypes.P2TR) {
            // note: first two bytes are OP_1 and Pushdata Bytelength.
            // note: script hash length is 32.
            bitcoinAmount = keccak256(_script) == keccak256(abi.encodePacked(_scriptPubkey.index(2, 32))) ? value(output) : 0;
        } else if (_scriptType == ScriptTypes.P2PK) {
            // note: first byte is Pushdata Bytelength.
            // note: public key length is 32.
            bitcoinAmount = keccak256(_script) == keccak256(abi.encodePacked(_scriptPubkey.index(1, 32))) ? value(output) : 0;
        } else if (_scriptType == ScriptTypes.P2PKH) {
            // note: first three bytes are OP_DUP, OP_HASH160, Pushdata Bytelength.
            // note: public key hash length is 20.
            bitcoinAmount = keccak256(_script) == keccak256(abi.encodePacked(_scriptPubkey.indexAddress(3))) ? value(output) : 0;
        } else if (_scriptType == ScriptTypes.P2SH) {
            // note: first two bytes are OP_HASH160, Pushdata Bytelength
            // note: script hash length is 20.
            bitcoinAmount = keccak256(_script) == keccak256(abi.encodePacked(_scriptPubkey.indexAddress(2))) ? value(output) : 0;
        } else if (_scriptType == ScriptTypes.P2WPKH) {
            // note: first two bytes are OP_0, Pushdata Bytelength
            // note: segwit public key hash length is 20.
            bitcoinAmount = keccak256(_script) == keccak256(abi.encodePacked(_scriptPubkey.indexAddress(2))) ? value(output) : 0;
        } else if (_scriptType == ScriptTypes.P2WSH) {
            // note: first two bytes are OP_0, Pushdata Bytelength
            // note: segwit script hash length is 32.
            bitcoinAmount = keccak256(_script) == keccak256(abi.encodePacked(_scriptPubkey.index(2, 32))) ? value(output) : 0;
        }

    }

    /// @notice                           Parses the BTC amount of a transaction
    /// @dev                              Finds the BTC amount that has been sent to the locking script
    ///                                   Returns zero if no matching locking scrip is found
    /// @param _vout                      The vout of a Bitcoin transaction
    /// @param _lockingScript             Desired locking script
    /// @return bitcoinAmount             Amount of BTC have been sent to the _lockingScript
    function parseValueHavingLockingScript(
        bytes memory _vout,
        bytes memory _lockingScript
    ) internal view returns (uint64) {
        // Checks that vout is not null
        bytes29 voutView = tryAsVout(_vout.ref(uint40(BTCTypes.Unknown)));
        require(!voutView.isNull(), "BitcoinHelper: vout is null");
        return parseValueHavingLockingScript(voutView, _lockingScript);
    }

        /// @notice                           Parses the BTC amount of a transaction
    /// @dev                              Finds the BTC amount that has been sent to the locking script
    ///                                   Returns zero if no matching locking scrip is found
    /// @param _voutView                  The vout of a Bitcoin transaction
    /// @param _lockingScript             Desired locking script
    /// @return bitcoinAmount             Amount of BTC have been sent to the _lockingScript
    function parseValueHavingLockingScript(
        bytes29 _voutView,
        bytes memory _lockingScript
    ) internal view returns (uint64 bitcoinAmount) {
        bytes29 output;
        bytes29 _scriptPubkey;

        // Finds total number of outputs
        uint _numberOfOutputs = uint256(indexCompactInt(_voutView, 0));

        for (uint index = 0; index < _numberOfOutputs; index++) {
            output = indexVout(_voutView, index);
            _scriptPubkey = scriptPubkey(output);

            if (
                keccak256(abi.encodePacked(_scriptPubkey.clone())) == keccak256(abi.encodePacked(_lockingScript))
            ) {
                bitcoinAmount = value(output);
                // Stops searching after finding the desired locking script
                break;
            }
        }
    }

    /// @notice                           Parses the BTC amount and the op_return of a transaction
    /// @dev                              Finds the BTC amount that has been sent to the locking script
    ///                                   Assumes that payload size is less than 76 bytes
    /// @param _vout                      The vout of a Bitcoin transaction
    /// @param _lockingScript             Desired locking script
    /// @return bitcoinAmount             Amount of BTC have been sent to the _lockingScript
    /// @return arbitraryData             Opreturn  data of the transaction
    function parseValueAndDataHavingLockingScript(
        bytes memory _vout,
        bytes memory _lockingScript
    ) internal view returns (uint64, bytes memory) {
        // Checks that vout is not null
        bytes29 voutView = tryAsVout(_vout.ref(uint40(BTCTypes.Unknown)));
        require(!voutView.isNull(), "BitcoinHelper: vout is null");
        return parseValueAndDataHavingLockingScript(voutView, _lockingScript);
    }

    /// @notice                           Parses the BTC amount and the op_return of a transaction
    /// @dev                              Finds the BTC amount that has been sent to the locking script
    ///                                   Assumes that payload size is less than 80 bytes
    /// @param _voutView                  The vout of a Bitcoin transaction
    /// @param _lockingScript             Desired locking script
    /// @return bitcoinAmount             Amount of BTC have been sent to the _lockingScript
    /// @return arbitraryData             Opreturn  data of the transaction
    function parseValueAndDataHavingLockingScript(
        bytes29 _voutView,
        bytes memory _lockingScript
    ) internal view typeAssert(_voutView, BTCTypes.Vout) returns (uint64 bitcoinAmount, bytes memory arbitraryData) {
        bytes29 output;
        bytes29 _scriptPubkey;
        bytes29 _scriptPubkeyWithLength;
        bytes29 _arbitraryData;

        // Finds total number of outputs
        uint _numberOfOutputs = uint256(indexCompactInt(_voutView, 0));

        for (uint index = 0; index < _numberOfOutputs; index++) {
            output = indexVout(_voutView, index);
            _scriptPubkey = scriptPubkey(output);
            _scriptPubkeyWithLength = scriptPubkeyWithLength(output);
            _arbitraryData = opReturnPayload(_scriptPubkeyWithLength);

            // Checks whether the output is an arbitarary data or not
            if(_arbitraryData == TypedMemView.NULL) {
                // Output is not an arbitrary data
                if (
                    keccak256(abi.encodePacked(_scriptPubkey.clone())) == keccak256(abi.encodePacked(_lockingScript))
                ) {
                    bitcoinAmount = value(output);
                }
            } else {
                // Returns the whole bytes array
                arbitraryData = _arbitraryData.clone();
            }
        }
    }

    /// @notice                           Parses the BTC amount and the op_return of a transaction
    /// @dev                              Finds the BTC amount that payload size is less than 80 bytes
    /// @param _voutView                  The vout of a Bitcoin transaction
    /// @return bitcoinAmount             Amount of BTC
    /// @return arbitraryData             Opreturn data of the transaction
    function parseToScriptValueAndData(
        bytes29 _voutView,
        bytes memory _script
    ) internal pure typeAssert(_voutView, BTCTypes.Vout) returns (uint64 bitcoinAmount, bytes29 arbitraryData, uint256 outputIndex) {
        bytes29 _outputView;
        bytes29 _scriptPubkeyView;
        bytes29 _scriptPubkeyWithLength;
        bytes29 _arbitraryData;

        // Finds total number of outputs
        uint _numberOfOutputs = uint256(indexCompactInt(_voutView, 0));

        for (uint index = 0; index < _numberOfOutputs; index++) {
            _outputView = indexVout(_voutView, index);
            _scriptPubkeyView = scriptPubkey(_outputView);
            _scriptPubkeyWithLength = scriptPubkeyWithLength(_outputView);
            _arbitraryData = opReturnPayload(_scriptPubkeyWithLength);

            // Checks whether the output is an arbitarary data or not
            if(_arbitraryData == TypedMemView.NULL) {
                // Output is not an arbitrary data
                if (
                    (_scriptPubkeyView.len() == 23 && 
                    _scriptPubkeyView.indexUint(0, 1) == 0xa9 &&
                    _scriptPubkeyView.indexUint(1, 1) == 0x14 &&
                    _scriptPubkeyView.indexUint(22, 1) == 0x87 &&
                    bytes20(_scriptPubkeyView.indexAddress(2)) == ripemd160(abi.encode(sha256(_script)))) ||
                    (_scriptPubkeyView.len() == 34 && 
                    _scriptPubkeyView.indexUint(0, 1) == 0 &&
                    _scriptPubkeyView.indexUint(1, 1) == 32 &&
                    _scriptPubkeyView.index(2, 32) == sha256(_script))
                ) {
                    bitcoinAmount = value(_outputView);
                    outputIndex = index;
                }
            } else {
                // Returns the whole bytes array
                arbitraryData = _arbitraryData;
            }
        }
    }

    /// @notice             extracts the scriptPubkey from an output
    /// @param _output      the output
    /// @return             the scriptPubkey
    function scriptPubkey(bytes29 _output) internal pure typeAssert(_output, BTCTypes.TxOut) returns (bytes29) {
        uint64 scriptLength = indexCompactInt(_output, 8);
        return _output.slice(8 + compactIntLength(scriptLength), scriptLength, uint40(BTCTypes.ScriptPubkey));
    }

    /// @notice             extracts the scriptPubkey from an output
    /// @param _output      the output
    /// @return             the scriptPubkey
    function scriptPubkeyWithLength(bytes29 _output) internal pure typeAssert(_output, BTCTypes.TxOut) returns (bytes29) {
        uint64 scriptLength = indexCompactInt(_output, 8);
        return _output.slice(8, compactIntLength(scriptLength) + scriptLength, uint40(BTCTypes.ScriptPubkey));
    }

    /// @notice                           Parses locking script from an output
    /// @dev                              Reverts if vout is null
    /// @param _vout                      The vout of a Bitcoin transaction
    /// @param _index                     Index of the output that we are looking at
    /// @return _lockingScript            Parsed locking script
    function getLockingScript(
        bytes memory _vout,
        uint _index
    ) internal view returns (bytes memory) {
        bytes29 vout = tryAsVout(_vout.ref(uint40(BTCTypes.Unknown)));
        require(!vout.isNull(), "BitcoinHelper: vout is null");
        return getLockingScript(vout, _index);
    }

    /// @notice                           Parses locking script from an output
    /// @dev                              Reverts if vout is null
    /// @param _voutView                  The vout of a Bitcoin transaction
    /// @param _index                     Index of the output that we are looking at
    /// @return _lockingScript            Parsed locking script
    function getLockingScript(
        bytes29 _voutView,
        uint _index
    ) internal view returns (bytes memory _lockingScript) {
        bytes29 output = indexVout(_voutView, _index);
        bytes29 _lockingScriptBytes29 = scriptPubkey(output);
        _lockingScript = _lockingScriptBytes29.clone();
    }

    /// @notice                   Returns number of outputs in a vout
    /// @param _vout              The vout of a Bitcoin transaction
    function numberOfOutputs(bytes memory _vout) internal pure returns (uint) {
        bytes29 voutView = tryAsVout(_vout.ref(uint40(BTCTypes.Unknown)));
        require(!voutView.isNull(), "BitcoinHelper: vout is null");
        return numberOfOutputs(voutView);
    }

    /// @notice                   Returns number of outputs in a vout
    /// @param _voutView          The vout of a Bitcoin transaction
    function numberOfOutputs(bytes29 _voutView) internal pure typeAssert(_voutView, BTCTypes.Vout) returns (uint _numberOfOutputs) {
        _numberOfOutputs = uint256(indexCompactInt(_voutView, 0));
    }

    /// @notice             determines the length of the first output in an array of outputs
    /// @param _outputs     the vout without its length prefix
    /// @return             the output length
    function outputLength(bytes29 _outputs) private pure typeAssert(_outputs, BTCTypes.IntermediateTxOuts) returns (uint256) {
        uint64 scriptLength = indexCompactInt(_outputs, 8);
        return uint256(compactIntLength(scriptLength)) + uint256(scriptLength) + 8;
    }

    /// @notice         extracts the output at a specified index
    /// @param _vout    the vout
    /// @param _index   the index of the desired output
    /// @return         the desired output
    function indexVout(bytes29 _vout, uint256 _index) internal pure typeAssert(_vout, BTCTypes.Vout) returns (bytes29) {
        uint256 _nOuts = uint256(indexCompactInt(_vout, 0));
        uint256 _viewLen = _vout.len();
        require(_index < _nOuts, "Vout read overrun");

        uint256 _offset = uint256(compactIntLength(uint64(_nOuts)));
        bytes29 _remaining;
        for (uint256 _i = 0; _i < _index; _i += 1) {
            _remaining = _vout.postfix(_viewLen - _offset, uint40(BTCTypes.IntermediateTxOuts));
            _offset += outputLength(_remaining);
        }

        _remaining = _vout.postfix(_viewLen - _offset, uint40(BTCTypes.IntermediateTxOuts));
        uint256 _len = outputLength(_remaining);
        return _vout.slice(_offset, _len, uint40(BTCTypes.TxOut));
    }

    /// @notice             extracts the Op Return Payload
    /// @dev                structure of the input is: 1 byte op return + 2 bytes indicating the length of payload + max length for op return payload is 80 bytes
    /// @param _skp         the scriptPubkey
    /// @return             the Op Return Payload (or null if not a valid Op Return output)
    function opReturnPayload(bytes29 _skp) internal pure typeAssert(_skp, BTCTypes.ScriptPubkey) returns (bytes29) {
        uint64 _bodyLength = indexCompactInt(_skp, 0);
        if (_skp.indexUint(1, 1) == 0x6a) {
            if (_skp.indexUint(2, 1) == 0x4c) {
                uint64 _payloadLen = _skp.indexUint(3, 1).toUint64();
                require(_payloadLen == _bodyLength - 3 && 
                    _bodyLength <= 83 && _bodyLength >= 79, "BitcoinHelper: invalid opreturn");
                return _skp.slice(4, _payloadLen, uint40(BTCTypes.OpReturnPayload));
            } else {
                uint64 _payloadLen = _skp.indexUint(2, 1).toUint64();
                require(_payloadLen == _bodyLength - 2 && 
                    _bodyLength <= 77 && _bodyLength >= 4, "BitcoinHelper: invalid opreturn");
                return _skp.slice(3, _payloadLen, uint40(BTCTypes.OpReturnPayload));
            }
        }
        return TypedMemView.nullView();
    }

    /// @notice     verifies the vin and converts to a typed memory
    /// @dev        will return null in error cases
    /// @param _vin the vin
    /// @return     the typed vin (or null if error)
    function tryAsVin(bytes29 _vin) internal pure typeAssert(_vin, BTCTypes.Unknown) returns (bytes29) {
        if (getVinLength(_vin) != _vin.len()) {
            return TypedMemView.nullView();
        }
        return _vin.castTo(uint40(BTCTypes.Vin));
    }


    /// @notice         verifies the vout and converts to a typed memory
    /// @dev            will return null in error cases
    /// @param _vout    the vout
    /// @return         the typed vout (or null if error)
    function tryAsVout(bytes29 _vout) internal pure typeAssert(_vout, BTCTypes.Unknown) returns (bytes29) {
        if (getVoutLength(_vout) != _vout.len()) {
            return TypedMemView.nullView();
        }
        return _vout.castTo(uint40(BTCTypes.Vout));
    }

    /// @notice         verifies the header and converts to a typed memory
    /// @dev            will return null in error cases
    /// @param _header  the header
    /// @return         the typed header (or null if error)
    function tryAsHeader(bytes29 _header) internal pure typeAssert(_header, BTCTypes.Unknown) returns (bytes29) {
        if (_header.len() != 80) {
            return TypedMemView.nullView();
        }
        return _header.castTo(uint40(BTCTypes.Header));
    }


    /// @notice         Index a header array.
    /// @dev            Errors on overruns
    /// @param _arr     The header array
    /// @param index    The 0-indexed location of the header to get
    /// @return         the typed header at `index`
    function indexHeaderArray(bytes29 _arr, uint256 index) internal pure typeAssert(_arr, BTCTypes.HeaderArray) returns (bytes29) {
        uint256 _start = index * 80;
        return _arr.slice(_start, 80, uint40(BTCTypes.Header));
    }


    /// @notice     verifies the header array and converts to a typed memory
    /// @dev        will return null in error cases
    /// @param _arr the header array
    /// @return     the typed header array (or null if error)
    function tryAsHeaderArray(bytes29 _arr) internal pure typeAssert(_arr, BTCTypes.Unknown) returns (bytes29) {
        if (_arr.len() % 80 != 0) {
            return TypedMemView.nullView();
        }
        return _arr.castTo(uint40(BTCTypes.HeaderArray));
    }

    /// @notice     verifies the merkle array and converts to a typed memory
    /// @dev        will return null in error cases
    /// @param _arr the merkle array
    /// @return     the typed merkle array (or null if error)
    function tryAsMerkleArray(bytes29 _arr) internal pure typeAssert(_arr, BTCTypes.Unknown) returns (bytes29) {
        if (_arr.len() % 32 != 0) {
            return TypedMemView.nullView();
        }
        return _arr.castTo(uint40(BTCTypes.MerkleArray));
    }

    /// @notice         extracts the merkle root from the header
    /// @param _header  the header
    /// @return         the merkle root
    function merkleRoot(bytes29 _header) internal pure typeAssert(_header, BTCTypes.Header) returns (bytes32) {
        return _header.index(36, 32);
    }

    /// @notice         extracts the target from the header
    /// @param _header  the header
    /// @return         the target
    function target(bytes29  _header) internal pure typeAssert(_header, BTCTypes.Header) returns (uint256) {
        uint256 _mantissa = _header.indexLEUint(72, 3);
        require(_header.indexUint(75, 1) > 2, "ViewBTC: invalid target difficulty");
        uint256 _exponent = _header.indexUint(75, 1) - 3;
        return _mantissa * (256 ** _exponent);
    }

    /// @notice         calculates the difficulty from a target
    /// @param _target  the target
    /// @return         the difficulty
    function toDiff(uint256  _target) private pure returns (uint256) {
        return DIFF1_TARGET / (_target);
    }

    /// @notice         extracts the difficulty from the header
    /// @param _header  the header
    /// @return         the difficulty
    function diff(bytes29  _header) internal pure typeAssert(_header, BTCTypes.Header) returns (uint256) {
        return toDiff(target(_header));
    }

    /// @notice         extracts the timestamp from the header
    /// @param _header  the header
    /// @return         the timestamp
    function time(bytes29  _header) internal pure typeAssert(_header, BTCTypes.Header) returns (uint32) {
        return uint32(_header.indexLEUint(68, 4));
    }

    /// @notice         extracts the parent hash from the header
    /// @param _header  the header
    /// @return         the parent hash
    function parent(bytes29 _header) internal pure typeAssert(_header, BTCTypes.Header) returns (bytes32) {
        return _header.index(4, 32);
    }

    /// @notice                     Checks validity of header chain
    /// @dev                        Compares current header parent to previous header's digest
    /// @param _header              The raw bytes header
    /// @param _prevHeaderDigest    The previous header's digest
    /// @return                     true if the connect is valid, false otherwise
    function checkParent(bytes29 _header, bytes32 _prevHeaderDigest) internal pure typeAssert(_header, BTCTypes.Header) returns (bool) {
        return parent(_header) == _prevHeaderDigest;
    }

    /// @notice                     Validates a tx inclusion in the block
    /// @dev                        `index` is not a reliable indicator of location within a block
    /// @param _txid                The txid (LE)
    /// @param _merkleRoot          The merkle root
    /// @param _intermediateNodes   The proof's intermediate nodes (digests between leaf and root)
    /// @param _index               The leaf's index in the tree (0-indexed)
    /// @return                     true if fully valid, false otherwise
    function prove(
        bytes32 _txid,
        bytes32 _merkleRoot,
        bytes29 _intermediateNodes,
        uint _index
    ) internal view typeAssert(_intermediateNodes, BTCTypes.MerkleArray) returns (bool) {
        // Shortcut the empty-block case
        if (
            _txid == _merkleRoot &&
                _index == 0 &&
                    _intermediateNodes.len() == 0
        ) {
            return true;
        }

        return checkMerkle(_txid, _intermediateNodes, _merkleRoot, _index);
    }

    /// @notice         verifies a merkle proof
    /// @dev            leaf, proof, and root are in LE format
    /// @param _leaf    the leaf
    /// @param _proof   the proof nodes
    /// @param _root    the merkle root
    /// @param _index   the index
    /// @return         true if valid, false if otherwise
    function checkMerkle(
        bytes32 _leaf,
        bytes29 _proof,
        bytes32 _root,
        uint256 _index
    ) private view typeAssert(_proof, BTCTypes.MerkleArray) returns (bool) {
        require(_root != bytes32(0), "BitcoinHelper: zero root");

        uint256 nodes = _proof.len() / 32;
        if (nodes == 0) {
            return _leaf == _root;
        }

        uint256 _idx = _index;
        bytes32 _current = _leaf;

        for (uint i = 0; i < nodes; i++) {
            bytes32 _next = _proof.index(i * 32, 32);
            if (_idx % 2 == 1) {
                _current = merkleStep(_next, _current);
            } else {
                _current = merkleStep(_current, _next);
            }
            _idx >>= 1;
        }

        return _current == _root;
    }

    /// @notice          Concatenates and hashes two inputs for merkle proving
    /// @dev             Not recommended to call directly.
    /// @param _a        The first hash
    /// @param _b        The second hash
    /// @return digest   The double-sha256 of the concatenated hashes
    function merkleStep(bytes32 _a, bytes32 _b) private view returns (bytes32 digest) {
        assembly {
        // solium-disable-previous-line security/no-inline-assembly
            let ptr := mload(0x40)
            mstore(ptr, _a)
            mstore(add(ptr, 0x20), _b)
            pop(staticcall(gas(), 2, ptr, 0x40, ptr, 0x20)) // sha256 #1
            pop(staticcall(gas(), 2, ptr, 0x20, ptr, 0x20)) // sha256 #2
            digest := mload(ptr)
        }
    }

    /// @notice                 performs the bitcoin difficulty retarget
    /// @dev                    implements the Bitcoin algorithm precisely
    /// @param _previousTarget  the target of the previous period
    /// @param _firstTimestamp  the timestamp of the first block in the difficulty period
    /// @param _secondTimestamp the timestamp of the last block in the difficulty period
    /// @return                 the new period's target threshold
    function retargetAlgorithm(
        uint256 _previousTarget,
        uint256 _firstTimestamp,
        uint256 _secondTimestamp
    ) internal pure returns (uint256) {
        uint256 _elapsedTime = _secondTimestamp - _firstTimestamp;

        // Normalize ratio to factor of 4 if very long or very short
        if (_elapsedTime < RETARGET_PERIOD / 4) {
            _elapsedTime = RETARGET_PERIOD / 4;
        }
        if (_elapsedTime > RETARGET_PERIOD * 4) {
            _elapsedTime = RETARGET_PERIOD * 4;
        }

        /*
            NB: high targets e.g. ffff0020 can cause overflows here
                so we divide it by 256**2, then multiply by 256**2 later
                we know the target is evenly divisible by 256**2, so this isn't an issue
        */
        uint256 _adjusted = _previousTarget / 65536 * _elapsedTime;
        return _adjusted / RETARGET_PERIOD * 65536;
    }

    /// @notice             returns size of vin
    /// @param _vinView     the vin
    /// @return             the size of vin
    function getVinLength(bytes29 _vinView) internal pure returns (uint256) {
        if (_vinView.len() == 0) {
            return 0;
        }
        uint64 _nIns = indexCompactInt(_vinView, 0);
        uint256 _viewLen = _vinView.len();
        if (_nIns == 0) {
            return 0;
        }

        uint256 _offset = uint256(compactIntLength(_nIns));
        for (uint256 i = 0; i < _nIns; i++) {
            if (_offset >= _viewLen) {
                // We've reached the end, but are still trying to read more
                return 0;
            }
            bytes29 _remaining = _vinView.postfix(_viewLen - _offset, uint40(BTCTypes.IntermediateTxIns));
            _offset += inputLength(_remaining);
        }
        return _offset;
    }

    /// @notice             returns size of vout
    /// @param _voutView    the vout
    /// @return             the size of vout
    function getVoutLength(bytes29 _voutView) internal pure returns (uint256) {
        if (_voutView.len() == 0) {
            return 0;
        }
        uint64 _nOuts = indexCompactInt(_voutView, 0);

        uint256 _viewLen = _voutView.len();
        if (_nOuts == 0) {
            return 0;
        }

        uint256 _offset = uint256(compactIntLength(_nOuts));
        for (uint256 i = 0; i < _nOuts; i++) {
            if (_offset >= _viewLen) {
                // We've reached the end, but are still trying to read more
                return 0;
            }
            bytes29 _remaining = _voutView.postfix(_viewLen - _offset, uint40(BTCTypes.IntermediateTxOuts));
            _offset += outputLength(_remaining);
        }
        return _offset;
    }

    /// @notice             extracts tx details from the given tx bytes
    /// @param _tx          the transaction bytes
    /// @return _version    parsed tx version
    /// @return _vinView    parsed tx vin
    /// @return _voutView   parsed tx vout
    /// @return _lockTime   parsed tx lock time
    function extractTx(bytes memory _tx) internal pure returns (uint32 _version, bytes29 _vinView, bytes29 _voutView, uint32 _lockTime) {
        bytes29 _txView = _tx.ref(uint40(BTCTypes.Unknown));

        _version = _txView.indexLEUint(0, 4).toUint32();
        uint256 _offset = 4;

        bytes29 _remaining = _txView.postfix(_txView.len() - _offset, uint40(BTCTypes.Unknown));
        uint256 _vinLen = getVinLength(_remaining);
        _vinView = _txView.slice(_offset, _vinLen, uint40(BTCTypes.Vin));
        _offset += _vinLen;

        _remaining = _txView.postfix(_txView.len() - _offset, uint40(BTCTypes.Unknown));
        uint256 _voutLen = getVoutLength(_remaining);
        _voutView = _txView.slice(_offset, _voutLen, uint40(BTCTypes.Vout));
        _offset += _voutLen;

        _lockTime = _txView.indexLEUint(_offset, 4).toUint32();
        require(_offset + 4 == _txView.len(), "BitcoinHelper: invalid tx");
    }
}
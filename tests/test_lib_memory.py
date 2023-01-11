import pytest
from web3 import Web3


@pytest.mark.parametrize("length", [0, 10, 32, 33])
def test_copy(test_lib_memory, length):
    data = b"d8as98d9asdasudpioj12je3kl12j3kl12a14c"
    data_copy = test_lib_memory.testCopy(data, length)
    assert Web3.toHex(data[:length]) == str(data_copy)

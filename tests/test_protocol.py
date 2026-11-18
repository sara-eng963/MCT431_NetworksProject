import pytest
from protocol import encode_atr, decode_atr, slip_encode, SlipDecoder

@pytest.mark.parametrize('size', [0, 6, 16, 64, 128])
def test_fragmented_wire_round_trip(size):
    payload = bytes((192+i) % 256 for i in range(size))
    decoder = SlipDecoder()
    frames = []
    for byte in slip_encode(encode_atr(payload, 192, 7)):
        frames.extend(decoder.feed(bytes([byte])))
    assert len(frames) == 1
    assert decode_atr(frames[0]) == (7, 192, payload)

def test_known_crc_vector():
    assert encode_atr(bytes(range(16)), 0, 0x1234).hex() == '1234000000000010000102030405060708090a0b0c0d0e0f5a74'

def test_corruption_and_truncation():
    data = bytearray(encode_atr(bytes(range(16))))
    data[8] ^= 1
    with pytest.raises(ValueError, match='CRC'):
        decode_atr(data)
    with pytest.raises(ValueError, match='length'):
        decode_atr(data[:-1])

def test_decoder_recovers_from_noise_invalid_escape_and_overflow():
    decoder = SlipDecoder()
    good = encode_atr(b'hello')
    data = b'boot text' + b'\xc0\xdb\xaa\xc0' + b'x'*200 + slip_encode(good)*2
    assert decoder.feed(data) == [good, good]
    assert decoder.errors == 2

def test_dangling_escape_is_not_a_valid_frame():
    decoder = SlipDecoder()
    assert decoder.feed(b'\xc0abc\xdb\xc0') == []
    assert decoder.errors == 1

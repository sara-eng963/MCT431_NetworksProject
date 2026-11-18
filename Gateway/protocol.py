"""Production serial wire protocol. All integer fields are big-endian."""
import binascii
import struct

STATUS = struct.Struct('>BBIIII')
COMMAND = struct.Struct('>BIIIBII')
EVENT = struct.Struct('>BIIBBB')
PART = struct.Struct('>BIIQIB')
PART_ACK = struct.Struct('>BIIQ')
HEARTBEAT = struct.Struct('>BI')
STATES = {0: 'IDLE', 1: 'RUNNING', 2: 'PAUSED', 3: 'FAULT'}
OPS = {'configure': 1, 'start': 2, 'pause': 3, 'resume': 4, 'stop': 5}
PHASES = {1: 'delivery', 2: 'acceptance', 3: 'completion'}
RESULTS = {0: 'OK', 1: 'INVALID', 2: 'STATE', 3: 'STALE', 4: 'CONFLICT'}

def encode_atr(payload, seq=0, test_id=0):
    if len(payload) > 128:
        raise ValueError('Payload exceeds 128 bytes')
    data = struct.pack('>HIH', test_id, seq, len(payload)) + payload
    return data + struct.pack('>H', binascii.crc_hqx(data, 0xffff))

def decode_atr(data):
    if len(data) < 10:
        raise ValueError('ATR too short')
    test_id, seq, size = struct.unpack('>HIH', data[:8])
    if size > 128 or len(data) != size + 10:
        raise ValueError('ATR length mismatch')
    if binascii.crc_hqx(data[:-2], 0xffff) != int.from_bytes(data[-2:], 'big'):
        raise ValueError('ATR CRC mismatch')
    return test_id, seq, data[8:-2]

def slip_encode(data):
    return b'\xc0' + data.replace(b'\xdb', b'\xdb\xdd').replace(b'\xc0', b'\xdb\xdc') + b'\xc0'

class SlipDecoder:
    def __init__(self):
        self.frame = bytearray()
        self.active = False
        self.escaped = False
        self.errors = 0

    def feed(self, data):
        frames = []
        for byte in data:
            if byte == 0xc0:
                if self.active and self.frame and not self.escaped:
                    frames.append(bytes(self.frame))
                elif self.escaped:
                    self.errors += 1
                self.frame.clear()
                self.active, self.escaped = True, False
            elif self.active:
                if self.escaped:
                    self.escaped = False
                    if byte not in (0xdc, 0xdd):
                        self.errors += 1
                        self.active = False
                        continue
                    self.frame.append(0xc0 if byte == 0xdc else 0xdb)
                elif byte == 0xdb:
                    self.escaped = True
                else:
                    self.frame.append(byte)
                if len(self.frame) > 138:
                    self.errors += 1
                    self.active = False
                    self.frame.clear()
        return frames

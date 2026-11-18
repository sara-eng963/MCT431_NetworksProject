"""Length-prefixed production TCP messages for inspection station B."""
import struct

CONFIGURE=struct.Struct('>BIIIIII')
JOB=struct.Struct('>BIIIQ')
REPLY=struct.Struct('>BIIBBBQ')
STATUS=struct.Struct('>BBIIIIII4x')
HEARTBEAT=struct.Struct('>BI')
RESET=struct.Struct('>BII')
MAX_MESSAGE=128

def frame(payload):
    if not 1<=len(payload)<=MAX_MESSAGE:
        raise ValueError('Invalid TCP payload length')
    return struct.pack('>H',len(payload))+payload

class Decoder:
    def __init__(self): self.buffer=bytearray()
    def feed(self,data):
        self.buffer.extend(data)
        messages=[]
        while len(self.buffer)>=2:
            length=int.from_bytes(self.buffer[:2],'big')
            if not 1<=length<=MAX_MESSAGE:
                self.buffer.clear()
                raise ValueError('Invalid TCP payload length; close connection')
            if len(self.buffer)<length+2: break
            messages.append(bytes(self.buffer[2:2+length]))
            del self.buffer[:length+2]
        return messages

"""Real Python gateway talks through SLIP/ATR to compiled C firmware logic."""
import ctypes
import subprocess
import sys
import threading
import time
from pathlib import Path

from production_cli import Gateway
from protocol import COMMAND, PART, SlipDecoder, decode_atr, encode_atr, slip_encode

ROOT=Path(__file__).resolve().parents[1]

def test_real_gateway_and_c_controller_with_lost_part_ack(tmp_path):
    library=tmp_path/'controller.dll'
    subprocess.run([sys.executable,'-m','ziglang','cc','-shared','-std=c11','-Wall','-Wextra','-Werror',
                    '-I',str(ROOT/'Production_ESP/main'),str(ROOT/'tests/controller_bridge.c'),
                    str(ROOT/'Production_ESP/main/controller.c'),str(ROOT/'Production_ESP/main/production.c'),
                    '-o',str(library)],check=True)
    dll=ctypes.CDLL(str(library))
    callback_type=ctypes.CFUNCTYPE(None,ctypes.POINTER(ctypes.c_uint8),ctypes.c_size_t,ctypes.c_void_p)
    dll.bridge_init.argtypes=[callback_type]
    dll.bridge_receive.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.c_int64]
    dll.bridge_tick.argtypes=[ctypes.c_int64]

    class Wire:
        def __init__(self):
            self.lock=threading.RLock()
            self.output=bytearray()
            self.decoder=SlipDecoder()
            self.now=0
            self.dropped=False
            self.duplicated_start=False
            self.seq=0
            self.callback=callback_type(self.emit)
            dll.bridge_init(self.callback)

        def emit(self,payload,size,context):
            self.output.extend(slip_encode(encode_atr(ctypes.string_at(payload,size),self.seq)))
            self.seq+=1

        @property
        def in_waiting(self):
            with self.lock: return len(self.output)

        def read(self,n):
            time.sleep(0.001)
            with self.lock:
                self.now+=1000
                dll.bridge_tick(self.now)
                data=bytes(self.output[:n])
                del self.output[:n]
                return data

        def write(self,data):
            with self.lock:
                for frame in self.decoder.feed(data):
                    _,_,payload=decode_atr(frame)
                    if payload[0]==5 and not self.dropped:
                        self.dropped=True
                        continue
                    dll.bridge_receive(payload,len(payload),self.now)
                    if payload[0]==2 and COMMAND.unpack(payload)[4]==2 and not self.duplicated_start:
                        self.duplicated_start=True
                        dll.bridge_receive(payload,len(payload),self.now)
            return len(data)

    wire=Wire()
    gateway=Gateway(wire,tmp_path/'integration.jsonl')
    thread=threading.Thread(target=gateway.pump,daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+8
        while gateway.boot is None and time.monotonic()<deadline:
            time.sleep(0.01)
        assert gateway.boot==123
        gateway.command('configure',10,50)
        gateway.command('start')
        while len(gateway.parts)<10 and not gateway.failure and time.monotonic()<deadline:
            time.sleep(0.01)
        assert gateway.failure is None
        assert len(gateway.parts)==10
        assert [PART.unpack(p)[4] for p in gateway.parts.values()]==list(range(1,11))
        assert wire.dropped and wire.duplicated_start
        log=(tmp_path/'integration.jsonl').read_text()
        assert 'part_duplicate' in log
    finally:
        gateway.running=False
        thread.join(timeout=2)
        gateway.log_file.close()

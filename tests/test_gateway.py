import threading
import pytest
from production_cli import Gateway
from protocol import STATUS, PART, EVENT, decode_atr, encode_atr, SlipDecoder

class SerialStub:
    def __init__(self): self.writes = []
    def write(self, data):
        self.writes.append(data)
        return len(data)

@pytest.fixture
def gateway(tmp_path):
    g = Gateway(SerialStub(), tmp_path/'events.jsonl')
    g.handle(STATUS.pack(1, 0, 123, 7, 0, 0))
    yield g
    g.log_file.close()

def test_duplicate_part_is_counted_once_but_acknowledged_again(gateway):
    packet = PART.pack(4, 123, 7, 99, 1, 0)
    gateway.handle(packet)
    gateway.handle(packet)
    assert len(gateway.parts) == 1
    assert len(gateway.uart.writes) == 2
    frames = SlipDecoder().feed(gateway.uart.writes[0])
    assert decode_atr(frames[0])[2][0] == 5

def test_conflicting_duplicate_is_fatal(gateway):
    gateway.handle(PART.pack(4, 123, 7, 99, 1, 0))
    with pytest.raises(RuntimeError, match='Conflicting'):
        gateway.handle(PART.pack(4, 123, 7, 99, 2, 0))

def test_old_batch_or_boot_is_not_acknowledged(gateway):
    gateway.handle(PART.pack(4, 122, 7, 99, 1, 0))
    gateway.handle(PART.pack(4, 123, 6, 99, 1, 0))
    assert not gateway.parts and not gateway.uart.writes

def test_reboot_requires_explicit_reconnect(gateway):
    with pytest.raises(RuntimeError, match='restarted'):
        gateway.handle(STATUS.pack(1, 0, 124, 0, 0, 0))

def test_acceptance_does_not_finish_command(gateway):
    gateway.pending = {'id': 1, 'done': threading.Event(), 'result': None,
                       'operation': 'configure', 'batch': 9}
    gateway.handle(EVENT.pack(3, 123, 1, 1, 0, 0))
    gateway.handle(EVENT.pack(3, 123, 1, 2, 0, 0))
    assert not gateway.pending['done'].is_set()
    gateway.handle(EVENT.pack(3, 123, 1, 3, 0, 0))
    assert gateway.pending['done'].is_set() and gateway.batch == 9

def test_duplicate_and_old_status_do_not_refresh_freshness(gateway):
    payload=STATUS.pack(1,0,123,7,0,0)
    gateway.process_atr(encode_atr(payload,10))
    gateway.last_status=100.0
    gateway.process_atr(encode_atr(payload,10))
    gateway.process_atr(encode_atr(payload,9))
    assert gateway.last_status==100.0
    gateway.process_atr(encode_atr(payload,11))
    assert gateway.last_status!=100.0

def test_reboot_is_detected_even_when_transport_sequence_restarts(gateway):
    gateway.process_atr(encode_atr(STATUS.pack(1,0,123,7,0,0),99))
    with pytest.raises(RuntimeError,match='restarted'):
        gateway.process_atr(encode_atr(STATUS.pack(1,0,124,0,0,0),0))

def test_transport_sequence_wrap(gateway):
    payload=STATUS.pack(1,0,123,7,0,0)
    gateway.process_atr(encode_atr(payload,0xffffffff))
    gateway.process_atr(encode_atr(payload,0))
    assert gateway.last_rx_seq==0

import ctypes
import subprocess
import sys
from pathlib import Path
import pytest
from inspection_protocol import CONFIGURE,JOB,REPLY,HEARTBEAT,RESET,frame,Decoder

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def compiled(tmp_path_factory):
    out=tmp_path_factory.mktemp('inspection')/'inspection.dll'
    subprocess.run([sys.executable,'-m','ziglang','cc','-shared','-std=c11','-Wall','-Wextra','-Werror',
                    '-I',str(ROOT/'Inspection_ESP/main'),str(ROOT/'tests/inspection_bridge.c'),
                    str(ROOT/'Inspection_ESP/main/inspection.c'),'-o',str(out)],check=True)
    return ctypes.CDLL(str(out))

@pytest.fixture
def station(compiled):
    messages=[]
    callback_type=ctypes.CFUNCTYPE(None,ctypes.POINTER(ctypes.c_uint8),ctypes.c_size_t,ctypes.c_void_p)
    callback=callback_type(lambda p,n,ctx:messages.append(ctypes.string_at(p,n)))
    compiled.bridge_init.argtypes=[callback_type]
    compiled.bridge_receive.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.c_int64]
    compiled.bridge_tick.argtypes=[ctypes.c_int64]
    compiled.bridge_init(callback)
    def send(payload,now=0): compiled.bridge_receive(payload,len(payload),now)
    def replies(): return [REPLY.unpack(m) for m in messages if m[0]==18]
    yield send,compiled.bridge_tick,compiled.bridge_disconnect,messages,replies

def test_tcp_fragmentation_and_coalescing():
    data=frame(b'hello')+frame(b'world')
    decoder=Decoder();result=[]
    for byte in data: result.extend(decoder.feed(bytes([byte])))
    assert result==[b'hello',b'world']
    assert Decoder().feed(data)==result
    with pytest.raises(ValueError): Decoder().feed(b'\x00\x00')
    with pytest.raises(ValueError): Decoder().feed(b'\xff\xff')

@pytest.mark.parametrize('part,k,n,expected',[(5,0,5,2),(6,0,5,1),(4,1,5,2),((1<<64)-1,1,5,1)])
def test_runtime_rule_delay_and_duplicate_replay(station,part,k,n,expected):
    send,tick,_,messages,replies=station
    send(CONFIGURE.pack(16,456,1,7,100,n,k))
    job=JOB.pack(17,456,2,7,part)
    send(job);send(job)
    assert not [r for r in replies() if r[2]==2 and r[3]==3]
    tick(99999)
    assert not [r for r in replies() if r[2]==2 and r[3]==3]
    tick(100000)
    complete=[r for r in replies() if r[2]==2 and r[3]==3]
    assert len(complete)==1 and complete[0][5:]==(expected,part)
    send(job,200000)
    assert [r for r in replies() if r[2]==2 and r[3]==3][-1]==complete[0]

def test_invalid_configuration_and_stale_boot(station):
    send,_,_,messages,replies=station
    send(CONFIGURE.pack(16,455,1,7,100,5,0));assert not messages
    send(CONFIGURE.pack(16,456,1,7,100,0,0));assert replies()[-1][4]==1

def test_busy_conflicting_job_cannot_replace_active_completion(station):
    send,tick,_,_,replies=station
    send(CONFIGURE.pack(16,456,1,7,100,5,0))
    send(JOB.pack(17,456,2,7,5))
    send(JOB.pack(17,456,2,7,6));assert replies()[-1][4]==4
    send(JOB.pack(17,456,3,7,6));assert replies()[-1][4]==2
    tick(100000)
    assert replies()[-1][2:]==(2,3,0,2,5)

def test_disconnection_fault_and_explicit_reset(station):
    send,tick,disconnect,_,replies=station
    send(CONFIGURE.pack(16,456,1,7,100,5,0))
    job=JOB.pack(17,456,2,7,5)
    send(job);disconnect();tick(100000);send(job)
    assert replies()[-1][4]==2
    assert not [r for r in replies() if r[2]==2 and r[3]==3]
    send(RESET.pack(21,456,3));assert replies()[-1][3:]==(3,0,0,0)
    send(JOB.pack(17,456,4,7,5));assert replies()[-1][4]==3

def test_heartbeat_loss_faults_long_job(station):
    send,tick,_,_,replies=station
    send(CONFIGURE.pack(16,456,1,7,10000,5,0))
    send(JOB.pack(17,456,2,7,5))
    send(HEARTBEAT.pack(19,456),1000000)
    tick(4000001)
    send(JOB.pack(17,456,2,7,5),4000002)
    assert replies()[-1][4]==2

def test_python_client_with_c_inspector_over_tcp_and_lost_completion(compiled,tmp_path):
    import socket
    import threading
    import time
    from inspection_client import InspectionClient
    listener=socket.socket()
    listener.bind(('127.0.0.1',0));listener.listen(1)
    port=listener.getsockname()[1]
    stop=threading.Event();failures=[];dropped=[]
    callback_type=ctypes.CFUNCTYPE(None,ctypes.POINTER(ctypes.c_uint8),ctypes.c_size_t,ctypes.c_void_p)
    def serve():
        try:
            conn,_=listener.accept()
            with conn:
                conn.settimeout(0.01)
                def emit(p,n,ctx):
                    payload=ctypes.string_at(p,n)
                    if payload[0]==18:
                        reply=REPLY.unpack(payload)
                        if reply[2]==3 and reply[3]==3 and not dropped:
                            dropped.append(True);return
                    conn.sendall(frame(payload))
                callback=callback_type(emit)
                compiled.bridge_init.argtypes=[callback_type]
                compiled.bridge_init(callback)
                decoder=Decoder();start=time.monotonic_ns()
                while not stop.is_set():
                    now=(time.monotonic_ns()-start)//1000
                    try:data=conn.recv(512)
                    except socket.timeout:data=None
                    except ConnectionError:break
                    if data==b'':break
                    if data:
                        for payload in decoder.feed(data):
                            compiled.bridge_receive(payload,len(payload),now)
                    compiled.bridge_tick(now)
        except Exception as exc: failures.append(exc)
        finally:listener.close()
    thread=threading.Thread(target=serve,daemon=True);thread.start()
    try:
        with InspectionClient('127.0.0.1',port,log_path=tmp_path/'tcp.jsonl') as client:
            client.reset()  # ID 1
            client.configure(7,10,5,1)  # ID 2
            result=client.inspect(4)  # ID 3; first completion intentionally lost
            assert result=={'identifier':3,'part_id':4,'verdict':2}
            assert client.inspect(5)['verdict']==1
            client.reset()
            stop.set()
            thread.join(timeout=2)
        assert dropped
    finally:
        stop.set();thread.join(timeout=2)
    assert not failures

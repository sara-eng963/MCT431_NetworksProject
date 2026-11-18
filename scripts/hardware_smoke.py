"""Exercise the real production board. This starts/aborts virtual production batches."""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'Gateway'))
import serial
from production_cli import Gateway
from protocol import PART

def wait_for(gateway, condition, timeout=8):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        with gateway.lock:
            if gateway.failure:
                raise RuntimeError(str(gateway.failure))
            if condition():
                return
        time.sleep(0.02)
    raise TimeoutError('Hardware smoke condition did not become true')

def connect(port, path):
    uart = serial.Serial(port=None,baudrate=115200,timeout=0.05,write_timeout=1)
    uart.dtr=False
    uart.rts=False
    uart.port=port
    uart.open()
    g=Gateway(uart,path)
    thread=threading.Thread(target=g.pump,daemon=True)
    thread.start()
    try:
        wait_for(g,lambda:g.boot is not None)
    except Exception:
        close(g,thread)
        raise
    return g,thread

def close(g,thread):
    g.running=False
    thread.join(timeout=2)
    g.uart.close()
    g.log_file.close()

def run(port):
    stamp=time.time_ns()
    logdir=ROOT/'logs'
    g,thread=connect(port,logdir/f'hardware-{stamp}.jsonl')
    results={}
    try:
        if g.batch:
            g.command('stop')
        g.command('configure',10,100)
        batch=g.batch
        g.command('start')
        wait_for(g,lambda:len(g.parts)==10)
        packets=[PART.unpack(p) for p in g.parts.values() if PART.unpack(p)[2]==batch]
        assert [p[4] for p in packets]==list(range(1,11))
        assert sum(p[5] for p in packets)==1 and packets[-1][5]==1
        results['ten_unique_parts']=True
        g.command('configure',20,100)
        g.command('start')
        wait_for(g,lambda:len(g.parts)>=12)
        g.command('pause')
        paused_count=len(g.parts)
        time.sleep(0.4)
        assert len(g.parts)==paused_count
        g.command('resume')
        wait_for(g,lambda:len(g.parts)==30)
        results['pause_resume']=True
        g.command('configure',1000,100)
        g.command('start')
        wait_for(g,lambda:len(g.parts)>=32)
        g.command('stop')
        stopped_count=len(g.parts)
        time.sleep(0.4)
        assert len(g.parts)==stopped_count and g.state==0
        results['stop_aborts']=True
        g.command('configure',1000,100)
        g.command('start')
        wait_for(g,lambda:len(g.parts)>=stopped_count+2)
    finally:
        close(g,thread)
    # Simulate loss of the gateway connection without a STOP.
    time.sleep(4)
    g,thread=connect(port,logdir/f'hardware-{stamp}-reconnect.jsonl')
    try:
        assert g.state==3, 'Station must fault on gateway loss'
        results['connection_loss_fault']=True
        g.command('stop')
        assert g.state==0
        results['explicit_fault_recovery']=True
    finally:
        close(g,thread)
    output=logdir/f'hardware-{stamp}-summary.json'
    output.write_text(json.dumps({'port':port,'results':results},indent=2)+'\n',encoding='utf-8')
    print('HARDWARE PASS:',output)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    run(parser.parse_args().port)

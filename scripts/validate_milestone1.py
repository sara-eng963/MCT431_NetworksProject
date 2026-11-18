"""Live Milestone 1 acceptance checks through HTTP and WebSocket; real ESP32s only."""
import argparse
import csv
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from websockets.sync.client import connect

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial',required=True)
    parser.add_argument('--inspector',required=True)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--output',default='logs/milestone1-20261118/acceptance')
    args=parser.parse_args()
    folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    snapshots=[];results=[];http=[];current=['setup'];stop=threading.Event();ws_errors=[]
    def get():return json.load(urllib.request.urlopen(args.base+'/api/status',timeout=5))
    def post(path,data):
        request=urllib.request.Request(args.base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        try:result=json.load(urllib.request.urlopen(request,timeout=15))
        except urllib.error.HTTPError as exc:raise RuntimeError(exc.read().decode()) from exc
        http.append({'monotonic_ns':time.monotonic_ns(),'path':path,'request':data,'response':result})
        return result
    def command(action,values=None):
        identifier=post('/api/command-id',{})['cmd_id']
        result=post('/api/command',{'cmd_id':identifier,'action':action,'values':values or {}})
        assert result['cmd_id']==identifier and result['phase']=='completion'
        return result
    def config(target,cycle,inspection,n,k,capacity):
        return command('configure',{'target':target,'cycle_ms':cycle,'inspection_ms':inspection,'n':n,'k':k,'capacity':capacity})
    def wait(condition,timeout=15):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            s=get()
            if condition(s):return s
            if s['state']=='Fault':raise RuntimeError(s['fault'])
            time.sleep(.05)
        raise TimeoutError('Acceptance condition did not become true')
    def verify_completed(s):
        assert s['outcome']=='Completed' and s['state']=='Idle'
        assert s['produced']==s['inspected']==s['config']['target']==s['accepted']+s['rejected']
        for part in s['parts']:
            expected='FAIL' if (part['part_id']+s['config']['k'])%s['config']['n']==0 else 'PASS'
            assert part['verdict']==expected and part['job_id'] is not None
        results.append({'case':current[0],'passed':True,'batch_id':s['batch_id'],
                        'produced':s['produced'],'accepted':s['accepted'],'rejected':s['rejected']})
    def listen():
        try:
            with connect(args.base.replace('http://','ws://')+'/ws/status',open_timeout=5) as socket:
                while not stop.is_set():
                    try:s=json.loads(socket.recv(timeout=.5))
                    except TimeoutError:continue
                    snapshots.append({'case':current[0],'monotonic_ns':time.monotonic_ns(),**s})
        except Exception as exc:ws_errors.append(str(exc))
    listener=threading.Thread(target=listen,daemon=True);listener.start()
    try:
        post('/api/connect',{'serial_port':args.serial,'host':args.inspector,'port':9000})
        current[0]='inspection_faster'
        config(12,200,50,5,0,8);command('start')
        verify_completed(wait(lambda s:s['outcome']=='Completed'))
        current[0]='production_faster_with_room'
        config(12,80,180,3,1,16);command('start')
        verify_completed(wait(lambda s:s['outcome']=='Completed'))
        current[0]='pause_resume'
        config(20,120,150,7,3,20);command('start')
        wait(lambda s:s['produced']>=3);command('pause');time.sleep(.25)
        before=get();time.sleep(.35);after=get()
        assert after['state']=='Paused' and after['produced']==before['produced']
        assert after['inspected']==before['inspected']
        command('resume');verify_completed(wait(lambda s:s['outcome']=='Completed'))
        current[0]='stop_aborts'
        config(100,100,150,5,1,20);command('start')
        wait(lambda s:s['produced']>=3);command('stop')
        before=get();time.sleep(.35);after=get()
        assert after['state']=='Idle' and after['outcome']=='Aborted'
        assert after['produced']==before['produced'] and after['inspected']==before['inspected']
        results.append({'case':current[0],'passed':True,'batch_id':after['batch_id']})
        current[0]='queue_full_fault'
        config(100,50,400,4,2,2);command('start')
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            s=get()
            if s['state']=='Fault':break
            time.sleep(.05)
        assert s['state']=='Fault' and 'queue full' in s['fault'].lower() and s['outcome']!='Completed'
        results.append({'case':current[0],'passed':True,'batch_id':s['batch_id'],'fault':s['fault']})
        time.sleep(3.5);command('stop')
        assert get()['state']=='Idle'
        current[0]='recovered_batch_new_rule'
        config(12,180,70,4,2,16);command('start')
        verify_completed(wait(lambda s:s['outcome']=='Completed'))
        assert snapshots and not ws_errors
        print('LIVE MILESTONE 1 ACCEPTANCE PASS:',json.dumps(results),flush=True)
    finally:
        stop.set();listener.join(timeout=2)
        (folder/'results.json').write_text(json.dumps({'results':results,'websocket_errors':ws_errors},indent=2)+'\n',encoding='utf-8')
        (folder/'http.json').write_text(json.dumps(http,indent=2)+'\n',encoding='utf-8')
        with (folder/'status.csv').open('w',newline='',encoding='utf-8') as file:
            fields=['case','monotonic_ns','batch_id','state','produced','inspected','accepted','rejected','waiting','inflight','outcome']
            writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
            for s in snapshots:writer.writerow({key:s[key] for key in fields})

if __name__=='__main__':main()

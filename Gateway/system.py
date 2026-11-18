"""Milestone 1 coordination. The only verdict source is inspection station B."""
import collections
import concurrent.futures
import csv
import json
import queue
import threading
import time
from pathlib import Path

import serial
from production_cli import Gateway
from inspection_client import InspectionClient


class SourceLink:
    def __init__(self, port, folder, on_part):
        self.uart=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=1)
        self.uart.dtr=False;self.uart.rts=False;self.uart.port=port;self.uart.open()
        self.gateway=Gateway(self.uart,folder/f'serial-{time.time_ns()}.jsonl',on_part=on_part)
        self.thread=threading.Thread(target=self.gateway.pump,daemon=True)
        self.thread.start()
        deadline=time.monotonic()+4
        while self.gateway.boot is None and not self.gateway.failure and time.monotonic()<deadline:
            time.sleep(.01)
        if self.gateway.boot is None:
            self.close();raise ConnectionError('Production station did not return a valid status')

    @property
    def last_id(self):return self.gateway.last_cmd
    @property
    def batch(self):return self.gateway.batch
    @property
    def failure(self):return self.gateway.failure
    def command(self,*args,**kwargs):return self.gateway.command(*args,**kwargs)
    def close(self):
        self.gateway.running=False;self.thread.join(timeout=2)
        self.uart.close();self.gateway.log_file.close()


class InspectorLink:
    """Only this worker owns B's socket, including cancellation/reset ordering."""
    def __init__(self, host, port, folder, allocate):
        self.client=InspectionClient(host,port,folder/f'tcp-{time.time_ns()}.jsonl')
        self.allocate=allocate
        self.tasks=queue.Queue()
        self.cancel=threading.Event()
        self.running=True;self.failure=None
        self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()

    @property
    def last_id(self):return self.client.last_id
    def submit(self,op,*args,identifier=None):
        future=concurrent.futures.Future()
        self.tasks.put((future,op,args,identifier));return future
    def work(self):
        try:
            while self.running:
                try:future,op,args,identifier=self.tasks.get(timeout=.02)
                except queue.Empty:
                    self.client.poll();continue
                if future.cancelled():continue
                try:
                    if identifier is None:identifier=self.allocate()
                    if op=='inspect':
                        # Clear cancellation only when the dispatcher explicitly re-enables it.
                        result=self.client.inspect(*args,identifier=identifier,cancel=self.cancel)
                    else:result=getattr(self.client,op)(*args,identifier=identifier)
                    future.set_result(result)
                except InterruptedError as exc:future.set_exception(exc)
                except Exception as exc:
                    future.set_exception(exc);raise
        except Exception as exc:
            self.failure=exc
            while True:
                try:future,*_=self.tasks.get_nowait();future.set_exception(exc)
                except queue.Empty:break
        finally:self.running=False;self.client.close()
    def close(self):
        self.cancel.set();self.running=False;self.thread.join(timeout=2)


class ProductionSystem:
    def __init__(self, folder, source_factory=SourceLink, inspector_factory=InspectorLink):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.operation=threading.Lock()
        self.events=collections.deque(maxlen=200)
        self.event_file=(self.folder/'events.jsonl').open('a',encoding='utf-8',buffering=1)
        self.source_factory=source_factory;self.inspector_factory=inspector_factory
        self.source=None;self.inspector=None;self.serial_port=None;self.host=None;self.port=9000
        self.state='Idle';self.fault=None;self.connected=False;self.configured=False
        self.config={};self.batch=0;self.identifier=0;self.epoch=0
        self.waiting=collections.deque();self.inflight=None;self.records={}
        self.received=0;self.accepted=0;self.rejected=0;self.production_finished=False
        self.outcome='No batch';self.command_cache={};self.active_command=None
        self.reservation=None
        self.running=True
        self.dispatcher=threading.Thread(target=self.dispatch,daemon=True);self.dispatcher.start()

    def event(self,kind,**values):
        with self.lock:
            item={'event':kind,'time_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),**values}
            self.events.append(item);self.event_file.write(json.dumps(item)+'\n')

    def allocate(self):
        with self.lock:
            self.identifier=max(self.identifier,self.source.last_id if self.source else 0,
                                self.inspector.last_id if self.inspector else 0)+1
            if self.identifier>0xffffffff:raise RuntimeError('Identifier space exhausted; restart devices')
            return self.identifier

    def reserve_identifier(self):
        with self.lock:
            if self.reservation and time.monotonic()<self.reservation[1]:
                raise ValueError('Another operator command is being prepared')
            identifier=self.allocate();self.reservation=(identifier,time.monotonic()+5)
            return identifier

    def release_identifier(self,identifier):
        with self.lock:
            if self.reservation and self.reservation[0]==identifier:self.reservation=None

    def connect(self,serial_port,host,port=9000):
        with self.operation:
            with self.lock:
                if self.state in ('Running','Paused'):raise ValueError('Stop the batch before reconnecting')
            self.disconnect()
            self.serial_port=serial_port;self.host=host;self.port=port
            try:
                self.source=self.source_factory(serial_port,self.folder,self.receive_part)
                self.inspector=self.inspector_factory(host,port,self.folder,self.allocate)
                identifier=self.allocate()
                if self.source.batch:self.source.command('stop',cmd_id=identifier)
                self.inspector.submit('reset',identifier=identifier).result(timeout=5)
                with self.lock:
                    self.connected=True;self.state='Idle';self.fault=None
                    self.configured=False;self.outcome='Ready to configure'
                self.event('connected',serial_port=serial_port,host=host,port=port)
            except Exception as exc:
                self.disconnect();self.set_fault(str(exc));raise
            return self.snapshot()

    def disconnect(self):
        with self.lock:self.connected=False;self.configured=False;self.epoch+=1
        if self.source:self.source.close();self.source=None
        if self.inspector:self.inspector.close();self.inspector=None

    def set_fault(self,reason):
        with self.lock:
            if self.state=='Fault':return
            self.state='Fault';self.fault=reason;self.outcome='Fault — batch incomplete'
            self.configured=False;self.epoch+=1
            if self.inspector:self.inspector.cancel.set()
            # Withhold heartbeats: A must stop safely even if its command channel failed.
            if self.source:self.source.gateway.running=False
            self.event('fault',reason=reason,batch_id=self.batch)

    @staticmethod
    def validate_config(values):
        names={'target','cycle_ms','inspection_ms','n','k','capacity'}
        if set(values)!=names:raise ValueError('Supply target, cycle_ms, inspection_ms, n, k and capacity')
        if any(type(v) is not int for v in values.values()):raise ValueError('Configuration values must be integers')
        for key in ('target','n'):
            if not 1<=values[key]<=0xffffffff:raise ValueError(f'{key} must be a positive 32-bit integer')
        if not 0<=values['k']<=0xffffffff:raise ValueError('k must be an unsigned 32-bit integer')
        for key in ('cycle_ms','inspection_ms'):
            if not 10<=values[key]<=3600000:raise ValueError(f'{key} must be 10..3600000 ms')
        if not 1<=values['capacity']<=10000:raise ValueError('Queue capacity must be 1..10000')

    def command(self,action,values=None,cmd_id=None):
        values={} if values is None else values
        with self.operation:
            with self.lock:
                request={'action':action,'values':values}
                if cmd_id is not None and cmd_id in self.command_cache:
                    old,result=self.command_cache[cmd_id]
                    if old!=request:raise ValueError('Identifier reused for a different command')
                    return result
                if action not in ('configure','start','pause','resume','stop'):raise ValueError('Unknown command')
                if not self.connected:raise ValueError('Connect both stations first')
                if action=='configure':
                    self.validate_config(values)
                    if self.state!='Idle':raise ValueError('Configure only while Idle')
                elif values:raise ValueError('Only Configure accepts settings')
                elif action=='start' and (self.state!='Idle' or not self.configured):raise ValueError('Configure before Start')
                elif action=='pause' and self.state!='Running':raise ValueError('Pause requires Running')
                elif action=='resume' and self.state!='Paused':raise ValueError('Resume requires Paused')
            # An explicitly requested Stop may reconnect failed links to perform an abort.
            if action=='stop':
                with self.lock:
                    self.epoch+=1;self.state='Paused';self.inspector.cancel.set();self.connected=False
                try:
                    if self.source.failure or not self.source.gateway.running:
                        self.source.close();self.source=self.source_factory(self.serial_port,self.folder,self.receive_part)
                    if self.inspector.failure or not self.inspector.running:
                        self.inspector.close();self.inspector=self.inspector_factory(self.host,self.port,self.folder,self.allocate)
                    self.connected=True
                except Exception as exc:self.set_fault(str(exc));raise
            if cmd_id is None:cmd_id=self.allocate()
            else:
                with self.lock:
                    reserved=self.reservation and self.reservation[0]==cmd_id and time.monotonic()<self.reservation[1]
                    if not reserved and (type(cmd_id) is not int or not max(self.identifier,self.source.last_id,self.inspector.last_id)<cmd_id<=0xffffffff):
                        raise ValueError('New command ID must exceed all previously used identifiers')
                    self.identifier=max(self.identifier,cmd_id)
                    self.active_command=cmd_id
                    self.release_identifier(cmd_id)
            self.active_command=cmd_id
            self.event('command_delivery',cmd_id=cmd_id,action=action)
            self.event('command_acceptance',cmd_id=cmd_id,action=action)
            try:
                if action=='configure':
                    self.source.command('configure',values['target'],values['cycle_ms'],cmd_id=cmd_id)
                    batch=self.source.batch
                    self.inspector.submit('configure',batch,values['inspection_ms'],values['n'],values['k'],identifier=cmd_id).result(timeout=5)
                    with self.lock:
                        self.epoch+=1;self.config=dict(values);self.batch=batch
                        self.waiting.clear();self.inflight=None;self.records={}
                        self.received=self.accepted=self.rejected=0;self.production_finished=False
                        self.configured=True;self.outcome='Configured';self.fault=None
                elif action=='start':
                    with self.lock:
                        self.state='Running';self.configured=False;self.outcome='In progress'
                        self.inspector.cancel.clear()
                    self.source.command('start',cmd_id=cmd_id)
                elif action=='pause':
                    with self.lock:self.state='Paused'
                    if not self.production_finished:self.source.command('pause',cmd_id=cmd_id)
                elif action=='resume':
                    if not self.production_finished:self.source.command('resume',cmd_id=cmd_id)
                    with self.lock:self.state='Running'
                elif action=='stop':
                    if self.source.batch:self.source.command('stop',cmd_id=cmd_id)
                    self.inspector.submit('reset',identifier=cmd_id).result(timeout=5)
                    with self.lock:
                        for record in self.records.values():
                            if record['verdict'] is None:record['status']='Aborted'
                        self.waiting.clear();self.inflight=None;self.state='Idle';self.fault=None
                        self.configured=False
                        if self.outcome!='Completed':self.outcome='Aborted'
                        self.export()
                result={'cmd_id':cmd_id,'action':action,'phase':'completion','state':self.state}
                self.event('command_completion',**result)
                self.command_cache[cmd_id]=(request,result)
                return result
            except Exception as exc:
                self.set_fault(str(exc));raise
            finally:self.active_command=None

    def receive_part(self,boot,batch,part,count,final):
        with self.lock:
            if batch!=self.batch or self.state not in ('Running','Paused'):
                raise RuntimeError('Unexpected part outside the active batch')
            if part in self.records:return
            if count!=self.received+1 or count>self.config['target'] or final!=(count==self.config['target']):
                self.set_fault('Inconsistent production sequence/count');raise RuntimeError(self.fault)
            self.received=count;self.production_finished=final
            record={'batch_id':batch,'producer_boot':boot,'part_id':part,'produced_count':count,
                    'job_id':None,'status':'Queued','verdict':None,'received_ns':time.monotonic_ns(),'completed_ns':None}
            self.records[part]=record
            if len(self.waiting)>=self.config['capacity']:
                record['status']='Queue full — not admitted'
                self.set_fault('Inspection queue full; documented policy is Fault')
                self.export();raise RuntimeError(self.fault)
            self.waiting.append(part)
            self.event('part_queued',part_id=part,batch_id=batch,waiting=len(self.waiting))

    def dispatch(self):
        while self.running:
            try:
                with self.lock:
                    if self.reservation and time.monotonic()>=self.reservation[1]:self.reservation=None
                    if self.connected and self.active_command is None:
                        failure=self.source.failure or self.inspector.failure
                        if failure:self.set_fault(str(failure))
                    if self.connected and self.active_command is None and self.reservation is None and self.state=='Running' and self.inflight is None and self.waiting:
                        part=self.waiting.popleft();epoch=self.epoch
                        self.inflight=part;identifier=self.allocate()
                        self.records[part].update(job_id=identifier,status='Inspecting')
                        future=self.inspector.submit('inspect',part,identifier=identifier)
                        future.add_done_callback(lambda result,p=part,e=epoch:self.inspected(p,e,result))
                time.sleep(.01)
            except Exception as exc:self.set_fault(str(exc));time.sleep(.05)

    def inspected(self,part,epoch,future):
        with self.lock:
            if epoch!=self.epoch:return
            try:
                result=future.result()
                if result['part_id']!=part or result['identifier']!=self.records[part]['job_id'] or result['verdict'] not in (1,2):
                    raise RuntimeError('Inspection result does not match its job')
                verdict='PASS' if result['verdict']==1 else 'FAIL'
                record=self.records[part];record.update(status='Completed',verdict=verdict,completed_ns=time.monotonic_ns())
                if verdict=='PASS':self.accepted+=1
                else:self.rejected+=1
                self.inflight=None
                self.event('inspection_completed',batch_id=self.batch,part_id=part,job_id=result['identifier'],verdict=verdict)
                if self.production_finished and self.accepted+self.rejected==self.config['target'] and not self.waiting:
                    self.state='Idle';self.outcome='Completed';self.configured=False
                    self.event('batch_completed',batch_id=self.batch,target=self.config['target'],accepted=self.accepted,rejected=self.rejected)
                    self.export()
            except Exception as exc:self.set_fault(str(exc))

    def export(self):
        if not self.batch:return
        with (self.folder/f'batch-{self.batch}.csv').open('w',newline='',encoding='utf-8') as file:
            fields=['batch_id','producer_boot','part_id','produced_count','job_id','status','verdict','received_ns','completed_ns']
            writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader();writer.writerows(self.records.values())

    def snapshot(self):
        with self.lock:
            return {'state':self.state,'connected':self.connected,'configured':self.configured,'fault':self.fault,
                    'batch_id':self.batch,'config':dict(self.config),'produced':self.received,
                    'inspected':self.accepted+self.rejected,'accepted':self.accepted,'rejected':self.rejected,
                    'waiting':len(self.waiting),'inflight':self.inflight,'outcome':self.outcome,
                    'serial_port':self.serial_port,'inspector_host':self.host,
                    'events':list(self.events)[-35:],'parts':list(self.records.values())[-100:]}

    def close(self):
        self.running=False;self.dispatcher.join(timeout=2)
        self.disconnect();self.event_file.close()

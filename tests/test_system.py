import concurrent.futures
import threading
import time
from types import SimpleNamespace
import pytest
from system import ProductionSystem

class Source:
    def __init__(self,port,folder,callback):
        self.last_id=0;self.batch=0;self.failure=None
        self.gateway=SimpleNamespace(running=True)
        self.commands=[];self.callback=callback
    def command(self,op,*args,cmd_id=None):
        assert cmd_id>self.last_id
        self.last_id=cmd_id;self.commands.append((op,args,cmd_id))
        if op=='configure':self.batch=77
    def close(self):self.gateway.running=False

class Inspector:
    def __init__(self,host,port,folder,allocate):
        self.last_id=0;self.failure=None;self.running=True
        self.cancel=threading.Event();self.jobs=[];self.commands=[]
    def submit(self,op,*args,identifier=None):
        assert identifier>self.last_id
        self.last_id=identifier;future=concurrent.futures.Future()
        self.commands.append((op,args,identifier))
        if op=='inspect':self.jobs.append((future,identifier,args[0]))
        else:future.set_result({'identifier':identifier,'part_id':0,'verdict':0})
        return future
    def finish(self,index=0,verdict=1):
        future,identifier,part=self.jobs[index]
        future.set_result({'identifier':identifier,'part_id':part,'verdict':verdict})
    def close(self):self.running=False

def wait(condition):
    end=time.monotonic()+2
    while time.monotonic()<end:
        if condition():return
        time.sleep(.005)
    assert condition()

@pytest.fixture
def system(tmp_path):
    instance=ProductionSystem(tmp_path,Source,Inspector)
    instance.connect('COM7','127.0.0.1')
    yield instance
    instance.close()

def configure(system,target=2,capacity=2):
    return system.command('configure',{'target':target,'cycle_ms':100,'inspection_ms':200,'n':5,'k':0,'capacity':capacity})

def test_complete_only_after_every_target_part_is_inspected(system):
    result=configure(system);identifier=result['cmd_id']
    assert system.source.commands[-1][-1]==identifier==system.inspector.commands[-1][-1]
    system.command('start')
    system.receive_part(123,77,1,1,False)
    wait(lambda:len(system.inspector.jobs)==1)
    system.receive_part(123,77,2,2,True)
    assert system.snapshot()['state']=='Running' and system.snapshot()['inspected']==0
    system.inspector.finish(verdict=1)
    wait(lambda:len(system.inspector.jobs)==2)
    assert system.state=='Running'
    system.inspector.finish(1,2)
    assert system.snapshot()['state']=='Idle' and system.outcome=='Completed'
    assert (system.accepted,system.rejected)==(1,1)
    assert (system.folder/'batch-77.csv').exists()

def test_pause_holds_waiting_jobs_and_resume_dispatches(system):
    configure(system);system.command('start')
    system.receive_part(123,77,1,1,False);wait(lambda:len(system.inspector.jobs)==1)
    system.receive_part(123,77,2,2,True)
    system.command('pause');system.inspector.finish()
    time.sleep(.05)
    assert len(system.inspector.jobs)==1 and system.state=='Paused'
    system.command('resume');wait(lambda:len(system.inspector.jobs)==2)
    system.inspector.finish(1)
    assert system.outcome=='Completed'

def test_stop_aborts_and_ignores_a_late_verdict(system):
    configure(system);system.command('start')
    system.receive_part(123,77,1,1,False);wait(lambda:len(system.inspector.jobs)==1)
    result=system.command('stop')
    assert system.source.commands[-1][-1]==result['cmd_id']==system.inspector.commands[-1][-1]
    system.inspector.finish()
    assert system.outcome=='Aborted' and system.accepted==0 and system.state=='Idle'

def test_full_queue_faults_without_silently_dropping_a_part(system):
    configure(system,3,1);system.command('start')
    system.receive_part(123,77,1,1,False);wait(lambda:len(system.inspector.jobs)==1)
    system.receive_part(123,77,2,2,False)
    with pytest.raises(RuntimeError,match='queue full'):system.receive_part(123,77,3,3,True)
    assert system.state=='Fault' and system.received==3 and len(system.records)==3
    assert system.records[3]['status']=='Queue full — not admitted'
    assert not system.source.gateway.running
    system.inspector.finish()
    assert system.accepted==0 and system.outcome!='Completed'

def test_http_command_identifier_replay_does_not_start_twice(system):
    configure(system)
    start=system.command('start')
    count=len(system.source.commands)
    assert system.command('start',cmd_id=start['cmd_id'])==start
    assert len(system.source.commands)==count
    with pytest.raises(ValueError,match='different command'):system.command('pause',cmd_id=start['cmd_id'])

def test_validation_cannot_start_unconfigured_or_accept_zero_rule(system):
    with pytest.raises(ValueError,match='Configure'):system.command('start')
    with pytest.raises(ValueError):system.command('configure',{'target':1,'cycle_ms':100,'inspection_ms':100,'n':0,'k':0,'capacity':2})
    assert system.state=='Idle' and not system.configured

def test_duplicate_part_does_not_create_another_job(system):
    configure(system,1);system.command('start')
    system.receive_part(123,77,10,1,True)
    system.receive_part(123,77,10,1,True)
    wait(lambda:len(system.inspector.jobs)==1)
    system.inspector.finish()
    assert system.received==system.accepted==1

def test_failed_device_enters_fault(system):
    configure(system);system.command('start')
    system.inspector.failure=ConnectionError('link lost')
    wait(lambda:system.state=='Fault')
    assert not system.source.gateway.running

def test_reserved_http_id_is_preserved_and_gates_new_job_dispatch(system):
    configure(system);system.command('start')
    identifier=system.reserve_identifier()
    system.receive_part(123,77,1,1,False)
    time.sleep(.03)
    assert len(system.inspector.jobs)==0
    result=system.command('pause',cmd_id=identifier)
    assert result['cmd_id']==identifier==system.source.commands[-1][-1]

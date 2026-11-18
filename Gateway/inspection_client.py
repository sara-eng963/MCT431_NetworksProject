"""Synchronous inspection link. Jobs complete only on B's matching verdict."""
import json
import socket
import time
from pathlib import Path
from inspection_protocol import CONFIGURE,JOB,REPLY,STATUS,HEARTBEAT,RESET,Decoder,frame

class InspectionClient:
    def __init__(self,host,port=9000,log_path=None):
        self.socket=socket.create_connection((host,port),timeout=3)
        self.socket.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.socket.settimeout(0.1)
        self.decoder=Decoder()
        self.messages=[]
        self.boot=None
        self.last_id=0
        self.batch=0
        self.inspection_ms=0
        self.last_heartbeat=0
        self.last_status=time.monotonic()
        self.log_file=None
        if log_path:
            path=Path(log_path);path.parent.mkdir(parents=True,exist_ok=True)
            self.log_file=path.open('a',encoding='utf-8',buffering=1)
        try:
            deadline=time.monotonic()+3
            while self.boot is None and time.monotonic()<deadline:
                self.poll()
            if self.boot is None: raise TimeoutError('No inspector greeting')
        except Exception:
            self.close();raise

    def log(self,kind,**fields):
        if self.log_file:
            self.log_file.write(json.dumps({'event':kind,'time_ns':time.time_ns(),
                                           'monotonic_ns':time.monotonic_ns(),**fields})+'\n')

    def send(self,payload):
        self.socket.sendall(frame(payload))
        self.log('tcp_tx',payload_hex=payload.hex())

    def poll(self):
        now=time.monotonic()
        if self.boot and now-self.last_heartbeat>=0.5:
            self.send(HEARTBEAT.pack(19,self.boot));self.last_heartbeat=now
        try: data=self.socket.recv(512)
        except socket.timeout: data=None
        if data==b'': raise ConnectionError('Inspector disconnected; active outcome is unknown')
        if data:
            for payload in self.decoder.feed(data):
                self.log('tcp_rx',payload_hex=payload.hex())
                if payload[0]==20:
                    _,state,boot,batch,last_id,ms,n,k=STATUS.unpack(payload)
                    if not boot or state not in (0,1,2): raise ValueError('Invalid inspector status')
                    if self.boot is not None and boot!=self.boot: raise ConnectionError('Inspector restarted')
                    self.boot=boot;self.last_id=max(self.last_id,last_id)
                    self.last_status=time.monotonic()
                    self.log('inspector_status',state=state,boot_id=boot,batch_id=batch,
                             last_id=last_id,inspection_ms=ms,n=n,k=k)
                elif payload[0]==18:
                    reply=REPLY.unpack(payload)
                    if reply[1]!=self.boot:
                        self.log('stale_reply',boot_id=reply[1],identifier=reply[2]);continue
                    if reply[3] not in (1,2,3) or reply[4] not in range(5) or reply[5] not in range(3):
                        raise ValueError('Invalid inspector reply')
                    self.messages.append(reply)
                else: raise ValueError('Unknown inspector message')
        if time.monotonic()-self.last_status>3.5: raise TimeoutError('Inspector status is stale')

    def execute(self,make_payload,part_id=0,work_ms=0,identifier=None,cancel=None):
        if self.last_id>=0xffffffff: raise RuntimeError('Inspector ID space exhausted; reboot required')
        identifier=self.last_id+1 if identifier is None else identifier
        if not self.last_id<identifier<=0xffffffff:
            raise ValueError('Inspector identifiers must increase')
        self.last_id=identifier
        payload=make_payload(identifier)
        # A successful sendall is not an application delivery/acceptance/completion.
        self.send(payload)
        attempts=1
        retry_at=time.monotonic()+0.75
        deadline=time.monotonic()+work_ms/1000+4
        self.messages.clear()
        while time.monotonic()<deadline:
            if cancel is not None and cancel.is_set():
                raise InterruptedError('Inspection cancelled by gateway; explicit reset required')
            self.poll()
            while self.messages:
                _,boot,received_id,phase,result,verdict,part=self.messages.pop(0)
                if received_id!=identifier:
                    self.log('old_reply',identifier=received_id);continue
                self.log({1:'delivery',2:'acceptance',3:'completion'}[phase],
                         identifier=identifier,result=result,verdict=verdict,part_id=part)
                if result: raise RuntimeError(f'Inspector rejected ID {identifier}: result {result}')
                if phase==3:
                    if part!=part_id or (part_id and verdict not in (1,2)) or (not part_id and verdict!=0):
                        raise ValueError('Inspector completion does not match request')
                    return {'identifier':identifier,'part_id':part,'verdict':verdict}
            now=time.monotonic()
            if now>=retry_at and attempts<4:
                self.send(payload);attempts+=1
                retry_at=now+max(0.75,work_ms/1000/3)
        raise TimeoutError(f'Inspector ID {identifier} has unknown outcome after {attempts} transmissions')

    def reset(self,identifier=None):
        result=self.execute(lambda identifier:RESET.pack(21,self.boot,identifier),identifier=identifier)
        self.batch=0;self.inspection_ms=0
        return result

    def configure(self,batch,inspection_ms,n,k,identifier=None):
        if not 1<=batch<=0xffffffff or not 10<=inspection_ms<=3600000 or not 1<=n<=0xffffffff or not 0<=k<=0xffffffff:
            raise ValueError('Invalid inspection settings')
        result=self.execute(lambda identifier:CONFIGURE.pack(16,self.boot,identifier,batch,inspection_ms,n,k),identifier=identifier)
        self.batch=batch;self.inspection_ms=inspection_ms
        return result

    def inspect(self,part_id,identifier=None,cancel=None):
        if not self.batch or not 1<=part_id<=0xffffffffffffffff:
            raise ValueError('Configure inspector first and supply a positive 64-bit part ID')
        return self.execute(lambda identifier:JOB.pack(17,self.boot,identifier,self.batch,part_id),
                            part_id,self.inspection_ms,identifier=identifier,cancel=cancel)

    def close(self):
        try:self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        self.socket.close()
        if self.log_file: self.log_file.close()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

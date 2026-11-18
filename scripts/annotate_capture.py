"""Add comments to actual PktMon PCAPNG packets; preserve captured packet bytes."""
import argparse
import collections
import csv
import json
import socket
import struct
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Gateway'))
from inspection_protocol import CONFIGURE,JOB,REPLY,RESET

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    args=parser.parse_args()
    data=args.capture.read_bytes();blocks=[];flows=collections.defaultdict(dict);number=0;offset=0;wireless=set()
    while offset<len(data):
        kind,length=struct.unpack_from('<II',data,offset)
        if length<12 or offset+length>len(data):raise ValueError('Invalid PCAPNG block')
        body=data[offset+8:offset+length-4]
        if struct.unpack_from('<I',data,offset+length-4)[0]!=length:raise ValueError('PCAPNG length mismatch')
        offset+=length;packet_number=None
        if kind==6:
            number+=1;packet_number=number
            _,_,_,captured,_=struct.unpack_from('<IIIII',body)
            frame=body[20:20+captured]
            ip_offset=14 if len(frame)>=54 and frame[12:14]==b'\x08\x00' else None
            if ip_offset is None:
                snap=frame.find(b'\xaa\xaa\x03\x00\x00\x00\x08\x00',24,48)
                if snap>=24 and frame[0]&0x0c==8:
                    ip_offset=snap+8;wireless.add(number)
            if ip_offset is not None:
                ip=frame[ip_offset:];ip=ip[:int.from_bytes(ip[2:4],'big')];header=(ip[0]&15)*4
                if ip[9]==6:
                    tcp=ip[header:];sport,dport,seq,_=struct.unpack_from('>HHII',tcp)
                    if 9000 in (sport,dport):
                        payload=tcp[(tcp[12]>>4)*4:]
                        flow=(socket.inet_ntoa(ip[12:16]),sport,socket.inet_ntoa(ip[16:20]),dport)
                        for index,byte in enumerate(payload):flows[flow].setdefault(seq+index,(byte,number))
        blocks.append((kind,body,packet_number))
    rows=[];comments=collections.defaultdict(list)
    expected={16:25,17:21,18:20,19:5,20:30,21:9}
    for flow,positions in flows.items():
        remaining=sorted(positions);i=0
        while i<len(remaining):
            end=i+1
            while end<len(remaining) and remaining[end]==remaining[end-1]+1:end+=1
            keys=remaining[i:end];stream=bytes(positions[key][0] for key in keys);at=0
            while at+3<=len(stream):
                size=int.from_bytes(stream[at:at+2],'big');kind=stream[at+2]
                if expected.get(kind)!=size or at+size+2>len(stream):at+=1;continue
                payload=stream[at+2:at+size+2];packet=positions[keys[at]][1]
                direction='B → gateway' if flow[1]==9000 else 'gateway → B'
                row={'frame_number':packet,'direction':direction,'type':'','identifier':'','part_id':'','verdict':''}
                if kind==16:
                    _,boot,identifier,batch,ms,n,k=CONFIGURE.unpack(payload)
                    row.update(type='Configure',identifier=identifier)
                    text=f'Configure cmd_id={identifier}, batch={batch}, inspection={ms} ms, N={n}, K={k}'
                elif kind==17:
                    _,boot,identifier,batch,part=JOB.unpack(payload)
                    row.update(type='Inspection request',identifier=identifier,part_id=part)
                    text=f'Inspection request job_id={identifier}, part_id={part}, batch={batch}'
                elif kind==18:
                    _,boot,identifier,phase,result,verdict,part=REPLY.unpack(payload)
                    label={1:'Delivery',2:'Acceptance',3:'Completion'}.get(phase,str(phase))
                    verdict_text={0:'',1:'PASS',2:'FAIL'}.get(verdict,'INVALID')
                    row.update(type=label,identifier=identifier,part_id=part,verdict=verdict_text)
                    text=f'{label} id={identifier}, result={result}, part_id={part}'+(f', verdict={verdict_text}' if verdict_text else '')
                elif kind==21:
                    _,boot,identifier=RESET.unpack(payload);row.update(type='Reset/abort',identifier=identifier)
                    text=f'Explicit reset/abort cmd_id={identifier}'
                else:
                    at+=size+2;continue
                rows.append(row);comments[packet].append(text);at+=size+2
            i=end
    rows.sort(key=lambda r:r['frame_number'])
    output=args.capture.with_name(args.capture.stem+'-annotated.pcapng')
    wireless_interface=sum(1 for kind,_,_ in blocks if kind==1)
    inserted=False
    with output.open('wb') as file:
        for kind,body,packet in blocks:
            if kind==6 and not inserted:
                # PktMon mixed raw 802.11 and Ethernet under one Ethernet IDB.
                # Add a truthful 802.11 IDB; captured packet bytes stay unchanged.
                interface=struct.pack('<HHI',105,0,65535)
                file.write(struct.pack('<II',1,20)+interface+struct.pack('<I',20))
                inserted=True
            if packet in wireless:
                body=struct.pack('<I',wireless_interface)+body[4:]
            if packet in comments:
                captured=struct.unpack_from('<I',body,12)[0]
                option_start=20+((captured+3)//4)*4
                options=body[option_start:];at=0
                while at+4<=len(options):
                    code,size=struct.unpack_from('<HH',options,at)
                    if code==0:break
                    at+=4+((size+3)//4)*4
                text=('MCT431: '+' | '.join(comments[packet])).encode('utf-8')
                new_option=struct.pack('<HH',1,len(text))+text+b'\0'*((-len(text))%4)
                body=body[:option_start]+options[:at]+new_option+b'\0'*4
            length=len(body)+12
            file.write(struct.pack('<II',kind,length)+body+struct.pack('<I',length))
    csv_path=args.capture.with_name('packet-index.csv')
    with csv_path.open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=['frame_number','direction','type','identifier','part_id','verdict'])
        writer.writeheader();writer.writerows(rows)
    jobs={r['identifier']:r['part_id'] for r in rows if r['type']=='Inspection request'}
    complete={r['identifier']:r for r in rows if r['type']=='Completion' and r['verdict']}
    pairs=[{'job_id':identifier,'part_id':part,'completion_frame':complete[identifier]['frame_number'],'verdict':complete[identifier]['verdict']}
           for identifier,part in jobs.items() if identifier in complete and complete[identifier]['part_id']==part]
    summary={'packets':number,'commented_packets':len(comments),'wireless_frames_classified':len(wireless),'matched_inspection_jobs':len(pairs),'examples':pairs[:12]}
    args.capture.with_name('packet-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2));print('Annotated capture:',output)

if __name__=='__main__':main()

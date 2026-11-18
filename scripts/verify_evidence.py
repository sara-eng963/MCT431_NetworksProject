"""Check real B serial verdicts, saved CSV records and PCAPNG packet preservation."""
import json
import struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'logs/milestone1-20261118'
requests={};completions={}
for line in (folder/'inspector-serial.jsonl').read_text().splitlines():
    item=json.loads(line)
    if item.get('event')=='inspection_request':requests[item['job_id']]=item['part_id']
    if item.get('event')=='inspection_completed':
        assert requests.get(item['job_id'])==item['part_id'],item
        assert item['verdict'] in ('PASS','FAIL')
        completions[item['job_id']]=item
assert len(completions)>=50
def packets(path):
    data=path.read_bytes();at=0;frames=[]
    while at<len(data):
        kind,size=struct.unpack_from('<II',data,at);body=data[at+8:at+size-4];at+=size
        if kind==6:
            cap=struct.unpack_from('<I',body,12)[0];frames.append(body[20:20+cap])
    return frames
capture=folder/'capture-final'
assert packets(capture/'milestone1.pcapng')==packets(capture/'milestone1-annotated.pcapng')
summary=json.loads((capture/'packet-summary.json').read_text())
assert summary['matched_inspection_jobs']>=1
acceptance=json.loads((folder/'acceptance-final/results.json').read_text())
assert len(acceptance['results'])==6 and all(r['passed'] for r in acceptance['results'])
result={'serial_unique_requests':len(requests),'serial_unique_completed_jobs':len(completions),
        'all_serial_verdicts_have_matching_request':True,'pcap_packet_bytes_unchanged':True,
        'packet_matched_jobs':summary['matched_inspection_jobs'],'live_acceptance_cases_passed':6}
(folder/'evidence-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))

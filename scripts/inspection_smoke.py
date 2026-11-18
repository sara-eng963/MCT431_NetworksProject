"""Verify ten live verdicts computed by ESP32 B, independently of production A."""
import argparse
import secrets
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Gateway'))
from inspection_client import InspectionClient

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--inspection-ms',type=int,default=100)
    parser.add_argument('--n',type=int,default=5)
    parser.add_argument('--k',type=int,default=0)
    args=parser.parse_args()
    log=ROOT/'logs'/f'inspection-{time.time_ns()}.jsonl'
    with InspectionClient(args.host,log_path=log) as client:
        client.reset()
        client.configure(secrets.randbits(32) or 1,args.inspection_ms,args.n,args.k)
        for part in range(1,11):
            result=client.inspect(part)
            # This is validation of B's response, not the production verdict source.
            expected=2 if (part+args.k)%args.n==0 else 1
            assert result['verdict']==expected,result
            print(f'part {part}: '+('FAIL' if result['verdict']==2 else 'PASS'))
        client.reset()
    print('Inspection smoke PASS; log:',log)

if __name__=='__main__':main()

"""Record B's real serial job/verdict evidence while production uses Wi-Fi TCP."""
import argparse
import json
import time
from pathlib import Path
import serial

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--seconds',type=int,default=300)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    uart=serial.Serial(port=None,baudrate=115200,timeout=.2)
    uart.dtr=False;uart.rts=False;uart.port=args.port;uart.open()
    deadline=time.monotonic()+args.seconds
    with uart,args.output.open('a',encoding='utf-8',buffering=1) as file:
        while time.monotonic()<deadline:
            line=uart.readline()
            try:record=json.loads(line)
            except (ValueError,UnicodeDecodeError):continue
            record={'received_time_ns':time.time_ns(),'received_monotonic_ns':time.monotonic_ns(),**record}
            file.write(json.dumps(record)+'\n')
    print('Inspector serial log saved:',args.output)

if __name__=='__main__':main()

"""Provision B's Wi-Fi over its USB serial port; credentials stay out of source/logs."""
import argparse
import getpass
import json
import time
import serial

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    args=parser.parse_args()
    ssid=input('2.4 GHz Wi-Fi SSID: ')
    password=getpass.getpass('Wi-Fi password: ')
    if not 1<=len(ssid.encode())<=31 or len(password.encode())>63:
        parser.error('SSID must be 1..31 UTF-8 bytes; password at most 63 bytes')
    uart=serial.Serial(port=None,baudrate=115200,timeout=1,write_timeout=2)
    uart.dtr=False;uart.rts=False;uart.port=args.port;uart.open()
    with uart:
        packet=json.dumps({'ssid':ssid,'password':password},ensure_ascii=False).encode()+b'\n'
        deadline=time.monotonic()+60
        print('Waiting for B; press its EN/RESET button if needed.')
        sent=False
        while time.monotonic()<deadline:
            line=uart.readline()
            try: event=json.loads(line)
            except (ValueError,UnicodeDecodeError): continue
            if event.get('setup_required') and not sent:
                uart.write(packet);sent=True
            elif event.get('ip'):
                print(f'Inspection station IP: {event["ip"]}; TCP port: {event["port"]}')
                return
            elif event.get('provisioned'): print('Wi-Fi credentials saved on board B.')
            elif event.get('error'): raise RuntimeError(event['error'])
        raise TimeoutError('No IP received. Check Wi-Fi credentials and 2.4 GHz availability.')

if __name__=='__main__':main()

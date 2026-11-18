"""Local setup window for B; never writes Wi-Fi credentials to PC files or logs."""
import argparse
import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
import serial

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM6')
    args=parser.parse_args()
    window=tk.Tk()
    window.title('MCT431 — Inspection station B Wi-Fi setup')
    window.resizable(False,False)
    frame=ttk.Frame(window,padding=22);frame.grid()
    ttk.Label(frame,text=f'Inspection station B — {args.port}',font=('Segoe UI',12,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
    ttk.Label(frame,text='Enter the 2.4 GHz network used by both PCs.').grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,12))
    ttk.Label(frame,text='Wi-Fi name (SSID)').grid(row=2,column=0,sticky='w',padx=(0,12),pady=6)
    ssid=ttk.Entry(frame,width=34);ssid.grid(row=2,column=1)
    ttk.Label(frame,text='Password').grid(row=3,column=0,sticky='w',pady=6)
    password=ttk.Entry(frame,width=34,show='*');password.grid(row=3,column=1)
    status=tk.StringVar(value='Credentials are sent by USB to B and saved on the board.')
    ttk.Label(frame,textvariable=status,wraplength=440).grid(row=5,column=0,columnspan=2,sticky='w',pady=(12,0))
    events=queue.Queue();running=False

    def provision(network,secret):
        try:
            packet=json.dumps({'ssid':network,'password':secret},ensure_ascii=False).encode()+b'\n'
            uart=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=2)
            uart.dtr=False;uart.rts=False;uart.port=args.port;uart.open()
            with uart:
                uart.reset_input_buffer()
                uart.rts=True;time.sleep(.1);uart.rts=False
                deadline=time.monotonic()+60;sent=False
                while time.monotonic()<deadline:
                    try:message=json.loads(uart.readline())
                    except (ValueError,UnicodeDecodeError):continue
                    if message.get('setup_required') and not sent:
                        uart.write(packet);sent=True
                        events.put(('status','Credentials sent. Waiting for an IP address…'))
                    elif message.get('ip'):
                        # Only the address and port are saved; never credentials.
                        destination=ROOT/'.tools/inspection-network.json'
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        destination.write_text(json.dumps({'host':message['ip'],'port':message['port']})+'\n',encoding='utf-8')
                        events.put(('success',f'Connected! B is {message["ip"]}:{message["port"]}. You can close this window.'))
                        return
                    elif message.get('error'):raise RuntimeError(message['error'])
                raise TimeoutError('No IP received. Confirm the network is 2.4 GHz. If credentials were saved incorrectly, tell Codex so B can be reset.')
        except Exception as exc:events.put(('error',str(exc)))

    def connect():
        nonlocal running
        network,secret=ssid.get(),password.get()
        if not 1<=len(network.encode())<=31 or len(secret.encode())>63:
            status.set('Use an SSID of 1–31 bytes and password of at most 63 bytes.');return
        running=True;button.config(state='disabled');ssid.config(state='disabled')
        password.delete(0,'end');password.config(state='disabled')
        status.set('Resetting B and connecting…')
        threading.Thread(target=provision,args=(network,secret),daemon=True).start()

    def poll():
        nonlocal running
        while True:
            try:kind,text=events.get_nowait()
            except queue.Empty:break
            status.set(text)
            if kind in ('success','error'):
                running=False
                if kind=='error':
                    button.config(state='normal');ssid.config(state='normal');password.config(state='normal')
        window.after(100,poll)

    button=ttk.Button(frame,text='Connect station B',command=connect)
    button.grid(row=4,column=0,columnspan=2,pady=(15,0))
    def close():
        if running:status.set('Please wait for the connection attempt to finish before closing.')
        else:window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    ssid.focus_set();poll();window.mainloop()

if __name__=='__main__':main()

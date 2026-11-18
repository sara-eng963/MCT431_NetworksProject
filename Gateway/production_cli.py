"""Bring-up console for production station A; inspection is a later stage."""
import argparse
import json
import secrets
import struct
import threading
import time
from pathlib import Path

import serial
from serial.tools import list_ports
from protocol import (STATUS, COMMAND, EVENT, PART, PART_ACK, HEARTBEAT,
                      STATES, OPS, PHASES, RESULTS, SlipDecoder,
                      encode_atr, decode_atr, slip_encode)

class Gateway:
    def __init__(self, uart, log_path, on_part=None):
        self.uart = uart
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_path.open('a', encoding='utf-8', buffering=1)
        self.lock = threading.RLock()
        self.decoder = SlipDecoder()
        self.boot = None
        self.batch = 0
        self.last_cmd = 0
        self.seq = 0
        self.last_rx_seq = None
        self.state = None
        self.pending = None
        self.parts = {}
        self.last_status = time.monotonic()
        self.last_heartbeat = 0.0
        self.running = True
        self.failure = None
        self.on_part = on_part

    def log(self, kind, **fields):
        row = {'time_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns(),
               'event': kind, **fields}
        self.log_file.write(json.dumps(row) + '\n')

    def send(self, payload):
        wire = slip_encode(encode_atr(payload, self.seq))
        if self.uart.write(wire) != len(wire):
            raise OSError('Incomplete serial write')
        self.seq = (self.seq + 1) & 0xffffffff
        self.log('tx', wire_hex=wire.hex())

    def handle(self, payload):
        if not payload:
            raise ValueError('Empty application message')
        if payload[0] == 1:
            _, state, boot, batch, count, cmd = STATUS.unpack(payload)
            if state not in STATES or not boot:
                raise ValueError('Invalid status')
            if self.boot is not None and boot != self.boot:
                raise RuntimeError('ESP32 restarted: old batch is incomplete; reconnect explicitly')
            first = self.boot is None
            self.boot, self.batch, self.state = boot, batch, state
            self.last_cmd = max(self.last_cmd, cmd)
            self.last_status = time.monotonic()
            self.log('status', boot_id=boot, batch_id=batch, state=STATES[state], produced=count)
            if first:
                print(f'Connected: boot={boot}, state={STATES[state]}, batch={batch}', flush=True)
            if state == 3:
                print('Station FAULT. Use stop to abort, then configure a new batch.', flush=True)
        elif payload[0] == 3:
            _, boot, cmd, phase, result, state = EVENT.unpack(payload)
            if phase not in PHASES or result not in RESULTS or state not in STATES:
                raise ValueError('Invalid command event')
            if boot != self.boot:
                self.log('stale_event', boot_id=boot, cmd_id=cmd)
                return
            self.log(PHASES[phase], cmd_id=cmd, result=RESULTS[result], state=STATES[state])
            if self.pending and cmd == self.pending['id']:
                print(f'cmd {cmd}: {PHASES[phase]} {RESULTS[result]}', flush=True)
                if result != 0 or phase == 3:
                    if result == 0 and phase == 3:
                        self.state = state
                        if self.pending['operation'] == 'configure':
                            self.batch = self.pending['batch']
                    self.pending['result'] = result
                    self.pending['done'].set()
        elif payload[0] == 4:
            _, boot, batch, part, count, final = PART.unpack(payload)
            if boot != self.boot or batch != self.batch:
                self.log('stale_part', boot_id=boot, batch_id=batch, part_id=part)
                return
            if not part or not count or final not in (0, 1):
                raise ValueError('Invalid part')
            key = (boot, batch, part)
            if key in self.parts and self.parts[key] != payload:
                raise RuntimeError('Conflicting data for an existing part identifier')
            duplicate = key in self.parts
            if not duplicate and self.on_part:
                self.on_part(boot, batch, part, count, bool(final))
            # Record before acknowledging; never silently acknowledge a failed log write.
            self.log('part_duplicate' if duplicate else 'part_received', boot_id=boot,
                     batch_id=batch, part_id=part, count=count, production_finished=bool(final))
            self.parts[key] = payload
            self.send(PART_ACK.pack(5, boot, batch, part))
            if not duplicate:
                print(f'Part {part}: produced #{count}' + (' (production finished; inspection not implemented)' if final else ''), flush=True)
        else:
            raise ValueError('Unknown application message')

    def pump(self):
        try:
            while self.running:
                # Bound each driver read, even if a stale/large receive count is reported.
                data = self.uart.read(min(256, max(1, self.uart.in_waiting)))
                with self.lock:
                    for frame in self.decoder.feed(data):
                        self.log('rx', atr_hex=frame.hex())
                        try:
                            self.process_atr(frame)
                        except (ValueError, struct.error) as exc:
                            self.log('rejected_frame', reason=str(exc))
                    now = time.monotonic()
                    if self.boot and now - self.last_heartbeat >= 0.5:
                        self.send(HEARTBEAT.pack(6, self.boot))
                        self.last_heartbeat = now
                    if now - self.last_status > 3.5:
                        raise TimeoutError('No fresh ESP32 status for 3.5 seconds')
                    if self.pending and not self.pending['done'].is_set() and now >= self.pending['deadline']:
                        if self.pending['attempts'] >= 4:
                            raise TimeoutError('Command outcome unknown after 4 attempts; station will fault when heartbeats cease')
                        self.send(self.pending['payload'])
                        self.pending['attempts'] += 1
                        self.pending['deadline'] = now + 0.75
        except Exception as exc:
            with self.lock:
                self.failure = exc
                self.running = False
                if self.pending:
                    self.pending['done'].set()
            print(f'Connection stopped: {exc}', flush=True)

    def process_atr(self, frame):
        test_id, seq, payload = decode_atr(frame)
        if test_id != 0:
            return
        # Recognize a reboot even if the transport sequence counter reset.
        if len(payload) == STATUS.size and payload[0] == 1 and self.boot is not None:
            if STATUS.unpack(payload)[2] != self.boot:
                raise RuntimeError('ESP32 restarted: old batch is incomplete; reconnect explicitly')
        if self.last_rx_seq is not None:
            distance = (seq - self.last_rx_seq) & 0xffffffff
            if distance == 0 or distance >= 0x80000000:
                self.log('transport_duplicate' if distance == 0 else 'transport_old', seq=seq)
                return
        self.handle(payload)
        self.last_rx_seq = seq

    def command(self, op, arg0=0, arg1=0, cmd_id=None):
        with self.lock:
            if self.failure:
                raise RuntimeError(str(self.failure))
            if not self.boot:
                raise RuntimeError('Wait for the first status message')
            if self.pending and not self.pending['done'].is_set():
                raise RuntimeError('A command is still pending')
            if self.last_cmd >= 0xffffffff:
                raise RuntimeError('Command ID space exhausted; reboot station')
            batch = (secrets.randbits(32) or 1) if op == 'configure' else self.batch
            identifier = self.last_cmd + 1 if cmd_id is None else cmd_id
            if not self.last_cmd < identifier <= 0xffffffff:
                raise ValueError('Command identifier must increase within a boot session')
            payload = COMMAND.pack(2, self.boot, identifier, batch, OPS[op], arg0, arg1)
            self.last_cmd = identifier
            pending = {'id': self.last_cmd, 'payload': payload, 'attempts': 1,
                       'operation': op, 'batch': batch,
                       'deadline': time.monotonic() + 0.75, 'done': threading.Event(), 'result': None}
            self.pending = pending
            self.send(payload)
            self.log('command_requested', cmd_id=self.last_cmd, operation=op, batch_id=batch)
        if not pending['done'].wait(5):
            raise TimeoutError('Command did not finish')
        if self.failure:
            raise RuntimeError(str(self.failure))
        if pending['result'] != 0:
            raise RuntimeError(f'Command rejected: {RESULTS.get(pending["result"], "UNKNOWN")}')
        if op == 'stop':
            with self.lock:
                self.log('batch_aborted', batch_id=batch)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--list-ports', action='store_true')
    parser.add_argument('--log', default=f'logs/production-{time.time_ns()}.jsonl')
    args = parser.parse_args()
    if args.list_ports:
        for port in list_ports.comports():
            print(port.device, port.description)
        return
    if not args.port:
        parser.error('--port is required; use --list-ports to discover it')
    uart = serial.Serial(port=None, baudrate=115200, timeout=0.05, write_timeout=1)
    uart.dtr = False
    uart.rts = False
    uart.port = args.port
    uart.open()
    gateway = Gateway(uart, args.log)
    thread = threading.Thread(target=gateway.pump, daemon=True)
    thread.start()
    print('Commands: configure <parts> <cycle_ms>, start, pause, resume, stop, status, quit')
    print('Quit disconnects; an active station faults after heartbeat timeout. Use stop to abort first.')
    try:
        while gateway.running:
            words = input('> ').strip().lower().split()
            if not words:
                continue
            try:
                if words == ['quit']:
                    break
                if words == ['status']:
                    with gateway.lock:
                        print(STATES.get(gateway.state, 'CONNECTING'), 'batch', gateway.batch,
                              'unique parts this session', len(gateway.parts))
                elif words[0] == 'configure' and len(words) == 3:
                    target, cycle = map(int, words[1:])
                    if not 1 <= target <= 0xffffffff or not 10 <= cycle <= 3600000:
                        raise ValueError('Parts: 1..4294967295; cycle: 10..3600000 ms')
                    gateway.command('configure', target, cycle)
                elif len(words) == 1 and words[0] in OPS and words[0] != 'configure':
                    gateway.command(words[0])
                else:
                    print('Unknown command')
            except (ValueError, RuntimeError, TimeoutError, serial.SerialException) as exc:
                print(exc)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        gateway.running = False
        thread.join(timeout=2)
        uart.close()
        gateway.log_file.close()
        print(f'Log saved: {gateway.log_path}')

if __name__ == '__main__':
    main()

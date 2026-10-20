
import binascii
import struct
import sys

import serial

BAUD_RATE = 115200

SLIP_END = 0xC0
SLIP_ESC = 0xDB
SLIP_ESC_END = 0xDC
SLIP_ESC_ESC = 0xDD

MAX_ATR_SIZE = 8 + 128 + 2

STATES = {
    0: "IDLE",
    1: "RUNNING",
    2: "PAUSED",
    3: "FAULT",
}


def process_atr(data):
    # Minimum ATR: 8-byte header + 2-byte CRC
    if len(data) < 10:
        raise ValueError("ATR too short")

    test_id, seq, payload_len = struct.unpack(
        ">HIH", data[:8]
    )

    if len(data) != 8 + payload_len + 2:
        raise ValueError("ATR length mismatch")

    received_crc = int.from_bytes(data[-2:], "big")
    calculated_crc = binascii.crc_hqx(data[:-2], 0xFFFF)

    if received_crc != calculated_crc:
        raise ValueError("ATR CRC mismatch")

    payload = data[8:-2]

    # Application traffic uses test_id = 0
    if test_id != 0:
        return

    # STATUS message: type(1), state(1), count(4)
    if len(payload) != 6 or payload[0] != 1:
        raise ValueError("Unknown application message")

    state = STATES.get(payload[1], "UNKNOWN")
    produced = int.from_bytes(payload[2:6], "big")

    print(
        f"ESP32 A | seq={seq} | "
        f"state={state} | produced={produced}"
    )


def receive(port):
    frame = bytearray()
    in_frame = False
    escaped = False

    with serial.Serial(port, BAUD_RATE, timeout=1) as uart:
        uart.dtr = False
        uart.rts = False
        print(f"Listening on {port} at {BAUD_RATE} baud...")

        while True:
            data = uart.read(1)
            if not data:
                continue

            byte = data[0]

            # SLIP frame boundary
            if byte == SLIP_END:
                if in_frame and frame and not escaped:
                    try:
                        process_atr(bytes(frame))
                    except ValueError as error:
                        print(f"Rejected frame: {error}")

                frame.clear()
                in_frame = True
                escaped = False
                continue

            if not in_frame:
                continue

            # SLIP escape handling
            if escaped:
                escaped = False

                if byte == SLIP_ESC_END:
                    frame.append(SLIP_END)
                elif byte == SLIP_ESC_ESC:
                    frame.append(SLIP_ESC)
                else:
                    frame.clear()
                    in_frame = False
                    continue

            elif byte == SLIP_ESC:
                escaped = True
            else:
                frame.append(byte)

            # Protect against malformed or oversized frames
            if len(frame) > MAX_ATR_SIZE:
                frame.clear()
                in_frame = False


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"

    try:
        receive(port)
    except KeyboardInterrupt:
        print("\nReceiver stopped.")
    except serial.SerialException as error:
        print(f"Serial error: {error}")

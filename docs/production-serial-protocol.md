# Production serial protocol, version 1

UART: 115200, 8 data bits, no parity, 1 stop bit. SLIP frames an ATR consisting of
`test_id:u16, seq:u32, payload_len:u16, payload, crc:u16`. All integers are
big-endian. CRC-16/CCITT-FALSE: polynomial 0x1021, initial 0xFFFF, no reflection,
no final XOR; covers header plus payload. Maximum payload: 128 bytes. Production
uses test_id=0; future benchmark runs must use nonzero IDs. Transport sequence
numbers are independent of application identifiers and may wrap.
The gateway rejects duplicate/older transport sequences using modular ordering,
and does not treat repeated status frames as fresh device-health evidence.

| Type | Payload fields, in wire order |
|---|---|
| 1 STATUS | type:u8, state:u8, boot_id:u32, batch_id:u32, produced:u32, last_cmd_id:u32 |
| 2 COMMAND | type:u8, boot_id:u32, cmd_id:u32, batch_id:u32, op:u8, arg0:u32, arg1:u32 |
| 3 COMMAND_EVENT | type:u8, boot_id:u32, cmd_id:u32, phase:u8, result:u8, state:u8 |
| 4 PART | type:u8, boot_id:u32, batch_id:u32, part_id:u64, produced_count:u32, final:u8 |
| 5 PART_ACK | type:u8, boot_id:u32, batch_id:u32, part_id:u64 |
| 6 HEARTBEAT | type:u8, boot_id:u32 |

States: 0 Idle, 1 Running, 2 Paused, 3 Fault. Phases: 1 Delivery, 2 Acceptance,
3 Completion. Results: 0 OK, 1 Invalid, 2 State, 3 Stale, 4 Identifier conflict.

Operations: 1 Configure (arg0=target parts, arg1=cycle milliseconds), 2 Start,
3 Pause, 4 Resume, 5 Stop. Non-configuration arguments must be zero. Target must
be positive; cycle is currently constrained to 10..3600000 ms, matching the 10 ms
firmware scheduling tick. Confirm that this range covers examiner-assigned values;
reduce the tick/range if necessary. Configuration is only accepted when Idle with
no pending part. Each completed or stopped run requires a fresh Configure.

## Command contract

One gateway sends one command at a time, using strictly increasing nonzero IDs
within a boot session. Retry identical bytes with the same ID. The ESP stores the
last command and its result. Identical retries replay the outcome; conflicting
reuse is rejected; every older ID is rejected without execution. This provides
at-most-once execution without an unbounded cache, but only the latest outcome is
replayable. A rejected well-formed command also consumes its ID.

After a CRC-valid command arrives, the device reports Delivery. It then validates
the command, reports Acceptance OK or rejection, and reports Completion only when
the state/configuration change has actually occurred. Start completion means the
start operation completed; it does not mean that the batch completed. Replays
report the original completion state. Status reports the current state.

The gateway waits 750 ms and retries up to four total transmissions. An unresolved
command has an unknown outcome; the gateway terminates its connection rather than
issuing another command or claiming success.

## Part delivery and safe behavior

Part identity is `(boot_id, batch_id, part_id)`. The 64-bit part counter increases
throughout the boot session, across batches. A new random nonzero boot identifier
separates restarts; it is not an authentication credential or a mathematical
guarantee against random collisions.

There is at most one unacknowledged part. A pauses generation while awaiting its
ACK; overdue cycles are skipped instead of generating bursts. Part events retry
every 500 ms, with four total transmissions, then enter Fault. An ACK must match
all identity fields. Duplicate part events are acknowledged again but recorded
only once in the gateway's in-memory unique-part map. Conflicting duplicates stop
the gateway connection. The record is logged before ACK. The integrated gateway
queues accepted parts for inspection. Durable restart recovery is not implemented;
this is not a claim of crash-safe processing.

Gateway heartbeat interval: 500 ms. Device timeout: 3 s while Running, Paused or
waiting on a part ACK. Device status interval: 1 s. Gateway stale-status timeout:
3.5 s. A detected reboot ends the gateway session and requires explicit reconnect.
On reconnect, a previous batch must be treated as incomplete and explicitly
aborted before starting new work; automatic batch recovery is not implemented.

Pause stops new production; pending notifications still retry. Resume begins a
fresh cycle. Stop is an explicit batch abort, discards the unacknowledged event,
invalidates configuration and returns to Idle, including from Fault. Lost work in
an aborted batch must not be counted as a completed batch. Fault does not resume
automatically on reconnect. No physical actuator is involved.

The final PART flag means **production finished only**. The final project must
wait until inspection is also finished before reporting full batch completion.

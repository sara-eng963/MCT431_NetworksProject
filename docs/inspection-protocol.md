# Inspection station B protocol

The firmware was built, flashed and verified on B. Live Wi-Fi inspection and the
integrated six-case acceptance suite passed on 18 November 2026. COM numbers in
the examples below are placeholders; identify the board before using them.

TCP server: port 9000. Each message has a two-byte unsigned big-endian length,
followed by 1..128 payload bytes. Invalid lengths close the connection. Receivers
must handle fragmented messages and multiple messages in a single read.

All fields below are big-endian; identifiers are unsigned. A and B's transport
formats differ, but the gateway must preserve assigned job/command identifiers
across future protocol migration. A part identifier stays the same through inspection.

| Type | Fields, in payload order |
|---|---|
| 16 Configure | type:u8, boot:u32, cmd_id:u32, batch:u32, inspection_ms:u32, N:u32, K:u32 |
| 17 Inspect | type:u8, boot:u32, job_id:u32, batch:u32, part_id:u64 |
| 18 Reply | type:u8, boot:u32, cmd_or_job_id:u32, phase:u8, result:u8, verdict:u8, part_id:u64 |
| 19 Heartbeat | type:u8, boot:u32 |
| 20 Status | type:u8, state:u8, boot:u32, batch:u32, last_id:u32, inspection_ms:u32, N:u32, K:u32, reserved:4 bytes zero |
| 21 Reset/abort | type:u8, boot:u32, cmd_id:u32 |

State: 0 Idle, 1 Busy, 2 Fault. Phases: 1 Delivery, 2 Acceptance, 3 Completion.
Result: 0 OK, 1 Invalid, 2 State, 3 Stale, 4 Conflict. Verdict: 0 none,
1 PASS, 2 FAIL. Configure/reset completion has part_id=0 and verdict=0.
An inspection's completion echoes the exact part ID and has an explicit verdict.

B computes rejection when `(part_id + K) mod N == 0`, using an equivalent modulo
calculation that avoids unsigned overflow. N must be positive. Time is currently
10..3600000 ms. Parameters arrive at runtime in a validated identified Configure
message. New configuration is rejected while an inspection is active.

One client and one outstanding command/job are supported. IDs increase strictly
within a boot session. The latest request/outcome is cached: identical retries
replay acceptance and, once available, completion, without starting work again.
Conflicting reuse and older IDs are rejected. A second job while Busy is rejected
without overwriting the active job's cache. Reset explicitly aborts work, invalidates
configuration and clears Fault. Reconnection never silently resumes interrupted work.

Heartbeat: 500 ms from gateway, fault after 3 s without it during active work.
Any TCP disconnection enters Fault. Status is sent every second while connected.
The client rejects stale status after 3.5 s and uses at most four transmissions per
request. Inspection result deadline includes the configured inspection duration.

## Wi-Fi setup

B uses the same router as both Windows PCs. Its network must support 2.4 GHz.
Credentials are provisioned by USB JSON lines and stored in B's NVS, rather than
committed to source. Provisioning currently supports SSIDs of 1..31 UTF-8 bytes
and passwords of 0..63 bytes. Serial console does not echo credentials. No Internet
connection is needed for normal operation. MQTT authentication is a later stage;
this TCP development link is not authenticated.

After building and flashing B on its separately identified port:

```powershell
./scripts/build.ps1 -Station Inspection_ESP
./scripts/build.ps1 -Station Inspection_ESP -Upload -Port COM6
.\.venv\Scripts\python.exe scripts/provision_inspector.py --port COM6
```

COM6 is an example: discover the actual new USB port first. The provisioning tool
prompts locally; press B's EN/RESET button once the tool says it is waiting. It
prints B's IP address. Stored credentials are reused on subsequent boots; to change
them, erase B's `nvs` partition and provision again. Never erase A by mistake.

Verify B with:

```powershell
.\.venv\Scripts\python.exe scripts/inspection_smoke.py --host 192.168.1.50
```

Replace the example address with B's reported address. The script configures B and
checks ten real responses. Integrated production and queue validation is provided
by `scripts/validate_milestone1.py`.

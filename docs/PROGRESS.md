# Verified progress — 18 November 2026

## Milestone 1 implementation

The two-station application now runs end to end through the browser interface.
The gateway and browser were tested as separate processes on one Windows laptop.
A later separate operator laptop connected over the LAN and controlled a
completed 30-part batch (batch 3319905393: 25 accepted, 5 rejected).

- A has MAC f4:2d:c9:86:f5:08; B has MAC 3c:8a:1f:b0:4b:a8.
  A used COM7 during acceptance and later moved to COM3. Identify roles again
  after reconnecting; B may use the operator laptop for USB power.
- Current images were backed up before restoration; manifests and images remain
  under ignored `.tools/backups/`. The newer unrelated project firmware is retained.
- Both firmware projects build, flash and verify. B sends identified job/verdict
  serial logs as independent evidence, while operational jobs use Wi-Fi TCP.
- Gateway queue, full-queue Fault policy, batch tracking, four states, safe abort,
  duplicate/stale handling and identified HTTP/WebSocket operator interface exist.
- 45 automated host/native/API checks passed.
- Six final live cases passed: inspection faster; production faster with room;
  pause/resume; stop/abort; queue-full Fault; recovery with new runtime rule.
- Desktop and narrow browser layouts passed real control tests with no JavaScript
  errors. Three real parts completed from browser button commands.
- 61 distinct B-side completed jobs had matching serial requests. Actual PCAPNG
  packet bytes are preserved in the annotated version. A packet-matched example
  is job 235 / part 199, request frame 101 and completion frame 102.
- Plots use real application status samples and terminal completion events. They
  are application validation, not Milestone 2 protocol benchmarks.

## Evidence

`logs/milestone1-20261118/acceptance-final/results.json` contains six passing cases.
`status.csv` is the raw sampled status. Per-batch CSVs, serial/TCP JSONL and gateway
phase events are in the parent directory. `capture-final/` contains actual raw and
annotated captures plus packet indices. `dashboard/` contains browser screenshots
and checks. `evidence-verification.json` records consistency assertions.

Earlier failed runs are retained as diagnostics. Real LAN delays can fill a small
queue even with a nominally fast inspector; the required Fault policy is explicit.
An initial broader PktMon capture is incomplete and is not used as the primary
packet evidence. Windows required elevation for real driver-level packet capture.

## What the student still needs to do

- Read and understand the code and the guide's oral checklist.
- Perform the live classroom demonstration and individual explanation.

No MQTT, UDP, Modbus or formal benchmark harness/matrix has been implemented.
Milestone 2 remains outside this work. Submission reports remain local and are
excluded from the Git repository.

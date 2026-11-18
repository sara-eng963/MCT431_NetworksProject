# MCT431 — Milestone 1

The production/inspection application is implemented and tested with two real
ESP32 boards. The Python gateway and operator browser can run on one laptop for
development. Milestone 2 features have not been added.

Start here: [Milestone 1 guide, diagrams and demonstration checklist](docs/MILESTONE1.md).
See [current verified progress](docs/PROGRESS.md) for evidence and remaining
classroom requirements.

## Start the operator interface

PowerShell in this repository:

```powershell
.\.venv\Scripts\python.exe Gateway/server.py --bind 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Connect the stations, apply settings, then Start.
Select A's actual serial port after identifying the board. B's IP is prefilled
from local setup when available. Port numbers and DHCP addresses may change.

For a fresh environment, install `requirements.txt`; firmware tooling is in
`requirements-build.txt`. Build/flash with `scripts/build.ps1` (the full guide
explains Windows path handling). For a separate operator PC, bind to `0.0.0.0`
and open the gateway's LAN address from that PC.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validate_milestone1.py --serial COM7 --inspector B_IP
```

Live validation starts and aborts virtual batches; run it only when no other
operator is using the stations. B accepts one TCP client. The standalone
`inspection_smoke.py` must run before connecting the gateway.

## Milestone 1 scope

- A: SLIP-framed USB serial, ATR/CRC, runtime settings, identified parts/commands.
- B: length-prefixed TCP, runtime inspection rule/time, verdict computed on B.
- Gateway: bounded queue, Idle/Running/Paused/Fault, complete-batch counts,
  acknowledgements, timeouts/retries, duplicate/stale protection.
- Operator: HTTP controls and WebSocket live status.
- Evidence: real hardware acceptance results, CSVs, serial logs, annotated actual
  PCAPNG, plots, and browser screenshots under `logs/milestone1-20261118/`.

The full-queue policy is **Fault**, not silent loss. Pause lets an active
inspection finish and holds queued work. Stop explicitly aborts remaining work.

The six-case hardware suite used one laptop. A later separate operator laptop
connected over the LAN and controlled a completed 30-part batch (25 accepted,
5 rejected). Both PCs and B use the same router. The classroom demonstration
and individual oral explanation remain to be performed.

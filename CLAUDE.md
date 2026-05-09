# UHARPI — Raspberry Pi UHA Gateway

## What This Is

A Raspberry Pi C++ application that acts as a gateway between the STM32 CAN nodes (UHA_FW) and the local web dashboard. It receives variable updates from all CAN nodes over a serial link, stores them in a flat array, and periodically writes JSON files that the web dashboard reads.

---

## Folder Structure

```
UHARPI/
├── UHA/
│   ├── UHA/        (v1 — legacy)
│   ├── UHA2/       (v2 — legacy)
│   ├── UHA3/       (v3 — legacy)
│   └── UHA4/       ← CURRENT VERSION
│       ├── Main.cpp
│       ├── UHA.h / UHA.cpp   ← main logic
│       ├── rpiserp.h / rpiserp.c  ← serial protocol
│       ├── LOG.h / LOG.cpp   ← event log
│       ├── cJSON.h / cJSON.c ← JSON library
│       └── CMakeLists.txt
│   └── service/
│       └── uhagate4.service  ← systemd unit
├── BMS/            (standalone BMS monitoring, separate app)
└── WS/             ← web dashboard (Bootstrap, JS, JSON)
    └── js/bms.js   ← polls bms.json every 3s, renders cell table
```

---

## RPISERP Protocol

Serial port: `/dev/ttyUSB0`  
Packet framing: `0x7F 0xAA | len | id(2B) | dlc | data(≤8B) | checksum`

Key message IDs:
| ID | Direction | Meaning |
|----|-----------|---------|
| `0x221` (`CMD_TM_VAR_VALUE`) | STM32 → RPi | Variable update: 2B var-id + 2B value (int16_t) |
| `0x620` (`CMD_LOG_MSG`) | STM32 → RPi | 8-byte log event (node-id, event-type, data) |
| `0x50` (`CMD_RPI_VAR_VALUE`) | RPi → STM32 | Send a variable value to nodes |
| `0x51` (`CMD_RPI_RTC_SYNC`) | RPi → STM32 | Unix timestamp + TZ offset (every 60s) |

A background pthread (`RPISERP_Start`) reads the serial port continuously and buffers received packets. `UHA_ProcessMessage()` is called in a tight loop from `Main.cpp` to drain the buffer.

---

## Variable Array

`UHA.cpp` maintains `short mVars[NUM_OF_VARS]` indexed by `VAR_*` constants defined in `UHA.h`.  
These IDs **must match** `VARS.h` in `UHA_COMMON` — they share the same ID space over the CAN/serial bus.

`NUM_OF_VARS` must be large enough to cover the highest-numbered VAR ID used.  
**Current value in UHA4: 350** — must be bumped to **400** when BMS3 vars (IDs up to 381) are added.

---

## JSON Outputs

Written to `/home/pi/Web/` on the Raspberry Pi:

| File | Written by | Content |
|------|-----------|---------|
| `uha.json` | `UHA_CreateUhaJson()` | All ~350 vars: power, temps, BMS summary, cell data |
| `bms.json` | `UHA_CreateBmsJson()` | Focused BMS view: pack summary, SOC, per-cell voltages and temps |
| `log.txt` | `LOG_InsertMsg()` | Timestamped events from all nodes |

`UHA_CreateUhaJson()` and `UHA_CreateBmsJson()` are called every 1000ms from the main loop.

---

## Main Loop (Main.cpp)

```
UHA_Init()           → open /dev/ttyUSB0, start RX thread
loop (1000ms tick):
    UHA_CreateUhaJson()
    UHA_CreateBmsJson()
    if (60s elapsed): UHA_SendRTC()
    while packets pending: UHA_ProcessMessage()
```

---

## Build & Deploy

```bash
# Build on RPi
cd UHA/UHA4
cmake . && make
# Binary: UhaGate4

# Service
sudo systemctl enable uhagate4
sudo systemctl start uhagate4
```

---

## BMS Variables — What UHA4 Currently Handles

| VAR namespace | VAR IDs (summary) | VAR IDs (cells) | Source node |
|---------------|-------------------|-----------------|-------------|
| BMS1 | 20–24 | 180–211 | ASW_ELECON_D (CAN node 7) — workshop pack |
| BMS2 | 30–34 | 220–251 | ASW_ELECON (CAN node 4) — house pack 1 |
| BMS3 | 35–39 | 350–381 | ASW_ELECON (CAN node 4) — house pack 2 |

**BMS3 is NOT yet in UHA.h or UHA.cpp** — this is the pending work (see below).

---

## Pending Work: Add BMS3 Support

Two files need updating in `UHA/UHA4/`:

### 1. UHA.h
- Add `VAR_BMS3_*` defines (IDs 35–39 summary, 350–381 cells) — mirror what is in `UHA_COMMON/Inc/VARS.h`
- Bump `NUM_OF_VARS` from `350` → `400`

### 2. UHA.cpp — `UHA_CreateUhaJson()`
- Add BMS3 summary vars after the BMS2 block (lines ~390–394)
- Add BMS3 cell vars (32 entries: CELL1_MV…CELL16_MV, CELL1_C…CELL16_C) after the BMS2 cell block (lines ~539–570)

Optionally, `UHA_CreateBmsJson()` can be extended to include a third pack section.

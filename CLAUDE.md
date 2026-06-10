# UHARPI — Raspberry Pi UHA Gateway

## What This Is

A Raspberry Pi C++ application that acts as a gateway between the STM32 CAN nodes (UHA_FW) and the local web dashboard. It receives variable updates from all CAN nodes over a serial link, stores them in a flat array, and periodically writes JSON files that the web dashboard reads.

---

## Folder Structure

```
UHARPI/
├── UHA/
│   ├── UHA/ UHA2/ UHA3/ UHA4/   (legacy versions)
│   └── UHA5/                    ← CURRENT VERSION
│       ├── src/                 ← source files (if reorganised on Pi)
│       ├── Main.cpp
│       ├── UHA.h / UHA.cpp      ← main logic + VAR defines
│       ├── rpiserp.h / rpiserp.c ← serial protocol
│       ├── LOG.h / LOG.cpp      ← event log
│       ├── cJSON.h / cJSON.c    ← JSON library
│       └── CMakeLists.txt       ← target: UhaGate5
│   └── service/
│       ├── uhagate4.service     (legacy)
│       └── uhagate5.service     ← current systemd unit
├── BMS/            (standalone BMS monitoring, separate app)
└── WS/             ← web dashboard
    ├── index.html  ← entry point (uses uha.js)
    └── js/
        ├── uha.js  ← ACTIVE: reads uha.json, all 3 BMS packs
        └── bms.js  ← kept as fallback (reads bms.json, BMS1 only)
```

---

## RPISERP Protocol

Serial port: `/dev/ttyUSB0`  
Packet framing: `0x7F 0xAA | len | id(2B) | dlc | data(≤8B) | checksum`

| ID | Direction | Meaning |
|----|-----------|---------|
| `0x221` (`CMD_TM_VAR_VALUE`) | STM32 → RPi | Variable update: 2B var-id + 2B value (int16_t) |
| `0x620` (`CMD_LOG_MSG`) | STM32 → RPi | 8-byte log event (node-id, event-type, data) |
| `0x50` (`CMD_RPI_VAR_VALUE`) | RPi → STM32 | Send a variable value to nodes |
| `0x51` (`CMD_RPI_RTC_SYNC`) | RPi → STM32 | Unix timestamp + TZ offset (every 60s) |

A background pthread (`RPISERP_Start`) reads serial continuously. `UHA_ProcessMessage()` drains the buffer in a tight loop in `Main.cpp`.

---

## Variable Array

`UHA.cpp` maintains `short mVars[NUM_OF_VARS]` indexed by `VAR_*` constants in `UHA.h`.  
These IDs **must match** `VARS.h` in `UHA_COMMON` — same ID space shared over CAN/serial.

**UHA5: `NUM_OF_VARS = 400`** (bumped from 350 to cover BMS3 cell IDs up to 381).

---

## BMS Variables

| VAR namespace | VAR IDs (summary) | VAR IDs (cells) | Physical pack |
|---------------|-------------------|-----------------|---------------|
| BMS1 | 20–24 | 180–211 | Workshop 251 Ah — published by ASW_ELECON_D (node 7) |
| BMS2 | 30–34 | 220–251 | House 220 Ah — published by ASW_ELECON (node 4) |
| BMS3 | 35–39 | 350–381 | House 80 Ah — published by ASW_ELECON (node 4) |

All three packs are handled in UHA5 (`UHA.h` + `UHA.cpp`).

---

## JSON Outputs

Written to `/home/pi/Web/` on the Raspberry Pi:

| File | Written by | Content |
|------|-----------|---------|
| `uha.json` | `UHA_CreateUhaJson()` | Flat key-value of all ~400 VAR_* variables |
| `bms.json` | `UHA_CreateBmsJson()` | Legacy format — BMS1 only, kept for fallback |
| `log.txt` | `LOG_InsertMsg()` | Timestamped events from all nodes |

### uha.json format (flat, all VAR_* as keys)
```json
{
  "VAR_SOLAR_POWER_W": 1200,
  "VAR_BAT_SOC": 76,
  "VAR_BAT_VOLTAGE_V10": 532,
  "VAR_BMS1_CELL1_MV": 3305,
  "VAR_BMS2_CELL1_MV": 3300,
  "VAR_BMS3_CELL1_MV": 3295,
  "UnixTime": 1637179541,
  ...
}
```

Unit conventions in uha.json: `_V10` → raw/10 = V, `_A10` → raw/10 = A, `_A100` → raw/100 = A, `_MV` → raw/1000 = V, `_10WH` → raw/100 = kWh.

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

Service files are installed to `/lib/systemd/system/` (not `/etc/systemd/system/`).

```bash
# Build on Pi (sources optionally in src/ subfolder)
cd /home/pi/UHA5
cmake src/ && make        # if sources are in src/
# or: cmake . && make     # if sources are flat in UHA5/
# Binary: UhaGate5

# Install and start service
sudo cp uhagate5.service /lib/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable uhagate5
sudo systemctl start uhagate5
sudo systemctl status uhagate5

# Switch from v4 to v5
sudo systemctl stop uhagate4
sudo systemctl disable uhagate4
sudo systemctl start uhagate5
```

---

## Web Dashboard (WS/)

Static files served by nginx from `/home/pi/Web/`. `uha.json` is written to the same folder by the C++ app, so no path issues.

**Active script: `js/uha.js`** (reads `uha.json`). `bms.js` kept as fallback.

### Local testing
AJAX does not work over `file://`. Use a local server:
```bash
cd WS/
python -m http.server 8080   # then open http://localhost:8080
```
Put a sample `uha.json` in the `WS/` folder for testing.

### uha.js — data flow
1. AJAX GET `./uha.json` every 3 seconds
2. `UpdateDashboard(resp)` — fills 4 top cards (Solar, Battery, Load, Weather)
3. `UpdateCells(resp)` — fills voltage + temperature tables for all 3 packs
4. `DrawCellChart(getCells(resp, selectedPack))` — redraws bar chart for selected pack

### Key unit conversions in uha.js
| VAR suffix | JS conversion |
|-----------|--------------|
| `_V10` | `/ 10.0` |
| `_A10` | `/ 10.0` |
| `_A100` | `/ 100.0` |
| `_MV` (cell voltages) | `/ 1000.0` |
| `_10WH` (energy today) | `/ 100.0` → kWh |

### Dashboard features
| Section | Content |
|---------|---------|
| Solar card | Power W, charging A, daily kWh, panel voltage |
| Battery card | SOC %, available kWh, voltage, current, today diff kWh |
| Load card | Power W, daily kWh, discharge A |
| Weather card | Temperature (from VAR_BMS2_CELL4_C) |
| Cell voltage chart | Bar chart for selected pack — tabs: BMS1 Workshop 251Ah / BMS2 House 220Ah / BMS3 House 80Ah |
| Cell voltages table | 16 rows × 3 packs (V, 3 decimal places) |
| Cell temperatures table | 16 rows × 3 packs (°C) |

### getCells helper
Builds a 16-element array from flat VAR_* keys:
```javascript
getCells(resp, packNum)  // packNum = 1, 2, or 3
// reads VAR_BMSx_CELLy_MV and VAR_BMSx_CELLy_C
// returns [{VoltageV, TemperatureC}, ...]
```

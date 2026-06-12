# BeamNG Racing Dashboard

A real-time racing telemetry dashboard for [BeamNG.drive](https://www.beamng.com/). It receives live vehicle data from the simulator over UDP, then streams it to one or more browsers via WebSocket so you can watch speed, RPM, gear, throttle, brake, and fuel at a glance — even on a second screen or tablet.

> [!IMPORTANT]
> This project was primarily generated with AI. <br>
> It is provided as-is, without any warranty or guarantee. <br>
> I do not provide support, maintenance, or assistance for its use.

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [BeamNG.drive Configuration](#beamngdrive-configuration)
- [Running the Dashboard](#running-the-dashboard)
- [Using the Dashboard](#using-the-dashboard)
- [Configuration Reference](#configuration-reference)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Troubleshooting](#troubleshooting)

---

## Features

- **Analog speedometer** — 0–300 km/h circular gauge with needle and digital readout
- **Analog tachometer** — 0–10 000 RPM gauge with red zone above 7 000 RPM
- **Gear indicator** — shows R / N / 1 / 2 / 3 …
- **Fuel, throttle, and brake bars** — horizontal progress bars updated in real time
- **Connection status** — Live / Connecting / Disconnected indicator
- **Responsive layout** — works on desktop, tablet, and mobile
- **Multi-client** — any number of browsers can connect at the same time
- **Auto-reconnect** — the browser automatically tries to reconnect after 3 seconds if the server drops

---

## How It Works

```
BeamNG.drive (game)
        │  UDP OutGauge packets  (port 4444)
        ▼
  Python server  (main.py)
  ├─ TelemetryReceiver  – parses 92/96-byte binary packets
  ├─ SharedState        – latest telemetry snapshot
  └─ UpdateController   – broadcasts JSON at 20 FPS via WebSocket
        │  ws://localhost:8080/ws
        ▼
  Browser (index.html + app.js)
  └─ Canvas render loop at ~60 FPS  →  smooth analog gauges
```

BeamNG.drive implements the [LFS OutGauge](https://en.lfs.net/programmer/outgauge) protocol. The server parses the binary UDP packets, stores the latest snapshot, and pushes a small JSON object to every connected browser twenty times per second.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.7 or later |
| pip | any recent version |
| BeamNG.drive | any version that supports OutGauge (see below) |
| A modern web browser | Chrome, Firefox, Edge, Safari |

> **Windows users:** Python must be added to `PATH` during installation, or use `py` instead of `python`.

---

## Installation

1. **Clone or download the repository**

   ```bash
   git clone https://github.com/construktdev/BeamNGRacingDash.git
   cd BeamNGRacingDash
   ```

2. **(Recommended) Create and activate a virtual environment**

   ```bash
   # macOS / Linux
   python -m venv .venv
   source .venv/bin/activate

   # Windows (Command Prompt)
   python -m venv .venv
   .venv\Scripts\activate.bat

   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

---

## BeamNG.drive Configuration

The dashboard receives data via BeamNG's built-in **OutGauge** telemetry output. You need to enable it and point it at the machine running the Python server.

### Same PC setup

If the game and the server run on the same computer, use `127.0.0.1` (localhost) as the destination.

### Step-by-step

1. Open (or create) the BeamNG user settings file:

   ```
   %LOCALAPPDATA%\BeamNG.drive\<version>\settings\game.settings.json
   ```

   On a typical Windows installation the path looks like:

   ```
   C:\Users\<YourName>\AppData\Local\BeamNG.drive\0.32\settings\game.settings.json
   ```

   > **Tip:** You can paste `%LOCALAPPDATA%\BeamNG.drive` directly into the Windows Explorer address bar.

2. Add or update the `outGauge` block inside the JSON file:

   ```json
   {
     "outGauge": {
       "enabled": true,
       "ip": "127.0.0.1",
       "port": 4444,
       "delay": 1,
       "id": 0
     }
   }
   ```

   | Field | Description |
   |---|---|
   | `enabled` | Must be `true` |
   | `ip` | IP address of the machine running the Python server |
   | `port` | Must match `UDP_PORT` in `main.py` (default `4444`) |
   | `delay` | Packet interval in milliseconds (1 = as fast as possible) |
   | `id` | Optional packet identifier; leave `0` |

3. **Save the file** and **restart BeamNG.drive** for the changes to take effect.

### Two-PC / tablet setup

If the server runs on a different machine (e.g., a tablet on the same Wi-Fi network), replace `127.0.0.1` with the **local IP address** of the server machine (e.g., `192.168.1.50`). Make sure the firewall on the server machine allows inbound UDP traffic on port 4444.

---

## Running the Dashboard

1. **Start the Python server**

   ```bash
   python main.py
   ```

   You should see output like:

   ```
   2024-01-01 12:00:00  INFO      __main__ – Telemetry receiver listening on UDP 0.0.0.0:4444
   2024-01-01 12:00:00  INFO      __main__ – Dashboard available at http://0.0.0.0:8080
   2024-01-01 12:00:00  INFO      __main__ – WebSocket endpoint: ws://0.0.0.0:8080/ws
   ```

2. **Open the dashboard in your browser**

   Navigate to [http://localhost:8080](http://localhost:8080).

   The connection status indicator will show **⚡ Connecting…** until a WebSocket connection is established, then switch to **● Live**.

3. **Launch BeamNG.drive** (with OutGauge configured as above) and spawn a vehicle.

   Gauges will start moving as soon as the game sends telemetry.

4. **Stop the server** by pressing `Ctrl+C` in the terminal.

---

## Using the Dashboard

Once the server is running and a vehicle is spawned in BeamNG.drive, you will see:

| Element | Description |
|---|---|
| **Speedometer** (left) | 0–300 km/h analog gauge. Blue arc shows current speed. |
| **Tachometer** (right) | 0–10 000 RPM analog gauge. Green arc turns red above 7 000 RPM. |
| **Gear** (centre, large) | Current gear: `R` (reverse), `N` (neutral), or a number (1, 2, 3 …). |
| **FUEL bar** | Remaining fuel as a percentage (cyan gradient). |
| **THR bar** | Throttle input, 0–100 % (green gradient). |
| **BRK bar** | Brake input, 0–100 % (orange-red gradient). |
| **Connection status** | `● Live` (green) when receiving data, `✕ Disconnected` (red) otherwise. |

### Accessing from another device

Any device on the same network can open the dashboard. Use the server machine's local IP address instead of `localhost`:

```
http://192.168.1.50:8080
```

The browser will automatically reconnect if the WebSocket drops.

---

## Configuration Reference

All server-side settings are constants at the top of `main.py`:

```python
UDP_HOST   = "0.0.0.0"  # Interface to listen for BeamNG packets
UDP_PORT   = 4444        # UDP port (must match BeamNG OutGauge config)

WEB_HOST   = "0.0.0.0"  # Interface for the web server
WEB_PORT   = 8080        # HTTP / WebSocket port

TARGET_FPS = 20          # How often (per second) updates are sent to browsers
```

The single browser-side setting is in `static/app.js`:

```javascript
const WS_RECONNECT_DELAY_MS = 3000;  // Milliseconds before auto-reconnect
```

---

## Project Structure

```
BeamNGRacingDash/
├── main.py                 # Entry point – wires everything together
├── requirements.txt        # Python dependencies
├── pytest.ini              # Pytest configuration
│
├── core/
│   ├── state.py            # SharedState – thread-safe telemetry snapshot
│   └── controller.py       # UpdateController – rate-limited WebSocket broadcaster
│
├── telemetry/
│   └── receiver.py         # UDP receiver + OutGauge binary packet parser
│
├── server/
│   └── app.py              # aiohttp web app – static files + WebSocket endpoint
│
├── static/
│   ├── index.html          # Dashboard HTML (single page)
│   ├── app.js              # Canvas gauges + WebSocket client
│   └── style.css           # Dark-themed responsive stylesheet
│
└── tests/
    ├── test_telemetry.py   # Tests for OutGaugeParser and TelemetryReceiver
    ├── test_controller.py  # Tests for UpdateController
    └── test_state.py       # Tests for SharedState
```

---

## Running Tests

The test suite uses [pytest](https://docs.pytest.org/) and [pytest-asyncio](https://pytest-asyncio.readthedocs.io/).

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a single test file
pytest tests/test_telemetry.py

# Run a single test by name
pytest -k "test_speed_conversion"
```

All dependencies needed for testing are already in `requirements.txt`.

---

## Troubleshooting

### Dashboard shows "⚡ Connecting…" and never switches to "● Live"

- Make sure the Python server is running (`python main.py`).
- Check that nothing else is using port 8080 (`netstat -ano | findstr 8080` on Windows, `lsof -i :8080` on Linux/macOS).
- Try refreshing the browser page.

### Gauges are stuck at zero / not moving

- Verify that BeamNG.drive is running and a vehicle is spawned (not in the menu).
- Confirm the OutGauge settings in `game.settings.json` are correct and that you restarted the game after saving the file.
- Check the server terminal — it should print log messages. If nothing appears for the UDP side, BeamNG is not sending packets.
- On Windows Firewall or a third-party firewall, add an inbound rule that allows UDP traffic on port 4444.

### `ModuleNotFoundError: No module named 'aiohttp'`

Run the install step again, making sure your virtual environment is active:

```bash
pip install -r requirements.txt
```

### Port already in use (`OSError: [Errno 98] Address already in use`)

Another process is already listening on port 4444 or 8080. Either stop that process or change `UDP_PORT` / `WEB_PORT` in `main.py` (and update the BeamNG OutGauge config to match).

### Two-PC setup — no data received

- Ensure both computers are on the same local network.
- Confirm the `ip` field in BeamNG's OutGauge config points to the correct IP of the server machine.
- Add a firewall rule on the server machine to allow inbound UDP on port 4444.
- Test connectivity: on the server machine, run a packet capture (`Wireshark` or `tcpdump -i any udp port 4444`) to see whether packets are arriving.

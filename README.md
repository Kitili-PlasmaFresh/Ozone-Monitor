# Ozone-Monitor

A Windows desktop app that shows a live ozone plot and logs data to CSV for the **2B Technologies Model 106-MH** ozone monitor. It reads the instrument's USB serial output, plots ozone concentration in real time and records every measurement to CSV.

The app has a PyQt6 interface with an embedded matplotlib plot. It can be packaged as a single portable `.exe`, so the PC at the instrument doesn't need Python.

## Features

### Connection
- **Port selector:** lists every serial port Windows detects, with each port's description (for example `COM9 - USB Serial Port`). You can also type a port name.
- **Refresh:** rescans the ports after you plug in the instrument.
- **Baud rate:** 2400 by default (the 106-MH default). Common rates are listed, or you can type another.
- **Connect / Disconnect:** starts or stops reading. Serial data is read in a background thread, so the window stays responsive.

### Logging
- **Log file:** defaults to a time-stamped file (`2B_106MH_YYYYMMDD_HHMMSS.csv`) next to the program. **Browse...** picks another location.
- **Start Logging / Stop Logging:** writes every line received from the instrument to the log file, flushing after each line so data survives a crash or power loss. The app asks before overwriting an existing file, and logging stops automatically on disconnect.
- **Save CSV As...:** exports every reading received since **Connect** to a file you choose, whether or not logging was running.

### Live display
- Ozone concentration (ppm) plotted against elapsed time, with axes that rescale automatically.
- **Time window:** sets how many seconds are visible, adjustable while running. CSV files always keep every point.
- **Clear Plot:** empties the graph without affecting logged data.
- Large readout of the current ozone value.
- Status bar showing the instrument date/time, ozone, temperature, pressure and flow.
- Message pane showing connection events, errors and any lines that couldn't be parsed.

### Data parsing
- Accepts the 106-MH's 7-field USB output (`ozone, temp, pressure, flow, photodiode, date, time`) and the 8-field saved-log format, which starts with a log number.
- Removes the NUL bytes the instrument may insert, and treats CR, LF or CRLF as line endings.
- Lines that can't be parsed are still recorded, marked `unparsed` and kept as raw text, so no data is silently lost.

## CSV columns

| Column | Description |
|---|---|
| `pc_timestamp` | PC clock time the line was received (ISO 8601, ms) |
| `elapsed_seconds` | Seconds since Connect |
| `instrument_date`, `instrument_time` | Date/time reported by the 106-MH |
| `ozone_ppm` | Ozone concentration (ppm) |
| `temperature_C` | Cell temperature (°C) |
| `pressure_mbar` | Cell pressure (mbar) |
| `flow_cc_min` | Flow rate (cc/min) |
| `photodiode_V` | Photodiode voltage (V) |
| `log_number` | Log number (saved-log format only) |
| `parse_status` | `ok` or `unparsed` |
| `raw_line` | The line exactly as received |

## Usage

### Running from source
```
python -m pip install pyserial matplotlib PyQt6
python 2B_106MH_Windows_Build/2B_106MH_Reader.py
```

1. Connect the 106-MH by USB and confirm its USB serial driver has created a COM port.
2. Select the port and baud rate, then click **Connect**. The plot starts updating.
3. Click **Start Logging** to record to the chosen CSV file, and **Stop Logging** when finished.
4. Use **Save CSV As...** at any time to export the whole session.

Optional command-line arguments set the starting values in the window:

```
2B_106MH_Reader.py --port COM5 --baud 2400 --window-seconds 600 --csv C:\data\run1.csv
```

### Building the Windows EXE
On a Windows 10/11 PC with Python 3 and internet access, double-click `2B_106MH_Windows_Build/BUILD_WINDOWS_EXE.bat`. It creates a virtual environment, installs the dependencies and PyInstaller, and produces:

```
2B_106MH_Windows_Build/dist/2B_106MH_OzoneMonitor.exe
```

Copy that one file to the target PC. Run it from a writable folder (for example Desktop or Documents, not Program Files), because the default log file is saved next to the EXE. The EXE is not digitally signed, so Windows may show a SmartScreen warning.

PyInstaller is not a cross-compiler, so build the EXE on Windows.

## Repository layout

```
2B_106MH_Windows_Build/
├── 2B_106MH_Reader.py           # Application source
├── 2B_106MH_OzoneMonitor.spec   # PyInstaller spec
├── BUILD_WINDOWS_EXE.bat        # One-click Windows build script
└── README.txt                   # Plain-text guide shipped with the EXE
```

## Requirements
- Windows 10/11
- Python 3 (for running from source or building only)
- PyQt6, pyserial, matplotlib
- 2B Technologies 106-MH USB serial driver

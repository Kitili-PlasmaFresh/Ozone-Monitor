2B TECHNOLOGIES MODEL 106-MH - WINDOWS STANDALONE EXE
=====================================================

This package builds a portable Windows application with all required Python
libraries bundled (Python interpreter, PyQt6, PySerial, Matplotlib and
dependencies).

BUILD COMPUTER (ONE TIME ONLY)
1. Install Python 3 on a Windows 10/11 computer if not already installed.
   Ensure Python is on PATH, or the Python launcher 'py' is installed.
2. Connect the build computer to the internet.
3. Double-click BUILD_WINDOWS_EXE.bat.
4. After a successful build, find the EXE here:
   dist\2B_106MH_OzoneMonitor.exe

TARGET COMPUTER
1. Copy ONLY dist\2B_106MH_OzoneMonitor.exe to a Windows 10/11 computer.
2. Connect the 2B 106-MH to USB and confirm the USB serial driver creates a COM port.
3. Double-click the EXE. The monitor window opens.

USING THE PROGRAM
Connection
  - Port: pick the monitor's COM port from the list (it shows each port's
    description). Click Refresh after plugging in the USB cable. You can also
    type a port name such as COM5 directly.
  - Baud: 2400 by default.
  - Connect starts reading and plotting live. Disconnect stops it.

Logging
  - Log file: defaults to a time-stamped CSV beside the EXE. Use Browse... to
    choose another location (use a writable folder such as Desktop or
    Documents, not Program Files).
  - Start Logging writes every incoming line to that file, flushed line by
    line, so data is kept even if the PC loses power. Stop Logging closes it.
    Logging stops automatically on disconnect.
  - Save CSV As... exports every reading received since you clicked Connect
    to a file of your choice, whether or not logging was running.

Plot
  - Time window sets how many seconds are visible (CSV files keep all points).
  - Clear Plot empties the graph without affecting logged data.

Optional command line defaults (from Command Prompt in the EXE's folder):
    2B_106MH_OzoneMonitor.exe --port COM5 --baud 2400 --window-seconds 600

The target PC requires a compatible Windows architecture and the monitor's
USB serial driver. No separate Python installation is necessary. The EXE is
not digitally signed, so Windows may show a warning.

Do not build on Linux/macOS for Windows: PyInstaller is not a cross-compiler.

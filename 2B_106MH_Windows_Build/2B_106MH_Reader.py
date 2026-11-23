"""2B Technologies Model 106-MH USB logger and live ozone plot (PyQt GUI).

Run: python -m pip install pyserial matplotlib PyQt6
     python 2B_106MH_Reader.py

Workflow:
  1. Pick the COM port (Refresh rescans) and baud rate, then click Connect.
     Readings are plotted live as soon as the instrument is connected.
  2. Choose a CSV file and click Start Logging to record every line to that
     file (written and flushed line by line). Click Stop Logging to close it.
  3. Save CSV As... exports every reading received since Connect to a file
     of your choice, whether or not logging was running.

Optional command line defaults: --port COM9 --baud 2400 --window-seconds 300
"""

import argparse
import csv
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import serial
import serial.tools.list_ports
from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

COLUMNS = [
    'pc_timestamp', 'elapsed_seconds', 'instrument_date', 'instrument_time',
    'ozone_ppm', 'temperature_C', 'pressure_mbar', 'flow_cc_min',
    'photodiode_V', 'log_number', 'parse_status', 'raw_line'
]

BAUD_RATES = ['1200', '2400', '4800', '9600', '19200', '38400', '57600', '115200']


def parse_measurement(text):
    """Parse the 7-column USB messages, or 8-column saved log messages."""
    text = text.replace('\x00', '').strip()
    parts = [x.strip() for x in text.split(',')]
    if len(parts) not in (7, 8):
        return None
    log_number = ''
    if len(parts) == 8:
        try:
            log_number = int(parts.pop(0))
        except ValueError:
            return None
    try:
        ozone, temperature, pressure, flow, photodiode = map(float, parts[:5])
        date_time = f'{parts[5]} {parts[6]}'
        if not any(_valid_date(date_time, fmt) for fmt in (
            '%d/%m/%y %H:%M:%S', '%d/%m/%Y %H:%M:%S'
        )):
            return None
    except (ValueError, OverflowError):
        return None
    return dict(instrument_date=parts[5], instrument_time=parts[6],
                ozone_ppm=ozone, temperature_C=temperature,
                pressure_mbar=pressure, flow_cc_min=flow,
                photodiode_V=photodiode, log_number=log_number)


def _valid_date(value, fmt):
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False


def app_dir():
    """Folder beside the EXE (PyInstaller) or beside this script."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_csv_path():
    return app_dir() / f'2B_106MH_{datetime.now():%Y%m%d_%H%M%S}.csv'


class SerialReader(QThread):
    """Reads the serial port off the GUI thread and emits one row per line."""

    row_received = pyqtSignal(dict)
    status = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, port, baud, start_time):
        super().__init__()
        self.port = port
        self.baud = baud
        self.start_time = start_time
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            with serial.Serial(self.port, self.baud, bytesize=serial.EIGHTBITS,
                               parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                               timeout=0.2) as ser:
                self.status.emit(f'Connected to {self.port} at {self.baud} baud. '
                                 'Waiting for first measurement...')
                buffer = bytearray()
                while self._running:
                    chunk = ser.read(ser.in_waiting or 1)
                    if not chunk:
                        continue
                    # The 106-MH may put NUL bytes between ASCII characters.
                    buffer.extend(chunk.replace(b'\x00', b''))
                    # Keep CR and LF as record separators, including CR-only streams.
                    while b'\n' in buffer or b'\r' in buffer:
                        candidates = [i for i in (buffer.find(b'\n'), buffer.find(b'\r')) if i >= 0]
                        pos = min(candidates)
                        line = bytes(buffer[:pos]).decode('ascii', errors='replace').strip()
                        del buffer[:pos + 1]
                        if line:
                            self.row_received.emit(self._make_row(line))
                    if len(buffer) > 8192:
                        self.status.emit('Warning: dropping oversized incomplete serial message')
                        buffer.clear()
        except (serial.SerialException, OSError) as exc:
            self.failed.emit(f'{exc}\nCheck that {self.port} is the monitor port and '
                             'is not open in another application.')

    def _make_row(self, line):
        row = {'pc_timestamp': datetime.now().isoformat(timespec='milliseconds'),
               'elapsed_seconds': round(time.monotonic() - self.start_time, 3),
               'raw_line': line}
        reading = parse_measurement(line)
        if reading is None:
            row['parse_status'] = 'unparsed'
        else:
            row.update(reading)
            row['parse_status'] = 'ok'
        return row


class MainWindow(QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.setWindowTitle('2B Technologies 106-MH - Ozone Monitor')
        self.resize(1100, 700)

        self.reader = None
        self.session_rows = []          # every row since Connect, for Save CSV As
        self.log_file = None            # open file while logging
        self.log_writer = None
        self.log_count = 0
        self.window_seconds = args.window_seconds
        self.times = deque()
        self.concentrations = deque()
        self.plot_dirty = False

        self._build_ui(args)
        self.refresh_ports(preferred=args.port)
        if args.csv:
            self.csv_edit.setText(str(args.csv))

        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self.redraw_plot)
        self.plot_timer.start(200)
        self._update_buttons()

    # ---------- UI ----------
    def _build_ui(self, args):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # Left: controls
        controls = QVBoxLayout()
        root.addLayout(controls, 0)

        conn_box = QGroupBox('Connection')
        conn_form = QFormLayout(conn_box)
        port_row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)   # allow typing a port that isn't listed
        self.port_combo.setMinimumWidth(180)
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.clicked.connect(lambda: self.refresh_ports())
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.refresh_btn)
        conn_form.addRow('Port:', port_row)
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(BAUD_RATES)
        self.baud_combo.setCurrentText(str(args.baud))
        conn_form.addRow('Baud:', self.baud_combo)
        self.connect_btn = QPushButton('Connect')
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_form.addRow(self.connect_btn)
        controls.addWidget(conn_box)

        log_box = QGroupBox('Logging')
        log_layout = QVBoxLayout(log_box)
        file_row = QHBoxLayout()
        self.csv_edit = QLineEdit(str(default_csv_path()))
        self.browse_btn = QPushButton('Browse...')
        self.browse_btn.clicked.connect(self.browse_log_file)
        file_row.addWidget(self.csv_edit, 1)
        file_row.addWidget(self.browse_btn)
        log_layout.addWidget(QLabel('Log file:'))
        log_layout.addLayout(file_row)
        self.log_btn = QPushButton('Start Logging')
        self.log_btn.clicked.connect(self.toggle_logging)
        log_layout.addWidget(self.log_btn)
        self.log_state = QLabel('Not logging')
        log_layout.addWidget(self.log_state)
        self.save_btn = QPushButton('Save CSV As...')
        self.save_btn.setToolTip('Export every reading received since Connect')
        self.save_btn.clicked.connect(self.save_csv_as)
        log_layout.addWidget(self.save_btn)
        controls.addWidget(log_box)

        plot_box = QGroupBox('Plot')
        plot_form = QFormLayout(plot_box)
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(10, 86400)
        self.window_spin.setDecimals(0)
        self.window_spin.setSuffix(' s')
        self.window_spin.setValue(self.window_seconds)
        self.window_spin.valueChanged.connect(self._window_changed)
        plot_form.addRow('Time window:', self.window_spin)
        self.clear_btn = QPushButton('Clear Plot')
        self.clear_btn.clicked.connect(self.clear_plot)
        plot_form.addRow(self.clear_btn)
        controls.addWidget(plot_box)

        self.current_label = QLabel('-- ppm')
        font = self.current_label.font()
        font.setPointSize(22)
        font.setBold(True)
        self.current_label.setFont(font)
        self.current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls.addWidget(QLabel('Current ozone:'))
        controls.addWidget(self.current_label)
        controls.addStretch(1)

        # Right: plot above message log
        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, 1)

        self.figure = Figure(figsize=(8, 5), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.line, = self.ax.plot([], [], lw=1.8)
        self.ax.set(title='2B Technologies 106-MH - Live Ozone',
                    xlabel='Elapsed Time (s)', ylabel='Ozone Concentration (ppm)')
        self.ax.grid(True, alpha=0.35)
        splitter.addWidget(self.canvas)

        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumBlockCount(2000)
        splitter.addWidget(self.messages)
        splitter.setSizes([520, 160])

        self.statusBar().showMessage('Disconnected')

    def log(self, text):
        stamp = datetime.now().strftime('%H:%M:%S')
        self.messages.appendPlainText(f'[{stamp}] {text}')

    def _update_buttons(self):
        connected = self.reader is not None
        logging = self.log_file is not None
        self.connect_btn.setText('Disconnect' if connected else 'Connect')
        self.port_combo.setEnabled(not connected)
        self.baud_combo.setEnabled(not connected)
        self.refresh_btn.setEnabled(not connected)
        self.log_btn.setText('Stop Logging' if logging else 'Start Logging')
        self.csv_edit.setEnabled(not logging)
        self.browse_btn.setEnabled(not logging)
        self.save_btn.setEnabled(bool(self.session_rows))

    # ---------- Ports / connection ----------
    def refresh_ports(self, preferred=None):
        current = preferred or self.port_combo.currentText().split(' ')[0]
        self.port_combo.clear()
        ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)
        for p in ports:
            self.port_combo.addItem(f'{p.device} - {p.description}', p.device)
        devices = [p.device for p in ports]
        if current and current in devices:
            self.port_combo.setCurrentIndex(devices.index(current))
        elif current:
            self.port_combo.setEditText(current)
        self.log(f'Found {len(ports)} serial port(s)'
                 + (': ' + ', '.join(devices) if devices else ''))

    def selected_port(self):
        idx = self.port_combo.currentIndex()
        text = self.port_combo.currentText().strip()
        if idx >= 0 and text == self.port_combo.itemText(idx):
            return self.port_combo.itemData(idx)
        return text.split(' ')[0]

    def toggle_connection(self):
        if self.reader is None:
            self.connect_serial()
        else:
            self.disconnect_serial()

    def connect_serial(self):
        port = self.selected_port()
        if not port:
            QMessageBox.warning(self, 'No port', 'Select or type a serial port first.')
            return
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            QMessageBox.warning(self, 'Invalid baud', 'Baud rate must be a whole number.')
            return
        self.session_rows.clear()
        self.clear_plot()
        self.reader = SerialReader(port, baud, time.monotonic())
        self.reader.row_received.connect(self.handle_row)
        self.reader.status.connect(self.log)
        self.reader.failed.connect(self.connection_failed)
        self.reader.finished.connect(self.reader_finished)
        self.reader.start()
        self.statusBar().showMessage(f'Connecting to {port}...')
        self._update_buttons()

    def disconnect_serial(self):
        if self.reader is not None:
            self.reader.stop()
            self.reader.wait(2000)

    def connection_failed(self, message):
        self.log(f'ERROR: {message}')
        QMessageBox.critical(self, 'Serial error', message)

    def reader_finished(self):
        self.reader = None
        if self.log_file is not None:
            self.stop_logging()
        self.log('Disconnected')
        self.statusBar().showMessage('Disconnected')
        self._update_buttons()

    # ---------- Data ----------
    def handle_row(self, row):
        self.session_rows.append(row)
        if self.log_writer is not None:
            try:
                self.log_writer.writerow(row)
                self.log_file.flush()
                self.log_count += 1
                self.log_state.setText(f'Logging: {self.log_count} rows')
            except OSError as exc:
                self.log(f'ERROR writing log file: {exc}')
                self.stop_logging()
        if row['parse_status'] == 'ok':
            ozone = row['ozone_ppm']
            self.times.append(row['elapsed_seconds'])
            self.concentrations.append(ozone)
            self.plot_dirty = True
            self.current_label.setText(f'{ozone:.3f} ppm')
            self.statusBar().showMessage(
                f"{self.selected_port()} | {row['instrument_date']} {row['instrument_time']} | "
                f"O3 {ozone:.3f} ppm | T {row['temperature_C']} C | "
                f"P {row['pressure_mbar']} mbar | Flow {row['flow_cc_min']} cc/min")
        else:
            self.log(f"Unparsed: {row['raw_line']!r}")
        if len(self.session_rows) == 1:
            self._update_buttons()

    def _window_changed(self, value):
        self.window_seconds = value
        self.plot_dirty = True

    def clear_plot(self):
        self.times.clear()
        self.concentrations.clear()
        self.line.set_data([], [])
        self.current_label.setText('-- ppm')
        self.canvas.draw_idle()

    def redraw_plot(self):
        if not self.plot_dirty or not self.times:
            return
        self.plot_dirty = False
        last = self.times[-1]
        # Plot shows the window only; session_rows keeps everything for CSV.
        while self.times and self.times[0] < last - self.window_seconds:
            self.times.popleft()
            self.concentrations.popleft()
        self.line.set_data(list(self.times), list(self.concentrations))
        self.ax.set_xlim(max(0, last - self.window_seconds), max(self.window_seconds, last + 1))
        lowest, highest = min(self.concentrations), max(self.concentrations)
        pad = max(0.05, (highest - lowest) * 0.15)
        self.ax.set_ylim(lowest - pad, highest + pad)
        self.canvas.draw_idle()

    # ---------- Logging / saving ----------
    def browse_log_file(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Choose log file', self.csv_edit.text(),
                                              'CSV files (*.csv);;All files (*)')
        if path:
            self.csv_edit.setText(path)

    def toggle_logging(self):
        if self.log_file is None:
            self.start_logging()
        else:
            self.stop_logging()

    def start_logging(self):
        text = self.csv_edit.text().strip()
        if not text:
            self.browse_log_file()
            text = self.csv_edit.text().strip()
            if not text:
                return
        path = Path(text)
        if path.suffix.lower() != '.csv':
            path = path.with_suffix('.csv')
        if path.exists():
            answer = QMessageBox.question(
                self, 'File exists', f'{path}\nalready exists. Overwrite it?')
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = path.open('w', newline='', encoding='utf-8')
            self.log_writer = csv.DictWriter(self.log_file, fieldnames=COLUMNS)
            self.log_writer.writeheader()
            self.log_file.flush()
        except OSError as exc:
            self.log_file = self.log_writer = None
            QMessageBox.critical(self, 'Cannot open log file', str(exc))
            return
        self.csv_edit.setText(str(path))
        self.log_count = 0
        self.log_state.setText('Logging: 0 rows')
        self.log(f'Logging started: {path.resolve()}')
        if self.reader is None:
            self.log('Note: not connected yet - rows are recorded once you Connect.')
        self._update_buttons()

    def stop_logging(self):
        if self.log_file is None:
            return
        path = self.log_file.name
        try:
            self.log_file.close()
        except OSError:
            pass
        self.log_file = self.log_writer = None
        self.log_state.setText(f'Stopped: {self.log_count} rows saved')
        self.log(f'Logging stopped. {self.log_count} rows saved to {path}')
        # Suggest a fresh file name for the next logging run.
        self.csv_edit.setText(str(default_csv_path()))
        self._update_buttons()

    def save_csv_as(self):
        if not self.session_rows:
            QMessageBox.information(self, 'No data', 'No readings received yet.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save CSV', str(default_csv_path()),
                                              'CSV files (*.csv);;All files (*)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(self.session_rows)
        except OSError as exc:
            QMessageBox.critical(self, 'Save failed', str(exc))
            return
        self.log(f'Saved {len(self.session_rows)} rows to {path}')

    def closeEvent(self, event):
        if self.log_file is not None or self.reader is not None:
            answer = QMessageBox.question(
                self, 'Quit', 'Stop logging/disconnect and quit?')
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.stop_logging()
        if self.reader is not None:
            self.reader.finished.disconnect(self.reader_finished)
            self.reader.stop()
            self.reader.wait(2000)
        event.accept()


def main():
    parser = argparse.ArgumentParser(description='Live ozone plot and CSV logger for 2B 106-MH')
    parser.add_argument('--port', default='COM9', help='Port preselected at startup')
    parser.add_argument('--baud', type=int, default=2400)
    parser.add_argument('--csv', type=Path, default=None, help='Initial log file path')
    parser.add_argument('--window-seconds', type=float, default=300,
                        help='Visible time window in seconds (CSV stores all points)')
    args, qt_args = parser.parse_known_args()
    if args.window_seconds <= 0:
        parser.error('--window-seconds must be greater than zero')

    app = QApplication([sys.argv[0]] + qt_args)
    window = MainWindow(args)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

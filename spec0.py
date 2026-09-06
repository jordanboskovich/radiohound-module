
"""
radiohound -- Stage 0 interface spec (stubs only, no implementation)
 
Modeled on the pandas pattern: a general-purpose core (connect / send /
receive) that knows nothing about *why* you're talking to a node, plus
three specialized layers built on top of that core -- one per use case
Chris identified: calibration, debug/iteration, and occupancy mapping.
 
Nothing here is implemented. The goal of this file is to nail down
names and signatures FIRST, circulate it to FPGA DAQ and Command &
Control for feedback, and only then write real code (Stage 1).
 
Open questions that block finalizing this spec are marked inline as
# TODO(team): ...
"""
 
from typing import Any
 
 
# ---------------------------------------------------------------------------
# CORE -- domain-agnostic. Doesn't know about calibration, debugging, or
# mapping. Just: talk to a node, hide the MQTT callback complexity.
# Equivalent to pandas' DataFrame.
# ---------------------------------------------------------------------------
 
class RadioHoundNode:
    """Represents one physical node, addressed by MAC address or node id."""
 
    def __init__(self, node_id: str):
        # TODO connect via the Flask API layer, not directly to MQTT 
        pass
 
    def connect(self) -> None:
        """Establish a connection to the node (via API)."""
        pass
 
    def disconnect(self) -> None:
        """Cleanly tear down the connection."""
        pass
 
    def send_command(self, command: dict) -> None:
        """
        Publish a command to the node. Internally wraps whatever
        sendMessage.py does in the Icarus repo -- read that file before
        implementing this for real.
        """
        pass
 
    def scan(self, freq: float, gain: float = None, mode: str = "fft") -> "ScanResult":
        """
        The single most important function in the whole module: publish a
        scan command, block internally on the MQTT callback, and return a
        result synchronously -- so the caller never sees the callback at all.
 
        # TODO(FPGA DAQ / Dom, Zhiyu): confirm return format -- raw IQ,
        # FFT bins, periodogram, or already-assembled array.
        """
        pass
 
    def status(self) -> dict:
        """Query the node's current state (idle, scanning, error, etc.)."""
        pass
 
 
class ScanResult:
    """
    Wraps whatever comes back from a scan into one consistent object,
    regardless of what raw format FPGA DAQ's interface returns.
 
    # TODO: decide whether the underlying storage is a NumPy array,
    # a pandas DataFrame, or DigitalRF (per Randy's proposal).
    """
    def __init__(self, data: Any, metadata: dict):
        self.data = data
        self.metadata = metadata  # frequency, location, node name, timestamp
 
 
# ---------------------------------------------------------------------------
# USE CASE 1: CALIBRATION / SWEEP
# Sequential, single-node. Request a periodogram over MQTT, likely
# visualized live (e.g. in a Jupyter notebook).
# Equivalent to pandas' .resample() -- a specialized accessor for one kind
# of work, built on the same core above.
# ---------------------------------------------------------------------------
 
def sweep(node: RadioHoundNode, freq_start: float, freq_stop: float, step: float) -> "CalibrationCurve":
    """
    Run a calibration sweep across a frequency range, calling node.scan()
    repeatedly under the hood.
 
    # TODO: check calibrationIO/ and SoapyCalibCurves in the Icarus repo --
    # there may already be an existing calibration curve format to match,
    # rather than inventing a new one.
    """
    pass
 
 
def load_calibration(path: str) -> "CalibrationCurve":
    """Load a previously saved calibration curve from disk."""
    pass
 
 
def save_calibration(curve: "CalibrationCurve", path: str) -> None:
    """Save a calibration curve to disk."""
    pass
 
 
class CalibrationCurve:
    """Represents a calibration result across a frequency range."""
    pass
 
 
# ---------------------------------------------------------------------------
# USE CASE 2: NORMAL USE / DEBUGGING
# Fast iteration -- stepping through frequencies while actively poking at
# the system. Optimized for low friction, not for completeness.
# ---------------------------------------------------------------------------
 
def quick_scan(node: RadioHoundNode, freq: float) -> ScanResult:
    """
    A minimal-overhead scan for fast, repeated calls at a REPL or notebook.
    Likely just a thin pass-through to node.scan() with sensible defaults
    baked in, so the caller doesn't need to specify gain/mode every time.
    """
    pass
 
 
def step_frequency(node: RadioHoundNode, current_freq: float, step: float) -> ScanResult:
    """Convenience for the common 'nudge frequency and rescan' pattern."""
    pass
 
 
def live_view(node: RadioHoundNode, freq: float, interval: float = 1.0):
    """
    A generator that yields ScanResults repeatedly at a fixed interval,
    for live plotting while debugging.
 
    # TODO: confirm whether this should reuse the FPGA DAQ ring-buffer
    # read pattern directly instead of issuing repeated fresh scans.
    """
    pass
 
 
# ---------------------------------------------------------------------------
# USE CASE 3: OCCUPANCY MAPPING / DATA COLLECTION
# Multi-node coordination. Save node values as a time series. Needs
# cross-node timing to be meaningful.
# ---------------------------------------------------------------------------
 
def collect(nodes: list[RadioHoundNode], freq: float, duration: float, interval: float) -> "TimeSeries":
    """
    Coordinate scans across multiple nodes over a period of time.
 
    # TODO(Time Sync / Jack, Cole, Dom/Zhiyu, Nazim): this function's
    # usefulness depends entirely on what timestamp precision is actually
    # available -- confirm before implementing.
    """
    pass
 
 
def save_timeseries(ts: "TimeSeries", path: str, format: str = "digitalrf") -> None:
    """
    Save collected multi-node data to disk.
 
    # TODO: confirm DigitalRF vs. pandas as the default storage format
    # (Randy's proposal was DigitalRF, since it's already standard for
    # this kind of RF time-series data).
    """
    pass
 
 
class TimeSeries:
    """Represents time-aligned scan results across one or more nodes."""
    pass
 
 
# ---------------------------------------------------------------------------
# STAGE 2 CONVENIENCE (not part of the core three use cases, but the
# original radiohound.go() idea -- included here to show how it composes
# from the pieces above rather than being a fourth separate thing)
# ---------------------------------------------------------------------------
 
def go(node_id: str, freq: float, mode: str = "fft") -> ScanResult:
    """Connect to a node and run one scan, in a single call."""
    node = RadioHoundNode(node_id)
    node.connect()
    return node.scan(freq, mode=mode)
 





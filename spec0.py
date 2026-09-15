"""
radiohound/core.py -- Stage 1, rebuilt against Randy's dummy API
(HTTP, not raw MQTT -- see notes below).

This targets a mocked/hardcoded backend right now. The RESPONSE SHAPE is
expected to match the eventual real API; specific VALUES in that response
(hardware_type, active, etc.) are just fixture data and shouldn't be
treated as representative.

freq units (Hz) and gain range (0-7) were confirmed against Icarus's
rf/scan.py source -- see CONTEXT.md #4. Still open: that source shows the
real periodogram task takes fmin/fmax (a range), not a single freq -- this
scan() signature likely needs to change to match before Stage 2.
"""

import base64

import numpy
import requests

BASE_URL = "http://radiohound2.ee.nd.edu:8000/api"


class ScanResult:
    """Wraps one scan response into something easy to work with."""

    def __init__(self, response_json):
        self.raw = response_json
        self.data = numpy.frombuffer(
            base64.b64decode(response_json["data"]),
            dtype=response_json["type"],
        )
        self.mac_address = response_json["mac_address"]
        self.timestamp = response_json["timestamp"]
        self.center_frequency = response_json["center_frequency"]
        self.sample_rate = response_json["sample_rate"]
        self.metadata = response_json["metadata"]      # fmin, fmax, nfft, gps_lock, scan_time, ...
        self.requested = response_json["requested"]     # what was actually asked for, echoed back
        self.gps_lock = response_json["metadata"].get("gps_lock")

    def __repr__(self):
        m = self.metadata
        return (f"<ScanResult mac={self.mac_address} n={self.data.size} "
                f"fmin={m.get('fmin')} fmax={m.get('fmax')} gps_lock={self.gps_lock}>")


def scan(mac_address, freq, gain=None, base_url=BASE_URL, timeout=10):
    """
    Request a scan from a node and return a ScanResult with the decoded
    array and metadata attached.

    `freq` is in Hz; `gain` should be in [0, 7] (step 1) -- both confirmed
    against Icarus's rf/scan.py source, see CONTEXT.md #4.

    NOTE: the real periodogram task takes fmin/fmax (a range), not a
    single freq -- this signature is Stage 1 placeholder shape and likely
    needs to change before Stage 2 (see CONTEXT.md #10).
    """
    params = {"freq": freq}
    if gain is not None:
        params["gain"] = gain

    resp = requests.get(f"{base_url}/scan/{mac_address}", params=params, timeout=timeout)
    resp.raise_for_status()
    return ScanResult(resp.json())


def get_node(mac_address, base_url=BASE_URL, timeout=10):
    """Fetch a node's raw status dict (active, last_update, sensors, ...)."""
    resp = requests.get(f"{base_url}/node/{mac_address}", timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def is_online(mac_address, base_url=BASE_URL, timeout=10):
    """
    Convenience wrapper answering the Stage 2 "is the node online"
    question directly from the API's own `active` field, rather than
    inferring it from timeouts or connection errors.
    """
    return get_node(mac_address, base_url=base_url, timeout=timeout)["active"]


if __name__ == "__main__":
    import sys
    result = scan(sys.argv[1], freq=float(sys.argv[2]))
    print(result)
    print(result.data[:8])
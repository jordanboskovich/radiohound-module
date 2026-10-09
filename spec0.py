"""
radiohound/core.py -- built against Randy's live API (real scans from
real nodes, as of Oct 2026)
"""

import base64
import time

import numpy
import requests

BASE_URL = "http://radiohound2.ee.nd.edu:8000/api"

# The server gives the node `timeout + 2` seconds before answering 504
# (Randy's scan_node(), Oct 2026), so the HTTP request has to wait longer
# than that or we'd give up before the server tells us what happened.
SERVER_GRACE = 2
HTTP_MARGIN = 3     # extra on top of that for network latency -- our own pick, not from the API


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
        self.metadata = response_json["metadata"]      # fmin, fmax, xstart, xstop, nfft, xcount, gps_lock, scan_time, ...
        self.requested = response_json["requested"]     # what was actually asked for, echoed back
        self.gps_lock = response_json["metadata"].get("gps_lock")
        # Added with the live API. .get() because they've only been seen from
        # one node -- not confirmed that every node sends them.
        self.latitude = response_json.get("latitude")
        self.longitude = response_json.get("longitude")
        self.altitude = response_json.get("altitude")
        self.batch = response_json.get("batch")
        self.software_version = response_json.get("software_version")

    def __repr__(self):
        m = self.metadata
        return (f"<ScanResult mac={self.mac_address} n={self.data.size} "
                f"fmin={m.get('fmin')} fmax={m.get('fmax')} gps_lock={self.gps_lock}>")


def _get_json(url, params=None, timeout=10):
    """
    GET `url` and return the decoded JSON body. API errors come back as
    {"detail": ...} (e.g. "Node not found", "Node did not respond in
    time"); those are raised as requests.exceptions.HTTPError with the
    detail in the message.
    """
    resp = requests.get(url, params=params, timeout=timeout)
    try:
        body = resp.json()
    except ValueError:
        if resp.ok:
            raise
        body = {"detail": resp.text}
    if not resp.ok or (isinstance(body, dict) and "detail" in body):
        detail = body.get("detail") if isinstance(body, dict) else body
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} from {resp.url}: {detail}", response=resp
        )
    return body


def _get_scan(mac_address, params, base_url, timeout):
    return ScanResult(_get_json(f"{base_url}/scan/{mac_address}", params, timeout))


def scan(mac_address, freq, gain=None, base_url=BASE_URL, timeout=10,
         rbw=None, batch=None):
    """
    Request a scan from a node and return a ScanResult with the decoded
    array and metadata attached.

    freq: center frequency in Hz. The API itself takes MHz; the
        conversion happens here so everything in this module stays in Hz,
        matching the values the API sends back.
    gain, rbw, batch: left out of the request when None, so the server's
        own defaults apply (gain=1, rbw=23437.5, batch=0 as of Oct 2026).
        The server only accepts whole-number gain and batch.
    timeout: whole seconds the node is given to respond. Sent to the
        server, which waits a little longer than that before giving up;
        the HTTP request waits a little longer again.

    The server currently turns every request into a zero-span scan: the
    result is the node's native window centered on `freq`, not a span
    you choose.
    """
    params = {"freq": freq / 1e6, "timeout": timeout}
    if gain is not None:
        params["gain"] = gain
    if rbw is not None:
        params["rbw"] = rbw
    if batch is not None:
        params["batch"] = batch
    return _get_scan(mac_address, params, base_url,
                     timeout + SERVER_GRACE + HTTP_MARGIN)


def get_node(mac_address, base_url=BASE_URL, timeout=10):
    """Fetch a node's raw status dict (active, last_update, sensors, ...)."""
    return _get_json(f"{base_url}/node/{mac_address}", timeout=timeout)


def is_online(mac_address, base_url=BASE_URL, timeout=10):
    """
    Convenience wrapper answering the Stage 2 "is the node online"
    question directly from the API's own `active` field, rather than
    inferring it from timeouts or connection errors.
    """
    return get_node(mac_address, base_url=base_url, timeout=timeout)["active"]


def sweep(mac_address, fmin, fmax, step=None, gain=None, doBlock=True,
          base_url=BASE_URL, timeout=10):
    """
    Step across [fmin, fmax) in `step`-sized windows, requesting a
    periodogram over [frequency, frequency+step) at each one.

    Each step sends `fmin`/`fmax` in Hz -- not the same request shape as
    scan(), which sends a single `freq`. The live API doesn't accept this
    shape (as of Oct 2026 its scan endpoint takes only `freq` and always
    does a zero-span scan; how to request spans/sweeps is still to be
    agreed with Randy). That's expected, not a bug here: until the API
    supports it every step will fail and get skipped (see failure
    handling below). Written this way anyway because fmin/fmax is the
    real target shape, not the API's current limitation.

    doBlock=True (default): run the whole sweep, return a list of
        ScanResult once it's done.
    doBlock=False: return a generator yielding each ScanResult as it
        completes, so a caller can process/plot results as they arrive
        instead of blocking on the whole sweep.

    `step` defaults to this node's own `sample_rate_max` (from
    get_node()'s reported sensor capabilities) if not given. This matches real code:
    Icarus's server-side sweep() (tasks/rf/scan.py) defaults
    `step` to `receiver.get_ibw()`, a method on its internal `receiver`
    object. That method isn't reachable from this HTTP client -- it's
    server-side Python, not an API field -- so `sample_rate_max` is used
    here as the closest available proxy. NOT confirmed identical to what
    `get_ibw()` actually returns; revisit if sweep results look off at
    the edges of each step.

    Per-step pacing mirrors the server-side sweep()'s `time.sleep(0.1)`
    between steps. The reasoning for that specific value isn't documented
    in the source and isn't confirmed to apply here (this client is
    already paced by HTTP round-trip latency, which the tight server-side
    loop doesn't have) -- kept as a hedge, not a confirmed requirement.
    Remove/tune it if it proves unnecessary.

    A failed or timed-out scan at a given step is skipped with a printed
    warning rather than aborting the whole sweep.
    """
    if step is None:
        node = get_node(mac_address, base_url=base_url, timeout=timeout)
        receiver = next(
            (s for s in node["sensors"] if s["type"] == "sensors.rf.receiver"), None
        )
        if receiver is None:
            raise ValueError(
                f"node {mac_address} has no sensors.rf.receiver in its "
                "capabilities -- can't infer a default step, pass step= explicitly"
            )
        step = receiver["capabilities"].get("sample_rate_max")
        if not step:
            raise ValueError(
                f"node {mac_address}'s capabilities have no sample_rate_max -- "
                "can't infer a default step, pass step= explicitly"
            )

    def _run():
        frequency = fmin
        while frequency < fmax:
            params = {"fmin": frequency, "fmax": frequency + step}
            if gain is not None:
                params["gain"] = gain
            try:
                yield _get_scan(mac_address, params, base_url, timeout)
            except requests.exceptions.RequestException as exc:
                print(f"WARNING: scan at {frequency}-{frequency + step} Hz "
                      f"failed ({exc}), skipping")
            frequency += step
            time.sleep(0.1)

    if doBlock:
        return list(_run())
    return _run()


if __name__ == "__main__":
    import sys
    result = scan(sys.argv[1], freq=float(sys.argv[2]))
    print(result)
    print(result.data[:8])
"""
radiohound/core.py -- built against Randy's API on the radiohound_app
branch api_function_specs (Nov 2026; not deployed yet). All frequencies
are Hz, in requests and responses.
"""

import base64
import json
import warnings

import numpy
import requests

BASE_URL = "http://radiohound2.ee.nd.edu:8000/api"

# The server waits `timeout + 2` s for the node before answering 504; the
# HTTP request must outlast that. HTTP_MARGIN is our own pick, not from the API.
SERVER_GRACE = 2
HTTP_MARGIN = 3

# Seconds to open the connection for a streamed sweep; our own pick.
CONNECT_TIMEOUT = 5


def frequency_bins(xstart, xstop, xcount):
    """
    Frequency in Hz of each power value, lowest first -- for plotting.
    Assumes each value sits at its bin's center. Periodograms only.
    """
    return numpy.linspace(xstart, xstop, xcount)


def _decode(response_json):
    return numpy.frombuffer(base64.b64decode(response_json["data"]),
                            dtype=response_json["type"])


class ScanResult:
    """Wraps one periodogram response into something easy to work with."""

    def __init__(self, response_json):
        self.raw = response_json
        # Power per frequency bin, watts (per Chris, Oct 2026). Nominal
        # only on nodes without calibration data.
        self.data = _decode(response_json)
        self.mac_address = response_json["mac_address"]
        self.timestamp = response_json["timestamp"]
        self.center_frequency = response_json["center_frequency"]
        self.sample_rate = response_json["sample_rate"]
        self.metadata = response_json["metadata"]      # fmin, fmax, xstart, xstop, nfft, xcount, gps_lock, scan_time, ...
        self.requested = response_json["requested"]     # what was actually asked for, echoed back
        self.gps_lock = response_json["metadata"].get("gps_lock")
        # Live-API fields; .get() since only seen from one node so far.
        self.latitude = response_json.get("latitude")
        self.longitude = response_json.get("longitude")
        self.altitude = response_json.get("altitude")
        self.batch = response_json.get("batch")
        self.software_version = response_json.get("software_version")

    @property
    def frequencies(self):
        """Frequency in Hz of each value in .data (see frequency_bins())."""
        m = self.metadata
        return frequency_bins(m["xstart"], m["xstop"], m["xcount"])

    def __repr__(self):
        m = self.metadata
        return (f"<ScanResult mac={self.mac_address} n={self.data.size} "
                f"fmin={m.get('fmin')} fmax={m.get('fmax')} gps_lock={self.gps_lock}>")


class RawResult:
    """Wraps one raw (time-domain) capture. No frequency axis."""

    def __init__(self, response_json):
        self.raw = response_json
        # Units unconfirmed (asked Randy). Complex dtype on IQ nodes, if any.
        self.samples = _decode(response_json)
        self.mac_address = response_json.get("mac_address")
        self.timestamp = response_json["timestamp"]
        self.center_frequency = response_json["center_frequency"]
        self.sample_rate = response_json["sample_rate"]
        self.gain = response_json.get("gain")
        self.batch = response_json.get("batch")
        self.metadata = response_json["metadata"]      # data_type, sample_count, capture_duration_s, real_sampling, calibrated, ...
        self.requested = response_json["requested"]
        self.gps_lock = self.metadata.get("gps_lock")

    @property
    def times(self):
        """Time in seconds of each sample, from the start of the capture."""
        return numpy.arange(self.samples.size) / self.sample_rate

    def __repr__(self):
        return (f"<RawResult mac={self.mac_address} n={self.samples.size} "
                f"center={self.center_frequency} sample_rate={self.sample_rate} "
                f"gps_lock={self.gps_lock}>")


class SweepIncomplete(Exception):
    """A sweep stopped early. .results holds the windows captured before it did."""

    def __init__(self, results, error):
        super().__init__(f"sweep stopped after {len(results)} windows: {error}")
        self.results = results
        self.error = error


class SweepResult(list):
    """
    The windows of a streamed sweep, in order, as ScanResults (not stitched;
    see join_windows()). .complete: whether every window arrived. .error:
    the server's reason if not. .segments: windows the server reported sending.
    """

    def __init__(self, results, complete, error, segments):
        super().__init__(results)
        self.complete = complete
        self.error = error
        self.segments = segments


class SweepStream:
    """
    Iterate to get each window's ScanResult as it arrives. Can be iterated
    once. After iteration finishes, .complete, .error and .segments are set
    (they stay None if you break out early); .results holds every window so far.
    """

    def __init__(self, response, strict):
        self.results = []
        self.complete = None
        self.error = None
        self.segments = None
        self._response = response
        self._strict = strict
        self._iter = self._run()

    def __iter__(self):
        return self._iter

    def _run(self):
        ended = False
        try:
            for line in self._response.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if msg["type"] == "segment":
                    result = ScanResult(msg["result"])
                    self.results.append(result)
                    yield result
                elif msg["type"] == "end":
                    ended = True
                    self.complete = msg["complete"]
                    self.error = msg["error"]
                    self.segments = msg["segments"]
                    break
        except requests.exceptions.RequestException as exc:
            self.error = f"connection lost mid-sweep ({exc})"
        finally:
            self._response.close()

        if not ended:
            self.complete = False
            self.error = self.error or "stream ended without an end line (connection dropped?)"
            self.segments = len(self.results)
        if not self.complete:
            if self._strict:
                raise SweepIncomplete(SweepResult(self.results, False, self.error,
                                                  self.segments), self.error)
            warnings.warn(f"sweep incomplete after {len(self.results)} windows: {self.error}")


def _query(**params):
    """Drop None (so server defaults apply); send bools as true/false."""
    query = {}
    for key, value in params.items():
        if value is None:
            continue
        query[key] = ("true" if value else "false") if isinstance(value, bool) else value
    return query


def _raise_api_error(resp):
    """Raise requests.exceptions.HTTPError carrying the server's {"detail": ...}."""
    try:
        body = resp.json()
    except ValueError:
        body = {"detail": resp.text}
    detail = body.get("detail") if isinstance(body, dict) else body
    raise requests.exceptions.HTTPError(
        f"{resp.status_code} from {resp.url}: {detail}", response=resp
    )


def _get_json(url, params=None, timeout=10):
    """
    GET `url`, return the JSON body. API errors ({"detail": ...}) are
    raised as requests.exceptions.HTTPError with the detail in the message.
    """
    resp = requests.get(url, params=params, timeout=timeout)
    if not resp.ok:
        _raise_api_error(resp)
    body = resp.json()
    if isinstance(body, dict) and "detail" in body:
        _raise_api_error(resp)
    return body


def _http_wait(timeout):
    return timeout + SERVER_GRACE + HTTP_MARGIN


def scan(mac_address, freq=None, span=None, fmin=None, fmax=None, gain=None,
         rbw=None, batch=None, base_url=BASE_URL, timeout=10):
    """
    One periodogram as a ScanResult. Frequencies in Hz. Give one of:
      freq             zero-span: the node's native window centered on freq
      freq + span      freq +/- span/2, stitched on the node
      fmin + fmax      as given, stitched on the node
    Other shapes are rejected by the server (422 HTTPError).

    gain, rbw, batch: omitted when None, so server defaults apply
        (gain=1, rbw=23437.5, batch=0). gain and batch must be whole numbers.
        batch is a tag echoed back in result.batch.
    timeout: whole seconds for the whole request; raise it for wide spans.
    """
    params = _query(freq=freq, span=span, fmin=fmin, fmax=fmax, gain=gain,
                    rbw=rbw, batch=batch, timeout=timeout)
    return ScanResult(_get_json(f"{base_url}/scan/{mac_address}", params,
                                _http_wait(timeout)))


def raw(mac_address, freq, gain=None, n_samples=None, calibrated=None,
        batch=None, base_url=BASE_URL, timeout=10):
    """
    Raw time-domain samples centered on freq (Hz), as a RawResult.

    n_samples: defaults to the node's own default.
    calibrated: server default False.
    Out-of-range freq or n_samples is rejected on the node and arrives as
    a 504 HTTPError, same as a node that didn't answer.
    """
    params = _query(freq=freq, gain=gain, n_samples=n_samples,
                    calibrated=calibrated, batch=batch, timeout=timeout)
    return RawResult(_get_json(f"{base_url}/scan/{mac_address}/raw", params,
                               _http_wait(timeout)))


def sweep(mac_address, fmin=None, fmax=None, freq=None, span=None, gain=None,
          rbw=None, batch=None, doBlock=True, fast=False, strict=False,
          base_url=BASE_URL, timeout=10):
    """
    Cover a band (fmin + fmax, or freq + span, in Hz). The server steps
    through it one capture window at a time.

    fast=False (default): windows are streamed back as they are captured.
        doBlock=True  -> SweepResult (a list of ScanResults) once done
        doBlock=False -> SweepStream; iterate it to get each window live
        timeout is per window. The sweep stops at the first failed window;
        earlier windows are kept. If it stops early, a warning is issued,
        or with strict=True, SweepIncomplete (carrying .results) is raised.
    fast=True: the node steps and stitches; returns one ScanResult. timeout
        covers the whole band, and a failure returns no data (504).

    Errors before the first window (unknown node, bad params, probe scan
    timed out) are raised as HTTPError in both modes, when sweep() is called.
    """
    url = f"{base_url}/scan/{mac_address}/sweep"
    params = _query(fmin=fmin, fmax=fmax, freq=freq, span=span, gain=gain,
                    rbw=rbw, batch=batch, timeout=timeout, stream=not fast)
    if fast:
        return ScanResult(_get_json(url, params, _http_wait(timeout)))

    # The read timeout applies between chunks: covers the probe and each window.
    resp = requests.get(url, params=params, stream=True,
                        timeout=(CONNECT_TIMEOUT, _http_wait(timeout)))
    if not resp.ok:
        try:
            _raise_api_error(resp)
        finally:
            resp.close()
    stream = SweepStream(resp, strict)
    if not doBlock:
        return stream
    results = list(stream)
    return SweepResult(results, stream.complete, stream.error, stream.segments)


def join_windows(results):
    """
    Join sweep windows into one (frequencies, data) pair of arrays, in order.
    Neighbouring windows share an edge point, so a window's first point is
    dropped when it matches the previous window's last frequency (within
    1 Hz, for float rounding; bins are kHz apart). Array joining only: no
    overlap handling, no trimming to the requested band, no level matching.
    For a node-stitched spectrum, use sweep(..., fast=True) instead.
    """
    freq_parts, data_parts = [], []
    last = None
    for result in results:
        f, d = result.frequencies, result.data
        if last is not None and f.size and abs(f[0] - last) <= 1:
            f, d = f[1:], d[1:]
        if f.size:
            last = f[-1]
        freq_parts.append(f)
        data_parts.append(d)
    if not freq_parts:
        return numpy.array([]), numpy.array([])
    return numpy.concatenate(freq_parts), numpy.concatenate(data_parts)


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


if __name__ == "__main__":
    import sys
    result = scan(sys.argv[1], freq=float(sys.argv[2]))
    print(result)
    print(result.data[:8])

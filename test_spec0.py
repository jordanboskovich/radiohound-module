"""
Offline tests for spec0.py: requests.get is replaced by a fake, so nothing
is sent to a server. Run with `python3 test_spec0.py` (or pytest).
"""

import base64
import json
import warnings

import numpy
import requests

import spec0

MAC = "3484e4f58836"


class FakeResponse:
    def __init__(self, body=None, status=200, lines=None, url="http://fake"):
        self.body = body
        self.status_code = status
        self.lines = lines or []
        self.url = url
        self.text = json.dumps(body) if body is not None else ""
        self.closed = False

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self.body is None:
            raise ValueError("no JSON")
        return self.body

    def iter_lines(self):
        for line in self.lines:
            if isinstance(line, Exception):
                raise line
            yield line.encode()

    def close(self):
        self.closed = True


class FakeGet:
    """Stands in for requests.get; records each call, returns `response`."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, params=None, **kwargs):
        self.calls.append({"url": url, "params": params, **kwargs})
        return self.response

    def __enter__(self):
        self._real = spec0.requests.get
        spec0.requests.get = self
        return self

    def __exit__(self, *exc):
        spec0.requests.get = self._real


def _b64(array):
    return base64.b64encode(array.tobytes()).decode()


def periodogram(fmin, fmax, n=5, batch=0):
    data = numpy.arange(1, n + 1, dtype="float32") * 1e-12
    return {
        "data": _b64(data), "type": "float32", "mac_address": MAC,
        "timestamp": "2026-11-17T12:00:00.000000+00:00",
        "center_frequency": (fmin + fmax) / 2, "sample_rate": 48e6,
        "batch": batch,
        "metadata": {"data_type": "periodogram", "fmin": fmin, "fmax": fmax,
                     "xstart": fmin, "xstop": fmax, "xcount": n, "gps_lock": True},
        "requested": {"fmin": fmin, "fmax": fmax},
    }


def raw_payload(n=8):
    samples = numpy.linspace(-1, 1, n).astype("float32")
    return {
        "data": _b64(samples), "type": "float32", "mac_address": MAC,
        "timestamp": "2026-11-17T12:00:00.000000+00:00",
        "center_frequency": 915e6, "sample_rate": 48e6, "gain": 3, "batch": 7,
        "metadata": {"data_type": "raw", "sample_count": n,
                     "capture_duration_s": n / 48e6, "real_sampling": True,
                     "calibrated": False, "gps_lock": False, "scan_time": 0.1},
        "requested": {"center_frequency": 915e6, "gain": 3, "N_samples": n,
                      "calibrated": False},
    }


def ndjson(*messages):
    return [json.dumps(m) for m in messages]


def segment(i, fmin, fmax):
    return {"type": "segment", "index": i, "result": periodogram(fmin, fmax)}


def end(complete, segments, error=None):
    return {"type": "end", "complete": complete, "segments": segments, "error": error}


# --- params sent -----------------------------------------------------------

def test_scan_sends_hz_and_omits_none():
    with FakeGet(FakeResponse(periodogram(903e6, 927e6))) as get:
        spec0.scan(MAC, freq=915e6)
    call = get.calls[0]
    assert call["url"] == f"{spec0.BASE_URL}/scan/{MAC}"
    assert call["params"] == {"freq": 915e6, "timeout": 10}
    assert call["timeout"] == 10 + spec0.SERVER_GRACE + spec0.HTTP_MARGIN


def test_scan_band_params():
    with FakeGet(FakeResponse(periodogram(902e6, 928e6))) as get:
        spec0.scan(MAC, fmin=902e6, fmax=928e6, gain=3, rbw=11718.75,
                   batch=2, timeout=20)
    assert get.calls[0]["params"] == {"fmin": 902e6, "fmax": 928e6, "gain": 3,
                                      "rbw": 11718.75, "batch": 2, "timeout": 20}
    assert get.calls[0]["timeout"] == 25


def test_raw_params():
    with FakeGet(FakeResponse(raw_payload())) as get:
        spec0.raw(MAC, freq=915e6, n_samples=8, calibrated=True)
    call = get.calls[0]
    assert call["url"] == f"{spec0.BASE_URL}/scan/{MAC}/raw"
    assert call["params"] == {"freq": 915e6, "n_samples": 8,
                              "calibrated": "true", "timeout": 10}


def test_sweep_fast_sends_stream_false():
    with FakeGet(FakeResponse(periodogram(4.4e9, 4.448e9))) as get:
        r = spec0.sweep(MAC, fmin=4.4e9, fmax=4.448e9, fast=True, timeout=20)
    call = get.calls[0]
    assert call["url"] == f"{spec0.BASE_URL}/scan/{MAC}/sweep"
    assert call["params"] == {"fmin": 4.4e9, "fmax": 4.448e9, "timeout": 20,
                              "stream": "false"}
    assert call["timeout"] == 25
    assert "stream" not in call          # plain request, not a streamed read
    assert isinstance(r, spec0.ScanResult)


# --- decoding --------------------------------------------------------------

def test_scan_result_decoding():
    with FakeGet(FakeResponse(periodogram(100e6, 104e6, batch=4))):
        r = spec0.scan(MAC, freq=102e6)
    assert numpy.allclose(r.data, numpy.arange(1, 6) * 1e-12)
    assert numpy.allclose(r.frequencies, [100e6, 101e6, 102e6, 103e6, 104e6])
    assert r.batch == 4 and r.gps_lock is True


def test_raw_result_decoding():
    with FakeGet(FakeResponse(raw_payload(n=8))):
        cap = spec0.raw(MAC, freq=915e6)
    assert numpy.allclose(cap.samples, numpy.linspace(-1, 1, 8))
    assert numpy.allclose(cap.times, numpy.arange(8) / 48e6)
    assert cap.batch == 7 and cap.gain == 3 and cap.gps_lock is False
    assert cap.metadata["data_type"] == "raw"
    assert "RawResult" in repr(cap)


# --- errors ----------------------------------------------------------------

def test_api_error_carries_detail():
    with FakeGet(FakeResponse({"detail": "Node not found"}, status=404)):
        try:
            spec0.scan("nope", freq=915e6)
        except requests.exceptions.HTTPError as exc:
            assert "404" in str(exc) and "Node not found" in str(exc)
        else:
            raise AssertionError("no HTTPError")


def test_streamed_sweep_http_error():
    detail = [{"loc": ["query", "fmin"], "msg": "bad"}]
    resp = FakeResponse({"detail": detail}, status=422)
    with FakeGet(resp):
        try:
            spec0.sweep(MAC, fmin=1, fmax=2)
        except requests.exceptions.HTTPError as exc:
            assert "422" in str(exc) and "bad" in str(exc)
        else:
            raise AssertionError("no HTTPError")
    assert resp.closed


# --- streamed sweeps -------------------------------------------------------

def test_complete_sweep():
    lines = ndjson(segment(0, 4.400e9, 4.424e9), segment(1, 4.424e9, 4.448e9),
                   end(True, 2))
    with FakeGet(FakeResponse(lines=lines)) as get:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = spec0.sweep(MAC, fmin=4.4e9, fmax=4.448e9)
    call = get.calls[0]
    assert call["params"]["stream"] == "true"
    assert call["stream"] is True
    assert call["timeout"] == (spec0.CONNECT_TIMEOUT, 15)
    assert isinstance(result, spec0.SweepResult) and len(result) == 2
    assert all(isinstance(r, spec0.ScanResult) for r in result)
    assert result.complete is True and result.error is None and result.segments == 2
    assert get.response.closed


def test_incomplete_sweep_warns():
    lines = ndjson(segment(0, 4.400e9, 4.424e9), end(False, 1, "Node did not respond"))
    with FakeGet(FakeResponse(lines=lines)):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = spec0.sweep(MAC, fmin=4.4e9, fmax=4.448e9)
    assert len(caught) == 1 and "Node did not respond" in str(caught[0].message)
    assert len(result) == 1 and result.complete is False
    assert result.error == "Node did not respond"


def test_incomplete_sweep_strict_raises():
    lines = ndjson(segment(0, 4.400e9, 4.424e9), end(False, 1, "Node did not respond"))
    with FakeGet(FakeResponse(lines=lines)):
        try:
            spec0.sweep(MAC, fmin=4.4e9, fmax=4.448e9, strict=True)
        except spec0.SweepIncomplete as exc:
            assert len(exc.results) == 1
            assert isinstance(exc.results[0], spec0.ScanResult)
            assert exc.error == "Node did not respond"
        else:
            raise AssertionError("no SweepIncomplete")


def test_stream_without_end_line():
    lines = ndjson(segment(0, 4.400e9, 4.424e9))
    with FakeGet(FakeResponse(lines=lines)):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = spec0.sweep(MAC, fmin=4.4e9, fmax=4.448e9)
    assert len(caught) == 1
    assert result.complete is False and len(result) == 1
    assert "end line" in result.error


def test_connection_dropped_mid_stream():
    lines = ndjson(segment(0, 4.400e9, 4.424e9))
    lines.append(requests.exceptions.ChunkedEncodingError("reset"))
    with FakeGet(FakeResponse(lines=lines)):
        try:
            spec0.sweep(MAC, fmin=4.4e9, fmax=4.448e9, strict=True)
        except spec0.SweepIncomplete as exc:
            assert len(exc.results) == 1 and "connection lost" in exc.error
        else:
            raise AssertionError("no SweepIncomplete")


def test_sweep_stream_yields_live():
    lines = ndjson(segment(0, 4.400e9, 4.424e9), segment(1, 4.424e9, 4.448e9),
                   end(True, 2))
    with FakeGet(FakeResponse(lines=lines)):
        stream = spec0.sweep(MAC, fmin=4.4e9, fmax=4.448e9, doBlock=False)
        assert isinstance(stream, spec0.SweepStream) and stream.complete is None
        seen = [w for w in stream]
    assert len(seen) == 2 and stream.results == seen
    assert stream.complete is True and stream.segments == 2


def test_sweep_stream_break_early():
    lines = ndjson(segment(0, 4.400e9, 4.424e9), segment(1, 4.424e9, 4.448e9),
                   end(True, 2))
    resp = FakeResponse(lines=lines)
    with FakeGet(resp):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            stream = spec0.sweep(MAC, fmin=4.4e9, fmax=4.448e9, doBlock=False)
            for w in stream:
                break
            stream._iter.close()   # what the garbage collector would do
    assert len(stream.results) == 1 and stream.complete is None
    assert resp.closed


# --- join_windows ----------------------------------------------------------

def test_join_windows_drops_shared_edge():
    a = spec0.ScanResult(periodogram(100e6, 104e6))
    b = spec0.ScanResult(periodogram(104e6, 108e6))
    freqs, power = spec0.join_windows([a, b])
    assert freqs.size == power.size == 9
    assert numpy.allclose(freqs, numpy.linspace(100e6, 108e6, 9))
    assert numpy.allclose(power, numpy.concatenate([a.data, b.data[1:]]))


def test_join_windows_keeps_gap():
    a = spec0.ScanResult(periodogram(100e6, 104e6))
    b = spec0.ScanResult(periodogram(105e6, 109e6))
    freqs, _ = spec0.join_windows([a, b])
    assert freqs.size == 10


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)

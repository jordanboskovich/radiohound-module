# radiohound-module

A Python module giving experimenters a simple, synchronous interface to
RadioHound sensor nodes — no MQTT callback handling required. Built for the
Wireless Institute (Notre Dame), replacing Icarus's non-scriptable web
dashboard and hand-rolled MQTT as the way to run experiments.

Owner: Jordan Boskovich · RadioHound STRAND, Fall 2026.

## Status (Nov 17, 2026)

The module is written against the **new API** (radiohound_app branch
`api_function_specs`), which is **not deployed yet**. The server at
`radiohound2.ee.nd.edu` still runs the old API, so `scan()`, `raw()` and
`sweep()` will fail against it until Randy deploys. Offline tests
(`test_spec0.py`) pass; live testing comes after the deploy.

New in this version: span scans, raw time-domain captures, and
server-stepped sweeps (streamed or node-stitched). All frequencies are Hz.

## Files

- [spec0.py](spec0.py) — the working code:
  - `scan()` — one periodogram: zero-span, `freq` + `span`, or `fmin` + `fmax`
  - `raw()` — time-domain samples, returned as a `RawResult`
  - `sweep()` — cover a band window by window (streamed), or node-stitched
    with `fast=True`
  - `join_windows()` — join sweep windows into one pair of arrays
  - `get_node()`, `is_online()` — node status
- [test_spec0.py](test_spec0.py) — offline tests with a fake
  `requests.get`; run `python3 test_spec0.py`.
- `CONTEXT.md` — full project context, findings log and open questions.
  Kept locally; not tracked in this repo.

## Design

One general-purpose core (connect / send a command / get data back) plus
thin, specialized layers per use case — calibration/sweep, fast
debugging, and multi-node occupancy mapping — the same pattern as pandas'
`DataFrame` plus its accessors.

## Examples

```python
import numpy as np
import matplotlib.pyplot as plt
import requests
from spec0 import scan, raw, sweep, join_windows, is_online, SweepIncomplete

MAC = "3484e4f58836"   # WI-Lab, RadioHound board at Notre Dame
```

**1. Check the node before an experiment**
```python
if not is_online(MAC):
    raise SystemExit("node is offline")
```

**2. Quick look at one frequency (zero-span, the node's native window)**
```python
r = scan(MAC, freq=915e6)            # Hz; about 24 MHz around 915 MHz on this node
plt.plot(r.frequencies / 1e6, 10 * np.log10(r.data) + 30)   # data is watts per bin -> dBm
plt.xlabel("MHz"); plt.ylabel("dBm"); plt.show()
```

**3. One spectrum of a whole band, stitched on the node**
```python
r = scan(MAC, fmin=902e6, fmax=928e6, timeout=20)   # or freq=915e6, span=26e6
print(r.data.size, "bins from", r.metadata["fmin"], "to", r.metadata["fmax"])
```

**4. Raw time-domain capture, saved for offline processing**
```python
cap = raw(MAC, freq=915e6, n_samples=65536)
np.save("capture_915MHz.npy", cap.samples)
print(cap.sample_rate, cap.metadata["capture_duration_s"])
```

**5. Streaming sweep: plot live, stop early when a signal shows up**
```python
threshold_w = 1e-9
for w in sweep(MAC, fmin=2.4e9, fmax=2.5e9, doBlock=False):
    plt.plot(w.frequencies / 1e6, w.data); plt.pause(0.01)
    if w.data.max() > threshold_w:
        print("signal near", w.frequencies[w.data.argmax()] / 1e6, "MHz")
        break
```

**6. Full sweep, then join the windows into one spectrum**
```python
result = sweep(MAC, fmin=4.4e9, fmax=4.448e9)        # warns if any window failed
print("complete:", result.complete, "windows:", len(result))
freqs, power = join_windows(result)
```

**7. Fast sweep: the node steps and stitches, one result**
```python
r = sweep(MAC, fmin=4.4e9, fmax=4.448e9, fast=True, timeout=20)
```

**8. Tag repeated measurements with `batch` (e.g. a gain series)**
```python
results = {}
for batch, gain in enumerate([0, 3, 6, 9]):
    r = scan(MAC, freq=915e6, gain=gain, batch=batch)
    results[gain] = r
    assert r.batch == batch       # echoed back by the node
```

**9. Error handling for long unattended runs**
```python
try:
    result = sweep(MAC, fmin=24e6, fmax=1.7e9, strict=True)
except SweepIncomplete as e:
    print("sweep stopped early:", e.error)
    result = e.results            # keep what was captured
except requests.exceptions.HTTPError as e:
    print("API error:", e)        # 404 unknown node, 504 node didn't answer, 422 bad params
```

Notes:

- `timeout` is whole seconds. For `scan()` and `sweep(fast=True)` it covers
  the whole request, so raise it for wide bands; for a streamed `sweep()`
  it applies per window.
- A streamed sweep stops at the first failed window and keeps the earlier
  ones. By default you get a warning and the partial result
  (`result.complete` is `False`); `strict=True` raises `SweepIncomplete`
  instead.
- Node-side rejections (out-of-range frequency, bad `n_samples`) arrive as
  a 504, the same as a node that didn't answer.
- The units of `raw()` samples are not confirmed yet.

## Requirements

`numpy` and `requests`; `matplotlib` for the plotting examples.

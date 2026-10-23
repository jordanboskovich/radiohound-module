# radiohound-module

A Python module giving experimenters a simple, synchronous interface to
RadioHound sensor nodes — no MQTT callback handling required. Built for Notre Dame's
Wireless Institute, replacing Icarus's non-scriptable web
dashboard and hand-rolled MQTT as the way to run experiments.

Owner: Jordan Boskovich · RadioHound STRAND, Fall 2026.

## Status

**Stage 1 works against the live API**: `scan()` returns real data from a
real node at `http://radiohound2.ee.nd.edu:8000/api/`. 

Sweeps work in a beta form only (`sweep_beta()`). The API currently
supports single zero-span scans, so the real `sweep()` is a commented-out
draft in `spec0.py.'

## Files

- [spec0.py](spec0.py) — the working code:
  - `scan()` — one scan from one node, returned as a `ScanResult`
  - `get_node()`, `is_online()` — node status
  - `sweep_beta()` — covers a band with back-to-back scans
  - commented-out `sweep()` — open API design questions
- [stage0_ideas.py](stage0_ideas.py) — draft interface ideas: `nodestats()`,
  `select()` / `Node` (working), `getnodes()`, `Node.getjoblist()` (stubs).

## Design

One general-purpose core (connect / send a command / get data back) plus
thin, specialized layers per use case — calibration/sweep, fast
debugging, and multi-node occupancy mapping — the same pattern as pandas'
`DataFrame` plus its accessors.

## Quick usage

All frequencies are in **Hz**.

```python
import matplotlib.pyplot as plt
from spec0 import scan, is_online, sweep_beta

result = scan("<mac_address>", freq=4444e6, gain=4)
print(result)            # summary
print(result.data)       # numpy array of power per bin, in Watts
print(result.metadata)   # fmin, fmax, nfft, xcount, ...

plt.plot(result.frequencies, result.data)   # frequency (Hz) of each value

print(is_online("<mac_address>"))

results = sweep_beta("<mac_address>", fmin=4400e6, fmax=4448e6)
```

Each scan returns the node's native window centered on `freq` (24 MHz wide
on the node tested). Errors from the API, such as an unknown node, are
raised as `requests.exceptions.HTTPError` with the server's message.

Requires `numpy` and `requests`.

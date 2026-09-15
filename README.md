# radiohound-module

A Python module giving experimenters a simple, synchronous interface to
RadioHound sensor nodes — no MQTT callback handling required. Built for the
Wireless Institute (Notre Dame), replacing Icarus's non-scriptable web
dashboard and hand-rolled MQTT as the way to run experiments.

Owner: Jordan Boskovich · RadioHound STRAND, Fall 2026.

## Status

**Stage 1** (single-node scan against Randy's dummy HTTP API). See
[CONTEXT.md](CONTEXT.md) for full project context, the staged plan, and
open questions being tracked.

## Files

- [spec0.py](spec0.py) — current Stage 1 code. `scan()`, `get_node()`,
  `is_online()`, and a `ScanResult` wrapper, built against the dummy API at
  `http://radiohound2.ee.nd.edu:8000/api/`.

## Design

One general-purpose core (connect / send a command / get data back) plus
thin, specialized layers per use case — calibration/sweep, fast
debugging, and multi-node occupancy mapping — the same pattern as pandas'
`DataFrame` plus its accessors. See `CONTEXT.md` §5–6 for the reasoning
and §7 for the staged rollout plan.

## Quick usage (Stage 1)

```python
from spec0 import scan, get_node, is_online

result = scan("<mac_address>", freq=2000e6, gain=1)
print(result)

print(is_online("<mac_address>"))
```

Requires `numpy` and `requests`.

"""
radiohound -- Stage 0 interface ideas, from conversations with various
people (not yet circulated to FPGA DAQ / Command & Control -- see
CONTEXT.md #7 Stage 0).

These are DRAFT SIGNATURES ONLY. Where the body needs something not yet
confirmed -- an API endpoint that may not exist, a data shape we haven't
seen, a design decision that's really a preference call -- it's left as
a comment/NotImplementedError instead of guessed-at code. Fill in as
things get confirmed; delete the comment once its question is answered.

`scan(nodename, frequency)` and `sweep()` are not repeated here -- both
now live in spec0.py (scan(mac_address, freq, gain=None, ...) and
sweep_beta(mac_address, fmin, fmax, gain=None, rbw=None, doBlock=True))
and work against the live API. See the Node.scan() note below for how
scan() might connect to select().
"""

from spec0 import BASE_URL, get_node, scan


def nodestats(mac_address, base_url=BASE_URL, timeout=10):
    """
    What can this node do -- its sensors and each sensor's capabilities
    (gain range, frequency range, sample rate, calibration data, ...).

    Thin wrapper around get_node(), which returns real node data:
        {"sensors": [{"type": "sensors.rf.receiver", "capabilities": {...}}]}

    As of Oct 2026, of 36 registered nodes: 25 report exactly one
    sensors.rf.receiver, 11 report no sensors (returns []). None report
    more than one, so multi-sensor handling is still untested.
    """
    node = get_node(mac_address, base_url=base_url, timeout=timeout)
    return node["sensors"]


class Node:
    """
    Handle for one node, returned by select() so callers don't have to
    keep passing mac_address around.

    OPEN DESIGN QUESTIONS (not data-shape unknowns -- these are genuine
    preference calls, make them deliberately rather than by accident):
    - Should select() eagerly check the node is reachable/online (an
      extra is_online() call up front), or stay lazy and let the first
      real call surface any failure?
    - Does this stay a thin wrapper (just mac_address + delegating
      methods, as sketched below), or grow real per-node state (cached
      capabilities from nodestats(), cached last-known-online status)?
      The pandas-analogy note in CONTEXT.md #5 (one core, thin layers on
      top) leans toward "thin," but worth deciding explicitly.
    - Should nodestats()/getnodes() below also become Node methods for
      consistency, or intentionally stay module-level (nodestats is a
      "tell me about a node I already know the ID of" question, getnodes
      is a "help me find a node" question -- arguably different enough
      to justify the split as-is).
    """

    def __init__(self, mac_address):
        self.mac_address = mac_address

    def scan(self, freq, gain=None, **kwargs):
        """Delegates to spec0.scan() -- no open questions here, just wiring."""
        return scan(self.mac_address, freq, gain=gain, **kwargs)

    def getjoblist(self):
        """
        List jobs/tasks running or queued on this node -- to answer "is
        this node busy right now" without inferring it from a slow scan().

        NOT WRITTEN -- the API has no per-node job list (as of Oct 2026):
        - Jobs exist, but under experiments/sessions: POST
          /api/sessions/<id>/job creates one, GET /api/jobs/<job_id>
          reads one. Nothing lists jobs by node.
        - GET /api/node/<mac>/scan-stats exists; not explored.
        - ASK RANDY: how should a client tell that a node is busy?
        """
        raise NotImplementedError(
            "the API has no per-node job list yet -- see docstring"
        )


def select(mac_address):
    """
    Same idea as "connect," named more clearly. Returns a Node so you
    don't have to keep passing mac_address to every call.

    See the open design questions on the Node class above before this
    goes from "obvious stub" to "final shape."
    """
    return Node(mac_address)


def getnodes(bbox=None):
    """
    Tell me all nodes that are online, optionally filtered to a
    geographic box.

    NOT WRITTEN. What's known (as of Oct 2026):
    - GET /api/nodes exists, no auth. Returns {"nodes": [...], "groups":
      [...]}; each node has the same fields as /api/node/<mac>, including
      `active`. So the unfiltered version is writable today.
    - Location is only returned to logged-in users (anonymous callers get
      a reduced node view; /api/nodes/gps returns 401). The bbox filter
      is blocked on login.
    - Scan responses carry latitude/longitude, but that is a per-scan
      reading; not confirmed to equal a node's registered location.
    - bbox format (corners? center+radius? coordinate order?) undecided.
    """
    raise NotImplementedError(
        "not written yet -- /api/nodes exists, location filter is blocked; see docstring"
    )


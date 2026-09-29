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
now live in spec0.py (scan(mac_address, freq, gain=None) and
sweep(mac_address, fmin, fmax, step=None, gain=None, doBlock=True)) and
work against the dummy API. See the Node.scan() note below for how scan()
might connect to select().
"""

from spec0 import BASE_URL, get_node, scan


def nodestats(mac_address, base_url=BASE_URL, timeout=10):
    """
    What can this node do -- its sensors and each sensor's capabilities
    (gain range, frequency range, sample rate range, etc).

    This one we mostly know: the confirmed dummy /api/node/<mac> response
    already includes this under `sensors`:
        {"sensors": [{"type": "sensors.rf.receiver", "capabilities": {...}}]}
    So this is a thin wrapper around get_node().

    CAVEAT: the dummy API is mocked/hardcoded -- trust the shape, not
    that every real node has exactly one `sensors.rf.receiver` entry.
    Once this hits real nodes, confirm whether multi-sensor nodes are
    a real thing worth handling here (e.g. a node with both an RF
    receiver and a GPS/locationing sensor -- `rf/scan.py` references
    'sensors.locationing' separately from 'sensors.rf.receiver').
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
        List jobs/tasks currently running or queued on this node -- e.g.
        to answer CONTEXT.md Stage 2's "is this node busy right now"
        question directly, instead of inferring busy-ness from a failed
        or slow scan() call.

        NOT CONFIRMED: no endpoint for this has shown up yet. The dummy
        API only has /api/node/<mac> (status: active/last_update/sensors)
        and /api/scan/<mac> (request a scan) -- neither obviously exposes
        a job queue.

        Icarus's private repo has a `tasks/` folder (CONTEXT.md #9,
        listed but not yet read) that's the most likely place a
        job/queue/status concept would live, given task_name and
        batch_id already show up in the scan task payloads reviewed so
        far (see rf/scan.py in CONTEXT.md #4). If you find something in
        there with "queue", "status", or "job" in the name, paste it in
        -- that would tell us what a "job" looks like (state field?
        keyed by batch_id?) and whether it's reachable over HTTP or only
        over MQTT.
        """
        raise NotImplementedError(
            "no confirmed API endpoint for per-node job/task lists yet -- see docstring"
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

    NOT CONFIRMED -- two separate unknowns, don't guess at either:

    1. Is there a bulk "list all nodes" endpoint at all? Everything
       confirmed so far (/api/node/<mac>, /api/scan/<mac>) is keyed by a
       mac_address you already have to know going in. Need to ask Randy
       (or check the public github.com/ndwireless/radiohound repo's
       docs/scripts, per CONTEXT.md #9) whether something like
       `/api/nodes` exists, and if so what fields it returns per node.

    2. If a bulk endpoint exists, does it include location? The
       confirmed /api/node/<mac> shape (CONTEXT.md #3) does NOT include
       lat/lon -- it's id/active/last_update/ip_address/hardware_type/
       sensors/git_branch. Scan *payloads* do carry latitude/longitude/
       altitude (seen in rf/scan.py's periodogram()/raw() payloads,
       sourced from the node's GPS sensor) -- but that's a per-scan GPS
       reading, not obviously the same thing as a static registry
       location you could filter on without having already scanned every
       candidate node. Don't assume these are interchangeable without
       confirming.

    bbox format itself (corners? center+radius? which coordinate order?)
    is also undecided -- not worth bikeshedding before (1) is answered.
    """
    raise NotImplementedError(
        "no confirmed bulk node-listing endpoint yet -- see docstring"
    )


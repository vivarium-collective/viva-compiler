"""RewriteHandler — the base for event-driven rewrite handlers.

An ordinary handler must conform to its draft's signature. A *rewrite* handler
realises an event-driven graph rewrite (e.g. cell division partitioning one cell
into two), whose draft signature is typically a placeholder; its real contract is
the ports the composite node WIRES. Marking a handler ``REWRITE = True`` tells the
compiler to check it against the node's wiring instead of the signature (law 2′).

Subclassing this is optional — the compiler only checks for a truthy class-level
``REWRITE`` attribute — but it documents intent and gives the marker one home.
"""
from __future__ import annotations

from process_bigraph import Process


class RewriteHandler(Process):
    """Marker base: conformance is checked against the node's wiring, not the
    draft's (placeholder) signature."""
    REWRITE = True

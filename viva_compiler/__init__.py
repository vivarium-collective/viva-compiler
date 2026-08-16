"""viva-compiler — a semantic→executable compiler for process-bigraph.

Compile a composite of *draft processes* (typed-port effect signatures) into an
executable composite by installing a conforming ``Process`` *handler* for each,
while preserving the place-graph and every wire. Domain-agnostic: handlers, draft
composites, and any ontology are the caller's.

Public API
----------
* :class:`Compiler` — the ergonomic object API.
* :func:`compile_composite` — the functor ``⟦C⟧_H`` (functional API).
* :func:`check_conformance` / :func:`check_wiring_conformance` — the ``H ⊢ S`` judgment.
* :func:`signature_of`, :func:`interface_of`, :func:`is_rewrite`.
* :class:`Signature`, :class:`ConformanceReport`, :class:`CompileError`.
* :func:`default_type_compatible` — the default type check; pass your own via
  ``type_compatible=`` to widen it (e.g. ontology-aware).
* :class:`RewriteHandler` — base marker for event-driven rewrite handlers.
"""
from __future__ import annotations

from .compiler import (
    Compiler,
    CompileError,
    ConformanceReport,
    Signature,
    check_conformance,
    check_wiring_conformance,
    compile_composite,
    default_type_compatible,
    interface_of,
    is_rewrite,
    signature_of,
)
from .reactions import ReactionRule, reaction_step_node, run_reactions
from .rewrite import RewriteHandler

__all__ = [
    "Compiler",
    "CompileError",
    "ConformanceReport",
    "Signature",
    "RewriteHandler",
    "ReactionRule",
    "reaction_step_node",
    "run_reactions",
    "check_conformance",
    "check_wiring_conformance",
    "compile_composite",
    "default_type_compatible",
    "interface_of",
    "is_rewrite",
    "signature_of",
]

__version__ = "0.1.0"

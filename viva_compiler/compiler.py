"""viva-compiler — compile a semantic (draft-process) composite into an executable one.

The domain-agnostic core of the semantic→executable compiler. It is an algebraic
effect system over process-bigraph:

* a **draft process** is an effect *signature* — typed input/output ports (+ an
  optional behavior contract), with an inert ``update``;
* an executable **Process** is a *handler* for a signature;
* a **handler environment** ``{DraftName: {handler, config, init, refine}}`` assigns
  each signature a handler (with config, initial store values, and declared store
  refinements);
* :func:`compile_composite` (``⟦C⟧_H``) is the functor that swaps each draft node
  for its handler while **preserving the place-graph (stores) and every wire**.

Nothing here is domain-specific. Handlers, draft composites, and any ontology are
supplied by the caller. Type compatibility is a **pluggable hook**
(``type_compatible``) so a workspace can widen it (e.g. ontology-equal types)
without changing this package.

Laws (see the README and tests):
1. **Conformance** — ``⟦C⟧_H`` is defined only if every handler supplies its
   signature's ports with compatible types.
2. **Interface preservation** — ``interface_of(⟦C⟧_H) == interface_of(C)``; only a
   declared ``refine`` may change a leaf's schema.
3. **Executability** — the compiled composite builds and runs; the semantic one is inert.
4. **Handler independence** — two conforming environments give two executables
   sharing one interface.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable, Optional

TypeCompatible = Callable[[object, str, str], bool]


class CompileError(Exception):
    """Raised when a handler environment does not conform to the semantic composite."""


# ── port introspection ────────────────────────────────────────────────────────
def _ports(cls, kind: str) -> dict:
    """A class's ``inputs``/``outputs`` port dict, obtained config-independently.

    Draft processes and workspace handlers declare fixed ports, so we introspect
    the class uninitialised (calling the method with the class as ``self``); fall
    back to a throwaway instance for classes whose ports method reads ``self``.
    """
    fn = getattr(cls, kind)
    try:
        return dict(fn(cls))
    except Exception:
        try:
            return dict(fn(cls.__new__(cls)))
        except Exception:
            return {}


@dataclass
class Signature:
    """The typed interface of a draft process: named input/output ports."""
    name: str
    inputs: dict
    outputs: dict


def signature_of(core, draft_name: str) -> Signature:
    cls = core.link_registry[draft_name]
    return Signature(draft_name, _ports(cls, "inputs"), _ports(cls, "outputs"))


# ── type compatibility (pluggable) ────────────────────────────────────────────
def default_type_compatible(core, sig_t, handler_t) -> bool:
    """A handler port type conforms to a signature port type if they are equal or
    the handler type inherits the signature type (a subtype). Workspaces can pass a
    wider hook (e.g. ontology-aware) via ``type_compatible=``."""
    if sig_t == handler_t:
        return True
    try:
        schema = core.access(handler_t) or {}
        inherit = schema.get("_inherit")
        return inherit == sig_t or sig_t in (inherit or [])
    except Exception:
        return False


# ── conformance: the H ⊢ S judgment ───────────────────────────────────────────
@dataclass
class ConformanceReport:
    draft: str
    handler: str
    missing: list = field(default_factory=list)          # (direction, port)
    type_mismatches: list = field(default_factory=list)  # (direction, port, sig_t, handler_t)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.type_mismatches

    def __str__(self) -> str:
        if self.ok:
            return f"{self.handler} ⊢ {self.draft}  ✓"
        parts = [f"{self.handler} ⊬ {self.draft}"]
        for d, p in self.missing:
            parts.append(f"  missing {d} port '{p}'")
        for d, p, st, ht in self.type_mismatches:
            parts.append(f"  {d} port '{p}': signature {st} vs handler {ht}")
        return "\n".join(parts)


def check_conformance(core, draft_name: str, handler_name: str,
                      allow_refine: Optional[set] = None,
                      type_compatible: Optional[TypeCompatible] = None) -> ConformanceReport:
    """A handler conforms iff it supplies every signature port with a compatible
    type. ``allow_refine`` names ports whose type may legitimately differ because
    the environment refines the store they wire to. ``type_compatible`` overrides
    the default equality/subtype check."""
    allow_refine = allow_refine or set()
    tc = type_compatible or default_type_compatible
    sig = signature_of(core, draft_name)
    hcls = core.link_registry[handler_name]
    h_in, h_out = _ports(hcls, "inputs"), _ports(hcls, "outputs")
    rep = ConformanceReport(draft_name, handler_name)
    for direction, sig_ports, h_ports in (("input", sig.inputs, h_in),
                                          ("output", sig.outputs, h_out)):
        for port, sig_t in sig_ports.items():
            if port not in h_ports:
                rep.missing.append((direction, port))
            elif not tc(core, sig_t, h_ports[port]) and port not in allow_refine:
                rep.type_mismatches.append((direction, port, sig_t, h_ports[port]))
    return rep


def is_rewrite(core, handler_name: str) -> bool:
    """A rewrite handler declares itself with a class-level ``REWRITE = True``."""
    cls = core.link_registry.get(handler_name)
    return bool(getattr(cls, "REWRITE", False))


def check_wiring_conformance(core, node: dict, handler_name: str) -> ConformanceReport:
    """Rewrite-handler conformance: the handler's ports must be exactly the ports
    the *node* wires (name-bijection per direction), so the composite builds and
    every wire has a port. The draft's own signature is a placeholder here."""
    hcls = core.link_registry[handler_name]
    h_in, h_out = set(_ports(hcls, "inputs")), set(_ports(hcls, "outputs"))
    n_in = set((node.get("inputs") or {}).keys())
    n_out = set((node.get("outputs") or {}).keys())
    rep = ConformanceReport(_draft_name(node) or "?", handler_name)
    for p in n_in - h_in:
        rep.missing.append(("wired-input", p))
    for p in n_out - h_out:
        rep.missing.append(("wired-output", p))
    for p in h_in - n_in:
        rep.missing.append(("handler-input-not-wired", p))
    for p in h_out - n_out:
        rep.missing.append(("handler-output-not-wired", p))
    return rep


# ── the compile functor ⟦C⟧_H ─────────────────────────────────────────────────
def compile_composite(semantic_state: dict, handler_env: dict, core,
                      type_compatible: Optional[TypeCompatible] = None) -> dict:
    """Return the executable state for ``semantic_state`` under ``handler_env``.

    Deep-copies the state; for each process node whose draft is handled, checks
    conformance (rewrite handlers against wiring, others against the signature),
    rewrites the node's ``address`` to the handler and merges its ``config``, then
    applies the environment's declared ``init``/``refine`` store overrides. Stores
    and wires are otherwise untouched. Raises :class:`CompileError` on
    non-conformance.
    """
    out = deepcopy(semantic_state)
    refine_ports_by_draft = _refined_ports(semantic_state, handler_env)

    def walk(node):
        if not isinstance(node, dict):
            return
        for val in node.values():
            if not isinstance(val, dict):
                continue
            if val.get("_type") == "process":
                _compile_node(val, handler_env, core, refine_ports_by_draft, type_compatible)
            elif "_type" not in val:
                walk(val)

    walk(out)
    _apply_store_overrides(out, handler_env)
    return out


def _draft_name(node: dict) -> Optional[str]:
    addr = str(node.get("address", ""))
    return addr.split(":")[-1] if addr.startswith("local:") else None


def _compile_node(node, handler_env, core, refine_ports_by_draft, type_compatible) -> None:
    draft = _draft_name(node)
    if draft is None or draft not in handler_env:
        return
    spec = handler_env[draft]
    handler = spec["handler"]
    if is_rewrite(core, handler):
        rep = check_wiring_conformance(core, node, handler)
    else:
        rep = check_conformance(core, draft, handler,
                                allow_refine=refine_ports_by_draft.get(draft, set()),
                                type_compatible=type_compatible)
    if not rep.ok:
        raise CompileError(str(rep))
    node["address"] = f"local:{handler}"
    node["config"] = {**spec.get("config", {}), **(node.get("config") or {})}
    node.pop("_draft", None)


def _refined_ports(semantic_state, handler_env) -> dict:
    """Map draft name → set of its port names whose wired store is refined."""
    refined_paths = {tuple(p.split("."))
                     for spec in handler_env.values()
                     for p in (spec.get("refine") or {})}
    out: dict = {}
    for node in _iter_processes(semantic_state):
        draft = _draft_name(node)
        if draft is None or draft not in handler_env:
            continue
        ports = set()
        for wiring in (node.get("inputs") or {}), (node.get("outputs") or {}):
            for port, path in wiring.items():
                if tuple(path) in refined_paths:
                    ports.add(port)
        if ports:
            out[draft] = ports
    return out


def _iter_processes(state):
    for val in state.values() if isinstance(state, dict) else []:
        if isinstance(val, dict):
            if val.get("_type") == "process":
                yield val
            elif "_type" not in val:
                yield from _iter_processes(val)


def _apply_store_overrides(state, handler_env) -> None:
    # NOTE: process-bigraph's realize initialises a typed leaf from ``_default``,
    # NOT ``_value``. So an ``init`` override sets ``_default`` to take effect at
    # build. All entries' init/refine blocks are merged across the environment.
    for spec in handler_env.values():
        for path, value in (spec.get("init") or {}).items():
            _set_leaf(state, path.split("."), {"_default": value})
        for path, schema in (spec.get("refine") or {}).items():
            _set_leaf(state, path.split("."), schema)


def _set_leaf(state, path, patch) -> None:
    node = state
    for key in path[:-1]:
        node = node.get(key, {}) if isinstance(node, dict) else {}
    leaf = node.get(path[-1]) if isinstance(node, dict) else None
    if isinstance(leaf, dict):
        leaf.update(patch)


# ── interface (law #2) ─────────────────────────────────────────────────────────
def interface_of(state: dict) -> dict:
    """The EXTERNAL interface: every process's port names + the store paths they
    wire to. Compilation must leave this identical (schemas may differ only at
    declared refine paths)."""
    ports, wired = set(), set()
    for node in _iter_processes(state):
        for wiring in (node.get("inputs") or {}), (node.get("outputs") or {}):
            for port, path in wiring.items():
                ports.add(port)
                wired.add(tuple(path))
    return {"ports": ports, "wired_store_paths": wired}


# ── ergonomic object API ───────────────────────────────────────────────────────
class Compiler:
    """A compiler bound to a core (and an optional type-compatibility hook).

    Example::

        compiler = Compiler(core, type_compatible=my_ontology_hook)
        executable = compiler.compile(semantic_state, handler_env)
        assert compiler.interface_of(executable) == compiler.interface_of(semantic_state)
    """

    def __init__(self, core, type_compatible: Optional[TypeCompatible] = None):
        self.core = core
        self.type_compatible = type_compatible

    def signature(self, draft_name: str) -> Signature:
        return signature_of(self.core, draft_name)

    def conformance(self, draft_name: str, handler_name: str,
                    allow_refine: Optional[set] = None) -> ConformanceReport:
        return check_conformance(self.core, draft_name, handler_name,
                                 allow_refine=allow_refine,
                                 type_compatible=self.type_compatible)

    def is_rewrite(self, handler_name: str) -> bool:
        return is_rewrite(self.core, handler_name)

    def compile(self, semantic_state: dict, handler_env: dict) -> dict:
        return compile_composite(semantic_state, handler_env, self.core,
                                 type_compatible=self.type_compatible)

    @staticmethod
    def interface_of(state: dict) -> dict:
        return interface_of(state)

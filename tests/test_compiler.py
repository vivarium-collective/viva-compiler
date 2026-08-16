"""viva-compiler laws, proven on toy (non-domain) drafts and handlers."""
from __future__ import annotations

import pytest
from process_bigraph import Composite, DraftProcess, Process, allocate_core, draft_process

from viva_compiler import (
    Compiler, CompileError, RewriteHandler,
    check_conformance, compile_composite, interface_of, is_rewrite, signature_of,
)


# ── toy signatures + handlers ─────────────────────────────────────────────────
@draft_process(name="Widget", inputs={"x": "float"}, outputs={"y": "float"},
               contract={"summary": "toy widget: turns x into y"})
class Widget(DraftProcess):
    pass


class Doubler(Process):
    def inputs(self):  return {"x": "float"}
    def outputs(self): return {"y": "float"}
    def update(self, state, interval):
        return {"y": state["x"] * 2 * interval}


class Tripler(Process):
    def inputs(self):  return {"x": "float"}
    def outputs(self): return {"y": "float"}
    def update(self, state, interval):
        return {"y": state["x"] * 3 * interval}


class OnlyX(Process):                       # missing the y output → non-conforming
    def inputs(self):  return {"x": "float"}
    def outputs(self): return {}
    def update(self, state, interval):
        return {}


@draft_process(name="Splitter", inputs={"trigger": "float"}, outputs={}, contract={})
class Splitter(DraftProcess):               # placeholder signature (a rewrite)
    pass


class SplitImpl(RewriteHandler):            # real contract is the node's wiring
    def inputs(self):  return {"a": "float"}
    def outputs(self): return {"b": "float"}
    def update(self, state, interval):
        return {"b": state["a"] * interval}


@draft_process(name="Thermo", inputs={"t": "temperature"}, outputs={"out": "temperature"},
               contract={})
class Thermo(DraftProcess):
    pass


class ThermoImpl(Process):                  # uses a differently-named-but-equivalent type
    def inputs(self):  return {"t": "celsius"}
    def outputs(self): return {"out": "celsius"}
    def update(self, state, interval):
        return {"out": state["t"] * interval}


@pytest.fixture
def core():
    c = allocate_core()
    c.register_types({"celsius": {"_inherit": "float"}, "temperature": {"_inherit": "float"}})
    for name, cls in [("Widget", Widget), ("Doubler", Doubler), ("Tripler", Tripler),
                      ("OnlyX", OnlyX), ("Splitter", Splitter), ("SplitImpl", SplitImpl),
                      ("Thermo", Thermo), ("ThermoImpl", ThermoImpl)]:
        c.register_link(name, cls)
    return c


def _widget_composite():
    return {
        "x": {"_type": "float", "_default": 1.0},
        "y": {"_type": "float", "_default": 0.0},
        "widget": {"_type": "process", "address": "local:Widget", "config": {}, "interval": 1.0,
                   "inputs": {"x": ["x"]}, "outputs": {"y": ["y"]}},
    }


# ── law 1: conformance ─────────────────────────────────────────────────────────
def test_conformance(core):
    assert check_conformance(core, "Widget", "Doubler").ok
    bad = check_conformance(core, "Widget", "OnlyX")
    assert not bad.ok and ("output", "y") in bad.missing


def test_signature(core):
    sig = signature_of(core, "Widget")
    assert sig.inputs == {"x": "float"} and sig.outputs == {"y": "float"}


# ── law 2: interface preservation ──────────────────────────────────────────────
def test_interface_preserved(core):
    sem = _widget_composite()
    ex = compile_composite(sem, {"Widget": {"handler": "Doubler"}}, core)
    assert interface_of(ex) == interface_of(sem)
    assert ex["widget"]["address"] == "local:Doubler"      # only the address changed


# ── law 3: executability ───────────────────────────────────────────────────────
def test_executable_runs(core):
    sem = _widget_composite()
    ex = compile_composite(sem, {"Widget": {"handler": "Doubler"}}, core)
    comp = Composite({"state": ex}, core=core)
    comp.run(3)
    assert comp.state["y"] == pytest.approx(6.0)           # 1*2 per step, 3 steps


def test_semantic_is_inert(core):
    comp = Composite({"state": _widget_composite()}, core=core)
    comp.run(3)
    assert comp.state["y"] == 0.0                          # draft has no dynamics


# ── law 4: handler independence ────────────────────────────────────────────────
def test_handler_independence(core):
    sem = _widget_composite()
    def run(handler):
        ex = compile_composite(sem, {"Widget": {"handler": handler}}, core)
        c = Composite({"state": ex}, core=core); c.run(3)
        return c.state["y"]
    assert run("Doubler") == pytest.approx(6.0)
    assert run("Tripler") == pytest.approx(9.0)            # same interface, different mechanism


def test_nonconformance_raises(core):
    with pytest.raises(CompileError):
        compile_composite(_widget_composite(), {"Widget": {"handler": "OnlyX"}}, core)


# ── rewrite handlers (law 2′) ──────────────────────────────────────────────────
def test_rewrite_handler_against_wiring(core):
    assert is_rewrite(core, "SplitImpl")
    sem = {
        "a": {"_type": "float", "_default": 1.0},
        "b": {"_type": "float", "_default": 0.0},
        "splitter": {"_type": "process", "address": "local:Splitter", "config": {}, "interval": 1.0,
                     "inputs": {"a": ["a"]}, "outputs": {"b": ["b"]}},
    }
    ex = compile_composite(sem, {"Splitter": {"handler": "SplitImpl"}}, core)  # wiring-conformance
    assert interface_of(ex) == interface_of(sem)
    comp = Composite({"state": ex}, core=core); comp.run(2)
    assert comp.state["b"] == pytest.approx(2.0)


# ── pluggable type compatibility ───────────────────────────────────────────────
def test_pluggable_type_compatible(core):
    sem = {
        "t": {"_type": "temperature", "_default": 1.0},
        "out": {"_type": "temperature", "_default": 0.0},
        "thermo": {"_type": "process", "address": "local:Thermo", "config": {}, "interval": 1.0,
                   "inputs": {"t": ["t"]}, "outputs": {"out": ["out"]}},
    }
    env = {"Thermo": {"handler": "ThermoImpl"}}
    # default check rejects celsius vs temperature (different names, neither a subtype).
    with pytest.raises(CompileError):
        compile_composite(sem, env, core)
    # a custom hook that treats them as the same quantity accepts it.
    same = lambda core, a, b: a == b or {a, b} <= {"celsius", "temperature"}
    ex = compile_composite(sem, env, core, type_compatible=same)
    assert interface_of(ex) == interface_of(sem)


# ── the object API ─────────────────────────────────────────────────────────────
def test_compiler_object_api(core):
    compiler = Compiler(core)
    sem = _widget_composite()
    ex = compiler.compile(sem, {"Widget": {"handler": "Doubler"}})
    assert compiler.interface_of(ex) == compiler.interface_of(sem)
    assert compiler.conformance("Widget", "Doubler").ok

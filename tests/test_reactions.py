"""The reactive-system backend: genuine structural rewrites via pbg's BRS."""
from __future__ import annotations

from viva_compiler import ReactionRule, reaction_step_node, run_reactions


def test_structural_division_adds_a_node():
    """One node genuinely becomes two (the reactum's node set differs from the
    redex's) — true runtime node insertion, not a pre-declared daughter."""
    rule = ReactionRule(redex={"cell": {}},
                        reactum={"cell_1": {}, "cell_2": {}}, label="divide")
    final, events = run_reactions({"cell": {}}, [rule], max_steps=1)
    assert [e.rule_label for e in events] == ["divide"]
    assert set(final) == {"cell_1", "cell_2"}       # one node -> two


def test_deterministic_relabel():
    rule = ReactionRule(redex={"a": {}}, reactum={"b": {}}, label="a->b")
    final, events = run_reactions({"a": {}}, [rule], max_steps=5)
    assert final == {"b": {}}                        # a rewritten to b
    assert events and all(e.rule_label == "a->b" for e in events)


def test_reaction_step_node_shape():
    rule = ReactionRule(redex={"cell": {}}, reactum={"cell_1": {}, "cell_2": {}})
    node = reaction_step_node([rule], ["colony"], mode="stochastic", seed=0)
    assert node["address"] == "local:ReactionStep"
    assert node["inputs"]["state"] == ["colony"] == node["outputs"]["state"]
    assert node["config"]["mode"] == "stochastic" and node["config"]["seed"] == 0
    assert node["config"]["rules"] == [rule]

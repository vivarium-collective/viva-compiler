"""Reactive-system backend — genuine structural rewrites via process-bigraph's BRS.

process-bigraph (through bigraph-schema) ships a real **bigraphical reactive
system**: parametric ``ReactionRule`` objects (redex → reactum with an
instantiation map, Milner Def. 8.5), a matcher, ``run_reactions`` (deterministic
*first-match* or stochastic *Gillespie* firing), and a registered ``ReactionStep``
that applies rules to a ``tree[node]`` subtree and overwrites it. Because a reactum
may have a different node set than its redex, rules can genuinely **add or remove
place-graph nodes at runtime** — e.g. one ``cell`` node dividing into two:

    ReactionRule(redex={"cell": {}}, reactum={"cell_1": {}, "cell_2": {}})
    run_reactions({"cell": {}}, [rule])  ->  {"cell_1": {}, "cell_2": {}}

This gives viva-compiler **two rewrite backends** for the Fig-10-style figures:

* :class:`~viva_compiler.RewriteHandler` — an ordinary ``Process`` that animates a
  *pre-declared* post-structure (daughters already in the place graph). Simple, no
  matching; the interface is byte-identical (law 2 holds as-is).
* **ReactionStep + ReactionRule** (this module) — a *true* structural rewrite:
  the daughter nodes are created by the rule firing. This is the honest realization
  of the paper's Fig 3c event-driven rewrites (divide / engulf / burst), including
  stochastic (Gillespie) timing for free.

:func:`reaction_step_node` builds a composite node that installs a ``ReactionStep``
over a target subtree; the rules are ``ReactionRule`` objects, so this node is for
*programmatic* composite construction (rules are Python objects, not JSON).
"""
from __future__ import annotations

from typing import Optional, Sequence

from bigraph_schema.assembly import ReactionRule, run_reactions  # re-exported

__all__ = ["ReactionRule", "run_reactions", "reaction_step_node"]


def reaction_step_node(rules: Sequence[ReactionRule], target_path: Sequence[str],
                       mode: str = "deterministic", seed: Optional[int] = None) -> dict:
    """A composite node installing a ``local:ReactionStep`` over ``target_path``.

    Wire it into a composite state to have the reaction ``rules`` rewrite the
    subtree at ``target_path`` (a ``tree[node]``) each step — the structural-rewrite
    backend for rewrite handlers.

    ``rules`` are :class:`ReactionRule` objects; ``mode`` is ``"deterministic"``
    (first match) or ``"stochastic"`` (Gillespie, weighted by ``rule.rate``).
    """
    config: dict = {"rules": list(rules), "mode": mode}
    if seed is not None:
        config["seed"] = seed
    path = list(target_path)
    return {
        "_type": "step",
        "address": "local:ReactionStep",
        "config": config,
        "inputs": {"state": path},
        "outputs": {"state": path},
    }

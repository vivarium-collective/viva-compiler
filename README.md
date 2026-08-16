# viva-compiler

**A semantic→executable compiler for [process-bigraph](https://github.com/vivarium-collective/process-bigraph).**

Compile a composite of *draft processes* — typed-port effect signatures with no
dynamics — into a running composite, by installing a conforming `Process` **handler**
for each, **while preserving the place-graph and every wire**. It is an algebraic
effect system over process-bigraph:

| algebraic effects | process-bigraph | viva-compiler |
|---|---|---|
| operation / effect signature | a `DraftProcess` (typed ports + contract, inert `update`) | `signature_of(core, draft)` |
| handler (interpretation) | an executable `Process` with matching ports + a real `update` | your handler class |
| handler installation | a **handler environment** `{Draft: {handler, config, init, refine}}` | the `env` you pass |
| running a handled term | building + running the `Composite` | `Composite(state).run(n)` |

It is **domain-agnostic**: handlers, draft composites, and any ontology are yours.
It formalizes the "process-implementation mapping" (Agmon's meta-modeler's guide,
Table 1's `R_L`) as a first-class, conformance-checked operation.

## Install

```bash
pip install viva-compiler        # or: uv pip install viva-compiler
```

## Use

```python
from process_bigraph import Composite
from viva_compiler import Compiler

compiler = Compiler(core)                      # core has your drafts + handlers registered
executable = compiler.compile(semantic_state, {"Widget": {"handler": "Doubler"}})
assert compiler.interface_of(executable) == compiler.interface_of(semantic_state)
Composite({"state": executable}, core=core).run(10)
```

Functional API is also exported: `compile_composite`, `check_conformance`,
`signature_of`, `interface_of`, `is_rewrite`.

## The four laws

1. **Conformance** (`check_conformance`, the `H ⊢ S` judgment) — a handler must
   supply every signature port with a compatible type.
2. **Interface preservation** — `interface_of(⟦C⟧_H) == interface_of(C)`; only a
   declared `refine` may change a leaf's schema. The external interface (port names
   + wired store paths) is identical.
3. **Executability** — the compiled composite builds and runs; the semantic one is inert.
4. **Handler independence** — two conforming environments give two executables
   sharing one interface (swap the mechanism, keep the interface).

## Pluggable type compatibility

The conformance type check is a hook. The default accepts equal or subtype
(`_inherit`) types; pass your own to widen it — e.g. ontology-aware:

```python
def ontology_compatible(core, sig_t, handler_t):
    return term_of(sig_t) == term_of(handler_t)          # your ontology
Compiler(core, type_compatible=ontology_compatible)
```

## Rewrite handlers, and two backends for structural change

Some figures (division, development, evolution) are not static handler swaps but
**event-driven rewrites**. viva-compiler supports two backends:

- **`RewriteHandler`** — an ordinary `Process` marked `REWRITE = True`. Its
  conformance is checked against the node's *wiring* rather than a placeholder
  draft signature (**law 2′**). It animates a *pre-declared* post-structure (the
  daughter nodes already exist in the place graph). Simple; the interface is
  byte-identical (law 2 holds as-is).

- **`ReactionStep` + `ReactionRule`** (`viva_compiler.reactions`) — a **genuine
  structural rewrite** using process-bigraph's built-in **bigraphical reactive
  system**. A parametric rule `redex → reactum` (Milner Def. 8.5) actually adds or
  removes place-graph nodes when it fires — one `cell` node *becoming* two:

  ```python
  from viva_compiler import ReactionRule, run_reactions
  rule = ReactionRule(redex={"cell": {}}, reactum={"cell_1": {}, "cell_2": {}})
  run_reactions({"cell": {}}, [rule])          # -> {"cell_1": {}, "cell_2": {}}
  ```

  `reaction_step_node(rules, target_path, mode="stochastic")` installs a
  `ReactionStep` over a subtree — deterministic (first match) or stochastic
  (Gillespie) firing — the honest realization of the paper's Fig 3c
  (divide / engulf / burst). Reach for this when the rewrite must *create* structure,
  not just fill a pre-declared slot.

## Scope

This is the **binding** stage of a compiler — conformance-checked handler
installation — not the whole pipeline. It does not *generate* handlers or elaborate
a higher-level description into a network; those are separate concerns a caller
supplies. That narrowness is what keeps it small (~250 lines) and general.

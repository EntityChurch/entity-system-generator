# HISTORY

Standard-extension implementations of `EXTENSION-HISTORY` v1.7, one per language.

**The spec is upstream and this is not a copy of it.** Read
`shared/spec-data/history-v1.7/EXTENSION-HISTORY.md` — the pinned snapshot these ports
were written against. A gap or contradiction in it is routed to
`entity-system-architecture` as a spec issue, never closed by a local decision and never
worked around in generated output.

## Layout

**THE LAYOUT IS TARGET-MAJOR.** What is here is the language-NEUTRAL half; the cells live
under the target that compiles them.

```
extension-contracts/history/
  EXTENSION.toml            the machine-readable contract; [contract] is DERIVED — see below
  arch/AUTHORING-NOTES.md   readings, ambiguities, assumptions   ← read this second
  README.md                 this file

languages/<target>/extensions/history/
                            the cell: source only. handler · types · patterns · sdk · index
                            the module-private half and the tests are spelled per ecosystem:
                              typescript  internal/      test/
                              python      _internal/     test/
                              rust        src/internal/  tests/   ← sees only `pub`
```

## `[contract]` is DERIVED here, not transcribed, and every field says from where

CONTENT carries GUIDE-EXTENSION-DEVELOPMENT §3.3's declaration header, so its `[contract]`
is a projection of a declaration. **This spec is one of the 24 that do not**, so every
field in `[contract]` names the section it was read out of, in `[contract.derived_from]`,
and **the two that are readings of ABSENCE say so inline** — `points_exposed` and
`owned_kinds`.

That is the entire cost of the missing header. A missing summary is not a missing fact:
§9.2 is an explicit six-entry type list, §9.3 is the manifest, §3.1 and §6.1 name the
namespaces. The filled-in header went to arch as a **draft**, not as a request.

## What is implemented

| face | status |
|---|---|
| **Handler** (§4) | `query` (§4.3.1) and `rollback` (§4.3.2), §4.2's dual capability check, §7.5's exfiltration refusal |
| **Types** (§9.2) | all six, published to `system/type/*` — the peers' registration writes none |
| **Emit consumer** (§5.1) | **the face CONTENT never had.** SYSTEM-COMPOSITION §2.2 position 4, self-guarded per §3.2 |
| **SDK** | `historyConfig` · `configPath` · `resolveConfig` · `buildContext` · the §2.2/§6.2 pattern algorithms |

**Implemented is not the same as installed, and on `rust` they came apart in a new
direction.** There the emit consumer **installs and runs** — the peer accumulates a real,
correct, content-addressed audit chain — and the handler face **cannot be installed at any
visibility**, so nothing can read that chain over the wire. The oracle's `history` category
scores 7 of 34 against a recorder that is working perfectly. See
`arch/AUTHORING-NOTES.md` §2.0 and `EXTENSION.toml [substrate.oracle_read_path]`.

Not implemented, declared rather than silent:

- **`max_depth` pruning (§3.3)**, a SHOULD. §3.3's algorithm describes severing an
  immutable content-addressed chain, which cannot be done without rewriting every
  transition's hash. Every port walks and reports; none severs. Routed as `A-4`.
- **The `accessed` event (§2.1, §5.2)**, a MAY. §5.2 puts read-audit inside the TREE
  handler's `get`, and the emit pathway fires on Bind — a read binds nothing, so no
  consumer on any peer observes one. `config.events` accepts `"accessed"` and it never
  matches.

## The MUST no port satisfies, and why that is the honest headline

**§2.1 makes `author` and `capability` non-optional and §9.1 MUSTs recording them, from the
execution context §5.1 says arrives with the tree-change event. No peer delivers one.**

`typescript` declares an `EmitContext` with almost exactly SYSTEM-COMPOSITION §1.4's
inventory and constructs it at **zero sites**; `python` and `rust` have no context field on
the event at all. So every transition records §2.1's **autonomous-case** values — which is
the reading the spec supplies for "no external request", and which is wrong about the world
for a write that arrived over the wire from a remote caller.

**Four oracle checks pass on that, and they are presence checks over values we fabricate.**
So the module records a `provenance` field **outside** the spec-declared entity (adding a
field to `system/history/transition` would move its content hash away from every other
implementation's), the composition prints `context_available=false`, and the unit test
asserts the fallback **FIRES** — so the day a context arrives, that test fails and says so.

**33 of 34 is a count of checks passed. It is not a claim that §9.1's MUST is satisfied.**
Routed as `H8`.

## The boundary, which is ours to draw

CONTENT had §3.4's MUST to point at for its module-private surface. **HISTORY has none** —
the line is ours (D16, the position `[sdk_surface]` put us in).

It is drawn at `record_transition` because a caller who can reach it can append a **forged
entry to an audit chain**: any `author`, any `capability`, at any path, linked into the real
chain by `previous` and content-addressed exactly like a real one. §7.2 calls the capability
field the answer to *"under what authority?"*, and a forgeable answer is worse than no
answer, because it is believed.

Three ports, three enforcement strengths, and they are not equal — asserted, not claimed:

| | boundary | enforced by |
|---|---|---|
| `typescript` | the `exports` map | **node**, at resolve time |
| `python` | `_internal` + `__all__` + a test | **nothing** — and the test asserts it can be walked around |
| `rust` | `mod internal;` with no `pub` | **rustc**, `error[E0603]` |

## Where the numbers are

Per composition, under `languages/<target>/compositions/<name>/status/`. The three that
exist:

```
typescript/compositions/content-history/status/
python/compositions/content-history/status/
rust/compositions/content-history/status/CONFORMANCE-2026-09-07.md
```

Every figure in them is the summary block of the JSON report named beside it, printed by
the artifact rather than counted off a listing (D14).

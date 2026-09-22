# HISTORY

Standard-extension implementations of `EXTENSION-HISTORY` v1.10, one per language.

**The spec is upstream and this is not a copy of it.** Read
`shared/spec-data/history-v1.10/EXTENSION-HISTORY.md` — the pinned snapshot the contract is
held to. The ports were first written against v1.7 and re-pinned through v1.8 and v1.10. A gap or contradiction in it is routed to
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

**All four faces install on all three targets.** Until keystone landed H1 on the `rust` peer
on 2026-09-12, the handler face could not be installed there: the emit consumer recorded a real
audit chain that nothing could read over the wire, and the `history` category scored 7 of 34.
`install_history` now installs the handler on `rust` as on the other two, and the category
measures 32 PASS / 1 WARN / 1 FAIL of 34 there (oracle 78db4a9). The earlier state is recorded in
`arch/AUTHORING-NOTES.md` §2.0 and `EXTENSION.toml [substrate.oracle_read_path]`.

Not implemented, declared rather than silent:

- **`max_depth` collection (§3.3)**, a SHOULD. Through v1.7 §3.3 described severing an
  immutable content-addressed chain; we routed that as `A-4`, and v1.8 rewrote §3.3 so
  `max_depth` is a retention floor and the chain is never rewritten. Every port walks and
  reports; none collects, which v1.8 states is conformant.
- **The `accessed` event (§2.1, §5.2)**, a MAY. §5.2 puts read-audit inside the TREE
  handler's `get`, and the emit pathway fires on Bind — a read binds nothing, so no
  consumer on any peer observes one. `config.events` accepts `"accessed"` and it never
  matches.

## The execution context, and what a green count does not say

**§2.1 makes `author` and `capability` non-optional and §9.1 MUSTs recording them, from the
execution context §5.1 says arrives with the tree-change event.** Until keystone landed H8 on
2026-09-07 no peer delivered one, and every transition recorded §2.1's **autonomous-case**
values — wrong about the world for a write that arrived over the wire. All three peers now put
a context on the event for a write made through dispatch, and the recorder uses it.

The module still records a `provenance` field **outside** the spec-declared entity (adding a
field to `system/history/transition` would move its content hash away from every other
implementation's): `"context"` when the event carried one, `"autonomous-fallback"` when it did
not. The installation's `context_available` is observed at runtime, never declared.

**A passing count is not a claim that §9.1's MUST is satisfied.** The four `context_*` oracle
checks are presence checks and passed identically before and after H8; see `EXTENSION.toml`
HIST-R3.

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

Those files are dated snapshots. The current measured numbers are the `[gate.baseline.*]`
tables in each composition's `SYSTEM.toml`, checked by `make expectation`.

# CONTENT

Standard-extension implementations of `EXTENSION-CONTENT` v3.7, one per language.

**The spec is upstream and this is not a copy of it.** Read
`shared/spec-data/content-v3.7/EXTENSION-CONTENT.md` — the pinned snapshot this port was written
against. A gap or contradiction in it is routed to `entity-system-architecture` as a spec issue,
never closed by a local decision and never worked around in generated output.

## Layout

```
EXTENSION.toml          the machine-readable contract; [contract] is TRANSCRIBED from the spec header
arch/AUTHORING-NOTES.md readings taken, ambiguities logged, assumptions carried  ← read this second
<lang>/                 the cell: source only. handler · types · chunking · sdk · index · internal/
<lang>/test/            per-cell unit tests   (`rust`: `tests/`, which sees only `pub`)
```

The toolchain is **not** here. It is in `languages/<lang>/`, one copy shared by every extension —
a build driver in the cell position would be 26 × 46 = 1,196 copies of one script.

## What is implemented

| face | status |
|---|---|
| **Handler** (§6) | `get` and `ingest`, both ops, both `path_required` MUSTs, §6.4 path-scope check |
| **Types** (§2, §6.2, §6.3) | all seven, published to `system/type/*` — the peer's `registerHandler` writes none |
| **SDK** (§3.3, §5.3, §6.4.2) | `ensureClosure` · `atPeer` / `bindAtPeer` · `createDescriptor` + the §5.3 integrity check · `reassembleUnderCapability` |
| **Chunking** (§3.2, §3.6) | fixed-size and FastCDC/NC2, gear table per §3.6.1 |
| **Emit consumer** | **none, and that is correct.** CONTENT registers no emit consumer — "consumer" in this spec means a client of content. That face arrives with HISTORY. |

**Implemented is not the same as installed, and the third port is where they came apart.** On
`rust` the handler is written and unit-tested and **cannot be installed at any visibility** —
`501 no_handler_body` with all four §11.6.1 tree writes bound, `404` with none, and the body
answering `200` when called directly with its invocation counter still at zero. The types face
installs there and the handler face does not. See `arch/AUTHORING-NOTES.md` §2.0, and D13 in
`AGENTS.md`, which now requires a capability claim to name **which face** it is about.

Not implemented, declared rather than silent: **namespace-scoped topology (§6.4.2 Hash Tree
Presence)**. This composition runs single-trust-domain, which §6.4.1 makes opt-in and restricted.
See `EXTENSION.toml [assumptions].topology`.

## The one MUST that is a security surface

§3.4: *"Implementations MUST NOT expose `reassemble_content` as a public substrate primitive
callable from third-party / SDK / external consumer code without an explicit capability-checking
wrapper."*

So the algorithm is module-private (`<lang>/internal/`), absent from the public entry point, and
the only public route is `reassembleUnderCapability(ctx, blobHash)` — which takes a handler context
a consumer cannot manufacture, because the dispatcher builds one only after `check_permission`
returned ALLOW.

**The enforcement point is not that paragraph** — a MUST with no check is a sentence. And **§3.4
turns out to be TWO clauses that do not move together**, which two substrates could not have shown:

| | `typescript` | `python` | `rust` |
|---|---|---|---|
| boundary | the `exports` map in `package.json` | convention: `_internal`, `__all__`, a test | `mod internal;` with no `pub` |
| enforced by | **node**, at resolve time | **nothing** | **rustc**, at compile time |
| clause 1 — do not expose it | ENFORCED | CONVENTION ONLY | **strongest**: `error[E0603]`, no dynamic route |
| clause 2 — capability-checking wrapper | dispatcher-anchored | dispatcher-anchored | **weakest**: crate-anchored only |
| the check asserts | the module resolver's refusal | the convention holds **and can be walked around** | a compile that must FAIL, with a control that must compile |

Two cells are not jokes. `test_export_surface.py` deliberately imports
`entity_content._internal.reassemble` and asserts it works, so that port's §3.4 claim cannot be read
as equivalent to the others'. And `rust`'s clause-2 cell is the inverse: there is no dispatcher-built
value to demand — the peer's context type is private and unconstructible — so `DispatchAuthority`
proves *"you came through this crate's handler"*, **not** *"the dispatcher authorized you"*.

Recorded as `[substrate.export_boundary]` and `[substrate.capability_wrapper]` — two blocks, because
reporting one verdict for two requirements that invert between substrates is the D13 error one level
up.

## Ports

| language | composition | unit tests | handler installable | conformance |
|---|---|---|---|---|
| `typescript` | `ts-content` | 31 | yes | `languages/typescript/compositions/content/status/CONFORMANCE-2026-09-05.md` |
| `python` | `py-content` | 38 | yes | `languages/python/compositions/content/status/CONFORMANCE-2026-09-06.md` |
| `rust` | `rs-content` | 40 + a compile that must fail | **no** | `languages/rust/compositions/content/status/CONFORMANCE-2026-09-06.md` |

**No port is a translation of another.** All three are transcriptions of the same pinned snapshot,
deliberately: a translation of our own first port would agree with it by construction and tell us
nothing. Where they differ, `arch/AUTHORING-NOTES.md` §2 says which differences are the substrate's
and which are ours — and §2.5 says which of the two-column rows survived the third column.

## Conformance

Of the oracle's 13 `content` checks, on `typescript` and `python`: **8 measure this MODULE and 8
pass**; 4 more pass without contacting the peer at all; 1 skips for want of a `local/files` root.
Never cite it as `13P·0F` or as a percentage — a skip counts as a failure, and 12 passes is not 12
measurements of us.

**Of those 8, five measure the handler face and three measure the types face.** That was written as
"8 measure our handler" until 2026-09-06, when `rs-content` separated them by experiment: with types
installed and no handler, exactly the 3 pass and exactly the 5 do not. No composition where both
faces installed could have made the distinction. The count never changed; the label did.

All three ports turn the same six checks green, with `type_system.*_content_*_match` reporting
**`content hash match`**: `entity-core-go`'s independent transcription of §2.1/§2.2/§2.4 renders
byte-identically to each of ours. That is **three** of ours agreeing with one that is not — one
reading of one snapshot in a shared generation lineage, not independent convergence, and no chunker
ran.

**Those six read a different severity depending on how they are run, and it is worth knowing which
you are quoting.** Under `--profile core` they are `WARN → PASS`; in a standalone
`-category type_system` run they are `FAIL → PASS`. The oracle downgrades non-floor type checks to
WARN inside the core profile, because a core peer is not required to publish extension
vocabularies. Same six checks, same six passes, two severities.

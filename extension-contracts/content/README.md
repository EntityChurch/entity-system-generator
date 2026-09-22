# CONTENT

Standard-extension implementations of `EXTENSION-CONTENT` v3.7, one per language.

**The spec is upstream and this is not a copy of it.** Read
`shared/spec-data/content-v3.7/EXTENSION-CONTENT.md` — the pinned snapshot this port was written
against. A gap or contradiction in it is routed to `entity-system-architecture` as a spec issue,
never closed by a local decision and never worked around in generated output.

## Layout

**THE LAYOUT IS TARGET-MAJOR** (2026-09-06). What is here is the language-NEUTRAL half; the
cells live under the target that compiles them, because the people who consume this arrive by
language and should be able to read one directory.

```
extension-contracts/content/
  EXTENSION.toml            the machine-readable contract; [contract] is TRANSCRIBED from the header
  arch/AUTHORING-NOTES.md   readings, ambiguities, assumptions   ← read this second
  README.md                 this file

languages/<target>/extensions/content/
                            the cell: source only. handler · types · chunking · sdk · index
                            the module-private half and the tests are spelled per ecosystem:
                              typescript  internal/    test/
                              python      _internal/   test/
                              rust        src/internal/  tests/   ← sees only `pub`
```

**This block described the OLD layout until 2026-09-07** — `<lang>/` and `<lang>/test/` as
subdirectories of this one, which is where they were before the restructure and have not been
since. `tools/check-citations.py` could not see it: the paths were relative and
placeholder-rooted, so nothing in them anchors on a directory the extractor knows. That is a
stated limit of the gate (D18) and not a hole it missed.

The toolchain is **not** in the cell either. It is `languages/<target>/profile.toml` plus
`languages/<target>/{build,test,host-entry}`, one copy shared by every extension — a build driver in the cell position would be
26 × 46 = 1,196 copies of one script.

## What is implemented

| face | status |
|---|---|
| **Handler** (§6) | `get` and `ingest`, both ops, both `path_required` MUSTs, §6.4 path-scope check |
| **Types** (§2, §6.2, §6.3) | all seven, published to `system/type/*` — the peer's `registerHandler` writes none |
| **SDK** (§3.3, §5.3, §6.4.2) | `ensureClosure` · `atPeer` / `bindAtPeer` · `createDescriptor` + the §5.3 integrity check · `reassembleUnderCapability` |
| **Chunking** (§3.2, §3.6) | fixed-size and FastCDC/NC2, gear table per §3.6.1 |
| **Emit consumer** | **none, and that is correct.** CONTENT registers no emit consumer — "consumer" in this spec means a client of content. That face arrives with HISTORY. |

**Implemented is not the same as installed, and the third port is where they came apart.** Until
keystone landed H1 on the `rust` peer on 2026-09-12, the handler there was written and unit-tested
and **could not be installed at any visibility** — `501 no_handler_body` with all four §11.6.1 tree
writes bound, `404` with none. `install_content` now installs it through `Peer::register_handler`,
and all four faces install on all three targets. The earlier state is recorded in
`arch/AUTHORING-NOTES.md` §2.0; D13 in `AGENTS.md` still requires a capability claim to name
**which face** it is about.

Not implemented, declared rather than silent: **namespace-scoped topology (§6.4.2 Hash Tree
Presence)**. This composition runs single-trust-domain, which §6.4.1 makes opt-in and restricted.
See `EXTENSION.toml [assumptions].topology`.

## The one MUST that is a security surface

§3.4: *"Implementations MUST NOT expose `reassemble_content` as a public substrate primitive
callable from third-party / SDK / external consumer code without an explicit capability-checking
wrapper."*

So the algorithm is module-private (the `internal/` half of the cell, spelled three ways
above), absent from the public entry point, and
the only public route is `reassembleUnderCapability(ctx, blobHash)` — a wrapper that, on review
(2026-09-12), checks no capability on any port; see `EXTENSION.toml [substrate.capability_wrapper]`.

**The enforcement point is not that paragraph** — a MUST with no check is a sentence. And **§3.4
turns out to be TWO clauses that do not move together**, which two substrates could not have shown:

| | `typescript` | `python` | `rust` |
|---|---|---|---|
| boundary | the `exports` map in `package.json` | convention: `_internal`, `__all__`, a test | `mod internal;` with no `pub` |
| enforced by | **node**, at resolve time | **nothing** | **rustc**, at compile time |
| clause 1 — do not expose it | ENFORCED | CONVENTION ONLY | **strongest**: `error[E0603]`, no dynamic route |
| clause 2 — capability-checking wrapper | caller-constructible context, no capability check | caller-constructible context, no capability check | crate-anchored token (unforgeable), no capability check |
| the check asserts | the module resolver's refusal | the convention holds **and can be walked around** | a compile that must FAIL, with a control that must compile |

Two cells are not jokes. `test_export_surface.py` deliberately imports
`entity_content._internal.reassemble` and asserts it works, so that port's §3.4 claim cannot be read
as equivalent to the others'. And `rust`'s clause-2 cell: `DispatchAuthority` proves *"you came
through this crate's handler"*, **not** *"the dispatcher authorized you"*. It was written when the
peer had no dispatcher-built context to demand; since keystone's H1 (2026-09-12) it has one, and
the wrapper has not been changed to require it.

Recorded as `[substrate.export_boundary]` and `[substrate.capability_wrapper]` — two blocks, because
reporting one verdict for two requirements that invert between substrates is the D13 error one level
up.

## Ports

| language | composition | unit tests | handler installable | conformance |
|---|---|---|---|---|
| `typescript` | `ts-content` | 31 | yes | `languages/typescript/compositions/content/status/CONFORMANCE-2026-09-05.md` |
| `python` | `py-content` | 38 | yes | `languages/python/compositions/content/status/CONFORMANCE-2026-09-06.md` |
| `rust` | `rs-content` | 40 + a compile that must fail | yes, since keystone H1 (2026-09-12) | `languages/rust/compositions/content/status/CONFORMANCE-2026-09-06.md` (pre-H1) |

**No port is a translation of another.** All three are transcriptions of the same pinned snapshot,
deliberately: a translation of our own first port would agree with it by construction and tell us
nothing. Where they differ, `arch/AUTHORING-NOTES.md` §2 says which differences are the substrate's
and which are ours — and §2.5 says which of the two-column rows survived the third column.

## Conformance

Of the oracle's 13 `content` checks, on `typescript` and `python` (and on `rust` since keystone's
H1, 2026-09-12; `languages/rust/compositions/content/SYSTEM.toml` baseline): **8 measure this MODULE and 8
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

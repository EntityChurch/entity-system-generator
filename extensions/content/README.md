# CONTENT

Standard-extension implementations of `EXTENSION-CONTENT` v3.6, one per language.

**The spec is upstream and this is not a copy of it.** Read
`shared/spec-data/content-v3.6/EXTENSION-CONTENT.md` — the pinned snapshot this port was written
against. A gap or contradiction in it is routed to `entity-system-architecture` as a spec issue,
never closed by a local decision and never worked around in generated output.

## Layout

```
EXTENSION.toml          the machine-readable contract; [contract] is TRANSCRIBED from the spec header
arch/AUTHORING-NOTES.md readings taken, ambiguities logged, assumptions carried  ← read this second
<lang>/                 the cell: source only. handler · types · chunking · sdk · index · internal/
<lang>/test/            per-cell unit tests
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

**The enforcement point is not that paragraph.** It is `test/export-surface.test.ts`, which imports
the module *by package name* through its own `exports` map — the same resolution a third party gets
— and asserts that nothing reachable there reassembles. A MUST with no check is a sentence.

## Conformance

`compositions/ts-content/status/CONFORMANCE-2026-09-05.md`. The short version: of the oracle's 13
`content` checks, **8 measure this handler and 8 pass**; 4 more pass without contacting the peer at
all; 1 skips for want of a `local/files` root. Never cite it as `13P·0F` or as a percentage.

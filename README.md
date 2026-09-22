# entity-system-generator

**Generating the optional capability layer.** This repo builds standard extension
implementations — `EXTENSION-CONTENT`, `EXTENSION-QUERY`, `EXTENSION-HISTORY` and the rest of the
family — across many languages, and installs them onto peers.

It is the second generator in the ecosystem. The first, `entity-core-keystone`, generates **core
protocol peers** from the three core spec files: 46 of them, in 46 languages, each independently
conformant on the wire. This repo takes that output as its substrate and generates the layer above
it.

```
entity-core-protocol/specs/       →  entity-core-keystone       →  a conformant peer
  (3 files, the core)                                                   │
                                                                        ▼
entity-system-architecture/       →  entity-system-generator    →  that peer, with extensions
  specs/extensions/ (26 files)                                          installed
```

## Why it is a separate repo and not another keystone phase

**A generator's input scope is its output scope.** Keystone's
`protocol-generator/shared/spec-data/` holds exactly three files — the whole of
`entity-core-protocol/specs/` — and has only ever held those. Its peers do not implement extensions
because the extension specs have never been in front of it. That boundary is not a limitation to
work around; it is the correct seam, and it is where this repo starts.

The two also differ in a way that matters more than input scope:

| | `entity-core-keystone` | `entity-system-generator` |
|---|---|---|
| Generates | a whole peer, from nothing | a handler set, onto an existing peer |
| Input | 3 core spec files | 26 extension specs + the SDK tier |
| Conformance profile | `--profile core` (16 of 68 `validate-peer` categories) | the **complement** — the 52 extension categories |
| Success | the peer talks to the network | the extension composes, and the peer still conforms |

## Status

**Bring-up.** Nothing is generated yet. The install seam — the mechanism by which a generated
extension handler is bound into a generated peer — is specified (`SDK-OPERATIONS` §11.6) and has now
been measured working end to end on one peer; the current work is the structure the generated output
has to hold.

| | |
|---|---|
| `docs/DESIGN-THE-GENERATION-MODEL.md` | how a build runs — the phase model, the dependency graph, the conformance surface |
| `docs/DESIGN-THE-SYSTEM-STRUCTURE.md` | how 26 extensions × N languages × M compositions stay separable, and the isolation invariants |
| `docs/DESIGN-THE-COMPOSITION-LOADER.md` | what composition emits: the resolve/refuse algorithm and the init program |
| `docs/DESIGN-THE-SDK-LAYER.md` | the layer above the handler — the three install models, the four faces of an extension, and what varies by platform |
| `docs/DESIGN-THE-COMPUTE-TRACK.md` | whether an extension can be written once as a compute expression and run everywhere — what the specification bounds, and what a probe measured |
| `docs/DESIGN-WHERE-THE-LINE-IS.md` | whose requirement is whose |
| `gates/README.md` | every gate, and the authority its checks derive from |
| `docs/STATUS.md` | where this actually is |

## Licence

Apache-2.0 (`LICENSE`). Spec text is licensed separately by the repo that owns it.

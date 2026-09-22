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

**Bring-up.** Nothing is generated yet. The current work is the install seam — the mechanism by
which a generated extension handler is bound into a generated peer — which is specified
(`SDK-OPERATIONS` §11.6) and one delta away from usable. See `docs/DESIGN-THE-GENERATION-MODEL.md`
and `docs/STATUS.md`.

## Licence

Apache-2.0 (`LICENSE`). Spec text is licensed separately by the repo that owns it.

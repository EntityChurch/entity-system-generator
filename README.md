# entity-system-generator

**Generating the optional capability layer.** This repo builds standard extension
implementations — `EXTENSION-CONTENT`, `EXTENSION-HISTORY`, `EXTENSION-COMPUTE` and the rest
of the family — across many languages, and installs them onto peers.

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

**Three extensions across three languages.** `CONTENT`, `HISTORY` and `COMPUTE` are implemented
in `typescript`, `python` and `rust` — nine compositions, each one built, unit-tested, and
measured against a conformance oracle this project does not own. The three were chosen to test
the generation model against different shapes: a request handler, an event recorder, and an
expression interpreter.

That is three extensions of twenty-six, and three languages of forty-six. What is built is a
working answer to *does the model retarget*; it is not coverage of the corpus.

**Measurements, and what they are measurements of, are in [`docs/STATUS.md`](docs/STATUS.md).**
A per-category conformance figure measures what the oracle's access path can reach on a
particular peer — which is not the same sentence as what the extension does, and this project
keeps the two apart deliberately rather than averaging them into one number.

## Building

The host needs **`make`**, **`podman`**, **`python3` ≥ 3.11**, POSIX **`sh`** and **`git`**.
Everything else runs in a container; the host half of the tooling is standard-library only.
`make toolchain` checks this and tells you what is missing.

### ⚠ This repo does not build from a clone on its own

**It generates onto peers it does not produce, so it needs `entity-core-keystone` checked out
beside it**, and it resolves that by relative path:

```
<parent>/
├── entity-core-keystone/          ← required
└── entity-system-generator/       ← this repo
```

From keystone it reads four things, all read-only — **this repo never writes into that tree, and
never patches a generated peer**:

| what | where |
|---|---|
| the peer source each extension compiles against | `protocol-generator/<language>/` |
| the vendored crate mirror (`rust`; nothing is fetched at build time) | `protocol-generator/rust/output/vendor` |
| the conformance oracle and the reference peer binary | `output/s4-oracles/{validate-peer,entity-peer}` |
| the toolchain container images | `localhost/entity-core-keystone/{node24,python-toolchain,rust-toolchain}:latest` |

Build those in keystone first, per its own README. Without them you get
`build: peer not found at $ROOT/../entity-core-keystone/protocol-generator/<language>`, which is
the check doing its job rather than a broken clone.

**What works with no sibling at all:** `make help`, `make toolchain`, and `make lint` — every
host-side gate reads only this tree. That is the fastest way to confirm a checkout is sane.

```sh
make help                                    # the verb list; the default goal
make lint                                    # read-only static checks — no sibling needed
make fmt                                     # autoformat (writes) — rust only today
make build TARGET=rust COMPOSITION=content   # compose and compile one cell
make test                                    # the extension cells' unit tests
make check                                   # the full gate set for one composition
make check-all                               # every (target × composition), then the
                                             #   cross-target gates
make clean
make reap                                    # remove any container this repo left behind
```

**A full `make check-all` is roughly forty minutes of container time** — nine compositions, each
building, unit-testing and running a two-arm conformance diff at `ROUNDS=2`. `make lint` is
seconds. `make check` for one composition is a few minutes.

`TARGET` is one of `typescript` `python` `rust`; `COMPOSITION` is a directory under
`languages/<target>/compositions/`. The build and test verbs have a `-native` opt-in that runs on
the host toolchain instead of in a container.

Adding a language means adding a directory under `languages/`. Adding an extension means adding
contract data under `extension-contracts/`. Neither requires editing a list — the build discovers
both by wildcard, which is the property the layout exists to protect.

### What not to touch

- **`../entity-core-keystone/`** — another team's tree, and our substrate. Read-only, including
  its git. A generated peer is **never patched in place**: if a peer cannot host what we generate,
  that is a finding about the seam and it gets routed, not worked around. A patched peer is a fork.
- **`shared/spec-data/`** — pinned snapshots of another repo's normative specs, vendored with a
  `MANIFEST` each. Re-pinned deliberately, never edited.
- **`languages/*/output/`, `output/`** — build artifacts. `make clean`.
- **`AGENTS-STANDARD.md`, `METHODOLOGY.md`** — maintained centrally and byte-identical across every
  repo in the ecosystem. You *may* edit them when you judge a change justified; the next release
  reconciles every repo's copy and adopts or drops each edit with a reason.

### Where the real gate is

Unit tests green is not the bar. The measurement that counts is
**`entity-core-go`'s `validate-peer`, run against a generated peer with our extensions installed**,
in two arms — bare peer and composed peer — so that *"the extension works"* and *"the peer still
conforms"* are separate answers. `make conformance` and `make regression` are those two arms;
`make expectation` compares the result against what the composition **pre-registered** before the
run. See [`docs/DESIGN-THE-ORACLE-SEAM.md`](docs/DESIGN-THE-ORACLE-SEAM.md) for what that
measurement does and does not reach.

## Documentation

| | |
|---|---|
| [`docs/STATUS.md`](docs/STATUS.md) | where this actually is |
| [`CHANGELOG.md`](CHANGELOG.md) | notable changes, by release |
| **Design** | |
| [`docs/DESIGN-THE-GENERATION-MODEL.md`](docs/DESIGN-THE-GENERATION-MODEL.md) | how a build runs — the phase model, the dependency graph, the conformance surface |
| [`docs/DESIGN-THE-SYSTEM-STRUCTURE.md`](docs/DESIGN-THE-SYSTEM-STRUCTURE.md) | how 26 extensions × N languages × M compositions stay separable, and the isolation invariants |
| [`docs/DESIGN-THE-COMPOSITION-LOADER.md`](docs/DESIGN-THE-COMPOSITION-LOADER.md) | what composition emits: the resolve/refuse algorithm and the init program |
| [`docs/DESIGN-THE-SDK-LAYER.md`](docs/DESIGN-THE-SDK-LAYER.md) | the layer above the handler — the install models, the four faces of an extension, and what varies by platform |
| [`docs/DESIGN-THE-COMPUTE-TRACK.md`](docs/DESIGN-THE-COMPUTE-TRACK.md) | whether an extension can be written once as a compute expression and run everywhere |
| [`docs/DESIGN-THE-CBOR-INTERCHANGE-LAYER.md`](docs/DESIGN-THE-CBOR-INTERCHANGE-LAYER.md) | why every hop travels as canonical ECF rather than JSON |
| [`docs/DESIGN-THE-ORACLE-SEAM.md`](docs/DESIGN-THE-ORACLE-SEAM.md) | how this repo is measured by a suite it does not own, and where that measurement stops |
| [`docs/DESIGN-WHERE-THE-LINE-IS.md`](docs/DESIGN-WHERE-THE-LINE-IS.md) | whose requirement is whose |
| **Reference** | |
| [`docs/KEYSTONE-PEER-HOST-CONTRACT.md`](docs/KEYSTONE-PEER-HOST-CONTRACT.md) | what a generated peer must offer for an extension to run, embed and extend |
| [`docs/SPEC-AMBIGUITIES.md`](docs/SPEC-AMBIGUITIES.md) | gaps found by generating against the corpus, and where each was routed |
| [`docs/CENSUS-DISPATCH-SURFACE.md`](docs/CENSUS-DISPATCH-SURFACE.md) | what the peer cohort actually exposes at the dispatch seam |
| [`gates/README.md`](gates/README.md) | every gate, and the authority its checks derive from |
| **How we work** | |
| [`AGENTS.md`](AGENTS.md) | this repo's charter — authority, boundaries, and the disciplines it has earned. **Read this first** |
| [`AGENTS-STANDARD.md`](AGENTS-STANDARD.md) | the conventions every repo in this ecosystem shares |
| [`METHODOLOGY.md`](METHODOLOGY.md) | disciplines, doctrines and the ratchet |
| [`docs/agents/memory/INDEX.md`](docs/agents/memory/INDEX.md) | **what this repo has learned, by subject** — the evidence behind every rule in `AGENTS.md`, opened when you hit the thing it describes |
| [`docs/ANTI-PATTERNS.md`](docs/ANTI-PATTERNS.md) | named failure modes, each with the commit that produced it |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Contributions are accepted under the
[Developer Certificate of Origin](https://developercertificate.org/) — sign off every commit
with `git commit -s`. There is no CLA.

## Licence

Apache-2.0 (`LICENSE`). Spec text is licensed separately by the repo that owns it.

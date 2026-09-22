# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-09-22

First publication. Nothing in this project has been released before, so everything below is
new rather than changed.

**Breaking:** no — first public release. There is no prior version of this project, so there
is nothing an existing caller could be relying on and nothing to break. The number is a `0.x`
one because the shape is still moving: three extensions of twenty-six, three languages of
forty-six, and a peer contract still being agreed with the generator this repo builds on.

**What this release promises to keep** is what it *generates* and the data you author against
it — never how it generates them. Four things: the extension contract format
(`extension-contracts/<ext>/EXTENSION.toml`) and what its declared blocks mean; the per-language
profile format (`languages/<target>/profile.toml`) and the layout it sits in, so a new language
is a new directory rather than an entry on a list; the `make` verbs `help build test lint fmt
check clean` with `TARGET` and `COMPOSITION` as the two coordinates; and the SDK names an
extension declares as `required`, which are promised in every port. Names an extension declares
as `drift` are a dated list of unresolved differences and are explicitly **not** promised.

The generator's own internals — the drivers, the gate probes, the cell sources, the host-side
scripts and everything under `languages/<target>/output/` — are **not** in that surface and will
change without ceremony. Nor is a generated peer's own interface, which belongs to the project
that produces the peer; this one consumes it. `AGENTS.md` carries the same line in full.

**On the version numbers inside this tree.** The three Rust extension cells carry the
extension-specification revision they were authored against (`3.6.0`, `1.7.0`, `3.29.0`), and
the gate probe crates carry `0.0.0` because a probe makes a claim about a peer and never about
itself. None of those is this project's release number, none is published under its own name,
and `.version-scope` at the repo root records which paths version on which axis and why.

### Added

- **Three standard extensions, implemented across three languages, installed onto generated
  peers.** `CONTENT`, `HISTORY` and `COMPUTE` in `typescript`, `python` and `rust` — nine
  compositions, each one built, unit-tested and measured against a conformance oracle this
  project does not own. An extension is written once as language-neutral contract data and
  once per language as a cell; a composition resolves the two into a peer with the extension
  installed.

- **The extension contract — `extension-contracts/<ext>/EXTENSION.toml`.** One language-neutral
  file per extension, holding what every port must agree on: the requirement map, the public
  SDK surface, the wire error codes with the authority that defines each one, the spec's own
  enumerations, and the per-substrate differences that turned out to be real. A port that
  disagrees with the contract fails a gate rather than drifting quietly.

- **A substrate model, recorded per language and per face.** An extension has four faces —
  types, handler body, emit consumer, SDK — and on a given peer they do not all get the same
  answer. Where a peer cannot host one, that is recorded as a property of the peer rather
  than averaged into a verdict about the extension. Differences between language runtimes
  that the specification does not address are enumerated before a port is measured, not
  discovered afterwards.

- **Sixteen gates, run by `make check`.** Conformance against the oracle, a two-arm
  regression differential over the core protocol profile, a declared baseline in time, SDK
  surface parity across ports, wire error-code authority, spec-enumeration agreement against
  the pinned snapshot, path-citation resolution, cross-port type-entity equality by content
  hash, and a cost model over the tree's own shape. Each gate ships an executed control, and
  each refuses rather than reporting a clean verdict when it cannot measure anything.

- **Pinned specification snapshots** under `shared/spec-data/`, sha256 per document, copied
  in and never edited. An extension names the snapshot it was written against, so an upstream
  revision becomes a re-pin with a number on it instead of a silent change of meaning.
  Currently `EXTENSION-CONTENT` v3.7, `EXTENSION-HISTORY` v1.10, `EXTENSION-COMPUTE` v3.29.

- **Authored conformance checks for requirements no upstream suite reaches**, as
  language-neutral data with a per-language transport binding. An authored check is admitted
  only after it has been observed producing a different answer against a peer with the
  extension not installed — a check that reports the same verdict either way is measuring
  something else, and it occupies the requirement row that would otherwise honestly read
  `none`.

- **The Tier-1 `make` vocabulary in full** — `help build test lint fmt check clean`. `help` is the
  default goal, so a bare `make` in a fresh clone prints the verb list instead of starting a
  forty-minute run. `lint` is read-only and `fmt` writes; the per-language half of both is declared
  in `languages/<target>/profile.toml` rather than named in the Makefile, so a target whose
  toolchain image has no formatter is reported as such instead of skipped silently.

- **`docs/agents/memory/`** — what this project has learned, by subject, with an index. Each file
  carries the disciplines for one part of the system together with the incidents they were promoted
  from, so a rule and its evidence are never in different places. `AGENTS.md` states each rule in
  one line and points here; where the two differ the memory text is canonical.

### Known limitations

- **Three extensions of twenty-six.** The corpus this project exists to generate is much
  larger than what is built. The three that exist were chosen to test the generation model
  against different shapes — a handler, a recorder, an interpreter — rather than to cover
  the corpus.
- **Three languages of forty-six.** The peers are generated in forty-six languages upstream;
  extensions are built for three of them.
- **Conformance figures are per composition and are not a project-wide score.** A category
  score measures what the oracle's access path can reach on that peer, which is not the same
  sentence as what the extension does.

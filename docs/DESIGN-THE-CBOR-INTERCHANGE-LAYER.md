# The CBOR interchange layer — what a CBOR-only ecosystem owes its own users

**Internal.** Not declared in `CANONICAL-DOCS.toml`; nothing here is routed yet.

**Where this came from.** An operator directive, 2026-09-08, on finding this repo's own gate
emitting JSON so a third language could read a corpus. Stated as a design constraint, not a
preference, and in two parts:

- **No JSON.** This ecosystem's data language is CBOR in Entity Canonical Form. Anyone using any
  part of the system must be able to ingest it, emit it, audit it and VIEW it, with command-line
  tooling that is easy to use and SDK support behind it. What we need for ourselves, an outside
  consumer needs too, and to the same standard.
- **The peers are a library, not just a program.** The implementations are standard and adoptable
  piecemeal: someone takes as much or as little of the system as they want.

That is a design constraint and a scoping ruling, and this document is the read-in behind it.

---

## 1. The gap, measured

The ecosystem's data language is CBOR in Entity Canonical Form. **Nothing standardises how a human
or a program outside a peer gets data into or out of that form.** Surveyed 2026-09-08 across the
sibling trees:

| Where | What exists | Reachable by whom |
|---|---|---|
| `ENTITY-CBOR-ENCODING` §8 | **Diagnostic notation is specified** — a syntax table, RFC 8949 §8, with worked examples | everyone, as prose |
| `ENTITY-CBOR-ENCODING` App. E | the ECF conformance corpus is **authored in `.diag` and compiled to `.cbor`** — *"a build script generates the binary"* | named, not specified; the script is not named |
| `entity-core-go` `cmd/internal/diagcodec` | **the only diag parser in the ecosystem.** 450 lines, plus a 137-line canonical encoder | **nobody.** Go's `internal/` is compiler-enforced; under `cmd/`, it is reachable only from that tree's own commands |
| `entity-core-go` `cmd/entity-shell` | `cat <path> [-diag]` — the only **view** in the ecosystem | anyone with the go shell and a peer to point it at |
| every keystone peer (46) | `encode` · `decode` · `decode_salvage` · `content_hash`, public | any embedder, in that language |
| every keystone peer's program surface | `--name --port --seed --debug-open-grants --validate`. **A peer host and nothing else** | anyone with a shell |
| `entity-core-keystone/protocol-generator/shared/test-vectors/ecf-conformance/` | **one shared copy** of `conformance-vectors.{diag,cbor}` — 71 vectors, LOCKED, `canonical` fields filled from a cross-impl 3-way byte-equality round | referenced by **39 peer trees**, and the `.diag` is readable by **none of them** |

Read the last two rows together. **The authored source of the corpus is a format no
implementation that consumes the corpus can parse**, because the parser that produces the binary
lives behind a compiler-enforced boundary in a tree that is not one of them.

> **The two numbers in that row are corrected, 2026-09-09, and the correction is D14's own
> shape.** This document first said *"both are shipped to all 46 peers"* and *"a human-readable
> source file to forty-six implementations"*. Neither was measured. There is **one** copy, in a
> `shared/` directory the peers reference rather than receive, and the count of peer trees
> referencing it is **39**, not 46 — a cohort count taken from the cohort's size instead of from
> the artifact, which is **AP-1** exactly. The finding is unaffected and slightly sharper.
> Re-derivable, from `entity-core-keystone/`:
>
> ```
> find . -name conformance-vectors.diag | wc -l                      # -> 1
> grep -rl ecf-conformance protocol-generator/ | grep -v '^protocol-generator/shared/' \
>   | sed 's|protocol-generator/||' | cut -d/ -f1 | sort -u | wc -l   # -> 39
> grep -c '^\s*{' .../ecf-conformance/conformance-vectors.diag       # -> 71
> ```
>
> **And the path was wrong too**, which is the more interesting half: the row read
> `shared/test-vectors/ecf-conformance/` (dead), and in *this* repo `shared/` is our own
> `shared/spec-data/`. So a citation that resolves to nothing read as though it resolved.
> That is **D18's stated exposure cashing** — `tools/check-citations.py`'s own docstring says
> `docs/**` is not in its corpus and names it as the obvious next increment. It just cost a
> wrong path and two wrong numbers in the read-in behind an operator directive.

That is the finding. It is not that the capability is hard — go's parser is 450 lines for a
constrained subset. It is that it was written once, as a private helper for one corpus build, and
so **every subsequent consumer's cheapest path is to reach for JSON**, which is precisely what
happened here: this repo's own gate emitted JSON so a `rust` arm could read a corpus of checks.

**And the failure has the shape this repo already has a discipline for.** D16: *an axis with no
upstream authority gets its gate at the second implementation.* The interchange axis has no
upstream authority, has had two implementations for some time (go's parser, go's shell renderer),
and has no gate, no spec beyond a syntax table, and no second implementation to disagree with.

---

## 2. Why "just use JSON for tooling" is the wrong answer

It was the answer this repo reached for, so the argument against it is owed.

- **It is a second data model, not a second encoding.** JSON has no byte strings, one number type,
  no map-key ordering rule, and no canonical form. Every one of those is load-bearing here: `data`
  fidelity is raw bytes (§5.4), `content_hash` depends on §4.2.1 map ordering over **encoded key
  bytes**, and the float ladder is a canonical-form rule with a decode-side minimality check. A
  JSON round trip does not preserve an entity; it preserves a lossy projection of one, and the
  loss is exactly in the fields the content address is computed from.
- **It needs a translation layer per consumer, forever.** Ours already had one — `{ bytes = "<hex>" }`
  in TOML, materialised per arm — which is a hand-rolled, undocumented, per-target CBOR-in-JSON
  convention. That is the layer the ecosystem spent a spec avoiding.
- **It hides codec bugs.** A corpus that never round-trips through the canonical encoder never
  exercises it. The `.diag → .cbor` pipeline does, on every build.
- **The ecosystem already chose.** The conformance corpus is `.diag`, not JSON. Tooling that
  disagrees with the corpus about how humans write CBOR is a second de-facto standard, which is
  the one thing `gates/README.md` says a Kind C position must never manufacture.

---

## 3. The capability, named

**ECF interchange.** Five operations. They are not new inventions: four of them exist in some peer
today, unexported, and the fifth is what every peer's S2 harness already does internally.

| Operation | What it does | Who has it today |
|---|---|---|
| **`decode`** | canonical ECF bytes → diagnostic notation, for reading and auditing | `entity-shell cat -diag` (go, one shell, tree paths only) |
| **`encode`** | diagnostic notation → canonical ECF bytes | `cmd/internal/diagcodec` (go, private) |
| **`inspect`** | is this canonical? **which rule fails, at which offset** — §4.2.1 rules 1/3/4/5, §6.3 tags | every peer's decoder *knows*; none of them **says** outside an error return |
| **`hash`** | `content_hash({type, data})` with its format code, and the §4.4 string form | every peer, as a library call |
| **`vectors`** | run the locked ECF corpus and report per-vector, per-category | every peer's S2 harness, none of them as a callable surface |

**Two surfaces, and the split is the SDK's own rule.** `ROADMAP-SDK`, quoted in
`DESIGN-THE-SDK-LAYER` §1: *"The SDK is a convention, not an API mandate — your language, your
idioms, but the boundary bytes and operation semantics agree."*

- **Library** — every peer already exposes `encode`/`decode`; interchange adds the diag pair and
  `inspect` alongside them, in each language's idiom. `entity_core.encode` (python),
  `Ecf` (typescript), `entity_core_protocol::cbor` (rust) are the existing shapes to extend.
- **Program** — a CLI, because *"easy to use"* means not writing a program to look at a file.
  The peers ship exactly one program each and it is a host; this is the second.

**What is NORMATIVE here is the dialect, and only the dialect.** Flags, subcommand names and
output formatting are idiom. The bytes are already normative (ECF). The gap in the middle — *what
exactly is `.diag`* — is what has to be pinned, because two implementations that disagree about
how a byte string or a NaN is written have created a second interop surface with no gate on it.
§8's table is a start and is not sufficient: it says nothing about comments, embedded CBOR
(`<<...>>`), the `h''` grammar, `NaN`/`Infinity` spelling, key ordering on output, or whether a
diag document may carry a top-level comment block — and go's parser has taken a position on every
one of those, undocumented, in a private package.

---

## 4. The gate this arrives with, which is the reason to specify it

**A diag encoder has a byte-exact oracle on day one, and the ecosystem already owns it.**

```
conformance-vectors.diag  --(impl's diag encoder)-->  bytes
                                                        ==  conformance-vectors.cbor
```

71 locked vectors whose `canonical` fields were filled from a **cross-impl 3-way byte-equality
round**. An implementation's diag encoder either reproduces those bytes from the shipped source or
it does not. No new fixtures, no new authority, no judgement call — and it exercises the canonical
encoder and the diag parser in one run.

The reverse direction (`decode` → diag text) has no byte oracle, because formatting is idiom. Its
gate is a **round trip**: `decode(encode(d)) ≡ d` as a value tree, and `encode(decode(b)) == b` as
bytes, over the same corpus. That is enough to pin behaviour without standardising whitespace.

**This is the strongest argument for making it a standard rather than a tool.** The capability is
small, the conformance statement is free, and the corpus that proves it is already in every peer's
tree.

---

## 5. Where each piece belongs

Correcting a claim made earlier the same day: **this does not require keystone.** Our composed
hosts already bind entities into a peer in-process on all three substrates
(`peer.store.bind`, `languages/python/compositions/content-history/host.py` and
`languages/rust/compositions/content-history/host.rs`), and the
`types` face is `installed` on every target we have — including the one where the handler face is
not installable. The capability lives where we already work.

| Seat | What is theirs |
|---|---|
| **`entity-system-architecture`** | **pin the dialect** and declare interchange in the SDK corpus. A proposal, not a direct edit. The §8 table is theirs to extend; the operation set is ours to propose with a working implementation behind it |
| **`entity-core-go`** | nothing required. Their `diagcodec` is the prior art and the de-facto dialect; the proposal should cite it rather than re-derive it, and the polite form of this packet is *"you have written the standard, it is trapped in `cmd/internal`"* |
| **`entity-core-keystone`** | nothing required for us to proceed. If the dialect lands in the SDK corpus, the peers grow the library half through their own generator, on their own cycle |
| **us** | **implement it across languages, use it in our own build, and route what generating it teaches.** That is this repo's job description applied to the layer above the core protocol, and it is the first SDK-face capability that is not a per-extension wrapper |

**It is an SDK-face artifact, and that is the interesting part.** `DESIGN-THE-SDK-LAYER` §1.1a
records the operator's ruling that the SDK is guidance rather than a pass/fail suite, and D16 later
recorded that *where arch declines to standardise, the standard is ours to set*. Interchange is the
first thing on that face with a **byte-exact conformance statement** available to it, which makes
it the case that tests whether "ungated by design" was a property of the SDK layer or an accident
of what had been built on it so far.

---

## 6. First consumer: this repo's own check corpus

The authored-check corpus (`extension-contracts/*/checks/`) is what surfaced the gap, and it is the
right first user because it is a corpus **read by N implementations in N languages** — the exact
shape the interchange layer exists for.

**Target architecture:**

```
  authored source            our tooling                  every arm
  ───────────────            ───────────                  ─────────
  checks (hand-written)  ->  validate (linter)       ->   ECF bytes  ->  decode with the
                             encode via a peer's                          arm's OWN peer
                             canonical ECF encoder                        library, execute
```

- **No JSON, at any hop.**
- **No parser in any arm.** An arm decodes ECF with the peer library it already links, because an
  arm *is* a wire client. A new target's arm needs a client and nothing else — which is what makes
  this scale to 46 rather than to 3.
- **The encoder is a peer's, used as a library.** Keystone's python peer exposes `encode`/`decode`
  as its documented public API (`entity_core/__init__.py`: *"leading-underscore modules are
  internal and re-exported here as the stable public API"*). Using it from our tooling is using the
  system as a library, which is what it is for.

**Two phases, because the second one needs the tool this document is about.**

1. **Kill the JSON.** The corpus compiles from its current authored form to ECF; arms decode ECF.
   No authoring churn, and the JSON hop is gone.
2. **Move authoring to `.diag`.** The check corpus becomes a corpus in the ecosystem's own idiom,
   compiled by our own diag encoder — which makes our tooling its own first user, and means a
   defect in it breaks our gate before it reaches anyone else's. It also removes the third data
   language (TOML) from this data path.

Phase 2 is the dog-food finish and it should not be rushed ahead of the dialect question in §3.

### 6.1 The dual role, which is real and has a clean answer

**`python` is both a peer under test and our tooling language.** If our corpus encoder is the
python peer's ECF encoder *and* the python arm's decoder is the same code, then a codec defect is
invisible on that arm — the corpus and the reader would agree by sharing the bug. That is L18 with
one implementation instead of a cohort.

**The control is free and already in place:** the `typescript` and `rust` arms decode the same
bytes with entirely different codecs, and `compare.py` refuses when arms disagree about which
checks exist. A python-side encoding defect surfaces as a cross-arm disagreement, which is the same
property the ECF corpus itself was locked with. Written down here because "the encoder and one
decoder are the same code" is a fact someone will otherwise discover as a surprise.

**And the roles must not be conflated in the other direction:** the peer our tooling links as a
library is keystone's python peer *as a library*; the peer the `python` arm dials is a *process*
under test. Same code, two roles, and only the second one is ever a subject of a measurement.

---

## 6.2 Phase 1 is done, and what it cost

Landed 2026-09-08. `make ext-checks` has **no JSON at any hop**: the corpus is emitted as
canonical ECF by `gates/ext-checks/schema.py` through the declared codec, both arms decode it
with their own peer's codec, both arms encode their verdicts as ECF, and `compare.py` decodes
those. `10 of 10` admitted, unchanged from the JSON run — which is the point: the transport
changed and the measurement did not.

Three things it taught, all of them recorded where they were found:

- **The codec is not separable from the crypto.** `import entity_core` executes a package
  `__init__` that pulls Ed25519 in, so the ECF codec cannot be loaded without it —
  measured as `ModuleNotFoundError: No module named 'cryptography'` on a host that has
  everything else. A consumer who wants only the data language cannot have it. That is the
  first concrete argument for §3's separable interchange surface, and it is why the emit and
  compare steps now run in a container.
- **The two-codec property is free and real.** The corpus is encoded by one implementation and
  decoded by two others on every run; the `typescript` arm's verdict is encoded by a third
  codec and decoded by the first. A canonical-form defect surfaces as a cross-arm
  disagreement, which is the same property the locked ECF corpus was established with.
- **A round-trip refusal belongs at the encoder.** `--emit` decodes what it just encoded and
  refuses on mismatch, because the producer and one consumer share a codec and a shared bug
  would agree with itself.

**Phase 2 is not started** and should not be rushed ahead of §3's dialect question.

---

## 7. What this document does not settle

- **The dialect.** §3's list of undocumented positions (comments, `<<>>`, `h''` grammar, special
  floats, key order on output) is the content of the arch proposal, and every one should be
  answered by *what go's parser already does* unless there is a reason to differ.
- **The CLI's name and shape.** Whether interchange is its own program or a subcommand of the peer
  host is an idiom question, and the peers have exactly one program each today.
- **Whether `inspect` reports the first violation or all of them.** Every peer's decoder currently
  returns on the first; an auditing tool usually wants all.
- **Where the diag implementation lives in OUR tree.** It is language-neutral in intent and
  per-target in execution — the same split as `gates/ext-checks` — but the neutral half cannot
  hold a parser without holding a codec, which is the thing this document says not to hand-roll.
  The likely shape is that the first implementation is a per-target SDK-face artifact and the
  neutral half only orchestrates.

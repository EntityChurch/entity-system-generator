# Spec ambiguities

**The log required by `AGENTS-STANDARD`:** a gap or ambiguity in a spec is logged here and routed
upstream. It is never closed by a local decision and never worked around in generated output.

**Most of what generating turns up does not belong here.** A spec that answers itself four lines
later is not ambiguous — it is a document being read too fast, and that goes in the extension's
`arch/AUTHORING-NOTES.md`. This file is for questions the corpus genuinely does not answer, where we
had to pick a value to emit anything at all.

Each entry carries: the value we emitted, so it is greppable; what breaks if the resolution goes the
other way; and whether it is routed.

---

## CONTENT v3.7

### C-1 · A zero-length blob's chunk list — **open, not routed**

`create_blob` (§3.2) and `create_blob_cdc` (§3.6.3) are both `while offset < length(raw_bytes)`
loops, so zero-length input falls straight through and produces `total_size: 0, chunks: []`. The
spec never says whether that is a valid blob.

- **We emit:** `total_size: 0, chunks: []`. It is what the pseudocode does, and it is consistent
  with §3.3, whose completeness check sums an empty list to 0 and matches. §3.3's `empty_chunk`
  guard is about a chunk whose *payload* is empty, which is a different object.
- **If the resolution is the other way** (a blob MUST have ≥1 chunk, or zero-length content is not
  representable as a blob), every implementation that took the pseudocode literally is emitting an
  entity nobody else accepts — and it would surface as a dedup miss on empty files, not as an error.
- **Not routed yet.** One reading of one spec by one seat is not a finding; §3.6.5's cross-impl
  vectors are the right place for this to surface, and it costs nothing to carry until then. Raise
  it when a second port or a sibling impl disagrees.
- **Three ports now emit this reading and that changes NOTHING** *(2026-09-06)*. `typescript`,
  `python` and `rust` all produce `total_size: 0, chunks: []`, and each was transcribed from the
  pseudocode rather than translated from the others. It is still three transcriptions of one
  snapshot in one generation lineage — cohort consistency, not evidence about the spec (L18).
  Written down explicitly because "all our implementations agree" is the sentence that turns a
  carried assumption into a claimed resolution, and the entry should not leave that to be inferred.
  **What WOULD raise it:** a sibling implementation that is not ours disagreeing, or a §3.6.5
  vector. `gates/chunking-parity/` does not settle it — that gate compares chunkers on non-empty
  input and never constructs the zero-length case.

### C-2 · §6.1's manifest spells the pattern `system/content/*` — **closed by the document itself**

The §6.1 code block writes `pattern: "system/content/*"`; the prose two lines below writes *"Manifest
at pattern path `system/content`. Index entry at `system/handler/system/content`."* The `/*` is the
capability-scope spelling from §6.4's grant examples, not a binding path.

- **We emit:** `system/content`. Prose, index path and oracle all agree.
- **Not an ambiguity.** Logged so the next language port does not re-litigate the same block, and
  because "the code block and the prose disagree" is the shape that *usually* is one.

---

### C-3 · `path_required` is MUST-ed by CONTENT and defined by no spec code set — **routed 2026-09-06**

Arrived with the v3.6 → v3.7 re-pin, and it is the first entry here that a *second* port could
not have found either: it took a **new kind of artifact** — v3.7's Appendix A — to make the gap
visible.

CONTENT §6.2 and §6.3 each **MUST** `400 path_required`. v3.7's Appendix A declares itself the
handler's code set and states that *"an undefined spelling is non-conformant"*. `path_required`
is not in it, and it is not in core §3.3's enumeration either:

```
$ grep -c 'path_required' specs/ENTITY-CORE-PROTOCOL.md
0
```

- **We emit:** `400 path_required`, unchanged, in all three ports. It is what the two MUSTs say,
  what `entity-core-go` asserts (`get_path_required`, `ingest_path_required`), and what the
  reference implementations do. Changing it to satisfy Appendix A's letter would fail the
  conformance suite, which is the clearest possible sign the letter is what is wrong.
- **The ambiguity is a reading of core §3.3, not of CONTENT.** `GUIDE-EXTENSION-DEVELOPMENT`
  §4.1 reads the 400 row as sanctioning the *category* of more-specific codes and calls itself
  "the authority for that status"; Appendix A reads the same row as a *closed set*. Both
  readings are in the corpus at once, and `path_required` is conformant under one and not the
  other.
- **If the resolution goes the other way** — Appendix A's closed reading stands and
  `path_required` is not added — then every peer in the cohort emits a non-conformant code on a
  path the oracle gates, and the correct value becomes `400 invalid_request`. That is a wire
  change for every implementation, which is why it is routed rather than picked.
- **Routed** to the specification authority (A-1), with two concrete asks. Tracked locally in
  `extension-contracts/content/EXTENSION.toml` `[error_surface].unresolved`, where
  `tools/check-error-codes.py --strict` turns it into a build failure the day it is pinned.

## What three ports taught about this file

**Every entry here came from the FIRST port — until C-3, which came from a RE-PIN.**
`python` and `rust` added none, not because they were read less carefully, but because reading a
spec closely enough to emit code forces every ambiguity to a value on the first pass, and later
ports re-read the same document with the same questions already answered.

**C-3 is the correction, and it names a third source rather than weakening the second.** It did
not come from a port at all: it came from **a new kind of artifact appearing in a snapshot we
already had three ports against**. v3.7 added an error-code table, and the table made visible a
gap that had been in the corpus the whole time and that no amount of re-reading §6.2 would have
surfaced, because §6.2 states its MUST perfectly well. What was missing was a *second document*
to check it against. So the list of things that find spec ambiguities is three long, not two:

| a new **extension** | forces a different part of the corpus to a value |
| a new **snapshot** | supplies a document the existing reading can be checked *against* |
| a new **language port** | finds substrate facts, and essentially no spec ambiguities |

So the planning consequence, recorded here because this is the file that would otherwise look
neglected: **a new language port is not how you find spec ambiguities. A new extension is.**
Ports two and three earned their keep on the substrate axis instead —
`extension-contracts/content/arch/AUTHORING-NOTES.md` §2 — and that is a different column in a different
document.

## Routed elsewhere

Findings about a **peer** are not spec ambiguities and do not belong here. They go to
`entity-core-keystone` and are then dropped — another repo's queue is not ours to track.

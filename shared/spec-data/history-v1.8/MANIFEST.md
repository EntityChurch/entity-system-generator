# spec-data snapshot — `history-v1.8`

**Immutable.** Operators never edit a snapshot. A defect in a snapshotted spec is routed upstream and
lands as a **new directory**, never as a local patch.

**Stamped:** 2026-09-08, from `entity-system-architecture` @ `523eae743f2153ed90aa529d937ca53440a43b62`.
*(An internal SHA. This file is not a publication surface — `docs/status/` rules apply.)*

| File | sha256 | Version |
|---|---|---|
| `EXTENSION-HISTORY.md` | `0a6346043cab5abff2a254bbd3e27db9f48100af3df3a28f0d083cb6eaabb919` | 1.8 |
| `SYSTEM-COMPOSITION.md` | `084faf207da6ebb9d7e57fd05bf31a14228e1d23c821d7e4675ff6a971166627` | — (§2.2 consumer ordering, §1.4/§1.5 execution context) |
| `GUIDE-EXTENSION-DEVELOPMENT.md` | `a3ebc7239aa27bb3c99d35f39230b632b2e5676911cf1c8c9cb52f1db5a6c679` | — (§4.1 `path_required`, §9 grade) |

Verify:

```
sha256sum -c <<'EOF'
0a6346043cab5abff2a254bbd3e27db9f48100af3df3a28f0d083cb6eaabb919  EXTENSION-HISTORY.md
084faf207da6ebb9d7e57fd05bf31a14228e1d23c821d7e4675ff6a971166627  SYSTEM-COMPOSITION.md
a3ebc7239aa27bb3c99d35f39230b632b2e5676911cf1c8c9cb52f1db5a6c679  GUIDE-EXTENSION-DEVELOPMENT.md
EOF
```

**`SYSTEM-COMPOSITION.md` is byte-identical to the `history-v1.7` pin** — same digest,
`084faf20…`. It is re-pinned rather than referenced across snapshots because a snapshot is a
self-contained input set; a directory that pointed at a sibling for one of its three files would
make the pin a graph rather than a set.

**`GUIDE-EXTENSION-DEVELOPMENT.md` MOVED** — `4bbe1521…` → `a3ebc723…`. It is the declared authority
for `path_required`'s status (Appendix A defers to it by name), so the digest change is load-bearing
here in a way it was not at v1.7. See `docs/archive/status/HANDOFF-2026-09-08-*` §2 for what the diff
contains and what it does and does not change for us.

---

## What v1.8 changed, and the honest summary is that three of our routed findings came back as spec

`EXTENSION-HISTORY` v1.7 → v1.8 is **+94 lines**, and it is not a wording pass. Ordered by what it
costs us:

### 1. §9.1 gains FIVE MUST rows — 10 requirements to 15

```
$ awk '/^### 9\.1/,/^### 9\.2/' EXTENSION-HISTORY.md | grep -c '^| '
16                                      # 15 rows + the header row
```

| new row | level |
|---|---|
| Refuse a rollback target absent from the chain with `404 not_in_history` (Appendix A, §7.5) | MUST |
| Emit error codes from Appendix A's set; no other more-specific spelling | MUST |
| Select the most specific matching config, independent of enumeration order (§6.2) | MUST |
| Compare specificity as the §6.2 tuple, not a collapsed scalar (§6.2) | MUST |
| Canonicalize a leading-`*` config pattern to `/*/` + remainder (§2.2) | MUST |

**This is the event `[conformance]` exists for** (D16's fourth instance). A re-pin that adds five
binding rows without anyone deciding what measures them is exactly the failure
`tools/req-coverage.py` refuses: an undeclared or stale row is a gate failure, so the rows had to
be read and assigned before this snapshot could be adopted.

### 2. Appendix A — the `system/history` code set now exists

Six rows. `not_in_history` (404) is the one that matters: §7.5 makes it the refusal that stops
`rollback` being an unrestricted write primitive, and **before v1.8 no code set defined it**, so a
peer following `ENTITY-CORE-PROTOCOL` §3.3's closed-set rule to the letter had to fall back to the
404 default `handler_not_found` and lose the distinction the security model depends on.

`path_required` is carried in the table **with its authority named and deliberately not resolved
there** — *"the code is emitted by more than one extension and its home is a corpus-level question
tracked separately."* Our `[error_surface]` declaration of it as `unresolved` was the right call and
now has a citable home rather than a routed question.

### 3. §2.2's pattern grammar, and §3.3's pruning — both are our routed readings, landed

Two things we implemented as **declared deviations from v1.7's own pseudocode**, routed, and shipped
in three ports, are now the spec text:

| we shipped | v1.8 says |
|---|---|
| bare `*` → `/{local}/*`, tested **before** the first-segment check | the pseudocode now tests `pattern == "*"` first, with a comment saying the check would otherwise "read it as a peer wildcard and emit the degenerate `/*/`" |
| `*/rest` → `/*/rest` | *"The peer wildcard is spelled `/*/rest` and **never** `*/rest`, which `canonicalize` rejects by name"* — and §2.2's table is corrected from `*/project/*` to `/*/project/*` |
| `pruneHistory` walks and reports, mutating nothing | *"It MUTATES NOTHING: no entity is rewritten, the head pointer is not moved, and the chain stays fully linked"* |

**The mechanism, not the luck.** We did not guess right; generating an implementation forced §2.2's
table and §2.2's pseudocode to a single value, and they disagreed. v1.8's own commit message reaches
the same finding independently and adds the part we could not see from here — the same invalid
spelling is in four other published documents, and a peer that configured cross-peer history
*recorded none and reported no error.*

### 4. Two new REQUIRED conformance vectors, and nothing upstream runs them

`HIST-CONFIG-SPECIFICITY-1` (key 1 separates) and `HIST-CONFIG-SPECIFICITY-2` (key 1 ties, **only
key 2 separates**), each REQUIRED, each specifying **both insertion orders** because *"an
implementation that returns the first match rather than the most specific one passes exactly one
order, by luck."*

The oracle's `history` category has no config-selection check — the executed corpus is the scope of
that claim (`tools/req-coverage.py` prints it). So these are two REQUIRED vectors with no
instrument, which is the `extension-contracts/history/checks/` case exactly.

### 5. What v1.8 says is NOT constructible, which is the part worth reading twice

v1.7 justified the specificity tuple with a worked pair, `a/b/c/d` against `a/*/c/*/e`. **v1.8
retracts that pair**: `a/*/c/*/e` is a mid-path spelling and is not a pattern at all, so no path
distinguishes the readings. It then proves by cases over §5.4's three admissible families that a
key-1 *and* key-2 tie is unreachable, and that the scalar collapse the MUST forbids **agrees with
the tuple on every pair a peer can construct today.**

The MUST is kept as forward-looking, and the spec says so in as many words: *"A specification that
claimed otherwise would be asking implementers to defend against a case they cannot write a test
for."* **Two of the five new MUSTs are therefore satisfiable-by-construction under the current
grammar**, and a `[conformance]` row that claimed a check proved them would be claiming more than
the requirement contains. Recorded here so the assignment in `EXTENSION.toml` is read against it.

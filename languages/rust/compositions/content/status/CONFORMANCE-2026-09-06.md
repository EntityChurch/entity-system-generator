# rs-content — conformance, 2026-09-06

**Internal.** `rust` × CONTENT v3.6, composed onto a keystone `entity-core-protocol-rust`
peer and measured by `entity-core-go`'s `validate-peer`.

**Read the numbers with §2 open.** This is the first composition where the extension's four
faces do not all install, so a single line of the form *"N of M"* would describe the wrong
thing. Two categories are reported and one of them is reported specifically because the
composition cannot move it.

**Measured at:** generator `HEAD` of this commit · keystone `8156792` **+ uncommitted
working tree** · oracle `output/s4-oracles/validate-peer` (gitignored local build from
`entity-core-go`; see `PROVENANCE.txt` beside it).

---

## 1. The numbers

Every figure below is the summary block of the JSON report named beside it, not a count read
off a listing (D14).

### 1.1 `type_system` — the category that measures us

```
                 PASS  WARN  FAIL  SKIP   total
bare              112    11   323     0     446    reports/bare-type_system-*.json
composed          118    11   317     0     446    reports/composed-type_system-*.json
```

**6 checks moved. All six are ours, all six FAIL → PASS, and nothing else moved:**

```
type_system_content_blob_fetch        FAIL -> PASS   fetched system/type/system/content/blob
type_system_content_blob_match        FAIL -> PASS   content hash match
type_system_content_chunk_fetch       FAIL -> PASS   fetched system/type/system/content/chunk
type_system_content_chunk_match       FAIL -> PASS   content hash match
type_system_content_descriptor_fetch  FAIL -> PASS   fetched system/type/system/content/descriptor
type_system_content_descriptor_match  FAIL -> PASS   content hash match
```

**The three `_match` checks are the point of this run.** `validate-peer` renders the same
three §11.1 types from `entity-core-go`'s **own independent transcription** of §2.1/§2.2/§2.4
and compares content hashes. This port's seven field maps are hand-built — the peer's `FSpec`
/ `TypeDef` builders carry no `pub` — and a subtly wrong map produces a well-formed entity
that hashes differently from everyone else's, ends dedup for that type, and raises no error
anywhere. Nothing local can catch that. This is what catches it.

**317 checks still FAIL on the composed peer and none of them are ours.** They fail on the
bare peer too, identically, and they are the extension type vocabularies a core peer does not
publish by design (`type_defs.rs`: *"Extension vocabularies (compute/\*, content/\*,
subscription/\*, …) are NOT published by a core peer"*). Six of them were CONTENT's, and they
are the six above.

### 1.2 `content` — the category that measures the absence

```
                 PASS  WARN  FAIL  SKIP   total
bare                4     0     5     4      13
composed            7     0     2     4      13
```

Check by check, composed:

```
SKIP   handler_manifest              no handler is registered
SKIP   handler_op_get                        "
SKIP   handler_op_ingest                     "
PASS   type_blob                     FAIL -> PASS   (ours)
PASS   type_chunk                    FAIL -> PASS   (ours)
PASS   type_descriptor               FAIL -> PASS   (ours)
FAIL   get_path_required             both arms — needs a handler to answer 400; the peer 404s
FAIL   ingest_path_required          both arms —          "
PASS   inline_include_at_threshold   never contacts the peer
PASS   inline_include_above_threshold        "
PASS   descriptor_presence_rule              "
PASS   descriptor_integrity_check            "
SKIP   frame-limit-respected         the Amendment 1 MUST is UNEXERCISED, as on both other ports
```

**The two FAILs are not ours and are not a regression.** They are `FAIL` on the bare arm and
`FAIL` on the composed arm; the peer answers `404 handler_not_found` where the check wants
`400 path_required`, because there is no handler. Our handler answers `400` and is unit-tested
doing so (`tests/handler.rs`), and no wire path reaches it.

### 1.3 `--profile core` — the guard for our own second failure mode

```
ROUNDS: 2   (756 checks per arm)
REGRESSIONS ATTRIBUTABLE TO THE COMPOSITION: 0
IMPROVEMENTS: 6   FLAKY: 0
```

bare `313 P / 337 W / 0 F / 106 S`, composed `319 P / 331 W / 0 F / 106 S`. The six
improvements are the six `type_system` checks above; `--profile core` includes that category.

**They read `WARN → PASS` here and `FAIL → PASS` in §1.1, and that is not a discrepancy.** The
oracle downgrades non-floor type checks to WARN inside the core profile — a core peer is not
required to publish extension vocabularies — and scores them FAIL in a standalone category run.
Same six checks, same six passes, two severities depending on the invocation. `ts-content` and
`py-content` recorded only the `WARN → PASS` form, because neither ran the category standalone.

### 1.4 Unit tests, and what they are not

```
40 tests   11 chunking · 13 handler · 9 sdk · 7 types
 + the §3.4 export-boundary arm: a compile that MUST fail (E0603), with a
   positive control (tests/sdk.rs) that must compile in the same invocation
```

**These reach code no oracle reaches on this peer.** `tests/handler.rs` drives every §6.2/§6.3
branch against a real peer `Store` and proves the algorithms are right. It does not prove that
anything on a wire runs them, and on this peer nothing does.

## 2. What this composition installs, and what it refuses to

| face | state | how we know |
|---|---|---|
| types (§11.1) | **installed** | the seven binds above; 6 oracle checks moved |
| emit consumer | available, unused | probe scenario 2, two negatives |
| SDK | library-only | no gated path reaches it here |
| handler body (§11.6.1 step 4) | **NOT INSTALLABLE** | probe scenario 1, both arms + rustc |

`gates/host-seam/rust/`, executed:

```
A. nothing bound at system/content        404  handler_not_found
B. all four §11.6.1 tree writes bound     501  no_handler_body
C. the same body called DIRECTLY          200  witness=rs-seam-9c41:hello
   invocations: before=0  after dispatch=0  after direct=1

error[E0624]: method `register_handler` is private
error[E0609]: no field `handlers` on type `Peer`
error[E0603]: struct `Outcome` is private
error[E0624]: method `resolve_handler` is private
```

**The composition does not perform the four tree writes, and that refusal is its most
important line.** It would move the peer from `404 handler_not_found` — true, no content
handler exists — to `501 no_handler_body`, which says one exists and is broken. Making a peer
worse so a report looks more installed is precisely what `make regression` exists to catch.
`tools/compose.py` enforces it structurally: with `[system.faces].handler = "not-installable"`
the pattern is dropped from the plan, so the wiring program that would do it cannot be
generated.

## 3. The prediction, and the part of it that was wrong

`[gate.expectation]` was written into `SYSTEM.toml` **before** the run, as on both prior
compositions. Recorded here as predicted-vs-measured rather than quietly corrected.

| | predicted | measured | verdict |
|---|---|---|---|
| `type_system` | the three CONTENT type checks go non-PASS → PASS; nothing else moves | **6** moved, all FAIL → PASS, nothing else | **direction right, count wrong** |
| `content` | bare and composed **identical, check for check** | **3 moved** (`type_blob`/`chunk`/`descriptor`) | **WRONG** |
| `--profile core` | 0 regressions | 0 regressions, 6 improvements, 0 flaky | right |

**The `type_system` miss was arithmetic**: each type has a `_fetch` check and a `_match`
check, so three types are six checks. `measures_us = 3` should have been `6`.

**The `content` miss was a wrong model of the category, and it is the more useful error.** The
prediction assumed the `content` category was handler-driven end to end. It is not: three of
its thirteen checks read type entities out of the tree and never touch a handler. The
composition moved them because it publishes types.

### 3.1 What that miss corrects, in a number we have already published

Both prior compositions report **"8 of 8 measure our handler"**, and `docs/STATUS.md` repeats
it. That figure is right about *how many checks measure our module* and wrong about *which
face they measure*. This run separates them, by experiment rather than by re-reading:

| | checks | which |
|---|---|---|
| measure the **handler** face | **5** | `handler_manifest`, `handler_op_get`, `handler_op_ingest`, `get_path_required`, `ingest_path_required` |
| measure the **types** face | **3** | `type_blob`, `type_chunk`, `type_descriptor` |
| never contact the peer | 4 | `inline_include_*`, `descriptor_*` |
| skipped | 1 | `frame-limit-respected` |

On `rs-content` the types face installs and the handler face cannot, so exactly the 3 pass and
exactly the 5 do not. **That is the measurement that splits the 8**, and no composition where
both faces installed could have made it — which is the strongest single argument for having
done a third port at all.

The corrected phrasing for `ts-content` and `py-content` is **"8 measure our module — 5 the
handler, 3 the types"**. The 8 was never wrong; the word "handler" was.

## 4. What we refuse to claim

- **This is not a CONTENT conformance result.** Three of thirteen `content` checks pass
  because of us and the three handler checks SKIP. A peer with this composition installed
  does not serve content.
- **`content hash match` is three of ours agreeing with one that is not.** It exercises the
  §3.6.5 ECF byte-equality surface for three type definitions across `typescript`, `python`
  and `rust`, each transcribed independently from the same pinned snapshot and each compared
  against `entity-core-go`'s own. **It ran no chunker**, and it says nothing about the other
  four types.
- **The frame-budget MUST is UNEXERCISED here as on both other ports**, and on this one it is
  additionally *unsatisfiable in mechanism*: `wire::MAX_FRAME` is a public const with nothing
  to configure. Routed (§3.4 of `AUTHORING-NOTES.md`) as *"make it configurable"*, which is a
  different packet from K-1's *"unimplementable"*.
- **Namespace-scoped topology (§6.4.2) is not implemented** on any port; declared as a gap in
  `EXTENSION.toml [assumptions].topology`.
- **Three ports agreeing is three ports agreeing** (L18). They share a generation lineage and
  a single reading of one snapshot.
- **The citation into keystone does not resolve.** Everything here was measured against their
  `8156792` plus an uncommitted working tree. Re-run once they commit.

---

## Re-measured at the CONTENT v3.6 → v3.7 re-pin — 2026-09-06

**Appended, not rewritten.** Everything above is the record of the **v3.6** run and stays as
written; a measurement is dated by when it was taken, and a document that edits its own numbers
when the input moves is not a record. This stanza is the **v3.7** run.

**Every verdict above reproduces.** The re-pin changed one thing this composition can emit —
§6.4's `403 forbidden` → `403 capability_denied` — and **no check in the `content` category
asserts that code**, which is exactly why the change needed a gate rather than a test
(`tools/check-error-codes.py`; AP-11; D16's third instance).

```
snapshot   shared/spec-data/content-v3.7/EXTENSION-CONTENT.md
           sha256 2a40b22b859b2a74f7de4d1c43b4655cb6ece2b791d7769f27fcc87efa65ee87
command    make check-all          (exit 0)
           content      7 PASS · 4 SKIP · 2 FAIL   (13 declared)
           type_system  317 FAIL · 118 PASS · 11 WARN   (446 declared)
artifact
           content-report-2026-09-06-v3.7.json
           sha256 d564ea9f7bd76fcffa1b2b34b00dc4d5aca867431eb6ff5a6395537aaf8aeb43
           type_system-report-2026-09-06-v3.7.json
           sha256 df298849bd3fc13d0cbe5eb66b1079bfbbadf1dae2e7566e714ef85dbaa106ce
```

Unchanged: **content 3 improved · type_system 6 improved**, `REGRESSIONS ATTRIBUTABLE TO THE COMPOSITION: 0`, `FLAKY: 0`.
Core profile both rounds: 0 regressions, 6 improvements.

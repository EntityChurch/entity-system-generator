# py-content — the retarget, measured

**2026-09-06. Internal.** The second substrate. The question this run exists to answer is
not *"does CONTENT work"* — `ts-content` answered that — it is **"is the generation model a
profile change or a rewrite"**.

---

## The number, identical to `ts-content`, and identical *before* the run

```
content: 12 PASS · 0 WARN · 0 FAIL · 1 SKIP  (13 declared)
```

Same breakdown, same 8/4/1, check-for-check the same verdicts:

| class | n | outcome |
|---|---|---|
| **measures our handler** | **8** | **8 of 8 PASS** — `handler_manifest` · `handler_op_get` · `handler_op_ingest` · `type_blob` · `type_chunk` · `type_descriptor` · `get_path_required` · `ingest_path_required` |
| **measures the oracle's own library** | 4 | 4 PASS, inattributable — they would pass against a bare peer, an empty peer, or no peer |
| **declared skip** | 1 | `frame-limit-respected` — needs a `local/files` root to seed >16 MiB. **The surface is untested.** |

> **CORRECTION, 2026-09-06.** The row labelled *"measures our handler"* is **8**, and the
> count is right. The label is not: **5 of the 8 measure the handler face and 3 —
> `type_blob`, `type_chunk`, `type_descriptor` — measure the TYPES face.** On this peer
> both faces install, so nothing distinguished them and the conflation cost nothing.
> `rs-content` is where it stops being free: on that peer the types face installs and the
> handler face cannot, and exactly the 3 pass while exactly the 5 do not. That is a
> measurement, not a re-reading — see
> `compositions/rs-content/status/CONFORMANCE-2026-09-06.md` §3.1. **No number in this
> document changes.** The honest phrasing is *"8 measure our module — 5 the handler, 3 the
> types"*.

Never `13P·0F`, never `12/13`, never a percentage. A skip counts as a failure ([ADR-0012]).

The expectation was written into `SYSTEM.toml [gate.expectation]` **before the port was
written**, on the argument that these 13 checks are wire-driven or in-process-to-the-oracle
and none of them knows what language the peer is in. That held.

Artifact: `content-report-2026-09-06.json`, sha256
`c42649dd6ebe6cc7d15867b2a3d0b4941feed03cd0a0c9606ceebdefcc93cd09`.

Reproduce: `make check COMPOSITION=py-content`.

## Regression guard: 0

```
round 1  bare PASS 314 · WARN 336 · SKIP 106      composed PASS 320 · WARN 330 · SKIP 106
round 2  bare PASS 314 · WARN 336 · SKIP 106      composed PASS 320 · WARN 330 · SKIP 106
                                                            (756 checks each)

REGRESSIONS ATTRIBUTABLE TO THE COMPOSITION: 0
IMPROVEMENTS: 6   FLAKY: 0
```

Per-check diff: `core-arms-diff-2026-09-06.txt`. Digests — bare `bed86d0f…` / `d7d5cfc7…`,
composed `2aa6a973…` / `4341855479…`.

**`FLAKY: 0` here and `FLAKY: 1` on `ts-content` is itself informative.** The flake that
made the single-round diff manufacture a regression was `concurrency.t1_1_concurrent_demux`,
whose verdict turns on whether the sequential baseline lands under a 50 ms floor. The
`typescript` peer sits within a millisecond of that floor; this one does not go near it. The
flake is a property of the peer's speed against the oracle's threshold, not of either
composition — which is exactly what "attributable to neither arm" was supposed to mean.

## The result worth the most: the hand-built type maps hash correctly

The same six checks went `WARN → PASS`, and the `_match` half reports **`content hash
match`** for `blob`, `chunk` and `descriptor`.

**This was the port's biggest live risk.** The `typescript` cell renders its type entities
through the peer's own public `TypeDef` / `FSpec` builder, which removes a way to disagree.
**`python` has no such builder to reuse** — its equivalents are all leading-underscore, and
`AGENTS-STANDARD` makes a sibling's private surface read-only context. So the seven field
maps are hand-built dicts, on precisely the surface where a mistake is silent: nothing in
the module fails if a field map is subtly wrong, the entity just hashes differently from
everyone else's and dedup stops working for that type with no error anywhere.

It matched. Stated at its true strength:

- **What this is:** `entity-core-go`'s own independent transcription of §2.1/§2.2/§2.4,
  rendered by its own encoder, produced the same content hashes as a hand-built Python dict
  and as a TypeScript builder call. That is the *ECF byte-equality surface* §3.6.5 names as
  a place where disagreement "breaks cross-peer dedup silently" — exercised on two of our
  substrates now, and agreeing with the one implementation that is not ours.
- **What this is not:** three-way convergence. Two of the three transcriptions are ours,
  read from one snapshot by one team. The independent axis is Go and only Go. And **no
  chunker ran** — this is agreement on type definitions, not on FastCDC boundaries.

## What the second substrate cost, concretely

Nothing in `extensions/content/python/` is a translation of the TypeScript. Both are
transcriptions of the same pinned snapshot, deliberately: a translation of our own port
would agree with it by construction and tell us nothing.

| | `ts-content` | `py-content` |
|---|---|---|
| cell files | 6 | 6 |
| unit tests | 31 | 38 |
| install adapter | `registerHandler` + publish types (2 steps) | **all four §11.6.1 writes + types + the body (6 steps)** — the peer has no registration surface |
| build driver | `tsc` × 2 (module, then tests against the built package) | **no compile step**; stage + an import check |
| `§3.4` boundary | **enforced by node's `exports` map** | **convention** — underscore, `__all__`, and a test that asserts the convention *can be walked around* |
| frame budget in tests | hand-built `ConnectionState` (in-process) | `Peer(seed, max_frame_bytes=N)` over a **real connection** |
| `languages/<lang>/` | 4 files | 4 files, same names, same interface |

**The toolchain axis held: `languages/python/` is the same four files with different
contents, and `compositions/py-content/SYSTEM.toml` differs from `ts-content`'s in exactly
two fields.** The claim that a composition names things and declares nothing new survived
its first real test.

## What is NOT measured, and stays unmeasured

- **`frame-limit-respected`** — skipped for want of a `local/files` root. Implemented and
  unit-tested here against a **real connection** with a configured 8 KiB budget, which is a
  stronger local test than the `typescript` port can construct. **It is still not the
  behavioural check, and this is not a claim it would pass.**
- **The SDK face.** No gate anywhere, by design. `AtPeer` and `reassemble_under_capability`
  have empty `reached_by`.
- **Namespace-scoped topology (§6.4.2).** Not implemented; declared as a gap in
  `EXTENSION.toml [assumptions].topology`.
- **The §3.4 boundary in this language is weaker than in `typescript`**, and
  `EXTENSION.toml [substrate.export_boundary]` records that rather than reporting both as
  satisfied. Reporting one verdict for two different boundaries is the D13 error.

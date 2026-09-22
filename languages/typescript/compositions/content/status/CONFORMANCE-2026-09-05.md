# ts-content — first conformance run

**2026-09-05. Internal.** The first generated extension measured by the oracle.

---

## The number, with its breakdown, never as a percentage

```
content: 12 PASS · 0 WARN · 0 FAIL · 1 SKIP  (13 declared)
```

**Do not cite that as `13P·0F`, and do not cite `12/13`.** A skip counts as a failure
([ADR-0012]), and — more importantly — 12 passes is not 12 measurements of us. Classified by
reading every check body in the oracle, `cmd/internal/validate/content.go` @ `ed9b547`:

| class | n | checks | what a pass means |
|---|---|---|---|
| **measures our handler** | **8** | `handler_manifest` · `handler_op_get` · `handler_op_ingest` · `type_blob` · `type_chunk` · `type_descriptor` · `get_path_required` · `ingest_path_required` | **8 of 8 PASS.** These are ours. |
| **measures the oracle's own library** | **4** | `inline_include_at_threshold` · `inline_include_above_threshold` (both call `exerciseInlineInclude`, which builds an in-memory store and never contacts the peer) · `descriptor_presence_rule` · `descriptor_integrity_check` (both call `content.ValidateDescriptor` in-process) | 4 PASS, **inattributable**. They would pass against a bare peer, an empty peer, or no peer. |
| **declared skip** | **1** | `frame-limit-respected` | needs a writable `local/files` root to seed >16 MiB of content. A CONTENT-only composition has no way to provide one. **The surface is untested.** |

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

**So the honest sentence is: 8 of the 8 checks that measure this handler pass; 4 more passed
without measuring it; one MUST is unexercised.** The 8/4/1 split was predicted before the run,
in `compositions/ts-content/SYSTEM.toml [gate.expectation]`, and the run matched it.

Artifact: `content-report-2026-09-05.json` (in this directory), sha256
`d7f47cd854ae528ae693211909b4e9f03c5f920c0c78b08f60b5df3cf0599ad3`.

Reproduce:

```
./tools/compose.py compositions/ts-content
podman run --rm --network=none --security-opt label=disable \
  -v "$CHURCH:/church:ro" -v "$CHURCH/entity-system-generator:/church/entity-system-generator" \
  -w /church/entity-system-generator localhost/entity-core-keystone/node24:latest \
  sh -c './languages/typescript/build ts-content && ./languages/typescript/host-launch ts-content -category content'
```

## The regression guard: 0

Our second failure mode is one keystone never has — **the peer was right and we broke it.** An
extension installs into a live peer, writes its tree and shares its dispatch table, so a
regression it causes surfaces as a *core* check failing in a category unrelated to CONTENT.

Two arms, same oracle, same flags, same container, one variable — `BARE=1` launches the peer's own
host out of the same staged `dist/`, so the arms differ by the composition and by nothing else,
including the peer build. **Three rounds per arm**, and the reason for that is below.

```
round 1  bare PASS 314 · WARN 336 · SKIP 106      composed PASS 320 · WARN 330 · SKIP 106
round 2  bare PASS 314 · WARN 336 · SKIP 106      composed PASS 320 · WARN 330 · SKIP 106
round 3  bare PASS 315 · WARN 335 · SKIP 106      composed PASS 321 · WARN 329 · SKIP 106
                                                            (756 checks each)

REGRESSIONS ATTRIBUTABLE TO THE COMPOSITION: 0
IMPROVEMENTS: 6   FLAKY: 1
```

Full per-check diff: `core-arms-diff-2026-09-05.txt` (`make regression ROUNDS=3`).
Digests — bare `03d7b188…` / `b9049377…` / `b049aa89…`, composed `e060fe66…` / `d2e8b161…` /
`21f394a0…`. *(Six 250 KB reports; they live under the gitignored `output/`, and the diff plus the
digests are what ship. Regenerating from the command above reproduces them.)*

### Why three rounds, and not one

**A single-round diff reported a REGRESSION that was not there.** On its second execution it flagged
`concurrency.t1_1_concurrent_demux`: bare PASS, composed WARN. The check suppresses its
parallel-speedup signal when the sequential baseline lands under a **50 ms floor** — the bare arm
measured 49.80 ms and got the free pass, the composed arm measured 50.85 ms and got the signal
evaluated. One millisecond of wall clock, and the arms had swapped sides since the run before.

Over three rounds the same check reads `WARN/WARN/PASS` on **both** arms — identically — and is
classified FLAKY rather than attributed to either. A check is now called a regression only when it is
PASS on bare in every round and non-PASS on composed in every round.

**This is the expensive direction of wrong.** A guard that manufactures a regression teaches the next
person to ignore it, and then it is not a guard.

**And "pre-existing" is now measured rather than asserted.** **335** core-profile checks are non-PASS
on the bare peer *in every round* — all WARN, mostly `type_system` fetches for types outside the §9.5
core floor. None is ours, and the diff is what says so. *(A single round counts 336; the extra one is
the flaky concurrency check above, which is why the count is taken over rounds and not off one run.)*
[ADR-0012] forbids calling a failure pre-existing without bisecting; two arms over three rounds is
the cheapest honest bisect there is.

## Six checks the composition turned green

| check | bare | composed |
|---|---|---|
| `type_system.type_system_content_blob_fetch` | WARN *(absent)* | **PASS** `fetched system/type/system/content/blob` |
| `type_system.type_system_content_blob_match` | WARN | **PASS** `content hash match` |
| `type_system.type_system_content_chunk_fetch` | WARN | **PASS** |
| `type_system.type_system_content_chunk_match` | WARN | **PASS** `content hash match` |
| `type_system.type_system_content_descriptor_fetch` | WARN | **PASS** |
| `type_system.type_system_content_descriptor_match` | WARN | **PASS** `content hash match` |

**`content hash match` is worth being precise about, in both directions.**

What it is: the oracle rendered `system/content/{blob,chunk,descriptor}` from **its own**
transcription of §2.1/§2.2/§2.4, in an independent Go codebase, and the content hash equalled ours.
Two independent readings of the spec produced byte-identical ECF. That is the *ECF byte-equality
surface* §3.6.5 names as a place where disagreement "breaks cross-peer dedup silently" — exercised,
and agreeing.

What it is **not**: cross-impl convergence on chunking. Nothing here ran a chunker. It is agreement
on the *type definitions*, by **two** readings — not N, and not a vector set. And our renderer is
the keystone peer's own `TypeDef`/`FSpec` builder, chosen deliberately (`types.ts`), so what the
comparison isolates is the transcription, not the encoder.

## What is NOT measured, and stays unmeasured

- **`frame-limit-respected`** — the Amendment 1 §6.2 MUST. Skipped for want of a `local/files`
  root. We implement it and test it in-process (`test/handler.test.ts` pins the CONNECTION's budget
  at 8 KiB against a peer whose default is 16 MiB, so a hardcoded literal would answer identically
  twice and be caught). **An in-process test is not the behavioural check, and this line is not a
  claim that it would pass.**
- **The whole SDK face.** No gate anywhere, by design — the SDK is a convention. `EXTENSION.toml
  [sdk]` records per operation which check reaches it; `AtPeer` and `reassembleUnderCapability`
  have empty `reached_by` and are genuinely unmeasured.
- **Namespace-scoped topology (§6.4.2 Hash Tree Presence).** Not implemented. This composition runs
  single-trust-domain, which §6.4.1 makes opt-in and restricted — declared in `EXTENSION.toml
  [assumptions].topology`, not assumed.
- **FastCDC cross-impl convergence.** Our unit tests pin the gear table against an independent
  derivation and pin edit-stability, which catches *our* mistakes. They say nothing about anyone
  else's. §3.6.5's vectors do not exist yet.

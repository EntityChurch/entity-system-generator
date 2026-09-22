# CONTENT — authoring notes

**Internal.** Readings taken, ambiguities logged, assumptions carried. Written while emitting the
`typescript` port on 2026-09-05, against snapshot `content-v3.6`
(`EXTENSION-CONTENT.md` sha256 `4bf4a43bd7b99adf20cb989581743348bbf8edf9c2a64f52a03764ddca03c5af`).

This is the file the second and third language ports read before they start. It is not a summary of
the spec — read the spec — it is the record of every place the spec did not decide for us and what
we did instead.

---

## 1. Readings that changed the code

### 1.1 `system/content/*` cannot be installed over the wire, and that is structural

CONTENT's pattern is `system/content`. The peer's `system/handler:register` operation refuses it:
core §6.2, *"user-installed handlers MUST NOT register at `system/*` paths"*, enforced in both
tier-A peers (typescript's handlers-handler and python's `_is_reserved_system_pattern`).

So `[install] model = "sdk-native"` is **forced, not chosen** — in-process, against a live peer
object. **Every extension that owns a `system/*` pattern inherits this**, which is most of the 26.
The consequence for the generation model: there is no "install a peer remotely" story for the
standard corpus, and a composition is a build-time artifact rather than a runtime one. Worth
knowing before designing anything that assumed otherwise.

### 1.2 §6.1's manifest block spells the pattern two ways

The code block says `pattern: "system/content/*"`. The prose two lines below says *"Manifest at
pattern path `system/content`. Index entry at `system/handler/system/content`."* The `/*` is the
**capability-scope** spelling used in §6.4's grant examples (`handlers: {include:
["system/content/*"]}`), not a binding path — binding at a literal `.../*` would put a `*` segment
in the tree.

We publish `system/content`. The prose, the index path and the oracle all agree on it. Not routed:
the document answers itself if you read four more lines. Recorded because the next port will hit
the same block.

### 1.3 §6.3's `if envelope.root is not null` branch is unreachable

The ingest algorithm guards `if envelope.root is not null`, then computes
`root_hash = content_hash(envelope.root)` unconditionally — which would fault on the null it just
guarded. But `system/envelope` extends `core/envelope`, whose `root` is a **required**
`core/entity`, so a well-formed envelope always has one.

We answer `400` for an envelope with no root, rather than an `ingested_count: 0` success. Not
routed: the type declaration already decides it.

### 1.4 A zero-length blob has an empty chunk list

`create_blob` / `create_blob_cdc` are `while offset < length(raw_bytes)` loops, so zero-length
input produces `total_size: 0, chunks: []`. That is internally consistent with §3.3 (the total of
no chunks is 0), and §3.3's `empty_chunk` guard is about a chunk whose *payload* is empty, which is
a different thing. The spec says neither way. Carried as written; logged.

### 1.5 `pending` is omitted, not emitted empty

§6.2 Amendment 2's `pending` sidecar is OPTIONAL and SHOULD be populated only by an implementation
with **sync-state visibility** — an active subscription on the namespace plus an inbox feeding the
content store. This composition has neither. §6.2 says a receiver that omits it is telling the
caller to treat all `missing` as terminal, which is the truth here.

Emitting `pending: []` would have been the reflex, and it would have **advertised a capability we
do not have**. The distinction is load-bearing: `absent` and `empty` mean the same thing to §6.2's
mapping table, but a future reader diffing two peers would read an empty array as "supports
sync-state, nothing pending".

### 1.6 `path_required` is 400, and nothing upstream checks that

§6.2/§6.3 make it a MUST; `GUIDE-EXTENSION-DEVELOPMENT` §171 pins the status at **400**. The
oracle checks only the error **code** (`content.go`, `errData.Code != "path_required"`), so a peer
answering `404 path_required` passes the gate and fails the spec. Our test asserts the status as
well as the code. *(That pin was this repo's own routed finding —
`PROPOSAL-PIN-THE-PATH-REQUIRED-STATUS`, landed.)*

---

## 2. Facts about the substrate that the generator has to model per language

Every one of these was **measured**, by `gates/host-seam/probe-seam.mjs` /
`probe-seam.py` or by the build itself. None is a source read.

| | `typescript` | `python` |
|---|---|---|
| registration surface | `registerHandler(handler)` | **none.** The caller assembles `store.bind` × 4 + `mint_token` |
| §11.6.1 writes it performs | handler entity · interface · grant · signature | n/a — all of them are the caller's |
| type entities written | **none** — the module must publish all 7 | none |
| operation input/output types expressible | **no** — `Handler.operations` is `readonly string[]` | yes (the caller writes the interface entity itself) |
| peer reachable from the handler body | `ctx.peer` (tree, contentStore, emit, frame budget) | **no** — `DispatchCtx` is exec/conn/included/caller_cap/has_cap; capture the peer at registration |
| URI suffix in the context | `ctx.suffix` | **no** — re-derive from `ctx.exec.uri` |
| connection frame budget | `ctx.frameBudget()` | **nothing carries one** (see §3.1) |

**The shape of the per-language adapter is now visible, and it is bigger than "call
`registerHandler`".** The install adapter is ours in both languages; what differs is how much of it
the peer already does. A template that assumed a registration method would have been written
against `typescript` and would not have retargeted.

---

## 3. Routed, one line each

Findings our own build turned up. Routed and then dropped — another repo's queue is not ours to
track.

### 3.1 → keystone: CONTENT's Amendment 1 §6.2 MUST is unimplementable on the `python` peer

Nothing on `Conn`, `DispatchCtx`, `Peer` or `Store` carries a frame budget; `wire.MAX_FRAME` is a
module constant equal to 16 MiB — **the exact literal the amendment names as the wrong answer**.
`typescript` has `ctx.frameBudget()` reading `connection.maxFrameBytes`. Measured:
`gates/host-seam/probe-seam.py`.

### 3.2 → keystone: `Handler.operations` cannot express operation input/output types

`readonly operations: readonly string[]` renders `{get: {}, ingest: {}}`, so §6.1's manifest cannot
be published through `registerHandler`. `installContent` re-writes the interface entity afterwards
through `peer.tree.put`. Changes no conformance number today — the oracle checks key presence only.

### 3.3 → keystone: the `typescript` client API discards `envelope.included` from a response

`PeerSession.execute` returns `new ExecuteResponse(response.root)` and drops the envelope
(`transport/peer-session.ts`). The **server** side is correct — `dispatcher.ts` returns
`new Envelope(response.entity, result.included)` — and the Go oracle reads `env.Included`, so
conformance is unaffected. But §6.2's whole wire contract is *"the fetched entities are delivered
via the response envelope's `included` map"*, and a consumer written against this peer's own client
surface **cannot receive content**. It is why `test/handler.test.ts` asserts the `included` half
in-process.

---

## 4. Mistakes we made here, so the next port does not

### 4.1 The chunker test's corpus was the defect

The edit-stability test failed against a **correct** FastCDC. The generator was a textbook LCG,
`x = (x * 1103515245 + 12345) >>> 0` — wrong in JS, because the product exceeds 2^53 and the float
multiply loses the low bits before the truncation. The stream had 256 distinct byte values and no
short period, so every cheap check said "random", but its low bits never satisfied `fp & mask_s`.
Every chunk ran to the forced `max_size` boundary, FastCDC degenerated into fixed-size chunking at
2× the target, and edit-stability vanished.

**A chunker test is only as good as its corpus, and "the test data was the defect" is a failure
mode a passing suite never reports.** Switched to xorshift32 (8/8 boundaries realign). The
degenerate stream is kept as its own test, because content that never satisfies the mask is real
and the resulting blob is perfectly conformant while being worthless for dedup.

### 4.2 Two staleness gates, both written wrong the first time

`languages/typescript/build`'s peer-freshness check compared `find src -newer dist` — against the
*directory's* mtime, which only updates when an entry is added or removed. It red-flagged a peer
whose `dist/` was ten minutes **newer** than its `src/`. Fixed to newest-file vs newest-file, which
is what the probes already did. **A staleness gate that fires on a fresh build is worse than none:
the next person adds `|| true`.**

`tools/diff-arms.py` was written against a nested `categories[].checks[]` report shape; the real
one is a flat `checks[]` list with `severity`. Its own "parsed 0 checks, refusing to report a clean
diff" guard caught it on the first run — an empty diff would have read as "no regressions".

### 4.3 The export-surface test could not have run as first written

`await assert.rejects(() => import("@entity-core/extension-content/internal/reassemble.js"))` —
written as a literal, `tsc` resolves the specifier at compile time, fails TS2307, and the build
dies before the assertion runs. **The check passing and the check being unrunnable look identical
from the outside.** The specifier is now assembled at runtime so *node* is the layer that refuses,
which is the layer the §3.4 MUST is about.

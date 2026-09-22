# CONTENT — authoring notes

**Internal.** Readings taken, ambiguities logged, assumptions carried. Written while emitting the
`typescript` port on 2026-09-05, against snapshot `content-v3.6`
(`EXTENSION-CONTENT.md` sha256 `4bf4a43bd7b99adf20cb989581743348bbf8edf9c2a64f52a03764ddca03c5af`).

**Re-pinned to `content-v3.7` on 2026-09-06** (`2a40b22b859b2a74f7de4d1c43b4655cb6ece2b791d7769f27fcc87efa65ee87`).
**The v3.6 attribution above is left standing on purpose** — it is where these readings were
*taken*, and rewriting it would claim they were re-derived against a document that did not exist
yet. What the re-pin changed is one behaviour (§6.4's 403 code) and one new document (Appendix A);
neither invalidates a reading below. See `shared/spec-data/content-v3.7/MANIFEST.md` for the
38-line diff and what it cost.

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

## 2. The substrate model — three peers, measured, not extrapolated

Every row was **measured**, by `languages/typescript/gates/host-seam/probe-seam.mjs` / `probe-seam.py` /
`rust/probe-seam-rust.sh` or by the build itself. None is a source read.

**Two columns were an extrapolation wearing a table, and the third column says so.**
`typescript` and `python` are both dynamic, both interpreted-or-JIT, both duck-typed at the
seam — so every row they agreed on was a row about *that paradigm*, not about substrates.
`rust` is AOT, statically typed, and has no post-construction install at all. Three of the
rows below invert or gain a third value at that column, two are demoted from "the invasive
difference" to "the common case", and one addition (§2.0) is not a row at all but a fact
about the shape of the table.

### 2.0 The finding that reframes the rest: the faces do not move together

| face | `typescript` | `python` | `rust` |
|---|---|---|---|
| types (§11.1) | installed | installed | **installed** |
| emit consumer (§6.13(c)) | available | available | **available** |
| SDK (§3.3/§5.3/§3.4) | usable | usable | **library-only** |
| handler body (§11.6.1 step 4) | installed | installed | **NOT INSTALLABLE** |

On the first two peers all four faces were available, so *"CONTENT installs"* was
unambiguous and a per-peer host state was adequate. **It is not adequate. The right
granularity is per (peer × face)**, and the reason the first two ports could not show it is
that neither ever had one face answer differently from another.

Measured, both arms, over real loopback TCP:

```
A. nothing bound at system/content        404  handler_not_found
B. all four §11.6.1 tree writes bound     501  no_handler_body
C. the same body called DIRECTLY          200  witness=<nonce>:<request field>
   invocations: before=0  after dispatch=0  after direct=1
```

and — because on an AOT substrate *"is the symbol there"* is a question for the compiler and
not for a running program — four claims each producing its own error, with a positive
control that MUST compile in the same invocation:

```
error[E0624]: method `register_handler` is private
error[E0609]: no field `handlers` on type `Peer`
error[E0603]: struct `Outcome` is private
error[E0624]: method `resolve_handler` is private
```

**The composition's most important line is the one it does not write.** Binding those four
tree writes is entirely possible — they are ordinary `store.bind` calls — and it would move
the peer from `404 handler_not_found`, which is true, to `501 no_handler_body`, which says a
handler exists and is broken. `tools/compose.py` drops the pattern from the plan when
`[system.faces].handler = "not-installable"`, so the wiring program that would do it cannot
be generated.

### 2.1 The install seam

| | `typescript` | `python` | `rust` |
|---|---|---|---|
| registration surface | `registerHandler(handler)` | **none.** `store.bind` × 4 + `mint_token` | **none, and not in `python`'s sense** |
| §11.6.1 writes it performs | handler entity · interface · grant · signature | n/a — all the caller's | n/a — and the fifth step has no destination |
| type entities written | **none** — the module publishes all 7 | none | none |
| op input/output types expressible | **yes**, as of 2026-09-06 (was names-only; K-2) | yes — the module writes the interface entity | moot: nothing consumes a manifest |
| install-adapter steps | 2 | **6** | **1** (types) — the other five are unreachable |

**`python` and `rust` both read "none" and they are not the same fact.** On `python` the
caller performs all four writes *and* binds a body into a container dispatch consults. On
`rust` the first four are performable and the fifth has nowhere to go at any visibility. A
generator reading a single `registration_surface = "none"` column would treat them the same
and emit a six-step adapter for a peer that cannot use step six.

The `typescript`/`python` asymmetry still holds and is still counter-intuitive: on `python`
the module always wrote its own interface entity, so it never carried the K-2 workaround at
all — the port that *had* a registration API was the one with the narrower manifest. "Richer
registration surface ⇒ less work for the extension" is backwards.

### 2.2 The handler context

| | `typescript` | `python` | `rust` |
|---|---|---|---|
| body protocol | `handle(ctx): Promise<HandlerResult>` | `handle_op(op, ctx) -> Outcome` (duck-typed) | **ours** — there is no protocol to conform to |
| context type | `ctx` | `DispatchCtx` | **none.** `(&mut Conn, &Envelope)`, passed to private code |
| peer reachable from the body | `ctx.peer` | **no** — capture at registration | **no** — capture at registration |
| URI suffix in the context | `ctx.suffix` | **no** — re-derive from `ctx.exec` | n/a |
| operation in the context | `ctx.operation` | first argument | first argument |
| connection frame budget | `ctx.frameBudget()` | `ctx.frame_budget()` (K-1) | `wire::MAX_FRAME` — a **public const**, not configurable |
| entity wire size | `entity.wireBytes.length` (retained, §1.8) | **re-encode** | **re-encode** |
| outcome type | the peer's | the peer's | **ours** — `Outcome` is private (E0603) |

Two rows are worth extracting.

**`ctx` carrying no peer was called "the single most invasive difference" at two columns,
and the third column demotes it.** It changes signatures rather than bodies —
`reassemble_under_capability(ctx, blob_hash, store)` takes a store on `python` and does not
on `typescript` — and `rust` agrees with `python`, so it is now 2 of 3 and reads as the
common case rather than the exception. **The genuinely invasive difference is the "context
type: none" row**, which does not change a signature; it removes the possibility of one.

**"Re-encode to get the wire size" is also 2 of 3**, which retires it as a `python` quirk.
Only `typescript` retains original bytes (§1.8 forward-original).

### 2.3 The packaging boundary — one MUST, two clauses, and they invert

| | `typescript` | `python` | `rust` |
|---|---|---|---|
| boundary object | `exports` map in `package.json` | convention | **the crate: `mod internal;` with no `pub`** |
| enforced by | **node**, at resolve time | **nothing** | **rustc**, at compile time |
| §3.4 **clause 1** (do not expose it) | ENFORCED | CONVENTION ONLY | **ENFORCED BY THE COMPILER — strongest** |
| §3.4 **clause 2** (capability-checking wrapper) | dispatcher-anchored | dispatcher-anchored | **crate-anchored only — weakest** |
| what the check asserts | the module resolver's refusal | the convention holds **and can be walked around** | a compile that must FAIL (`E0603`), with a control that must compile |

**§3.4 is two clauses and they do not move together.** At two columns that was invisible,
because on both peers the dispatcher's context type was reachable, so clause 2 was free and
only clause 1 varied. Here `rust` is the strongest port on clause 1 and the weakest on
clause 2 — there is no dispatcher-built value to demand, so `DispatchAuthority` is
unforgeable and proves only *"you came through this crate's handler"*, not *"the dispatcher
authorized you"*.

`EXTENSION.toml` now carries `[substrate.export_boundary]` and
`[substrate.capability_wrapper]` as separate blocks. **Reporting one verdict for two
requirements that invert between substrates is the D13 error one level up**: not two
boundaries read as one, but two MUSTs.

### 2.4 The toolchain

| | `typescript` | `python` | `rust` |
|---|---|---|---|
| build | `tsc` × 2 | **no compile step**; stage + an import check | `cargo` × 2 — cells to rlibs, then a linked host binary |
| build-time signal | full typecheck | "does every staged package import" | full typecheck **and a link** |
| staleness gate | **required, hand-written** — it links a build artifact | **absent, deliberately** — the source is the artifact | **required, and the TOOLCHAIN'S** — cargo fingerprints across the path dep |
| `--profile core` cost | ~35 s / arm / round | ~35 s / arm / round | **~2.5 min** / arm / round |

The staleness row is the useful one. `typescript`'s gate is hand-written and was **written
wrong the first time** (AP-4: it compared `find src -newer dist` against a *directory's*
mtime and red-flagged a peer whose `dist/` was ten minutes newer than its `src/`).
`python` has none, deliberately, because writing one would be a check that can never fail.
`rust` has one and it is not ours: re-deriving cargo's fingerprinting would be a second
implementation of a mechanism the toolchain already owns, and it would be the one more
likely to be wrong. **Across three substrates the right number of hand-written staleness
gates turned out to be one, and it is the one that has already had a defect.**

### 2.5 What the third column did to the table itself

Three columns is where a substrate model stops being a list of differences and starts being
a claim about which differences *generalise*. On the rows that had two values before:

- **three inverted or gained a third value** — the §3.4 clauses, the frame budget
  (`satisfiable` / `satisfiable` / *satisfied-degenerately*), and the install seam's
  "none", which turned out to be two different facts wearing one word;
- **two were demoted from "the invasive difference" to "the common case"** — no peer in
  the context, and re-encoding for wire size, both now 2 of 3;
- **one row was added that is not a difference between languages at all** (§2.0, the
  faces), and it is the one that changes what a `[host]` roster column can mean.

That ratio is the argument for having done the third port. It is also the argument against
generalising from three.

## 3. Routed, one line each

Findings our own build turned up. Routed and then dropped — another repo's queue is not ours to
track.

### 3.1 → keystone: CONTENT's Amendment 1 §6.2 MUST is unimplementable on the `python` peer

**CLOSED 2026-09-06, verified by our own instrument.** Nothing on `Conn`, `DispatchCtx`,
`Peer` or `Store` carried a frame budget; `wire.MAX_FRAME` was a module constant equal to
16 MiB — **the exact literal the amendment names as the wrong answer**. keystone landed
`Peer(seed, max_frame_bytes=N)`, a `Conn.max_frame_bytes` stamped by the transport, and
`DispatchCtx.frame_budget()`.

**And re-measuring it forced an upgrade to the probe, which is the part to remember.** The
original check searched for an attribute whose *name* matched `frame` and
`max|limit|budget|bytes`. It went green the day the fix landed — correctly — and **could not
have gone red** for a peer that stamped the 16 MiB constant onto every connection and named
the field `max_frame_bytes`. The name is not the property. The probe now configures the peer
to enforce 3,145,749 and asserts the body reads back 3,145,749, with a negative-control arm
that builds the peer unconfigured and asserts the body reads 16,777,216 and that the scoring
rejects it. D15, applied to our own instrument the session after ratifying it.

### 3.2 → keystone: `Handler.operations` cannot express operation input/output types
**CLOSED 2026-09-06, and their version of the finding was sharper than ours.**

`readonly operations: readonly string[]` renders `{get: {}, ingest: {}}`, so §6.1's manifest cannot
be published through `registerHandler`. `installContent` re-writes the interface entity afterwards
through `peer.tree.put`. Changes no conformance number today — the oracle checks key presence only.

### 3.3 → keystone: the `typescript` client API discards `envelope.included` from a response
**CLOSED 2026-09-06, and it was bigger than we reported.**

`PeerSession.execute` returns `new ExecuteResponse(response.root)` and drops the envelope
(`transport/peer-session.ts`). The **server** side is correct — `dispatcher.ts` returns
`new Envelope(response.entity, result.included)` — and the Go oracle reads `env.Included`, so
conformance is unaffected. But §6.2's whole wire contract is *"the fetched entities are delivered
via the response envelope's `included` map"*, and a consumer written against this peer's own client
surface **cannot receive content**. It is why `test/handler.test.ts` asserts the `included` half
in-process.

---

### 3.4 → keystone: the `rust` peer's frame bound is a public const with no way to configure it

**Open, routed 2026-09-06. Deliberately NOT the K-1 packet, and the difference is the
point.**

`wire::MAX_FRAME` is `pub const MAX_FRAME: usize = 16 * 1024 * 1024` — the exact literal
CONTENT Amendment 1 §6.2 names as the wrong answer — and `read_frame` enforces it. But it is
`pub`, and it is the *only* bound the peer enforces, so a handler body reading it reads the
number in force. **The MUST's purpose is met and its mechanism has nothing to configure**:
`CreateOptions` carries `seed` / `open_grants` / `conformance` and no frame field, and `Conn`
carries no budget.

So the ask is *"make it configurable"* — `Peer::create` taking a bound, stamped onto `Conn`
by the transport, exactly the shape they landed on `python`. It is **not** *"this is
unimplementable"*, which is what K-1 said, and the distinction matters: on `python` the body
could not see the number at all. Filed as a lower-priority packet for that reason.

**And per AP-5, the search was run rather than a call site named.** Every occurrence in the
crate, and the command that prints it:

```
$ grep -rniE "max_frame|frame_budget|16777216|16 \* 1024" src/ | wc -l
3
src/peer/wire.rs:17   pub const MAX_FRAME: usize = 16 * 1024 * 1024;
src/peer/wire.rs:24   /// Length prefix exceeded [`MAX_FRAME`] -> maps to 413 payload_too_large.
src/peer/wire.rs:57   if len > MAX_FRAME {
```

Three sites, one file, one constant. There is no second definition and no per-connection
copy — which is also why this is a small change rather than a sweep.

### 3.5 → keystone: `rust` hosts the emit face and not the handler face

**Open, routed 2026-09-06.** Not a defect report; a measured `[extension_host]` row they do
not have. Their profile blocks exist on `typescript` and `python` only, and the other 44 read
`unknown` — their rule and the right one.

What we measured, with controls, is in §2.0. The part worth their attention is that **one
peer gives two different answers for two faces of one extension**, so the `[host]` axis they
are carrying as a per-peer profile value will need a second dimension before it can describe
this peer. `Store::register_tree_consumer` is public, is consulted by `bind`/`unbind`, and
fires with a witness we derived — while `register_handler` is private, `Peer.handlers` does
not exist, and `Outcome` is private.

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

### 4.4 We reported one site and there were three

K-3 was routed as *"`PeerSession.execute` discards `envelope.included`"*. True, and
incomplete: the same defect sat on `OutboundDispatchImpl.execute` and on
`ExecuteResponse`'s own constructor. keystone found the other two.

**The shape, in their words and worth keeping:** *a peer offers two surfaces for one
operation, and the oracle drives exactly one of them — the other is the one an extension host
is told to use.* The oracle is a wire client. It never constructs the peer's `Handler` type
and never reads a response through `ExecuteResponse`, so a defect in either sits outside
`--profile core` by construction. Both fixes moved **zero** conformance checks.

**What we did wrong is narrower than that and is ours:** we reported the site our test
happened to touch, as though it were the finding. A routed packet naming one call site should
say *"at least here"* unless the search for others was run and can be cited. That is now the
first line of the routing template.

### 4.5 A test that asserted the layer, not the behaviour

`test_an_empty_targets_list_is_treated_as_absent` asserted that `{targets: []}` returns
`400 path_required`, because that is what our handler's `_resource_targets` does with it. Over
the wire it returns **`403 capability_denied`**: `check_permission` runs before dispatch and
refuses the malformed resource first, so the handler's branch is never reached.

The handler's branch is kept — it is still right for an in-process dispatch, which has no cap
check in front of it — and the test now asserts the measured behaviour with the difference as
its subject. **A test written from the implementation's intent rather than from the wire will
pass or fail for reasons that have nothing to do with the contract**, and this one failed for
the useful reason on its first run.

### 4.6 An inherited environment variable beat our own default, and only one driver noticed

`languages/rust/{build,test,host-launch}` each wrote
`export CARGO_HOME="${CARGO_HOME:-$ROOT/output/.cargo-home}"`. The toolchain image declares
`ENV CARGO_HOME=/cargo`, so the `:-` default **never fired** and every driver used the
image's path.

**`build` and `test` worked anyway, and that is the whole lesson.** They *write* the offline
vendor config before reading it, so inside one container they wrote it to `/cargo` and read
it straight back. The defect was invisible until `host-launch` ran in a *fresh* container —
`podman run --rm`, so `/cargo` was empty again — and tried to read a config nobody in that
container had written. It failed as:

```
error: no matching package named `ed25519-dalek` found
location searched: crates.io index
```

which reads as a missing crate, or a broken vendor mirror, or an offline-mode quirk. It is
none of those. **A value this repo declares was set in two places and the one that won was
not ours**, which is the drift D14 is about, arriving through an environment variable rather
than through a document. All three drivers now set it unconditionally, and the two that only
read the config refuse when it is absent instead of letting cargo produce a misleading error.

The generalisable bit: **a script that both writes and reads its own configuration cannot
detect that it is writing to the wrong place.** Two of our three drivers were in that
position, and the third — the one that only reads — is the only one that could ever have
found it.

### 4.7 The corpus was wrong again, in a new way, and the assertion caught it

`identical_chunks_dedup_in_the_content_store` was written with a 20,000-byte input and failed
at "4 of the first blob's 5 chunks". **The code was right.** Under §3.2 fixed-size chunking a
20,000-byte input ends in a 3,808-byte partial chunk, and in the doubled input those same
bytes fall inside a full 4,096-byte chunk — different payload, different hash, no dedup, and
nothing wrong.

Not the same defect as AP-3, where the corpus could not exercise the branch at all. Here the
corpus exercised it correctly and the *expectation* was arithmetic nobody had done. Two
outcomes, both kept: the dedup assertion now uses an aligned length and asserts **all ten**
chunks are shared, plus a negative control that unrelated content shares **zero**; and the
unaligned case is its own named test asserting exactly `len - 1`, because a partial tail
failing to dedup is a real property of §3.2 and is one of the reasons §11.2 SHOULDs FastCDC.

**A chunking test that passes on the first run is the one to distrust.** Both ports that
have had one have had it fail first, for a different reason each time.

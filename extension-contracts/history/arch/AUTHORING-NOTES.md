# HISTORY — authoring notes

**Internal.** Readings taken, ambiguities logged, assumptions carried. Written while
emitting the `typescript` port on 2026-09-06 against snapshot `history-v1.7`
(`EXTENSION-HISTORY.md` sha256
`5980bdc96d4818edbc43dd73a1152292e306f126e62d5e4d007ca48bd5fa850b`), and completed on
2026-09-07 when the third port landed.

This is the file the second and third language ports read before they start. It is not a
summary of the spec — read the spec — it is the record of every place the spec did not
decide for us and what we did instead.

**Its CONTENT twin is `../../content/arch/AUTHORING-NOTES.md`.** Where a row here is
identical to a row there, it says so and does not repeat the argument: two extensions
agreeing about a peer is a fact about the peer.

---

## 1. Readings that changed the code

### 1.1 The spec has no §3.3 declaration header, and it stopped nothing

`EXTENSION-HISTORY` is one of the 24 specs without GUIDE-EXTENSION-DEVELOPMENT §3.3's
declaration header. CONTENT has one, so its `[contract]` is a *projection of a
declaration*; here it is **derived**.

**A missing summary is not a missing fact**, and the temptation to treat it as a blocker
is the one the next 23 specs will present. §9.2 is an explicit six-entry list of installed
types. §9.3 is the handler manifest. §3.1 and §6.1 name the namespaces. §5.1 plus
SYSTEM-COMPOSITION §2.2 give the consumed hook. All of it derivable, all of it citable,
all of it checkable against a pinned digest.

So `EXTENSION.toml` carries `[contract.derived_from]` — every field, naming the section it
was read out of — and **the two fields that are readings of ABSENCE say so inline**:
`points_exposed` and `owned_kinds`. That is the entire cost of the missing header, and it
is written down rather than smoothed over, because a derivation presented as a
transcription is the failure that block exists to prevent.

The filled-in header went to arch as a **draft**, not as a request (`A-5`).

### 1.2 The self-guard is narrower than the namespace, on purpose

§3.2's `is_local_history_path` guards `system/history/head`, **not** `system/history/`.
§3.2 says why: config paths "are handler-written via explicit EXECUTE and do not create
recursion risk — they SHOULD be recorded as normal transitions for audit purposes."

Guarding the whole namespace is the natural reflex, it is one character cheaper, and
**nothing would fail**. Config-change auditing would silently stop. There is no constant
named `HISTORY_NAMESPACE` in any port, deliberately, so the wrong thing is not to hand.

Second load-bearing property: **it is LOCAL-ONLY.** A remote peer's `system/history/…`
arriving via sync is ordinary tracked content; the head pointer it produces lands at
`/{local}/system/history/head/{remote}/…` and is excluded by the same check, so there is
no recursion. Every port asserts both directions.

### 1.3 §2.2's pattern TABLE and §2.2's pseudocode disagree, and the pseudocode is silent

The table lists a leading-star pattern meaning "that subtree in any peer's namespace". The
pseudocode passes it through unchanged. **Core §5.4 rejects that spelling** — `canonicalize`
errors on a leading `*/`, and `matches_pattern` recognises a peer wildcard only as
`/*/rest`.

So a config written the pseudocode's way is well-formed, stored, resolvable, and **matches
nothing at all**, with no error anywhere. We implement the table: `*/rest` → `/*/rest`.
Every port's test asserts the normalised form matches another peer's path **and** that the
un-normalised form matches nothing — the second arm is the control, without which the test
passes for any implementation that happens to be permissive. Routed as `A-3`.

### 1.4 The enabled check belongs to the caller, and that changes which config wins

§6.2's `find_history_config` returns the most specific MATCHING config. §5.1 separately
tests `config is null or not config.data.enabled`.

**Folding the `enabled` test into the lookup would change the answer.** A specific
`enabled: false` must SHADOW a general `enabled: true`, or "turn history off for this
subtree" cannot be expressed at all. That is not stated in §6.2 and it is the only reading
under which the `enabled` field is useful. Carried in `[assumptions]`; asserted in every
port.

### 1.5 `transitions` carries data maps inline, and §2.4 does not settle it

§2.4 types the field `array_of: {type_ref: "system/history/transition"}`, which admits
three readings — hashes, entity wrappers, or inline data maps. A `system/hash` field
elsewhere in the same type is also a reference to an entity.

**The oracle settles it.** `HistoryQueryResultData` is `Transitions []TransitionData` and
it decodes elements straight into the field struct. A hash array decodes as nothing; an
array of `{type, data}` entity maps decodes as a struct with every field zero — which
**passes** `transition_recorded` (the array is non-empty) and fails
`transition_event_created` four checks later. The wrong reading does not fail where you
made it.

### 1.6 `not_in_history` is defined in no code set, and it guards §7.5

§4.3.2's algorithm names it directly — `return error(404, "not_in_history", …)` — so unlike
`path_required` there is no ambiguity about what to emit. What is missing is a **table**:
HISTORY has no Appendix A, so under core §3.3's default-code force the string is a
more-specific 404 that no spec code set defines, and §3.3's 404 default is
`handler_not_found`, which would be actively wrong.

**§7.5 is why this matters more than most.** It is the refusal that stops rollback being an
unrestricted write primitive; a caller has to tell it apart from a storage failure, and a
code nothing defines is a code an implementation may spell differently. Routed as `A-1`,
with `[error_surface]` as the proposed content of the appendix.

### 1.7 A walk bound that is not in the spec

§2.3's `limit` defaults to 50, is caller-supplied, and is unbounded above; §4.3.1's loop
walks until the chain ends. A caller asking for `limit: 2^53` materialises the whole chain.

Every port caps at 1000 and **declares it**, because it changes an observable answer —
`has_more` goes true earlier than a naive reading of §4.3.1 produces. A cap nobody declared
is the kind of local decision this repo does not get to make quietly.

---

## 2. The substrate model — three peers, measured, not extrapolated

Same five axes as CONTENT's §2, plus two that only HISTORY reaches. **Rows identical to
CONTENT's are marked `= CONTENT` and not re-argued.**

### 2.0 The finding that reframes the rest: the write face and the read face

CONTENT's §2.0 established that an extension's four faces do not move together on one peer.
HISTORY is the case that shows what that costs when the faces that install are the ones
that do the work.

| face | `typescript` | `python` | `rust` |
|---|---|---|---|
| types (§9.2) | installed | installed | **installed** |
| emit consumer (§5.1) | installed | installed | **installed, and it RUNS** |
| handler (§4.3) | installed | installed | **NOT INSTALLABLE** |
| SDK | installed | installed | library-only |

**On `rust` the extension works and nothing outside it can see that it does.** The peer
accumulates a real, correct, content-addressed audit chain at `system/history/head/*`;
every §4.3 read path is an operation on the handler that cannot exist; and the oracle's
`history` category therefore scores **7 of 34** against a recorder that is correct.

That is not a limit on the extension. It is a limit on what can be MEASURED about it, and
it needed a new kind of `[substrate]` row to say so — `[substrate.oracle_read_path]`.
CONTENT could not have produced it: there, the un-installable handler meant the extension
did nothing at runtime, so *"can't install"* and *"can't measure"* were the same sentence.

### 2.1 The emit seam — and whether it is RE-ENTRANT

**The row HISTORY needed and CONTENT never asked for.** §5.1's recorder writes a transition
and advances a head pointer **from inside the callback**, so "can a consumer be registered"
is not the question.

| | `typescript` | `python` | `rust` |
|---|---|---|---|
| registration | `EmitBus.registerConsumer` (appends) | `store.register_tree_consumer` | `Store::register_tree_consumer` |
| re-entrant write from the callback | yes | yes | **yes — measured, behind a timeout** |
| position argument | **none** | **none** | **none** |

On `rust` this was a question about a lock, not about a hook: `Store::fire` holds
`consumers.read()` across the callback, and a `bind` from inside re-enters it —
`std::sync::RwLock::read` documents a possible panic, and the futex implementation is
writer-preferring. **Reading `store.rs` could not settle it, and a probe that simply called
`bind` would have HUNG rather than reported.** `gates/host-seam` arm G runs the write on a
worker thread behind a `recv_timeout`, which turns a deadlock into a measured NO instead of
a stalled gate. The seam held, and the head write's own event comes back to the guard
**exactly once** — which is what makes §3.2's guard sufficient rather than conventional.

**None of the three peers takes a consumer position**, and SYSTEM-COMPOSITION §2.2 fixes
nine. Three mechanisms, one absence.

### 2.2 The execution context — the row that decided the extension's shape

**No peer delivers one.** §2.1 makes `author` and `capability` non-optional and §9.1 MUSTs
them; §5.1 says they arrive with the tree-change event.

| | state |
|---|---|
| `typescript` | `EmitContext` declared with almost exactly §1.4's inventory, **constructed at zero sites** |
| `python` | event is `(event_type, path, new_hash, previous_hash)`; `frozen+slots`, no slot |
| `rust` | event is the same four `pub` fields; there is no fifth |

Every transition on every port records §2.1's **autonomous-case** values, which is the
reading the spec supplies for "no external request" — and which is **wrong about the
world** for a write that arrived over the wire. §7.2 calls `capability` the answer to
"under what authority?", and the answer is always "its own".

**Four oracle checks pass on that**, and they are presence checks over values we fabricate.
So: a `provenance` field outside the spec-declared entity (adding a field to
`system/history/transition` would move its content hash away from every other
implementation's), `context_available=false` on the composition's `COMPOSED` line, and a
unit test that asserts the fallback **FIRES** — so the day a context arrives, that test
fails and says so. Routed as `H8`.

**A probe is the wrong instrument for an absence at the type level**, which is why none was
written — and claiming one had been is D18's first incident.

### 2.3 The handler grant — the row the third port added

§2.1's autonomous `capability` is *"the handler grant"*, and the second bullet has no
referent on one peer.

| | what an extension can use |
|---|---|
| `typescript` | the grant `registerHandler` bound, read back from the tree |
| `python` | `peer.mint_token(...)` is public; keeps the token it minted |
| `rust` | **nothing.** `impl Peer` has two `pub fn`: `create` and `dispatch` |

So on `rust` **`author == capability` on every transition** — a step weaker than the other
two ports' fallback, which is already a fabrication. There, `capability` is a real grant
merely used for the wrong write; here it is not a grant at all. Declared at the seam
(`handler_grant_available`), printed by the host, and recorded in the composition. Routed
as `R-4`.

### 2.4 §4.2's dual check, and the primitive that exists on one peer

§4.2 names core's `check_path_permission` (§6.3) for its second check.

| | |
|---|---|
| `typescript` | `Permissions.checkPathPermission(...)` is public and is exactly §4.2's primitive |
| `python` | **absent.** Scope helpers are all leading-underscore |
| `rust` | **absent.** Scope helpers carry no `pub` at all (rustc, not convention) |

Two of three ports synthesise an EXECUTE describing the TARGET access and hand it to the
peer's own `check_permission` with `system/tree` as the pattern. Never signed, never
dispatched.

**`python`'s first draft hand-walked the token's grants and it was wrong twice over.** It
denied every request the oracle made — 23 of 34 checks failed on one root cause — and it
was the wrong SHAPE even when working: re-transcribing part of core §5.2's scope logic
inside an extension is a security divergence waiting to be found by somebody else (L18,
D12). **L7 is the rule that applies: check the toolkit before you build.** The peer had a
predicate that answers the question; it just did not have the one §4.2 names. Routed as
`H9`.

One declared difference on `rust`: the granter frame. `capability::granter_frame` wants an
`Envelope` and the probe is synthetic, so §PR-8's frame degrades to the local peer —
correct for a self-issued or locally-granted token, a stated limit for a delegated one.

### 2.5 The packaging boundary — `= CONTENT`, with a different clause behind it

Same three mechanisms, same three strengths: node's `exports` map (resolve time), Python
convention (nothing enforces it, and the test asserts it can be walked around), the absence
of `pub` (`error[E0603]`, compile time).

**What differs is the authority.** CONTENT had §3.4's MUST to point at. **HISTORY has
none** — the line is ours to draw (D16, the position `[sdk_surface]` put us in). It is
drawn at `record_transition` because a caller who reaches it can append a **forged entry to
an audit chain**: any `author`, any `capability`, at any path, linked into the real chain by
`previous` and content-addressed exactly like a real one. §7.2 calls the capability field
the answer to *"under what authority?"*, and a forgeable answer is worse than no answer,
because it is believed.

### 2.6 The toolchain — `= CONTENT`, minus one row

Identical, except HISTORY pins **no `sha2`**: there is no chunking, so there is no version
to keep unified with the peer's. `languages/rust/build`'s pin check is written to skip a
cell that pins none rather than to require one, which is what let this cell decline a
dependency it does not use without failing a gate.

### 2.7 What the third column did to the table

Three things, and none of them was "a new column":

1. **Two rows were added** — §2.3 (the handler grant) and §2.1's re-entrancy question,
   neither of which any prior port had a reason to ask.
2. **One row changed KIND.** §2.0's `[substrate.oracle_read_path]` is not a statement about
   what the peer can host. Every other row in this file answers *"can we build it here"*;
   that one answers *"can anyone tell"*. The `[substrate]` block now has three kinds — a
   MUST whose satisfiability differs per peer, a capability that is simply absent, and a
   limit on measurement — and only the first was designed.
3. **One row was CONFIRMED rather than extended**, which is the first time that has
   happened: §2.4's missing `check_path_permission` was a two-peer finding and the third
   peer agreed, adding a second mechanism (rustc rather than convention) to the same column.
   Two peers of three lacking a primitive the spec names is a spec-vs-cohort finding; three
   would have been the same finding with more weight. **It was not re-routed.**

---

## 3. Routed, one line each

- **`A-1`** → arch — no error-code table; `not_in_history` guards §7.5 and is defined
  nowhere. `[error_surface]` offered as the appendix.
- **`A-2`** → arch — `HIST-CONFIG-SPECIFICITY-1` is REQUIRED and cannot be constructed:
  its worked pair needs a mid-path wildcard core §5.4's grammar does not have, and the tie
  the v1.7 MUST defends against is unreachable under that grammar (a parity argument).
  Implemented anyway; the half that survives is asserted.
- **`A-3`** → arch — §2.2's table and §2.2's pseudocode disagree; the pseudocode's reading
  matches nothing, silently.
- **`A-4`** → arch — §3.3's pruning describes mutating immutable content-addressed
  entities. We walk and report and say so.
- **`A-5`** → arch — the §3.3 declaration header, as a filled-in draft.
- **`A-6`** → arch — §6.3's worked `pattern: "*"` sweeps the peer's own §3.5 signature
  writes into the audit chain. One wire PUT is three bindings, measured.
- **`H8`** → keystone — the tree-change event carries no execution context, on any peer.
- **`H9`** → keystone — `check_path_permission` exists on one peer of three.
- **`R-3`** → keystone — `[extension_host].emit_consumer` names a registration function and
  does not say whether a consumer may WRITE. Proposed `emit_consumer_reentrant`.
- **`R-4`** → keystone — `Peer` exposes no token mint on one peer, so §2.1's handler grant
  has no referent. Proposed `token_mint`.
- **`G-1`** → core-go — `rollback_invalid_hash_rejected` (§7.5) PASSES on a peer with no
  history handler, because `404 handler_not_found` is not 200. Measured on the bare arm of
  all three targets.
- **`G-2`** → core-go — the `history` category has no S1 gate, so a types-installed /
  handler-absent peer reports 23 FAIL where `content`'s equivalent reports SKIP.
- **`G-3`** → core-go — HISTORY's six `type_*` checks assert presence; CONTENT's three have
  a `_match` that compares content hashes against an independent transcription.

---

## 4. Mistakes we made here, so the next port does not

### 4.1 An expectation counted by eye

`content-history/SYSTEM.toml` said the `history` category had 27 checks. It has **34**. The
27 was read off `grep` output rather than printed by `grep -c`, in the session after
shipping a gate for a different D14 shape. AP-1, third instance.

### 4.2 A test that hand-walked the peer's authorization logic

See §2.4. 23 of 34 checks failed on one root cause, and the fix was not the bug fix — it
was reusing the peer's predicate instead of re-deriving it.

### 4.3 A parity gate that under-reported the surface, twice

`tools/sdk-parity.py` swallowed the name after a `//` comment inside an `export {…}` block,
and missed `export type {…} from` entirely. Both under-reported, which for a parity gate is
the dangerous direction: an under-reported surface reads as drift and a real drift reads as
agreement.

### 4.4 A probe arm that asserted a total where the property is a delta

`gates/host-seam` arm H asserted one consumer invocation after one wire `system/tree:put`
and measured **4**: serving one request also binds the caller's §3.5 signature and the
responder's own. The arm reported `NO` for a face that works — a **false red**, the
expensive direction.

It was caught because the arm PRINTS the number beside the verdict, and the miscount
became `A-6`. **Assert on the change your action caused, not on the state afterwards** —
and where the delta is over a set, assert on the MEMBER, so "fired on everything" and
"fired on ours" cannot both pass.

### 4.5 A citation to a gate that was never written

`[substrate.execution_context].probe` named `gates/emit-context` (dead) for a day. The claim was
true and was measured; what it cited was a gate somebody intended to write. **A citation is
what a reader checks instead of re-deriving the claim**, so a well-formed one suppresses
exactly the scrutiny that would find it wrong. AP-13, promoted immediately to D18 —
`tools/check-citations.py` found it and two others on its first run.

### 4.6 A hardcoded crate name in a per-target driver

`languages/rust/build` emitted `entity-content = { path = … }` as a literal — a
per-EXTENSION value in a per-TARGET driver, correct for exactly as long as `rust` had one
extension. `check-drivers.py` compares drivers to each other and is blind to it by
construction. **The D17 question has a second half: if it is a value, along which axis does
it vary?** AP-14.

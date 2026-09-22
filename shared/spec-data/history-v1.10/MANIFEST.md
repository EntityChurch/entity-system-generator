# spec-data snapshot — `history-v1.10`

**Immutable.** Operators never edit a snapshot. A defect in a snapshotted spec is routed upstream and
lands as a **new directory**, never as a local patch.

**Stamped:** 2026-09-09, from `entity-system-architecture` @ `7bb396e43fda415a4ba01d250db2f4a5501296fd`.
`EXTENSION-HISTORY.md`'s own last-touching commit is `8e2c38e8ca146fb17e0cd61e94348a5b11baa188`
(*"GI-10: a wildcard is a statement about scope, not consent to audit the machinery"*), which is where
v1.10 landed.
*(Internal SHAs. This file is not a publication surface — `docs/status/` rules apply. **The digests
below are the pin**; the commits are a convenience and [ADR-0012] Am. 1 says so.)*

| File | sha256 | Version |
|---|---|---|
| `EXTENSION-HISTORY.md` | `11de3057555e64ba8e0f9fb2cb285efe81184a800274680bae8abbfc23029c29` | 1.10 |
| `SYSTEM-COMPOSITION.md` | `084faf207da6ebb9d7e57fd05bf31a14228e1d23c821d7e4675ff6a971166627` | — (§2.2 consumer ordering, §1.4/§1.5 execution context) |
| `GUIDE-EXTENSION-DEVELOPMENT.md` | `7c085bea74ef15f636dc891b0810454eba00741fe7a09ab81831bbce2b33341b` | — (§4.1 `path_required`, §9 grade) |

Verify:

```
sha256sum -c <<'EOF'
11de3057555e64ba8e0f9fb2cb285efe81184a800274680bae8abbfc23029c29  EXTENSION-HISTORY.md
084faf207da6ebb9d7e57fd05bf31a14228e1d23c821d7e4675ff6a971166627  SYSTEM-COMPOSITION.md
7c085bea74ef15f636dc891b0810454eba00741fe7a09ab81831bbce2b33341b  GUIDE-EXTENSION-DEVELOPMENT.md
EOF
```

**`SYSTEM-COMPOSITION.md` is byte-identical across `history-v1.7`, `-v1.8` and this pin** — same
digest, `084faf20…`. Re-pinned rather than referenced, for the reason v1.8's manifest gives: a
snapshot is a self-contained input set, and a directory pointing at a sibling for one of its three
files would make the pin a graph rather than a set.

**`GUIDE-EXTENSION-DEVELOPMENT.md` MOVED** — `a3ebc723…` → `7c085bea…`, and the move is
**`path_required`'s resolution**. At v1.8 this guide's §4.1 declared *itself* the authority for that
status; arch's GI-2 ruling removed that claim, because a guide never owns a wire-observable status
code. See "what changed", below.

---

## What v1.8 → v1.10 changed, and what it cost us

**Two versions in one re-pin**, because v1.9 landed while nothing in this tree was watching for it.
That is the finding this snapshot exists to close, and it is recorded in `docs/ANTI-PATTERNS.md`
rather than here: **our pin gates check the integrity of the snapshot, never its currency.** A
snapshot cannot notice that the thing it is a copy of has moved.

### v1.9 — §9.1 becomes an addressable conformance inventory

`SPECIFICATION-FORMAT` v1.3 §8.5a, with `EXTENSION-HISTORY` §9.1 as the worked reference: one row per
independently failable obligation, a declared id prefix, a per-row `Level`, and a `HIST-R<n>` id
**allocated once and never reused or renumbered**.

**This is arch's answer to `ROUTING-2026-09-07-d`, and it is the half of our filing that was right.**
The other half was wrong and the correction is worth carrying: *"no declared shape"* is false — §5.1
has prescribed the section's form since the format standard was written and 19 of 26 specs follow it.
It was **a declared shape with no enforcement point**. *"No stable ids"* is the whole cost.

**What it costs us: our own ids are retired.** We minted `H-R1…H-R15` because no upstream id existed,
and the numbering does **not** align with arch's — our `H-R4` is their `HIST-R8`, our `H-R5` their
`HIST-R9`, our `H-R6` their `HIST-R10`. Every `[conformance]` row is re-keyed to the upstream id in
this re-pin. **Ours were a local invention filling an upstream gap, and the moment the gap closed they
became a second numbering for one set of obligations** — which is the thing `[conformance]` exists to
prevent, one level up.

Two rows also **changed meaning** and arch calls them out under the table: `HIST-R7` now states §3.3's
retention floor rather than the "pruning" the v1.8 chain ruling removed, and `HIST-R8` is restated as
the `MUST NOT` it always was.

### v1.10 — `pattern_exclude`, and our own finding coming back as spec

§2.2 gains `pattern_exclude`, and §6.3's worked configuration uses it. **This is `ROUTING-2026-09-07-arch-the-default-config-audits-the-peers-own-protocol-writes` landing** — our measurement that a
`pattern: "*"` config records the peer's own §3.5 signature bookkeeping as ordinary transitions, one
or more per served request, permanently, in a store §3.3 says cannot be pruned.

**Arch REVERSED its own recorded lean, and that is the part to remember.** `ROUTING-2026-09-08-e`
said their lean was to widen §3.2's self-exclusion guard to *"local, engine-written protocol paths"*
with the set enumerated, rather than add a config field. What landed is the config field. The stated
reason: core §1.9 makes those paths a **convention**, so the spec does not know the set it would have
been defaulting — §6.3's exclusion list is *"an example for the recommended path convention and
deliberately not a normative set."*

**The normative content is the ORDER, not the matching** (`HIST-R16`, MUST): exclusion is checked
**after** the most-specific matching configuration is selected and **before** the event-type filter,
and an excluded path **does not fall through** to a less specific configuration — *"an exclusion is a
decision, not a failure to match."* §2.2 says two conformant readings exist without that sentence and
that they differ on a path two configurations cover. All three ports implement the ordered form and
each carries a test for the fall-through case specifically, because it is the only one that separates
the readings.

Also in v1.10: §2.2's specificity paragraph corrects its peer-wildcard example to `/*/project/*`, the
spelling v1.8 ruled. No behaviour change here — this port already canonicalizes to that form.

### What did NOT change, and was checked

**The §3.3 declaration header ARRIVED** — GI-5 closed at 26 of 26. `[contract]` moves from **derived**
to **transcribed** in this re-pin.

**And the derivation it replaces was wrong in exactly one field, which is the argument for the header
made better than we made it.** Six of seven agree with the landed declaration: `depends`, owned
namespaces, the empty `properties.kind`, both ops, the six owned types, `points_exposed: none`.

**`points_consumed` does not.** We derived one entry — the emit pathway. The header declares **two**:

```
- The emit pathway
- The extension-contributed context field `clock`, owned by EXTENSION-CLOCK,
  typed `system/clock/state`  (SYSTEM-COMPOSITION §1.5; §5)
```

**A cross-extension consumed field is invisible from the consuming spec's own body**, which is why
`points_exposed: none` was derivable *"from absence"* and this was not: absence of a mention is
evidence about `EXTENSION-HISTORY`'s text and no evidence at all about what `EXTENSION-CLOCK` says it
contributes. That is **D12 / L8's shape** — an artifact is not a conclusion about the thing it names —
and the artifact here was our own careful read of the wrong document.

**We had said the cost of the missing header was the presentation, not the content.** That sentence is
now measured and it was optimistic: one field in seven, and the one that names another extension.
Recorded in `docs/ANTI-PATTERNS.md` — a derivation from a document cannot see the fields another
document owns, and the ports do not consume `clock` today, so nothing would have failed.

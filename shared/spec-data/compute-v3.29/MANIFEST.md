# spec-data snapshot — `compute-v3.29`

**Immutable.** Operators never edit a snapshot. A defect in a snapshotted spec is routed upstream and
lands as a **new directory**, never as a local patch.

**Stamped:** 2026-09-09, from `entity-system-architecture` @ `4cdf8b4ac26d8ed8b776c813c465104f72882bef`.
`EXTENSION-COMPUTE.md`'s own last-touching commit is `5e6ff770ef54c2e12b8593290a4359a17f56474c`
(*"GI-5 CLOSES: 26 of 26 dependency contracts, and the gate can enforce"*), which is where the
**§3.3 declaration header** arrived. The last commit to touch the spec's *normative* text is
`dc9f7c6` (*"the system/\* reservation is withdrawn"*), which is where **v3.29** landed.
*(Internal SHAs. This file is not a publication surface — `docs/status/` rules apply. **The digests
below are the pin**; the commits are a convenience and [ADR-0012] Am. 1 says so.)*

| File | sha256 | Version |
|---|---|---|
| `EXTENSION-COMPUTE.md` | `d1de19425d5dc80a30a4ae228cd15db9681ca27e1fc437bb448a8ecbe732de53` | 3.29 |
| `SYSTEM-COMPOSITION.md` | `084faf207da6ebb9d7e57fd05bf31a14228e1d23c821d7e4675ff6a971166627` | — (§2.2 consumer ordering — **position 5, unbounded reactive**; §1.4/§1.5 execution context) |
| `GUIDE-EXTENSION-DEVELOPMENT.md` | `7c085bea74ef15f636dc891b0810454eba00741fe7a09ab81831bbce2b33341b` | — (§3.3 the declaration header's own definition; §4.1 status codes; §9 grade) |

Verify:

```
sha256sum -c <<'EOF'
d1de19425d5dc80a30a4ae228cd15db9681ca27e1fc437bb448a8ecbe732de53  EXTENSION-COMPUTE.md
084faf207da6ebb9d7e57fd05bf31a14228e1d23c821d7e4675ff6a971166627  SYSTEM-COMPOSITION.md
7c085bea74ef15f636dc891b0810454eba00741fe7a09ab81831bbce2b33341b  GUIDE-EXTENSION-DEVELOPMENT.md
EOF
```

**Both companions are byte-identical to `history-v1.10`'s** — `084faf20…` and `7c085bea…`. Re-pinned
rather than referenced, for the reason every prior manifest gives: a snapshot is a self-contained
input set, and a directory pointing at a sibling for two of its three files would make the pin a
graph rather than a set.

**What is deliberately NOT pinned, and why it is worth saying here.** `ENTITY-CORE-PROTOCOL` is not
in any snapshot in this tree, and for CONTENT and HISTORY that cost nothing. **For COMPUTE it is a
live exposure**, because §6.6's entity-native dispatch pseudocode and §3.7's `expression_path` are
where this extension's most consequential seam lives (the H7 evaluator), and they are core text. The
core protocol also moved twice this week in ways that touch us (0.8.2.13 withdrew the `system/*`
reservation; 0.8.2.14 enumerated `path_required`). Recorded as a gap in the pin rather than closed
here: adding a fourth file changes what every prior snapshot means by *"snapshot"*, and that is a
decision for the port, not for the pin. **Read it live and cite it live until then.**

---

## Why v3.29 and not v3.27

**`docs/DESIGN-THE-COMPUTE-TRACK.md` was written against v3.27 (arch `627ef47`) and this repo has
never held a COMPUTE snapshot at all.** Two versions landed since, and **both touch things that
document asserts** — which is `AP-27` exactly: our pin mechanisms check the integrity of a copy and
can never observe that the original moved. There was no copy here to be stale; the *reading* was.

### v3.28 → v3.29 — the builtin override prohibition now stands on its own, and that lands on US

§4's override prohibition previously described itself as *"a subset of"* the core `system/*`
reservation, telling implementers that enforcing the core rule needed **"no separate compute-specific
guard."** `ENTITY-CORE-PROTOCOL` 0.8.2.13 **withdrew that reservation entirely**, so the subset claim
named a rule that no longer exists. v3.29 restates the prohibition on its own basis: it binds **every
installation path** because it is a *cross-peer determinism* requirement, not a namespace policy.

**This closes `DESIGN-THE-COMPUTE-TRACK` §6 item 6 in the direction we predicted, by a bigger
move than the one we predicted.** That row read: *"the builtins guard may become ours to emit **if**
D1 lands and §3.5's delegation to §6.2 stops holding. Cheap now; expensive after 26 ports exist."*
D1 asked to *narrow* the reservation; arch **deleted** it. So the condition is met and the guard is
ours to emit — recorded as `[assumptions].builtin_override_guard` in the contract, with the ports
owing it from port one rather than acquiring it at port twenty-six.

### v3.27 — the contained set is a RULE, not a count

v3.26 pinned the contained set as *"exactly three positions"*; the enumeration was taken over the
four v3.25 primitives and missed `map` / `filter` / `fold`, which predate that table. **It is five**,
and the count is replaced by the rule that generates it — a position is **contained** when the
primitive places the value without reading it, **consumed** when it reads it to decide control flow,
ordering, membership or a write location.

**Recorded here because it is D15 clause 2's sharpened form arriving in somebody else's document**,
on the same week we ratified it (AP-28): a count that is correct when written goes stale silently as
its subject grows, and the rule that generates the count does not. Arch reached the identical
conclusion independently and for the identical reason. Nothing to route; noted because a port
reading §3.5 will meet the rule and should know it replaced an enumeration.

Also in v3.27: `depth_exceeded` **contains** (its counter is restored on unwind, §5.1) while
`budget_exhausted` and `cascade_limit` **short-circuit everywhere** — cumulative and chain-wide
respectively. That distinction is a per-error-code property and is transcribed into
`[error_surface]`, because it is not derivable from the §9.1 table.

---

## What the read-for-generation found, before a line was generated

Four, routed as `ROUTING-2026-09-09-d-arch-*`. All four are in the **declaration header, the
constants tables and §10** — the machine-readable furniture — and **none is in the normative body**,
which reads as the most carefully-worked spec in the corpus. That distribution is itself the finding:
the parts a human reads closely are sound, and the parts a *tool* reads are the ones that drifted.

1. **`Extension points consumed` omits the emit pathway.** The header's stated job is *"what does
   installing this extension touch."* Installing COMPUTE with reactive mode registers an
   **unbounded-reactive consumer at `SYSTEM-COMPOSITION` §2.2 position 5** — carried in §2.7A's
   worked stable-name list as `"compute/reevaluator"` — whose body is §7.2's `on_tree_change`. The header
   lists *"core protocol (v7.33+) — the only dependency"* and the optional `budget_consumed`
   EXECUTE_RESPONSE field, which is not a registration hook at all. `EXTENSION-HISTORY`'s header, from
   the same GI-5 sweep against the same guide clause, declares `emit.tree_change`.
2. **§10.1 MUSTs three behaviours of an operation §10.2 makes a SHOULD.** *"Install audit collects
   `compute/lookup/hash` targets…"*, *"Sealed `authorized_data_hashes` on subgraph metadata"* and
   *"`validate_compute_resolvable` Tier 2: sealed set check for installed subgraphs"* are §10.1 MUSTs
   about `system/compute:install`; §10.2 reads *"Install and uninstall operations (§3.3, §3.4) —
   required if reactive mode is implemented."* **And the oracle has already picked a side**:
   `validate-peer`'s `handler_op_install` / `handler_op_uninstall` are `FailCheck` on a manifest that
   omits either. Four documents, three answers, and a generator has to emit one.
3. **§9.2 Standard Operations omits `install` and `uninstall`** — it lists `eval` twice, against two
   handler patterns. §3.1's manifest declares all three and the declaration header names all three.
   **This is the SAME defect we routed against CONTENT and arch has already fixed once**: §10.3
   omitted `ingest` (our F3, closed 2026-09-03), and the fix added the sentence that prevents a
   recurrence — *"This table enumerates the operations the `system/content` handler declares in its
   §6.1 manifest."* COMPUTE §9.2 has the drift and not the sentence. So it is routed as *the
   operations table is a hand-maintained second copy of the manifest and nothing checks that they
   agree* — the fix arch already wrote, applied where it was not applied. HISTORY needs nothing: it
   has no operations table, only §9.3's manifest, which is one copy.
4. **The manifest block spells the pattern in capability-scope form.** `pattern: "system/compute/*"`,
   with the prose four lines below reading *"Manifest at pattern path `system/compute`."* Measured
   across the corpus: **2 of 18** manifest blocks use the `/*` spelling and they are exactly CONTENT
   and COMPUTE — the two extensions this repo has read for generation. Binding at a literal `.../*`
   puts a `*` segment in the tree.

   ```
   $ grep -h 'pattern:  *"system/' specs/extensions/*.md | sort | uniq -c | sort -rn
   ```

**And one we withdrew before routing it, which is worth more than the four.** The header's
`Owned namespaces` names only `system/compute/`, while the extension's entire IR lives in the
top-level `compute/*` type namespace — 20 types, a namespace core §2.7 carves out by name. That
reads as a glaring omission until you read the guide clause it answers: §3.3 defines the field as
*"every `system/<ext>/…` subtree the extension claims."* **`compute/*` is out of scope for the field
by the field's own definition.** D12/L8, caught by reading the canonical source instead of the
plausible inference, one step before it became a packet.

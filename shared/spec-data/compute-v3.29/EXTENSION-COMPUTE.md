# Compute Extension — Normative Specification

**Version**: 3.29
**Status**: Active
**v3.29 — the builtin override prohibition stands on its own** (§4, override prohibition). The rule previously described itself as *"a subset of"* the core `system/*` reservation and told implementers that enforcing that reservation needed *"no separate compute-specific guard."* **That reservation has been withdrawn from the core protocol entirely** (`ENTITY-CORE-PROTOCOL` 0.8.2.13), so the subset claim named a rule that no longer exists — and before the withdrawal it was already false in the direction that opens a hole. The prohibition now states its own basis: it binds every installation path because it is a **cross-peer determinism requirement**, not a namespace policy. Two peers disagreeing about what `"add"` means is an interop failure, which is why this is a MUST while local install policy is not. *(v3.28 stated the same conclusion by reference to the core rule's scope and is superseded.)*
**v3.27 — the contained set is a RULE, not a count; and eval limits are not ordinary errors**
(§3.5, §2.3, §7.1): v3.26 pinned the contained set as *"exactly three positions."* That enumeration was
taken over the four v3.25 primitives; `map`, `filter` and `fold` predate that table and also place
closure results into outputs. **It is five.** The count is replaced by the rule that generates it —
a position is **contained** when the primitive places the value without reading it, **consumed** when
it reads it to decide control flow, ordering, membership or a write location — so a new primitive adds
a row by applying the rule rather than amending a number. Two consequences are pinned with it: a
`compute/error` behaves **identically however it was produced**, minted or value-form (a restatement of
§2.4, not a new rule); and the three **evaluation-limit** codes are separated on whether their counter
survives an element — `depth_exceeded` **contains** (restored on unwind, §5.1), `budget_exhausted` and
`cascade_limit` **short-circuit** everywhere (cumulative and chain-wide respectively; containing either
reports a value for an evaluation that was aborted, at a split point no rule pins). `concat-args`
carries **one hash of an expression**, uniform with every sibling collection argument. And §7.1's
dependency walk is corrected to reach references inside containers, which its own conservative-collection
rule already required and its pseudocode did not do.
**v3.26 — a CONTAINED `compute/error` has a boundary form** (§2.3, §3.5): v3.25's data positions made
v3.23 ruling B's premise false — *"an error is never placed into the data"* was true until `assoc`'s
`value`, `concat`'s elements and `group-by`'s `members` existed. Ruling B is **scoped, not reversed**:
it is a consumption-site invariant, and in those three positions the error materializes **code-only,
by bare `system/hash`**. Code-only is load-bearing — a contained `message` would fork the containing
array's bytes across two conformant peers. Everywhere else §7.2's short-circuit is unchanged.
**v3.25 — the v3.24 primitives' four corners close** (§3.5, §9.1): the first implementation of v3.24
found three corners that determine boundary bytes, and a fourth surfaced while ruling them. `group-by`
returns **`system/compute/group{key, members}`** — the key is in the result, restored from the shape the
design record ruled and the v3.24 fold narrowed away. `assoc`'s out-of-range index is
**`index_out_of_range`**, correcting a v3.24 clause that contradicted §2.2's cross-impl ruling that an
out-of-domain magnitude is not a type error. `range`'s negative or oversized `n` is the new
**`count_out_of_range`**, following `cast_out_of_range`'s precedent rather than overloading either
neighbour. Error-as-value flow-through needed no new rule — §7.2's consumed-operand `[MUST]` already
decides all seven positions, and §3.5 now cites it instead of leaving it to be re-derived.
**v3.23 — `is_error` is defined, and it is kind-based** (§4.1): the predicate the evaluator branches on
39 times was used throughout and defined nowhere, so a `compute/error` reaching a `compute/construct`
field embedded in one implementation, propagated in a second, and embedded-without-materializing in a
third. `compute/error` is removed from §4.1's construct materialization set and from §2.3 N1's
placement list — an error materializes where it is written (§7.2 `result_path`, SA-9 `store`), never
where it is consumed. Worked example added at the short-circuit `[MUST]`.

**v3.22 (2026-07-23) — §11 Alternate-Engine Admission** (AE-1 boundary-equivalence + AE-2–AE-6): folded from
`PROPOSAL-COMPUTE-ALT-ENGINE-ADMISSION` on its only gate being met — the first green **inproc** alternate-engine
admission run (**Axis-1**, Go, `entity-core-go` report `2026-07-23-ae5-axis1-inproc-admission-GREEN`: 330/330
byte-identical alternate==reference, 0 fallbacks, `engine-role==alternate` enforced). The reference interpreter
(§4) remains the conformance floor; an alternate engine is a per-impl opt-in.
**v3.21 (2026-07-23) — validated by the compute corpus three-way LOCK (330/330 byte-identical across Go/Rust/Python,
oracle-pinned `seed 20260716 / SplitMix64 / corpus-SHA d0fdd757`)** *(that pin is **historical**: it records what v3.21
was blessed against and **does not describe the corpus today** — the set has since grown past 330 and re-frozen under a
new SHA, and the outcome cross-bless at the current SHA is owed. A conformance claim cites the MANIFEST beside the
bytes, never this line.)* **:** `PROPOSAL-COMPUTE-BUDGET-CEILING-DETERMINISM`
(implemented — §4.2, Q2; all three impls charge `evaluate()` steps only, `worked/budget/exhausted-deterministic`
agrees). Also validated three-way by the same lock: F-1 (Rust cast-to-uint materialization, §2.2 rule 11), F-2
(§9.1 out-of-range index), F-3 (Python tier-1 `included`). Ruled in `ARCH-RESPONSE-COMPUTE-CORPUS-FIRST-RUN`.
**Pending (provisional — folded in §2.4 but NOT yet corpus-gated cross-impl):**
`PROPOSAL-COMPUTE-ERROR-MATERIALIZATION-DETERMINISM` (§2.4 — materialized `compute/error` is `code`-only, Q1) —
validated intra-Go (Axis-1 == Stage-1, code-only). **Cross-impl gate:** Python (+Rust) materialize `compute/error`
code-only per this §2.4, and a corpus vector that materializes an error *into a construct/tree* runs three-way.
(This §2.4 is the canonical home for `compute/error`. `ENTITY-CORE-MACHINE-SPEC.md`, which carried a derived
condensed restatement, is **retired** and is not a citable source.)
**Depends**: ENTITY-CORE-PROTOCOL.md (v7.33+)

**The dependency contract** (per `GUIDE-EXTENSION-DEVELOPMENT.md` §3.3 — *"an implementer scanning
the spec should be able to answer 'what does installing this extension touch' from the header
alone"*). Every entry below is derived from this document's own sections, cited beside it.

**Used by (informative):**
- `EXTENSION-TYPE` — the §2.2 constraint-handler dispatch surface admits a compute-backed constraint
  handler; convergence semantics are deferred to a follow-on TYPE amendment.
- `EXTENSION-HISTORY` · `EXTENSION-QUERY` — bounded read-only subtree inspection.
- `EXTENSION-SUBSCRIPTION` · `EXTENSION-CONTINUATION` · `EXTENSION-INBOX` · `EXTENSION-REVISION` ·
  `EXTENSION-REGISTRY`.

**Owned namespaces:**
- `system/compute/` **(closed)** — §2. The IR node families and their argument types (`map-args`,
  `filter-args`, `fold-args`, `concat-args`, `assoc-args`, `group-by-args`, `range-args`,
  `store-args`) · `builtins` · `group` and `subgraph` · `scope-binding` · `processes` (§7 reactive
  mode) · `install-request` / `install-result` and `uninstall-request` (§3).
- **`compute/error` is canonical HERE, in §2.4.** The condensed machine-spec restatement of it is
  **retired and is not a citable source** — cite §2.4.

**Owned `properties.kind` values:** none. This extension defines no `kind` and claims no row in the
kind-ownership table (`EXTENSION-ATTESTATION.md` §3.2).

**Owned handler ops** — handler at pattern `system/compute/*` (§3):
- `system/compute:eval` · `system/compute:install` (and the uninstall counterpart, §3).

**Extension points exposed:**
- **Alternate-engine admission (§11), and its framing is the load-bearing part.** The §4 reference
  evaluator is the **conformance floor**, and the cross-impl LOCK is over reference evaluators. A
  peer MAY add an alternate execution strategy for the same content-addressed IR — decode-once,
  compiled or fused, memoizing, defunctionalized — governed by **one** admission rule (AE-1) plus
  the invariants and evidence that make it hold (AE-2–AE-6). ***Stating the rule once, over "any
  engine," is deliberate — an equivalence pinned per-engine-kind springs apart at the next kind
  nobody wrote a rule for.*** An alternate engine is **optional and per-implementation, a
  performance choice and never a conformance surface.**
- **The builtins table (§2)** and the reactive-mode process surface (§7).

**Extension points consumed:**
- **Core protocol (v7.33+) — the only dependency.** The conformance surface is the **materialized**
  boundary, and the IR is content-addressed; nothing else is required to install this.
- **The optional `budget_consumed` field on EXECUTE_RESPONSE (§5).** Peers in trusted relationships
  MAY exchange budget metadata; **when absent — the default — no cross-peer accounting occurs.**
  Do not build a budget model that assumes it is present.
**Source**: PROPOSAL-COMPUTE-AMENDMENTS.md (implemented — C1-C10), PROPOSAL-COMPUTE-AMENDMENTS-V2.md (implemented — V1-V32 + V6/V7/V7'), PROPOSAL-COMPUTE-AMENDMENTS-V3.md (implemented — C1-C4 core helpers + E1-E3 compute fixes), PROPOSAL-COMPUTE-SPEC-AMBIGUITIES.md (implemented — A1-A4, B1, C1, D1, D2), PROPOSAL-COMPUTE-CONTENT-STORE-SCOPING.md (implemented — D3-D6), PROPOSAL-COMPUTE-TAIL-CALL-OPTIMIZATION.md (implemented — T1-T3, R1-R2), PROPOSAL-ENTITY-NATIVE-HANDLER-DISPATCH.md (implemented — E1-E4), PROPOSAL-COMPUTE-APPLY-RESOURCE-CEILING.md (implemented — F1-F5, H2-H3), PROPOSAL-COHERENT-CAPABILITY-AUTHORITY.md (implemented — CP1, CP2), PROPOSAL-COMPUTE-LOOKUP-TREE-LOCAL-QUALIFICATION.md (implemented — S8), PROPOSAL-COMPUTE-CLOSURE-RESULT-POSITIONS-AND-CONCAT-ARGS-SHAPE.md (implemented — D1-D8)

---

> **Path notation.** Paths in this document use peer-relative notation (without leading `/{peer_id}/`). All peer-relative paths resolve to the local peer's namespace: `system/tree` means `/{local_peer_id}/system/tree`. Every path in the entity tree is absolute at rest — rooted at a peer identity. See ENTITY-CORE-PROTOCOL.md §1.4 for the path model. Cross-peer examples use absolute paths with explicit peer identities.

## 1. Overview

The compute extension defines a minimal expression language embedded in the entity type system. Programs are entities — content-addressed, storable, transferable, and inspectable. The compute handler evaluates expression entities and produces result entities.

The extension defines:

- Expression types for representing computation
- An evaluation algorithm
- Budget and depth constraints
- Purity classification and capability requirements for impure operations
- Reactive mode — automatic re-evaluation when dependencies change
- Determinism requirements for cross-implementation verification

This extension is independent of EXTENSION-INBOX.md, EXTENSION-CONTINUATION.md, and EXTENSION-SUBSCRIPTION.md. A peer **MAY** implement inbox delivery and subscriptions without compute — inbox delivery provides basic synchronization (remote data arrives, handler writes it to local tree, peer has an up-to-date copy) and subscriptions provide change notification, both without any computation layer. Compute adds reactive re-evaluation on top of tree changes, but the tree notification pattern is useful on its own.

All three extensions share an internal tree notification pattern (tree change triggers reactive behavior), but each defines its own use of that pattern independently.

### 1.1 Coherent Capability

`system/compute/subgraph` entities and the compute expressions they reference are load-bearing: their `installation_grant`, `authorized_data_hashes`, and embedded `compute/apply.capability` fields authorize future evaluations and dispatches. Use `system/compute:install` to create subgraphs. The install operation audits the expression graph, validates literal capability references against the installer's authority chain (§3.3), and persists subgraph metadata under the handler's own grant.

Direct `tree:put` to `system/compute/processes/*` is permitted but bypasses the install audit's validation; metadata written that way is not guaranteed to satisfy the subgraph invariants. The compute handler writes to its managed namespace under its own grant during normal install; direct `tree:put` is appropriate for system-extension code and administrative/bootstrap contexts. Direct writes to expression entity paths similarly bypass the install audit and produce expressions that have not been validated for capability embedding. See ENTITY-CORE-PROTOCOL.md §6.3 for the kernel-vs-handler principle.

---

## 2. Type Definitions

### 2.1 Core Expression Types

Seven primitive expression types form the computation language (the `compute/lookup` family has two members — scope and tree — introduced in v3.3).

#### compute/literal

Introduce a concrete value.

```
compute/literal := {
  fields: {
    value: {type_ref: "primitive/any"}          ; The literal value
  }
}
```

#### compute/lookup/scope

Read a value from the current evaluation scope by binding name. Pure — no tree access, no capability check required.

```
compute/lookup/scope := {
  fields: {
    name: {type_ref: "primitive/string"}        ; Scope binding name
  }
}
```

Scope bindings come from enclosing `compute/let` blocks or `compute/lambda` parameters. If the name is not in the current scope, evaluation returns a `not_found` error. `compute/lookup/scope` does NOT fall through to the tree — it is strictly scope-local.

#### compute/lookup/tree

Read a value from the entity tree by path. Impure — accesses mutable tree state, registers a dependency for reactive mode (§7.1), requires a capability check (§6.2).

```
compute/lookup/tree := {
  fields: {
    path:     {type_ref: "system/tree/path"}                    ; Tree path
    relative: {type_ref: "primitive/bool", optional: true}      ; Resolve against subgraph root
  }
}
```

If the tree entity at `path` is itself a compute expression (§4.7), it is evaluated — `compute/lookup/tree` returns the computed **value**, not the raw expression entity. This is the spreadsheet semantic: referencing a cell with a formula gives you the formula's result. This enables recursive patterns: a `compute/lambda` stored at a tree path evaluates to a `compute/closure` when looked up, which can then be applied via `compute/apply`. Note that storing a `compute/closure` directly at a tree path returns it as a value — closures are values, not expressions, and are not re-evaluated (see §4.7).

If the tree entity is NOT a compute expression (e.g., a regular `system/peer` or application entity), it is returned as-is.

For raw entity access without evaluation (inspecting the expression itself), use protocol-level GET, which returns the entity directly without entering the compute evaluator.

**Relative paths (`relative: true`).** When `relative` is `true`, the path is resolved against the subgraph root at eval time: `clean_path(ctx.subgraph_root + "/" + path)`. When `relative` is absent or `false`, the path is **canonicalized** per V7 §5.4 before use: a peer-relative path (no leading `/`) is qualified to the local peer's namespace — `/{local_peer_id}/{path}` — and a path already in absolute form (`/{peer_id}/…`) is used as-is. This is the same canonicalization the tree layer applies to writes, performed identically at resolution and at dependency registration (§7.1) so a dependency keys on the absolute-at-rest path tree writes notify on. (Storing the verbatim peer-relative string instead is a silent footgun — the dependency `app/x` never matches a write to the canonical `/{local_peer_id}/app/x`, and the reactive subgraph never recomputes.) All three forms read the **local** tree; an absolute path naming another peer's namespace is a local-tree entry kept current by subscription/inbox (see the absolute-path note below and §7.5), never a fetch across the peer boundary.

The subgraph root is a tree node — the `root_expression_path` from the install request (§3.3). It is both where the root expression entity lives and the prefix under which the subgraph's data, helpers, and results are organized. A tree node defines a subtree — internally coherent, externally relocatable. The default result path `{root_expression_path}/result` already establishes this convention — results are children of the root.

A typical subgraph layout:

```
app/compute/my-job/             ← root_expression_path (subgraph root)
app/compute/my-job/data/input-1 ← data entity (relative path: "data/input-1")
app/compute/my-job/data/input-2 ← data entity (relative path: "data/input-2")
app/compute/my-job/lib/helper   ← helper lambda (relative path: "lib/helper")
app/compute/my-job/result       ← result (default result_path)
```

Relative paths make expressions portable — the same expression entity can be installed at `app/compute/my-job/` on one peer and `other/prefix/` on another. The expression entities are content-addressed and don't encode the root; the root is provided by the installation context. Data and helpers under the root are part of the transferable subtree.

Absolute paths remain available for dependencies outside the subgraph — cross-peer references, external data sources, etc. These are non-portable by definition. A "cross-peer reference" here is a tree path *in another peer's namespace that resides in the **local** tree*, kept current by subscription/inbox (§7.5) — it is read locally, not fetched across the peer boundary. **Reactive evaluation and dispatch remain local: the reactive engine triggers on local tree writes only (§7.1, §7.2) and does not re-evaluate or dispatch across the peer boundary. Cross-peer data flow is the subscription/inbox seam writing into the local tree (§7.5), not reactive re-evaluation itself.** (Explicit `eval` MAY dispatch `compute/apply` to a remote handler; that is the caller-driven path, distinct from reactive mode.)

For explicit eval, the subgraph root is the expression URI (the tree path targeted by the EXECUTE). For installed subgraphs, the root comes from the subgraph metadata's `root_expression_path`. Same value, different source — relative paths work in both contexts.

**Why three types.** Earlier drafts had a single `compute/lookup` that tried scope first, then fell through to the tree. This was ambiguous: a static auditor walking the expression graph could not determine whether a given lookup would resolve in scope or in the tree without evaluating it. The three-type split makes the resolution target explicit at the type level — `compute/lookup/scope` is always scope, `compute/lookup/tree` is always tree, `compute/lookup/hash` is always content-addressed. Static dependency analysis (§7.1) becomes trivial: collect every `compute/lookup/tree` path for reactive dependencies, collect every `compute/lookup/hash` target for install-time authorization. No ambiguity, no spurious tree dependencies from scope-name collisions.

#### compute/lookup/hash

Read a value from the content store by content hash. Pure — the hash is immutable, so the result is deterministic. Requires install-time authorization via path hint (§3.3) or `content_store_access` allowance.

```
compute/lookup/hash := {
  fields: {
    hash:     {type_ref: "system/hash"}                          ; Content hash of target entity
    path:     {type_ref: "system/tree/path", optional: true}     ; Authorization hint — tree path where entity was stored
    relative: {type_ref: "primitive/bool", optional: true}       ; Path hint is relative to subgraph root
  }
}
```

The `path` field is an **authorization hint** consumed at install time. The install audit reads the entity at `path`, verifies `content_hash(entity) == hash`, and verifies the caller's grant covers tree GET at `path` (V7 §6.3). The validated hash is sealed into the subgraph's `authorized_data_hashes` set. At eval time, the sealed set is checked — the path has no runtime role.

If the target entity at `hash` is itself a compute expression (§4.7), it is evaluated — `compute/lookup/hash` returns the computed **value**, not the raw expression entity. This matches the `compute/lookup/tree` semantic: referencing a formula gives you the formula's result. If the target is NOT a compute expression, it is returned as-is.

Pure at eval time. Install-time path-hint validation reads from the tree, but that is an authorization step, not part of evaluation — install is inherently impure (writes subgraph metadata). The purity classification applies to eval behavior: a content store read of an immutable hash. No reactive dependency is registered — hash references never change.

**Explicit eval.** `compute/lookup/hash` targeting non-compute entities in explicit eval (no installed subgraph) requires `content_store_access` (Tier 0). Without it, eval returns `not_found`. For ad-hoc external data access without admin privileges, use `compute/lookup/tree`.

#### compute/apply

Call a handler or closure with arguments.

```
compute/apply := {
  fields: {
    path:       {type_ref: "system/tree/path", optional: true}   ; Handler path (handler mode)
    operation:  {type_ref: "primitive/string", optional: true}   ; Handler operation (handler mode)
    resource:   {type_ref: "system/hash", optional: true}        ; Hash reference to expression evaluating to system/protocol/resource-target (handler mode)
    fn:         {type_ref: "system/hash", optional: true}        ; Hash of closure entity (closure mode)
    args:       {map_of: {type_ref: "system/hash"}, optional: true}  ; Named argument hashes
    capability: {type_ref: "system/hash", optional: true}        ; Dispatch with this capability (handler mode only, voluntary restriction)
  }
}
```

The `capability` field follows the same resolve-then-evaluate pattern as other `system/hash`-typed expression references. The evaluated result must be a valid capability entity. When present in handler mode, dispatch uses the provided capability instead of `ctx.capability` — subject to the dual-check (§4.1): `ctx.capability` must ALSO cover the target including the resource (full-resolution dual-check).

The `resource` field carries the resource target for the dispatched EXECUTE, mirroring V7 §3.3 EXECUTE.resource. It uses the same resolution pattern as `capability` — a `system/hash` reference to an expression evaluating to a `system/protocol/resource-target`. Static literals stay statically auditable at install time; dynamic resources defer to runtime checks (the same conservative-static / dynamic-runtime split used for `store` builtin paths). When `capability` is present, `resource` MUST also be present — see F5 below and §4.1.

**A builtin-path apply carrying `capability` or `resource` is invalid `[MUST; ruled — the three-way split]`.** Both fields are defined **only** as parameters of the **dispatched EXECUTE**: `capability` replaces `ctx.capability` *"when present in handler mode, dispatch uses the provided capability"*, and `resource` *"carries the resource target for the dispatched EXECUTE."* A `system/compute/builtins/*` path is evaluated **inline** (§3.5) and **dispatches no EXECUTE**, so neither field has a referent. An implementation **MUST** return `invalid_expression` for a builtin-path `compute/apply` whose `capability` or `resource` is present, and **MUST NOT** silently ignore them.

> **Why rejection, and not "ignore them as harmless."** The dual-check can only ever **narrow** — a provided capability is honored *and* `ctx.capability` must still cover the target. So a caller supplying one is asking for the operation to be **more** constrained than ambient authority. **Silently dropping that request grants a wider operation than the caller asked for**, and the builtin it matters for is `store` — the one impure builtin (§6.2), writing to a caller-specified path. Ignoring is therefore the one disposition that fails quietly in the dangerous direction.
>
> **Nothing legitimate is lost.** §6.2 already fixes the authority for `store`: the caller's capability on the explicit-eval path, or the installation grant on the reactive path, checked with `check_path_permission("put", path, capability)` — **never a field on the expression.** A caller wanting an attenuated `store` attenuates the capability it evaluates under. And rejecting keeps §3.5's alias result **hash-identical to the inline form** for every legal builtin apply, which falling back to handler dispatch would not.
>
> **The rejection is a SHAPE check and runs before any field is resolved or evaluated `[MUST]`.** It depends only on `path` and on the **presence** of the fields, never on their values. Rejecting after evaluation would make the outcome depend on a value the expression is not allowed to carry: an error-valued `resource` would short-circuit to **that** error instead of `invalid_expression`, so two conformant implementations would answer one malformed expression with different codes. It would also perform tree reads on the strength of an expression already known to be invalid.
>
> **It is enforced at install time too, on the same static/dynamic split this section already uses `[MUST]`.** Where `path` is a **static literal** under `system/compute/builtins/`, the whole condition is decidable without evaluating anything, so an install-time audit **MUST** reject it — exactly as F5 rejects capability-without-resource, and for the same reason: *a static structural error, regardless of whether the fields would be statically resolvable.* Where `path` is **dynamic**, the shape is not knowable until evaluation and the runtime rejection above is the whole enforcement. **An audit that fail-fasts F5 while installing this shape clean is internally inconsistent** — both are structural, and neither is a value-dependent check.

Two modes:
- **Handler mode**: `path` and `operation` present. Dispatch EXECUTE to handler.
- **Closure mode**: `fn` present. Apply closure to arguments.

A `compute/apply` entity **MUST** have either `path` or `fn`, not both and not neither.

**Handler-mode params assembly.** In handler mode, the compute evaluator MUST construct the dispatched EXECUTE's `params` entity using the target operation's declared `input_type` (from the handler manifest, per V7 §6.2). The evaluated `args` map populates the fields of this entity. This matches how every other EXECUTE dispatch works in the system: the caller constructs an entity of the handler's expected input type and sends it. Compute/apply is the automated version — the evaluator builds the entity from resolved args.

```
params_entity = {
  type: target_operation.input_type,
  data: {<resolved args as fields>}
}
```

If the type extension is present, the constructed params entity SHOULD be validated against the declared input type before dispatch. Unknown fields are preserved per V7 §2.10 (open types). Missing required fields produce a `type_mismatch` error. Peers with and without type extension produce identical results on valid inputs but differ on invalid inputs — implementations SHOULD document whether validation is enabled.

**Per-field arg encoding (SA-2).** The evaluator encodes each resolved arg into its field position per the declared `input_type` field schema: a field declared `system/hash` receives the content hash of the evaluated arg (stored in the content store); other fields receive the evaluated value inline (per the value-encoding table in this section). The evaluator consults `input_type` for this — it does not pre-evaluate-and-inline uniformly — so handlers with hash-typed inputs remain hash-determinism-stable.

**Return wrapping (SA-4).** Handler-mode `compute/apply` MUST wrap a bare-primitive return from the dispatched handler in `compute/result`, uniformly across handler shapes (compiled, entity-native, or `system/compute:eval`), so a downstream expression decodes every dispatch target the same way. An entity-typed return passes through unchanged.

**Value encoding into field positions.** Each evaluated arg value is encoded into its corresponding field position based on the declared field type in `input_type.fields[name]`:

| Declared field type | Value kind | Encoding |
|---|---|---|
| `primitive/*` (specific) | Matching primitive | Inline directly |
| `primitive/*` (specific) | Mismatched primitive, entity, or closure | `type_mismatch` error |
| `primitive/any` | Any value | Inline directly (hash refs preserved) |
| `system/hash` | Entity or closure value | Store in content store, set field to content hash |
| `system/hash` | Primitive value | `type_mismatch` error |
| Unknown field (open type) | Any value | Inline directly, preserved per V7 §2.10 |

Content store writes performed during encoding are local storage operations — content addressing makes them idempotent, so adding an entity is effectively free if it's already present. The authorization check for the dispatch itself happens at `ctx.dispatch_execute` using `ctx.capability` (the caller's capability for explicit eval, the installation grant for reactive eval). See §4.1 for the normative `encode_arg_for_field` pseudocode.

When the type extension is NOT present, the compute handler does not know the declared `input_type` fields. In that case, encoding falls back to "inline the value directly" for every arg. Cross-implementation agreement still holds within the same-configuration cohort: two peers both running with or both running without the type extension produce identical params entities; a mixed pair may diverge on entity-valued args targeting hash fields.

**Closure-mode application.** In closure mode, the `args` map keys correspond to the closure's declared parameter names. Arguments are evaluated and bound to parameter names in the closure's captured scope before the body is evaluated. No type assembly is needed — the closure defines its own parameter list.

#### compute/if

Conditional evaluation.

```
compute/if := {
  fields: {
    condition: {type_ref: "system/hash"}                        ; Hash of expression (evaluates to truthy/falsy)
    then:      {type_ref: "system/hash"}                        ; Hash of expression (evaluated if truthy)
    else:      {type_ref: "system/hash", optional: true}        ; Hash of expression (evaluated if falsy)
  }
}
```

**MUST** be a special form — the non-taken branch **MUST NOT** be evaluated.

#### compute/let

Bind names in a scope, then evaluate a body expression.

```
compute/let := {
  fields: {
    bindings: {array_of: {type_ref: "primitive/any"}}           ; [{name: string, value: system/hash}, ...]
    body:     {type_ref: "system/hash"}                         ; Hash of expression to evaluate with bindings
  }
}
```

Each binding maps a `name` to an entity hash. The hash identifies an entity whose evaluated value is bound to that name.

```
binding := {
  name:  string        ; Binding name, visible in body via compute/lookup/scope
  value: system/hash   ; Hash of expression entity to evaluate and bind
}
```

**`compute/let` is sequential (`let*`).** Bindings **MUST** be evaluated in declaration order. Each binding's value expression is evaluated in the scope accumulated from all prior bindings in the same `let` block. Later bindings MAY reference earlier bindings via `compute/lookup/scope`. Implementations MUST NOT use parallel binding semantics, where each binding's value expression evaluates only in the outer scope without seeing prior bindings in the same block.

Example:
```
let x = 5
    y = x + 1    ; y evaluates to 6 — x is in scope from the previous binding
in y + 1         ; evaluates to 7
```

This matches the pseudocode in §4.1 and the intuitive behavior users expect from spreadsheet-style expressions.

#### compute/lambda

Create a function value. Does **NOT** evaluate the body.

```
compute/lambda := {
  fields: {
    params: {array_of: {type_ref: "primitive/string"}}          ; Parameter names
    body:   {type_ref: "system/hash"}                           ; Hash of unevaluated body expression
  }
}
```

Evaluation produces a `compute/closure` entity capturing the current scope.

### 2.2 Inline Expression Types

Syntactic sugar for common operations. These avoid `compute/apply` indirection for arithmetic, comparison, and logic. Both inline and apply forms **MUST** be supported and **MUST** produce identical results.

#### compute/arithmetic

```
compute/arithmetic := {
  fields: {
    op:    {type_ref: "primitive/string"}       ; "add" | "sub" | "mul" | "div" | "mod"
    left:  {type_ref: "system/hash"}            ; Hash of left operand expression
    right: {type_ref: "system/hash"}            ; Hash of right operand expression
  }
  constraints: {
    op: {one_of: ["add", "sub", "mul", "div", "mod"]}
  }
}
```

**Arithmetic result types (normative).** All arithmetic operations follow these rules:

1. **Type promotion.** If either operand is a float, both operands are promoted to IEEE 754 binary64 before the operation. The result is a float.
2. **Integer arithmetic.** If both operands are integers, the result is an integer — except for non-exact division (see below).
3. **Division float promotion.** `div` with two integer operands produces an integer if the division is exact (zero remainder), otherwise a float. `div(10, 2)` → `5` (integer). `div(7, 2)` → `3.5` (float).
4. **Truncated mod (integer, signed).** `mod` returns the truncated remainder; the result's sign matches the dividend (left operand). `mod(7, 3)` → `1`; `mod(-7, 3)` → `-1` (operands interpreted signed per rule 9 — these examples evaluate as written, no casts). `mod` is integer-only: a **float operand to `mod` → `type_mismatch`** (rule 1's float promotion applies to `add`/`sub`/`mul`/`div`, not `mod`).
5. **Division by zero.** Integer `div` or `mod` by zero produces a `division_by_zero` error. Float division by zero follows IEEE 754: `div(1.0, 0.0)` → `+Inf`, `div(-1.0, 0.0)` → `-Inf`, `div(0.0, 0.0)` → `NaN`.
6. **Operand types.** Both operands MUST be numeric (integer or float). Non-numeric operands produce a `type_mismatch` error.
7. **IEEE 754 special value encoding.** `+Inf`, `-Inf`, and `NaN` MUST encode to their canonical CBOR half-precision representations (0xf97c00, 0xf9fc00, 0xf97e00) per RFC 8949 §3.9. Implementations MUST canonicalize NaN to a single quiet NaN bit pattern before encoding.
8. **Integer arithmetic is 64-bit two's-complement; `add`/`sub`/`mul` are sign-agnostic.** In two's-complement these three operations produce identical bit patterns whether operands are read as signed or unsigned — so there is no int/uint decision and no "mixed-operand" case: `add(3, -1)` = `2`. Results wrap modulo 2⁶⁴ (one 64-bit width; there is no separate per-type width). An implementation with arbitrary-precision host integers MUST truncate to 64 bits after each such operation. No checked/saturating variant (a future op if needed).
9. **`div` / `mod` / `compare` use signed interpretation by default.** These are the only sign-sensitive integer operations in compute (the high bit's meaning differs signed vs unsigned). Signed-default matches the common case and rule 4's examples (which evaluate as written — no casts). Unsigned `div`/`mod`/`compare` on a value in [2⁶³, 2⁶⁴) is obtained by `compute/numeric-cast → primitive/uint` on the operand immediately before the operation (the WASM `div_u` role, reached by explicit conversion rather than a separate opcode). *The `primitive/int` / `primitive/uint` distinction is a **type-system annotation**: a value's classification follows its CBOR major type (non-negative → uint, negative → int) for typing/constraints, but it does not steer evaluation.*
10. **Canonical wire encoding of integer results.** A 64-bit integer result MUST be canonically encoded by its **signed** two's-complement interpretation: bit 63 clear → CBOR major type 0 (the non-negative value); bit 63 set → major type 1 (the negative two's-complement value). One wire form per result → one content hash → cross-impl agreement. (Bit-for-bit agreement alone is insufficient — CBOR encodes integers by sign, so without this rule the same result could encode two ways.) A result intended as unsigned in [2⁶³, 2⁶⁴) is produced by `compute/numeric-cast → primitive/uint`, which yields a genuinely non-negative number encoding as major type 0.
11. **`numeric-cast` is eager; the unsigned interpretation lives *syntactically* at the operation.** For the int↔uint case, a `compute/numeric-cast → primitive/uint` makes the consuming `div`/`mod`/`compare` unsigned **only when the cast is the direct operand entity of that operation.** Any indirection drops the unsigned intent and the operation is signed-default — a `compute/let` binding, a `compute/if` branch, a `compute/lookup/scope`, a `compute/construct` field, or a closure-arg binding. So `div(numeric-cast(y, uint), 2)` is unsigned, but `let y = numeric-cast(x, uint) in div(y, 2)` and `div(if(c, numeric-cast(x, uint), x), 2)` are signed-default (the cast is not the direct operand). This keeps signedness a property of the *operation* — statically observable from the expression graph, requiring no value-level tag carrier — consistent with rule 8 (signedness is not a value-level tag) and with WASM/LLVM (`div_s`/`div_u` chosen at the op). *(A standalone or indirected `numeric-cast → uint` reinterprets the bits and yields the non-negative **magnitude** — CBOR major type 0, per rule 10's exception, **not** signed-canonical (the `v314_cast_int_to_uint_negative` vector confirms `cast(-1, uint)` → `2⁶⁴−1`). The cast's value-conversion and its major-0 encoding always apply; what indirection drops is only the **operation-level unsigned intent** for a consuming `div`/`mod`/`compare`.)*

**A note for readers coming from Go / Rust / TypeScript.** Compute does not carry `int`/`uint` as a *value* type the way those languages do. Integer values are 64-bit two's-complement bit patterns; `int`/`uint` are type-system annotations (intent), and arithmetic operates on the patterns. So a `uint` does not "stay uint" through arithmetic: `add`/`sub`/`mul` are sign-agnostic (rule 8), the canonical result is encoded signed (rule 10), and you apply `numeric-cast` at the point you need unsigned `div`/`mod`/`compare` (rule 11) — not at the point you define the value. This is the WASM/LLVM/JVM model: integer types are widths, signedness is a property of operations.

#### compute/compare

```
compute/compare := {
  fields: {
    op:    {type_ref: "primitive/string"}       ; "eq" | "neq" | "lt" | "gt" | "lte" | "gte"
    left:  {type_ref: "system/hash"}            ; Hash of left operand expression
    right: {type_ref: "system/hash"}            ; Hash of right operand expression
  }
  constraints: {
    op: {one_of: ["eq", "neq", "lt", "gt", "lte", "gte"]}
  }
}
```

**Comparison semantics (normative).** `eq` and `neq` accept any operand types: values of incompatible types are never equal (`eq` returns `false`, `neq` returns `true`). Ordering operations (`lt`, `gt`, `lte`, `gte`) require both operands to be numeric or both to be strings. Numeric comparisons use float promotion when operand types are mixed. String comparisons use lexicographic UTF-8 byte order — no Unicode normalization is applied; two strings that differ at the byte level are unequal regardless of visual equivalence. Other type combinations produce a `type_mismatch` error.

#### compute/logic

```
compute/logic := {
  fields: {
    op:    {type_ref: "primitive/string"}       ; "and" | "or" | "not"
    left:  {type_ref: "system/hash"}            ; Hash of left operand expression
    right: {type_ref: "system/hash", optional: true}  ; Hash of right operand (absent for "not")
  }
  constraints: {
    op: {one_of: ["and", "or", "not"]}
  }
}
```

#### compute/field

Extract a named field from an entity **or a record/map value** (N.5). The target is the value produced by evaluating the `entity` field's referenced expression; that value's own result is itself a valid navigation target, so `field`/`index`/`length` **compose to arbitrary depth** — `field(field(x,"a"),"b")`, `index(field(x,"xs"),0)`, and `field(index(xs,0),"k")` are all well-formed. An implementation MUST NOT restrict a navigation operator to entity-typed targets only.

```
compute/field := {
  fields: {
    name:   {type_ref: "primitive/string"}      ; Field name to extract
    entity: {type_ref: "system/hash"}           ; Hash of expression evaluating to an entity or record/map value
  }
}
```

> **Disambiguation is by kind, not by shape (v3.19b, N3).** A `kind:"entity"` value is navigated via its `.data`; a `kind:"value"` (record) value is navigated flat. Implementations **MUST NOT** distinguish entity-vs-record by key-shape (e.g. presence of `type`/`data`/`content_hash`). See the scope-binding value model in §2.3 (`compute/scope`) for the full rule and the `kind`-tagged binding it rests on.

#### compute/construct

Build an entity from fields.

```
compute/construct := {
  fields: {
    entity_type: {type_ref: "system/type/name"} ; Type name for constructed entity
    fields:      {map_of: {type_ref: "system/hash"}}  ; Named field hashes (evaluated to construct entity)
  }
}
```

#### compute/index

Index into an array — the element at a position.

```
compute/index := {
  fields: {
    array: {type_ref: "system/hash"}            ; Hash of array expression
    index: {type_ref: "system/hash"}            ; Hash of index expression (evaluates to an integer)
  }
}
```

Returns the element at the (evaluated) `index` of the (evaluated) `array`. Pure (a deterministic function of the values), core, and override-prohibited like `compute/field`. Edge cases (normative):
- **Out-of-range index → `index_out_of_range` error.** Negative indices are out of range — there is no from-end (Python-style) indexing. A `uint`-annotated index (e.g. `cast(-4, uint)`) is **not** a `type_mismatch`: `int`/`uint` are annotations, not distinct value types (§2.2), so any integer bit-pattern is a valid index *argument*; an out-of-bounds magnitude — whether read signed (negative) or unsigned (≥ length) — is `index_out_of_range`. *(Ruled from the compute corpus's first cross-impl run — `ARCH-RESPONSE-COMPUTE-CORPUS-FIRST-RUN`, R3/F-2.)*
- **`index` on `null` or a non-array value → `type_mismatch` error.**

#### compute/length

The element count of an array.

```
compute/length := {
  fields: {
    array: {type_ref: "system/hash"}            ; Hash of array expression
  }
}
```

Returns the element count of the (evaluated) `array`. Pure, core, override-prohibited. Edge cases (normative):
- **Empty array → `0`.**
- **`length` on `null` or a non-array value → `type_mismatch` error.**

#### compute/numeric-cast

Convert a numeric value between numeric primitive types. **Intra-numeric only** — the value matrix is exactly {`primitive/int`, `primitive/uint`, `primitive/float`} × {same}. The `numeric-` qualifier carries the scope; no general/non-numeric conversion is defined.

```
compute/numeric-cast := {
  fields: {
    value:   {type_ref: "system/hash"}          ; Hash of value expression (numeric)
    to_type: {type_ref: "system/type/name"}     ; Target numeric primitive type
  }
}
```

Conversion semantics (normative). Pure, core, override-prohibited:
- **int ↔ uint:** reinterpret the two's-complement bit pattern at 64-bit width (e.g. `int → uint` of `-1` → `2^64-1`; matches Go `uint64(i)`/`int64(u)`).
- **int/uint → float:** convert to IEEE 754 binary64. Magnitudes above 2^53 lose mantissa precision — this is **defined-lossy, not an error**.
- **float → int/uint:** truncate toward zero. **Out-of-range, `NaN`, and ±`Inf` → `cast_out_of_range` error.**
- **`to_type` not in {`primitive/int`, `primitive/uint`, `primitive/float`}, or `value` non-numeric (including `null`) → `type_mismatch` error.**

Interpretation is **eager and at the point of use** — see §2.2 arithmetic rule 11: a cast's effect is consumed by the immediately-following operation and does not flow through `compute/let` bindings. `numeric-cast.to_type` is a bare type-name string (`system/type/name`), matching `compute/construct.entity_type`.

### 2.3 Value Types

Produced during evaluation. Not written directly by users.

**Evaluating a value-type entity returns it unchanged (SA-1).** When `Evaluate` is applied to an entity whose type is a value type (`compute/closure`, `compute/scope`, `compute/result`, `compute/error`) — e.g. a `compute/apply` arg whose `system/hash` references a pre-computed `compute/closure` — it returns the value as-is, generalizing the `compute/lookup/hash` "return non-expressions as values" rule (§4.1). This lets pre-computed values be threaded directly as args.

#### compute/closure

```
compute/closure := {
  fields: {
    params: {array_of: {type_ref: "primitive/string"}}
    body:   {type_ref: "system/hash"}                   ; Hash of body expression
    env:    {type_ref: "system/hash", optional: true}   ; Hash of captured environment (compute/scope)
  }
}
```

A closure is a content-addressed entity. Two closures with identical body, params, and environment have the same hash.

#### compute/scope

```
compute/scope := {
  fields: {
    bindings: {map_of: {type_ref: "system/compute/scope-binding"}}   ; name → kind-tagged binding (v3.19b)
  }
}

system/compute/scope-binding :=
    {kind: "entity", entity_hash: {type_ref: "system/hash"}}    ; an entity, referenced by hash
  | {kind: "value",  value: {type_ref: "primitive/any"}}        ; an inline primitive/record value
```

**The scope-binding value model (v3.19b).** A scope binding is **kind-tagged**: an inline value, or a hash reference to an entity. This makes the captured scope content-addressed and self-describing, and it is the canonical rule for navigation, capture, and (when needed) cross-peer transfer. (Replaces the v3.18 `primitive/any` bindings, under which a captured `entity.Entity` round-tripped to its envelope shape and broke field navigation / disambiguation.)

- **N1 — reference, don't duplicate (one rule, three boundaries).** Wherever an entity- or `compute/closure`-valued thing is placed into another entity's data — **scope bindings, `compute/construct` fields, and `compute/apply` args** — it is referenced by content hash into the content store and tagged with its kind, never inlined. This is the materialized-subtree model (V7 §3) applied uniformly; `compute/apply` args' `input_type` consultation (V30) is the typed-encoding case of the same rule.
  > **`compute/error` is deliberately not in that list `[corrected v3.23]`.** It was, and it was wrong at all three sites: an error reaching any of them **short-circuits** (§4.1 `is_error`, and the short-circuit `[MUST]` in §7.2 names all three), so it is never placed into the data and N1 never applies to it. The listing was unreachable, and it is where one implementation's reading of the construct branch came from. **An error materializes where it is *written* — the §7.2 `result_path` and SA-9 `store` — never where it is *consumed*.**
  >
  > **Scoped, not reversed `[v3.26]`.** The sentence above is a **consumption-site** invariant, and its premise — *"it is never placed into the data"* — was true when written and stopped being true at v3.25. §3.5's collection primitives created **data positions**, where an error is **contained in a value** rather than consumed, so N1 **does** apply to it there. **Which positions those are is decided by §3.5's places-without-reading rule, not by an enumeration kept here** `[v3.27]` — today `assoc`'s `value`, `concat`'s elements, `group-by`'s `members`, `map`'s output element and `fold`'s accumulator, and §3.5's table is the single home for that list. In a contained position the error materializes **code-only, by bare `system/hash`** (§3.5), except where §3.5's evaluation-limit rule short-circuits instead. Everywhere else — `compute/construct`, `field`, `arithmetic`, `compare`, `logic`, `apply`'s consumed operands, `if`'s condition — the §7.2 short-circuit is unchanged, and **an error reaching materialization from any of those is still the defect this note names.** An implementation guarding that path should add the carve-out, not remove the guard.
- **N3 — navigation is by kind, not by shape.** `compute/field`/`compute/index`/`compute/length` on a `kind:"entity"` value navigate its `.data`; on a `kind:"value"` (record) value navigate it flat. Implementations **MUST NOT** distinguish entity-vs-record by inspecting keys (e.g. presence of `type`/`data`/`content_hash`) — such heuristics misfire on legitimate records. (This pins the N.5 disambiguation deferred from v3.19a; it resolves a symmetric cross-impl divergence — flat-read was wrong for entity envelopes, envelope-peel wrong for records — for all implementations.)
- **N4 — binding resolution inherits the closure's authorization.** When `load_scope` (§4.3) resolves a binding's `entity_hash`, the resolve rides the authorization already granted to the closure; the binding entity need **not** be `is_compute_type` (§4.2) or in the sealed set. The closure was authorized at creation, and its bindings are structurally part of it.
- **N4a — resolution is eager (normative; ratified 3/3 cross-impl).** `load_scope` resolves **all** `kind:"entity"` bindings at apply time (when the scope is loaded), **not** lazily on first access. Consequently an unresolvable binding surfaces as `scope_unreachable` (N8) at apply time regardless of whether the closure body reads it — whole-scope validity is checked up front. ("At apply time" throughout this model means eager. The earlier "lazy" lean was a mis-attribution; all three impls resolve eagerly, and the eager reading is what the "at apply time" wording elsewhere in this section already implies.)
- **N8 — missing binding → `scope_unreachable`.** If a binding hash resolves in neither the local content store nor the envelope `included`, `load_scope` yields a `compute/error{code: "scope_unreachable"}` at apply time — an error *value* (status 200, §1.5 / F10), not a transport failure.
- **N7 — cross-peer transfer: semantics pinned, wire deferred.** When a `compute/closure` crosses a peer boundary, its reachable subtree (closure → `compute/scope` → binding entities) is materialized into the envelope `included` map — the same mechanism continuation cross-peer dispatch uses (`EXTENSION-CONTINUATION §916`). This is the **normative semantics**. The wire *implementation* (subtree-walk + `included` population + receiver-side resolution) is **deferred until a consumer exists** (e.g. peer handoff); same-peer resolution via the local content store is the path implementations provide today. Adding the wire later **implements this rule** — it needs no spec redesign.

**Canonical encoding (N2 — RATIFIED cross-impl).** The `bindings` map and each binding are ECF-canonical (`ENTITY-CBOR-ENCODING.md §4.1`: map keys sorted by encoded byte length, then lexicographically). Within a binding the keys sort `kind` (4) before `entity_hash` (11) or `value` (5). The `kind` tag is an **explicit discriminator**, so a binding's kind is known by construction — it is **never** inferred from the value's byte-length or shape. (A length/shape test would be fragile: `system/hash` is variable-length with an *extensible* multicodec-style LEB128 varint format-code per §1.2 — "33 bytes" is only today's `ecfv1-sha256` size — so the explicit tag, not a byte-pattern, is what carries the kind.) **Ratified via the cross-impl `validate-peer` hash-agreement check: all three implementations produce the bit-identical `compute/scope` content hash `ecf-sha256:3edc51381d12e22a22412890d329cbab87d98970362b5a4c1b3e0328effb9efd` for the canonical fixture** (the SHA-256 algorithm byte is `0x00` in all three). Rust + Python carry unit-test regression-detectors locking it in. Any future byte-level disagreement is amended via `PROPOSAL-COMPUTE-NAVIGATION-AND-ERROR-SURFACE`.

**Construct materialization & read-back navigation (v3.19c, option α — ratified three-way).** The compute value model (kind-tags) is **compute-internal**; what crosses to the rest of the system is a **normal bare entity**. Two normative consequences:

- **`compute/construct` materializes bare.** The materialized constructed entity — the form stored to the tree, returned from a handler, passed as a `compute/apply` arg, or sent on the wire (the four compute→non-compute crossings) — is a normal bare entity: an entity-/`compute/closure`-valued field is referenced by a **bare `system/hash`** (the value recursively materialized and stored, per V7 §1.4); a primitive/record field is inlined. Encoding is **by the runtime kind of the evaluated value, never the constructed type's declared schema** (keeping it type-extension-independent), so a constructed entity is byte-identical to the same entity built outside compute (`entity.NewEntity`) and identical across implementations. **No `kind` tags appear in materialized `data`** — kind-tagging is confined to `compute/scope` (the one typeless, round-tripped compute container). The *in-flight* representation is implementation-private; only the materialized form is normative (convergence is the `validate-peer` materialized-hash gate, == hand-built).
- **Read-back navigation returns the value (N3 clarification).** On a materialized bare entity, `compute/field`/`index`/`length` return a field's value **as-is**; a `system/hash` field yields the hash value — follow it explicitly with `compute/lookup/hash`. An implementation **MUST NOT** identify or auto-resolve a reference by its **byte-length or shape**: `system/hash` is variable-length with an extensible multicodec-style LEB128 varint format-code (§1.2; "33 bytes" is only today's `ecfv1-sha256` size), so a fixed-length test is both the shape-heuristic class N3 forbids *and* a crypto-agility bug (it breaks when the hash algorithm changes or a format code ≥ `0x80` widens the prefix). References are identified by **type** and handled by **structural deconstruction** (parse the varint format-code, then the digest — never assume a length). Navigation composes transparently **only where the kind is known** (in-flight typed values; kind-tagged `compute/scope` bindings); on a bare materialized entity, a reference is followed explicitly.

### 2.4 Result and Error Types

#### compute/result

Wraps a primitive evaluation result.

```
compute/result := {
  fields: {
    value:      {type_ref: "primitive/any"}
    expression: {type_ref: "system/hash"}               ; Hash of source expression
  }
}
```

Entity-typed results from `compute/construct` retain their natural type and are **NOT** wrapped in `compute/result`.

#### compute/error

```
compute/error := {
  fields: {
    code:       {type_ref: "primitive/string"}          ; Error code (§9.1) — the ONLY materialized field
    message:    {type_ref: "primitive/string", optional: true}  ; In-flight diagnostic; NOT materialized (see below)
    at:         {type_ref: "primitive/string", optional: true}  ; In-flight diagnostic; NOT materialized
    expression: {type_ref: "system/hash", optional: true}  ; In-flight diagnostic; NOT materialized
  }
}
```

**Materialized `compute/error` is content-hashed over `code` alone (normative — cross-impl determinism; v3.21 provisional, `PROPOSAL-COMPUTE-ERROR-MATERIALIZATION-DETERMINISM`, validated intra-Go — cross-impl gate: Python+Rust materialize code-only + a materialized-error vector runs three-way).**
When a `compute/error` **materializes** — written to a `result_path` (§7.2), stored via SA-9 `store`,
or sent on the wire as part of a materialized subtree downstream of one of those writes (the compute→non-compute crossings, §2.3 N1) —
its canonical content is exactly `{code}`. `message`, `at`, and `expression` are **diagnostic-only**: they MAY
appear in the *in-flight / dispatch-boundary* representation of an error (the handler-dispatch status-200
error-as-value return, §3.7 / the F10 surface; a debugging view), but they MUST **NOT** be part of the bytes
V7 content-addresses. The reason is load-bearing: `message` is unpinned prose (§9.1 pins codes, not strings),
`at` is an impl-dependent attribution point, and `expression` is the hash of *whichever* sub-expression an impl
blames — so if any of the three entered the content hash, two conformant peers writing the **same** error to
the **same** path would produce **different** entity hashes, breaking AE-1 materialized-boundary equivalence,
V7 content-dedup, cross-peer sync, and any reactive consumer keyed on the result hash. Two errors with the same
`code` **are** the same materialized entity — that is correct content-addressing. This is the error-side of the
"only the materialized form is normative; the in-flight representation is implementation-private" rule (§2.3 N1
/ the `compute/construct` materialization note). **Any materialized error field beyond `code` MUST first be
proven a pure function of the IR + inputs** (not of impl attribution). *(Ruled from the compute corpus's first
cross-impl run — `ARCH-RESPONSE-COMPUTE-CORPUS-FIRST-RUN`, Q1; the corpus's `code`-strict error comparison is
exactly this materialized boundary.)*

### 2.5 Subgraph Metadata Type

```
system/compute/subgraph := {
  fields: {
    root_expression_path: {type_ref: "system/tree/path"}
    root_expression:      {type_ref: "system/hash"}
    installation_grant:   {type_ref: "system/hash"}
    installed_by:         {type_ref: "system/hash"}
    result_path:          {type_ref: "system/tree/path"}
    status:               {type_ref: "primitive/string"}
  }
}
```

| Field | Description |
|-------|-------------|
| `root_expression_path` | Tree path where the root expression entity lives |
| `root_expression` | Content hash of the root expression at installation time (audit record) |
| `installation_grant` | Content hash of the caller's capability at installation time |
| `installed_by` | Content hash of the installer's identity entity |
| `result_path` | Tree path where reactive results are written |
| `status` | `"active"` (normal) or `"frozen"` (error condition — `compute/error` at result_path, reactive triggers skipped) |

### 2.6 Install/Uninstall Request and Response Types

```
system/compute/install-request := {
  fields: {
    result_path: {type_ref: "system/tree/path", optional: true}
                  ; Override for result storage path.
                  ; Default: {root_expression_path}/result
                  ; Handler-write target — created under the handler's grant.
  }
}

system/compute/install-result := {
  fields: {
    subgraph_path:     {type_ref: "system/tree/path"}
    impure_operations: {type_ref: "primitive/any"}
    result_path:       {type_ref: "system/tree/path"}
  }
}

; uninstall has no params content — the subgraph path is carried in
; EXECUTE.resource per the path-as-resource convention (V7 §3.2).
; Callers send the empty-params shape: a primitive/any entity with
; canonical CBOR-encoded empty map data.
```

`eval`, `install`, and `uninstall` all carry their target tree path in `EXECUTE.resource.targets[0]` per the path-as-resource convention (ENTITY-CORE-PROTOCOL.md §3.2):

- `eval` — resource is the expression path the handler reads.
- `install` — resource is the `root_expression_path` the handler audits and from which the subgraph is built.
- `uninstall` — resource is the subgraph path the handler removes.

`install`'s `result_path` stays in `params` because it's a *handler-write target* (the handler creates entries there under its own grant), not a path the caller needs separate authorization on. The caller's grant covers `system/compute:install` on the resource (the root expression path); the handler's grant covers all other I/O the install performs.

---

## 3. Handler

### 3.1 Compute Handler Manifest

```
system/handler := {
  pattern:    "system/compute/*"
  name:       "compute"
  operations: {
    eval: {
      input_type: "primitive/any"               ; Compute expression entity or eval params
      output_type: "primitive/any"              ; Result value or compute/error
    }
    install: {
      input_type: "system/compute/install-request"
      output_type: "system/compute/install-result"
    }
    uninstall: {
      input_type: "primitive/any"                ; empty-params per V7 §3.2
      output_type: "system/protocol/status"
    }
  }
}
```

Manifest at pattern path `system/compute`. Index entry at `system/handler/system/compute`. The handler matches URIs under `system/compute/*`, consistent with other system infrastructure (`system/inbox/*`, `system/subscription/*`).

### 3.2 Eval Operation

Receives an EXECUTE requesting evaluation of a compute expression.

```
handle_eval(ctx, params):
  ; The expression path comes from EXECUTE.resource per the path-as-resource
  ; convention (V7 §3.2). params optionally carries operation knobs (budget).
  if ctx.resource is null or len(ctx.resource.targets) != 1:
    return error(400, "ambiguous_resource",
      "eval requires exactly one resource target (the expression path)")
  expression_uri = ctx.resource.targets[0]

  expression = ctx.entity_tree.get(expression_uri)
  if expression is null: return error(404, "not_found", "No entity at path")
  if not is_compute_expression(expression):
    return error(400, "invalid_expression", "Entity at path is not a compute expression")

  ; Initialize budget
  budget = init_budget(params, ctx.capability, ctx.bounds)

  ; Set subgraph root for relative path resolution.
  ; For explicit eval, the root is the expression URI — the tree path of the
  ; expression being evaluated. For installed subgraphs (reactive re-eval),
  ; the root comes from subgraph metadata (root_expression_path). Same value,
  ; different source.
  ctx.subgraph_root = expression_uri

  ; Evaluate
  scope = empty_scope()
  result = evaluate(expression, scope, budget, ctx)

  ; F10: an evaluated compute/error is a *value* (errors propagate like NaN, §1.5) —
  ; evaluation completed, its result is an error. Return it at status 200 with the
  ; compute/error body. Reserve 4xx for dispatch/transport/auth failures (handler
  ; not found, pre-eval authorization, malformed request). Callers detect a computed
  ; error by result.type == "compute/error", not by HTTP status.
  return {status: 200, result: result}
```

**Entity-native handler dispatch (v3.9, E1).** The compute evaluator can be invoked with a pre-populated scope by the handler dispatch layer. When a handler with `expression_path` (ENTITY-CORE-PROTOCOL.md §3.7) is dispatched, the dispatch layer invokes compute eval with scope bindings `{operation, params, resource, caller_capability}` from the request context. The expression accesses these via `compute/lookup/scope`. The result is unwrapped at the dispatch boundary: `compute/result` → extract value, `compute/error` → **returned as the result entity at status 200** (error-as-value, F10 — *not* translated into a transport error response), bare primitive → wrap as `{type: "primitive/any", data: <primitive>}`, entity result → return as-is. The wire format requires typed entities in responses. See ENTITY-CORE-PROTOCOL.md §6.6 for the entity-native dispatch pseudocode.

**Impure-op permission denial during eval is an error *value* (normative clarification — v3.19c).** A `permission_denied` that arises from *evaluating* an impure operation — a `compute/lookup/tree` outside the authorized scope, a `store`/dispatch the capability or the §4.1 dual-check blocks — is a propagated `compute/error` **value returned at status 200**, exactly like any other propagated error (§1.5 / F10 above). A `4xx`/`403` is reserved for authorization of the **request itself, before evaluation**: the eval or `system/compute:install` EXECUTE being unauthorized, or the §3.3 install pre-audit rejecting an under-capable subgraph. The §3.3 / pre-flight capability audit MAY still fail-fast, but for explicit eval an impure-op denial that manifests *during* evaluation surfaces as the F10 value, **not** re-raised as a transport `4xx`. (This is the determinism-safe line: a pre-flight-`403`-vs-runtime-`200` split keyed on whether the denied target is statically determinable would make the status implementation-dependent. Resolves the §588 / pre-flight-audit ambiguity; conformance vectors for impure-op denial during eval expect `200 + compute/error{permission_denied}`. See `PROPOSAL-COMPUTE-NAVIGATION-AND-ERROR-SURFACE §3.5`.)

Compute expressions can be stored at any tree path. To evaluate an expression, send EXECUTE to the compute handler with the expression's tree path in `resource`:

```
EXECUTE {
  uri:       "entity://peer/system/compute"
  operation: "eval"
  resource:  {targets: ["local/data/my-expression"]}
  params:    <empty primitive/any, or {budget: ...}>
}
```

### 3.3 Install Operation

Registers a compute subgraph for reactive evaluation. The caller provides the root expression path and the compute handler audits the subgraph, records the installation grant, and enables dependency tracking. Expression entities remain at their original tree paths — the handler stores tracking metadata in its own managed namespace (`system/compute/processes/`).

```
handle_install(ctx, params):
  ; Root expression path comes from EXECUTE.resource per the path-as-resource
  ; convention (V7 §3.2). params optionally carries result_path override and budget.
  if ctx.resource is null or len(ctx.resource.targets) != 1:
    return error(400, "ambiguous_resource",
      "install requires exactly one resource target (the root expression path)")
  root_path = ctx.resource.targets[0]
  expression = ctx.entity_tree.get(root_path)
  if expression is null:
    return error(404, "not_found", "No expression at path")
  if not is_compute_expression(expression):
    return error(400, "invalid_expression", "Entity at path is not a compute expression")

  ; Phase 1: Audit the subgraph
  impure_ops = audit_subgraph(expression, ctx)
  ; impure_ops = {read_paths: [...], handler_targets: [...], write_paths: [...]}

  ; Phase 2: Verify caller's capability covers all impure operations
  for path in impure_ops.read_paths:
    if not check_path_permission("get", path, ctx.caller_capability):
      return error(403, "permission_denied",
        "Caller capability does not cover read: " + path)
  for target in impure_ops.handler_targets:
    ; Pre-flight check using core helper from V7 §5.2 (grant-probe without a
    ; synthetic EXECUTE). target.resource may be null (no resource field on the
    ; compute/apply, or dynamic) or a resource-target struct (static literal).
    ; Null resource keeps the prior behavior — handler/operation-only coverage.
    ; Static resources get full-resolution check at install. Dynamic resources
    ; are checked at runtime via the §4.1 dual-check or via the dispatch chain.
    if check_grant_covers(target.path, target.operation, target.resource,
                          ctx.caller_capability, ctx.local_peer_id) == DENY:
      return error(403, "permission_denied",
        "Caller capability does not cover handler: " + target.path + "." + target.operation)
  result_path = params.result_path or root_path + "/result"
  if not check_path_permission("put", result_path, ctx.caller_capability):
    return error(403, "permission_denied",
      "Caller capability does not cover result write: " + result_path)
  for path in impure_ops.write_paths:
    if not check_path_permission("put", path, ctx.caller_capability):
      return error(403, "permission_denied",
        "Caller capability does not cover write: " + path)

  ; Phase 2b: Validate compute/lookup/hash data references (v3.7, D5/D6)
  authorized_data_hashes = set()
  for entry in impure_ops.data_hashes:
    if entry.path is not null:
      ; Path hint — O(1) validation: read entity at path, verify hash, check grant
      tree_entity = ctx.entity_tree.get(entry.path)
      if tree_entity is null:
        return error(404, "not_found", "No entity at hint path: " + entry.path)
      if content_hash(tree_entity) != entry.hash:
        return error(400, "hash_mismatch",
          "Entity at " + entry.path + " has hash " + content_hash(tree_entity)
          + ", expression references " + entry.hash)
      if not check_path_permission("get", entry.path, ctx.caller_capability,
                                    "system/tree", ctx.local_peer_id):
        return error(403, "permission_denied",
          "Caller grant does not cover tree GET at: " + entry.path)
      authorized_data_hashes.add(entry.hash)
    else:
      ; No path hint — implementation-defined (reverse index, scan, or reject)
      return error(400, "no_authorization_path",
        "compute/lookup/hash without path hint requires reverse index or content_store_access")

  ; Phase 3: Create subgraph metadata in handler's managed namespace
  subgraph_id = deterministic_id(root_path)
  subgraph_path = "system/compute/processes/" + subgraph_id
  subgraph_entity = {
    type: "system/compute/subgraph",
    data: {
      root_expression_path: root_path,
      root_expression:      content_hash(expression),
      installation_grant:   content_hash(ctx.caller_capability),
      installed_by:         ctx.author,
      result_path:          result_path,
      status:               "active",
      authorized_data_hashes: list(authorized_data_hashes)
    }
  }
  ; The compute handler MUST persist the caller's capability entity to the content
  ; store before recording its content hash on the subgraph metadata. The reactive
  ; engine retrieves this entity by hash during re-evaluation (§7.2) to verify
  ; the grant has not been revoked or expired. Without persistence, the grant entity
  ; is only available during the install EXECUTE and is lost for future re-evaluations.
  ctx.content_store.put(ctx.caller_capability)
  ctx.entity_tree.put(subgraph_path, subgraph_entity)   ; write authorized by handler grant — see §6.3

  ; Phase 4: Register dependencies for reactive mode
  register_subgraph_dependencies(subgraph_path, root_path, expression, ctx)

  return {
    status: 200,
    result: {
      subgraph_path: subgraph_path,
      impure_operations: impure_ops,
      result_path: result_path
    }
  }
```

**Subgraph ID (normative derivation).** The `deterministic_id(root_path)` function MUST produce a stable, length-bounded, path-safe identifier using:

```
subgraph_id = base32_lower_no_padding(sha256(utf8_bytes(root_path)))
```

That is: UTF-8 encode the canonicalized root path, compute SHA-256 over the bytes, then encode the 32-byte digest as lowercase base32 without padding. The result is a 52-character string that fits in tree path segments without special characters and never collides within SHA-256's collision resistance.

All conformant implementations MUST use this derivation so that cross-peer subgraph inspection works consistently — a subgraph installed by Peer A at root path `app/cell/A1` is discoverable at the same `system/compute/processes/{subgraph_id}` on any peer that scans the namespace. Same root path always produces the same subgraph ID, so reinstalling the same expression path overwrites the previous metadata. The invariant: metadata lives under `system/compute/processes/` and is scannable for rebuild (§7.1).

**Note (v7.68).** The SHA-256 here is a *referential* algorithm choice for a local-namespace identifier — it is **not** a `content_hash_format` decision (the `subgraph_id` is not part of the content-address space; it is a deterministic path-segment identifier). All implementations MUST use SHA-256 here regardless of their configured `content_hash_format` (§1.2), precisely so that cross-peer subgraph inspection is consistent across a mixed-format cohort. This site is pinned so a future agility round does not mistake it for a `content_hash_format` dispatch site.

**Subgraph boundary.** A subgraph is defined by its root expression path, which is a tree node. All expressions reachable from the root expression (via hash references in expression data) are part of the subgraph. The installation grant covers the entire reachable graph from the root. The root expression path also serves as the resolution prefix for relative paths (§2.1) — data, helpers, and results organized as children of the root form a self-contained subtree that can be transferred and installed at a different tree prefix. This mirrors revision's trie model: a tree node defines a subtree, internally coherent, externally relocatable. Pure inline expression types (including `compute/index`, `compute/length`, `compute/numeric-cast`) carry only hash references in their data fields, so this generic reachability walk follows them with no type-specific audit hook. Likewise the **pure collection builtins** (`map`/`filter`/`fold`) require no install-time handler-target authorization grant — they perform no tree or capability access (SA-11); only `store` is authorization-gated at install time, via its `write_path`.

**Content store retention (normative).** An installed subgraph's metadata references entities by hash in its data fields: `installation_grant`, `root_expression`, and `authorized_data_hashes`. These are hash references in entity data, not tree bindings. Additionally, expression sub-entities (referenced by hash from parent expressions) may be content-store-only. GC implementations MUST treat these hashes as reachable — they are required for reactive re-evaluation (§7.2), dependency index rebuild (§7.1), and `compute/lookup/hash` resolution. The same reachability requirement applies to entities in the subgraph's tree subtree (expression, data, helpers at tree paths under `root_expression_path`). This parallels revision's requirement that version trie nodes in the content store are reachable from the version entry.

**Live suspended-state retention (normative — v3.19c).** The reachability rule above extends from installed-subgraph roots to **live runtime-captured state**: a reachable `compute/closure`, suspended continuation, or pending reactive evaluation keeps the entities its captured scope references (its `kind:"entity"` bindings, transitively) GC-reachable for as long as the suspended computation itself is reachable. (Uniform across the three suspended-state siblings — closure / continuation / reactive subgraph — so retention does not drift between them.) The full GC collector — eviction policy, the root-set definition for a returned closure across a restart, checkpoint semantics — is deferred; this clause is the invariant any collector MUST honor so a peer can resume a closure it shut down mid-computation. (Today the content store is treated as effectively unbounded; this rule anticipates the collector without specifying it.)

**Resume safety (normative — v3.19c).** If a suspended computation is resumed and a scope binding it requires resolves in neither the local content store nor (for a transferred closure) the envelope `included` map, resolution yields `compute/error{code: "scope_unreachable"}` at apply time — an error *value* (status 200, §1.5 / F10 / N8), **never** a silent substitution, a partial result presented as complete, or a transport fault. A peer MUST NOT resume a closure with a missing binding as though it were present. (So an over-aggressive or buggy collector that removes a needed binding degrades to a clean, attributable error, not corruption.)

**Subgraph audit algorithm.** The `audit_subgraph` function walks the expression graph from the root and collects three categories of impure operations for capability checking:

```
audit_subgraph(expression, ctx):
  read_paths      = []
  handler_targets = []   ; list of {path, operation}
  write_paths     = []   ; literal write paths only (dynamic paths deferred to runtime)
  data_hashes     = []   ; list of {hash, path} from compute/lookup/hash (v3.7, D3/D6)
  visited = set()
  audit_walk(expression, read_paths, handler_targets, write_paths, data_hashes, visited, ctx)
  return {
    read_paths:      read_paths,
    handler_targets: handler_targets,
    write_paths:     write_paths,
    data_hashes:     data_hashes
  }

audit_walk(entity, read_paths, handler_targets, write_paths, data_hashes, visited, ctx):
  if entity.hash in visited: return   ; Cycle detection
  visited.add(entity.hash)

  ; Collect tree reads (resolve relative paths against root)
  if entity.type == "compute/lookup/tree":
    path = entity.data.path
    if entity.data.relative == true:
      path = clean_path(root_path + "/" + path)
    read_paths.append(path)
    return

  ; Collect hash lookup targets for install-time authorization (v3.7, D3/D6)
  if entity.type == "compute/lookup/hash":
    hint_path = entity.data.path
    if hint_path is not null and entity.data.relative == true:
      hint_path = clean_path(root_path + "/" + hint_path)
    data_hashes.append({hash: entity.data.hash, path: hint_path})
    return

  ; Collect handler dispatches and literal store targets
  if entity.type == "compute/apply" and entity.data.path is not null:
    ; F5 install-time enforcement (v3.10): capability without resource is a static structural error.
    ; Statically checkable (field presence, not resolved value).
    if entity.data.capability is not null and entity.data.resource is null:
      return error("invalid_expression",
        "compute/apply with capability field MUST also have resource field")

    ; CP1 (v3.11): static-literal capability in-chain authorization check
    ; (in-chain, NOT rooted-at-author — V7 §5.5; see the §11.1 note).
    ; Run BEFORE F3 resource-coverage check — chain-root is cheaper (chain walk
    ; vs scope-coverage) and more fundamental (an unauthorized embedded cap
    ; should be rejected before reasoning about whether its scope covers the
    ; target). Distinct error codes (embedded_cap_unauthorized vs permission_denied)
    ; let callers distinguish the two failure modes.
    if entity.data.capability is not null:
      cap_ref = resolve(entity.data.capability, ctx)
      if cap_ref is not null and cap_ref.type == "compute/literal":
        cap_entity = resolve(cap_ref.data.value, ctx)  ; the actual cap entity
        if cap_entity is not null:
          ; R1 creator-authorization check via check_creator_authority (V7 §5.5).
          ; collect_authority_chain walks the full chain, verifies reachability,
          ; then checks whether the installer's identity is in the granter chain.
          (found, cap_chain, err) = check_creator_authority(cap_entity, ctx.execute.data.author, ctx)
          if err == ChainUnreachable:
            return error(404, "chain_unreachable",
              "Static compute/apply.capability authority chain not fully resolvable")
          if not found:
            return error(403, "embedded_cap_unauthorized",
              "Installer identity not in static compute/apply.capability chain")
        ; else: cap entity unreachable at install — surface as chain_unreachable
      ; else: dynamic capability — runtime dual-check applies (PROPOSAL-COMPUTE-APPLY-RESOURCE-CEILING F2)

    ; F3 (v3.10): collect resource target — static literals audited; dynamic resources deferred to runtime
    static_resource = null
    if entity.data.resource is not null:
      res = resolve(entity.data.resource, ctx)
      if res is not null and res.type == "compute/literal":
        ; res.data.value is a system/protocol/resource-target struct
        ; ({targets: [...], exclude: [...]}) — NOT a path string. check_grant_covers
        ; consumes this struct shape directly.
        static_resource = res.data.value
      ; else: dynamic — runtime check applies via §4.1 dual-check or dispatch chain

    handler_targets.append({
      path:      entity.data.path,
      operation: entity.data.operation,
      resource:  static_resource
    })
    ; Special case: store builtin with a literal path arg gets a static write_path entry
    if entity.data.path == "system/compute/builtins/store":
      store_path_hash = entity.data.args?["path"]
      if store_path_hash is not null:
        store_path_expr = resolve(store_path_hash, ctx)
        if store_path_expr is not null and store_path_expr.type == "compute/literal":
          write_paths.append(store_path_expr.data.value)
        ; else: dynamic store path — deferred to runtime capability check (§6.2)

  ; Recursively walk all hash references in expression data
  for field_value in entity.data.values():
    if field_value is system/hash:
      referenced = resolve(field_value, ctx)
      if referenced is not null:
        audit_walk(referenced, read_paths, handler_targets, write_paths, data_hashes, visited, ctx)

  ; Walk closure body and captured environment
  if entity.type == "compute/closure":
    if entity.data.env is not null:
      env = resolve(entity.data.env, ctx)
      if env is not null:
        audit_walk(env, read_paths, handler_targets, write_paths, data_hashes, visited, ctx)
    if entity.data.body is not null:
      body = resolve(entity.data.body, ctx)
      if body is not null:
        audit_walk(body, read_paths, handler_targets, write_paths, data_hashes, visited, ctx)
```

**Dynamic store path policy.** The `store` builtin MAY be called with a `path` argument that is the result of arbitrary computation rather than a `compute/literal`. Such dynamic paths cannot be audited statically at install time — they are not known until evaluation. The install audit MUST include only literal store targets in `write_paths`. Dynamic store targets MUST be capability-checked at runtime per §6.2 (store builtin and no-silent-escalation). This is a deliberate conservative-static / runtime-dynamic split: static literals get upfront authorization, dynamic targets get checked at the store call site.

**Walker relationship to §7.1.** `audit_subgraph` shares structure with `walk_tree_lookups` (§7.1) — both walk the expression graph with cycle detection and recursive hash resolution. `walk_tree_lookups` collects only tree-read dependencies for the reactive dependency index; `audit_subgraph` collects all four categories for installation-time capability checking. Implementations MAY factor them into one walker with multiple visitors.

**Audit scope (normative).** `audit_subgraph` walks the compute expression graph. Hash references that resolve to non-compute entities are skipped via `validate_compute_resolvable` (§4.2) — the audit does not traverse into non-expression entities. External data access is audited by collecting `compute/lookup/tree` paths, `compute/lookup/hash` target hashes, and `compute/apply` handler targets, not by following arbitrary hash references.

**Expressions without installation.** If a compute expression entity exists at a tree path but was not installed via the `install` operation (e.g., written directly via tree `put`), the compute handler MUST NOT reactively re-evaluate it. Reactive mode requires an installation grant. The expression can still be evaluated explicitly via the `eval` operation (using the caller's capability).

**Re-installation of a frozen subgraph.** When `install` is called for a root expression path that has an existing frozen subgraph (same `deterministic_id`), the handler re-audits the subgraph (Phase 1-2), overwrites the subgraph metadata with `status: "active"` (Phase 3), and re-registers dependencies (Phase 4). The install pseudocode handles this — the deterministic subgraph ID means the put overwrites the frozen metadata with fresh `"active"` metadata. Implementations SHOULD also clear any `compute/error` entity at the old result_path and perform an initial evaluation after installation. Re-installation is the universal recovery mechanism for frozen subgraphs (`cascade_limit`, `installation_grant_invalid`).

**Re-install atomicity on failure.** Re-installation is atomic with respect to failure: if the audit or capability check (Phase 1-2) fails during re-installation, the previous frozen subgraph metadata is preserved unchanged. The caller can retry with corrected inputs (different capability, different expression at the root path) without losing the frozen state. Only on successful audit does the frozen metadata get overwritten with fresh `"active"` metadata in Phase 3. Implementations MUST NOT partially update the subgraph metadata — Phases 1-2 are pre-flight validation; Phases 3-4 are the commit step.

**Capability requirements for install.** The caller's capability MUST cover every impure operation the subgraph will perform — reads, handler dispatches, and writes (including the `result_path`). The default `result_path` is `{root_expression_path}/result` — a child path. A capability scoped to a single exact path (e.g., `{resources: {include: ["app/cell/A1"]}}`) does NOT cover `app/cell/A1/result` and will fail Phase 2. Most practical reactive setups use subtree grants that cover both the expression and its result:

```
; Typical install capability (subtree grant covers expression + result):
{
  grants: [{
    handlers:  {include: ["system/compute"]},
    operations: {include: ["install"]},
    resources:  {include: ["app/*"]}            ; Covers app/cell/A1 AND app/cell/A1/result
  }, {
    handlers:  {include: ["system/tree"]},
    operations: {include: ["get", "put"]},
    resources:  {include: ["app/*"]}            ; Covers reads during audit + reactive writes
  }]
}
```

If a subtree grant is not possible and only a single-path grant is available, the caller MUST override `result_path` in the install request to a sibling path covered by the grant:

```
; Single-path grant with result_path override:
EXECUTE {
  uri:       "entity://peer/system/compute"
  operation: "install"
  resource:  {targets: ["app/cell/A1"]}              ; the root expression path
  params:    install-request {
    result_path: "app/cell/A1_result"                ; Sibling, not child
  }
}
```

The install handler will audit the override against the caller's capability as part of Phase 2.

### 3.4 Uninstall Operation

Removes a subgraph from reactive evaluation. Clears the dependency registrations. Does not delete the expression entities — they remain in the tree as inert data.

```
handle_uninstall(ctx, params):
  ; Subgraph path comes from EXECUTE.resource per the path-as-resource
  ; convention (V7 §3.2). params is the empty-params shape (V7 §3.2).
  if ctx.resource is null or len(ctx.resource.targets) != 1:
    return error(400, "ambiguous_resource",
      "uninstall requires exactly one resource target (the subgraph path)")
  subgraph_path = ctx.resource.targets[0]

  subgraph = ctx.entity_tree.get(subgraph_path)
  if subgraph is null or subgraph.type != "system/compute/subgraph":
    return error(404, "not_found", "No installed subgraph at path")

  ; Remove dependency registrations
  dependency_index.remove_subgraph(subgraph_path)

  ; Remove subgraph metadata from handler namespace
  ctx.entity_tree.delete(subgraph_path)              ; delete authorized by handler grant — see §6.3

  return {status: 200}
```

### 3.5 Builtin Handlers

Standard library handlers at `system/compute/builtins/*`:

| Handler Path | Operation | Description |
|---|---|---|
| `system/compute/builtins/arithmetic` | `eval` | `{op}` on `left`, `right` refs |
| `system/compute/builtins/compare` | `eval` | `{op}` on `left`, `right` refs |
| `system/compute/builtins/logic` | `eval` | `{op}` on `left`, `right` refs |
| `system/compute/builtins/field` | `eval` | `{name}` extracts field from `entity` ref |
| `system/compute/builtins/construct` | `eval` | `{entity_type}` builds entity from ref fields |
| `system/compute/builtins/map` | `eval` | Apply `fn` ref to each element of `collection` ref |
| `system/compute/builtins/filter` | `eval` | Keep elements where `fn` ref returns truthy |
| `system/compute/builtins/fold` | `eval` | Reduce `collection` using `fn` with `initial` value |
| `system/compute/builtins/store` | `eval` | Write `value` ref to tree at `path` (impure) |

Builtins **MUST** produce identical result hashes for identical input hashes (except `store`, which modifies tree state).

**Override prohibition.** The builtin handlers at `system/compute/builtins/*` are registered at peer bootstrap and **MUST NOT** be overridden. A handler registration request targeting a `system/compute/builtins/*` path **MUST** be rejected. The inline expression types (§2.2) and the builtin handler dispatches produce identical results — implementations MAY treat the handler dispatches as aliases for the inline types internally. Prohibiting overrides preserves cross-peer semantic determinism: two peers dispatching to `system/compute/builtins/arithmetic` cannot disagree on what `"add"` means. **This prohibition stands on its own and is not derived from any `system/*` prefix rule.** It binds **every** installation path — over the wire and in-process, at composition time and after — because the determinism argument above is about what `"add"` means to two peers, not about how a handler arrived or who installed it. **It is a cross-peer interoperability requirement, which is why it is a MUST here**: two peers that disagree about `system/compute/builtins/arithmetic` produce different results for the same expression. A peer's local install policy is its own; this one rule is not local.

**Builtin input type declarations.** Each builtin MUST declare an `input_type` for its operation so that `compute/apply` handler-mode (§2.1) can construct a properly-typed params entity via the V30 encoding rule. The input types for inline-equivalent builtins match the inline expression types (the handler form IS an alias for the inline form):

| Handler | Operation | Input type |
|---|---|---|
| `system/compute/builtins/arithmetic` | `eval` | `compute/arithmetic` |
| `system/compute/builtins/compare` | `eval` | `compute/compare` |
| `system/compute/builtins/logic` | `eval` | `compute/logic` |
| `system/compute/builtins/field` | `eval` | `compute/field` |
| `system/compute/builtins/construct` | `eval` | `compute/construct` |
| `system/compute/builtins/map` | `eval` | `system/compute/map-args` (collection + fn) |
| `system/compute/builtins/filter` | `eval` | `system/compute/filter-args` (collection + fn) |
| `system/compute/builtins/fold` | `eval` | `system/compute/fold-args` (collection + fn + initial) |
| `system/compute/builtins/store` | `eval` | `system/compute/store-args` (path + value) |
| `system/compute/builtins/range` | `eval` | `system/compute/range-args` (n) — **v3.24** |
| `system/compute/builtins/group-by` | `eval` | `system/compute/group-by-args` (collection + fn) — **v3.24** |
| `system/compute/builtins/concat` | `eval` | `system/compute/concat-args` (collections) — **v3.24** |
| `system/compute/builtins/assoc` | `eval` | `system/compute/assoc-args` (collection + index + value) — **v3.24** |

The collection builtins (`map`, `filter`, `fold`) and `store` use dedicated args types because they have no inline form. **These args types are pinned in this spec — not implementation-owned** (a transferable IR requires every peer to agree on their shape; the §3.5 override-prohibition determinism guarantee extends to them). All four are defined here.

**`system/compute/map-args`:**

```
system/compute/map-args := {
  fields: {
    collection: {type_ref: "system/hash"}   ; Hash of array expression
    fn:         {type_ref: "system/hash"}    ; Hash of a unary closure (element → element)
  }
}
```

**`system/compute/filter-args`:**

```
system/compute/filter-args := {
  fields: {
    collection: {type_ref: "system/hash"}   ; Hash of array expression
    fn:         {type_ref: "system/hash"}    ; Hash of a unary closure (element → bool); the predicate (F11: renamed from `predicate` for uniformity with map/fold)
  }
}
```

**`system/compute/fold-args`:**

```
system/compute/fold-args := {
  fields: {
    collection: {type_ref: "system/hash"}   ; Hash of array expression
    fn:         {type_ref: "system/hash"}    ; Hash of a binary closure (acc, element → acc)
    initial:    {type_ref: "system/hash"}    ; Hash of the initial accumulator value
  }
}
```

**Observable semantics (normative, pinned).** `map` applies `fn` to each element in index order, returning a new array of the results. `filter` returns a new array of the elements for which `fn` (the predicate) evaluates truthy, in index order. `fold` threads `initial` through `fn(acc, element)` left-to-right and returns the final accumulator. All three are defined over `compute/index`/`compute/length` (§2.2) — a canonical compute-expression definition over `index`/`length`/recursion MAY serve as the implementation, or a native implementation that produces hash-equal results.

#### The v3.24 collection primitives — `range`, `group-by`, `concat`, `assoc`

Four additions, all **MUST-given-COMPUTE** (§10.1): they produce boundary bytes, so a peer that computes different results is not a slower peer but a divergent one. Their args types are pinned here on the same reasoning as `map`/`filter`/`fold` above.

```
system/compute/range-args := {
  fields: { n: {type_ref: "system/hash"} }        ; Hash of a non-negative integer expression
}

system/compute/group-by-args := {
  fields: {
    collection: {type_ref: "system/hash"}          ; Hash of array expression
    fn:         {type_ref: "system/hash"}          ; Hash of a unary closure (element → key)
  }
}

; group-by's RESULT element. The one result type this section pins; the others
; return arrays of the input's own element type and need no declaration.
system/compute/group := {
  fields: {
    key:     {type_ref: "primitive/any"}           ; The derived key, as fn returned it
    members: {array_of: {type_ref: "primitive/any"}}  ; The group's elements, in input index order
  }
}

system/compute/concat-args := {
  fields: { collections: {type_ref: "system/hash"} }   ; Hash of an expression evaluating to an array of arrays — v3.27
}

system/compute/assoc-args := {
  fields: {
    collection: {type_ref: "system/hash"}          ; Hash of array expression
    index:      {type_ref: "system/hash"}          ; Hash of an integer expression
    value:      {type_ref: "system/hash"}          ; Hash of the replacement element
  }
}
```

**Observable semantics (normative, pinned).**

- **`range(n)`** returns the array `[0 … n-1]`, empty when `n` is `0`. **Single-argument form only** — a start offset is expressed inside the lambda, not as a second parameter. It exists because `map`/`filter`/`fold` pass an element and not its index, so every program that needs an index carries a static index array and indexes back into its data. **A negative `n`, or an `n` exceeding the maximum representable array length, is a `count_out_of_range` error-as-value `[MUST, v3.25]`** — *not* `type_mismatch`, on §2.2's ruled reasoning that `int`/`uint` are annotations rather than distinct value types, so any integer bit-pattern is a well-formed *argument* and an out-of-domain **magnitude** is not a type error. It is likewise not clamped to the empty array: `n` is a loop bound, so a silent `[]` propagates through every downstream `map`/`filter`/`fold` and yields a well-formed wrong answer carrying no error.
- **`group-by(collection, fn)`** applies `fn` to each element to derive a key and returns the elements grouped by that key in **one pass**. **The result is an array of `system/compute/group`, each carrying its `key` and its `members` `[MUST, v3.25]`** — the key is part of the result and is not dropped, because the shapes this primitive exists to serve (a histogram, a bucketed aggregation, a router) are exactly the ones whose output is unreadable without its labels. Within each group, elements retain their input index order; **groups are ordered by first appearance of their key** — not by key sort order, which would require a total order over arbitrary key types that this extension does not define. Key **equality** is byte-identity over the canonical ECF encoding of the derived key — the protocol's own value identity, which is defined for every key type `fn` may return. **For an entity-valued key that is the encoding of its MATERIALIZED form `[MUST, v3.27]`** — the bare-entity bytes, never the in-flight value. The in-flight representation of an entity-valued key is kind-tagged in some implementations (§2.3 N1 confines kind-tagging to `compute/scope`), so encoding it would make an implementation-private representation byte-load-bearing in a group's identity — the same thing §2.4 forbids for the in-flight form generally, and the same failure mode v3.26 ruled for contained errors one subsection over. The prior expression — a filter per candidate key — is `O(B·N)`. *(`partition-by` is subsumed by this and is not separately adopted: a two-way partition is `group-by` with a boolean key.)*

  > **`system/compute/group` is a pinned type *name*, not a type-extension registration.** Per §2.3 N1 and §4.1's materialization rule, a constructed entity is encoded **by the runtime kind of the evaluated value, never by the constructed type's declared schema** — so a peer with no type extension produces byte-identical groups. The cost of the key-carrying shape is one agreed string.
- **`concat(...collections)`** joins arrays **order-preserving, one level** — it does not flatten recursively. Element types MUST match; a mismatch is a `type_mismatch` **error-as-value**, not a fault. **A `compute/error` element is type-transparent to that check `[MUST, v3.25]`**: it neither matches nor mismatches, and flows through untouched. Per §1.5 an error is *"the same model as NaN propagation in IEEE 754"* — a poisoned value **of** the array's element type, not a value of a different type — and §7.2 scopes `concat` to consuming its `collections`, never their elements, so inspecting elements for errors is the one behaviour it must not have. `concat()` with no arguments is the empty array; `concat(a)` is `a`. There is otherwise no way to join k arrays: `fold` cannot (the accumulator step needs the append that does not exist), `map` yields k arrays, and `construct` changes the entity shape, which boundary equivalence forbids.

  > **`collections` is ONE hash of an expression, not a literal array of hashes `[MUST, v3.27]`.** It is uniform with every sibling collection argument — `map-args.collection`, `filter-args.collection`, `fold-args.collection`, `group-by-args.collection` and `assoc-args.collection` are each a scalar hash of an expression that evaluates to an array — and the uniformity is load-bearing rather than cosmetic: **a literal array of hashes freezes `concat`'s arity at authoring time.** A `concat` over a computed number of collections — over the output of a `map`, over a `group-by`'s `members`, over anything whose length is not known when the IR is written — is inexpressible under the literal shape, which would make the one primitive adopted to join k arrays the one primitive whose k is a constant. *(v3.24 and v3.25 declared `{array_of: {type_ref: "system/hash"}}`. The §3.5 short-circuit row is unaffected by the change: the outer array's items are the collections, which are consumed, and items **of** a sub-collection are elements, which are contained. Both shapes express that distinction, so it does not discriminate between them.)*
- **`assoc(collection, index, value)`** returns a new array identical to `collection` except at `index`, which carries `value`. **An out-of-range `index` — negative, or ≥ the collection's length — is an `index_out_of_range` error-as-value `[MUST, v3.25]`**, the same code and the same condition as `compute/index` (§2.2). *(v3.24 said `type_mismatch` here. That contradicted §2.2's ruling — reached on the compute corpus's first cross-impl run — that an out-of-bounds magnitude is not a type error, and it is corrected rather than carried: one document must not answer one malformed program with two codes depending on which array operation it reached.)* **`assoc` MUST NOT be an implicit lowering target `[MUST]`** — `map` and `fold` are never lowered onto it. It is an explicit author choice, because an indexed update buys scatter at the cost of sharding: a program written as a sequence of `assoc` updates is inherently sequential, where the same computation expressed as a fold over a read-only input shards. **A lowering pass that "optimizes" a fold into `assoc` would silently remove the parallelism**, which is why the choice stays the author's.

**Error-as-value flow-through is governed by §7.2, not by a rule of its own `[v3.25]`.** An error already present in an input is not a new question for these four primitives: §7.2's short-circuit `[MUST]` binds *"all expression types that **consume values**"* and its `store` worked example already settles the other side — *"a builtin's write payload is not a consumed operand."* Applied here, so that no implementer re-derives it:

| Primitive | Position | Class | Behaviour |
|---|---|---|---|
| `range` | `n` | consumed — the magnitude is read to size the array | **short-circuit** |
| `group-by` | derived key | consumed — compared to assign a group | **short-circuit** |
| `group-by` | element | copied into `members` | contain |
| `assoc` | `index` | consumed — read to position the write | **short-circuit** |
| `assoc` | `value` | placed into the output — the SA-9 `store` case | contain |
| `concat` | each `collection` | consumed — its length is read to copy | **short-circuit** |
| `concat` | element | copied into the output | contain |
| `map` | element (bound into the closure) | not read by `map` — bound into closure scope | pass through; the closure's own operators short-circuit *inside* the closure |
| **`map`** | **output element (the closure's result)** | **not read — placed into the output array** | **contain** — `[v3.27]` |
| `filter` | element (bound into the closure) | not read by `filter` — bound | pass through |
| **`filter`** | **predicate result** | **consumed — read for truthiness (§4.5) to decide inclusion** | **short-circuit** — `[v3.27]` |
| `fold` | element / accumulator (bound into the closure) | not read by `fold` — bound | pass through |
| **`fold`** | **the accumulator, at every step and as the result** | **not read — bound into the next invocation, then returned** | **contain** — `[v3.27]` |

A `compute/error` **key** short-circuits even though the key now has an output position (`system/compute/group.key`), because key equality is byte-identity over the canonical encoding: grouping by an error would make its message string structurally load-bearing, so two failures worded differently would become two groups and one reworded message would change the result's shape.

**Handing a value to a closure is a BINDING, not a consumption. A primitive consumes only what it reads itself `[MUST, v3.27]`.** That is the distinction the three collection builtins turn on, and each of the three falls out of it:

- **`map`'s output element contains.** `map` never reads the closure's result; it places it. That is structurally the same position as `concat`'s element and `assoc`'s `value` — the §7.2 write-payload case. It is also what §1.5's model requires: *"the same model as NaN propagation in IEEE 754"* is **element-wise**, so `map(f, [1,2,3])` where `f` fails only on element 2 yields `[a, E, c]`. Short-circuiting the whole array is exception semantics, which §1.5 explicitly declined.
- **`filter`'s predicate result short-circuits.** It is read for truthiness, which makes it a consumed operand by §7.2's plain terms — the identical case to `group-by`'s derived key. Containing it fails the same way: an error has no truth value, and coercing it to false **silently drops the element**, a well-formed wrong answer carrying no error. That is the reasoning §3.5 already used to refuse clamping a negative `range(n)` to `[]`.
- **`fold`'s accumulator contains, and a closure that ignores it RECOVERS.** `fold` binds the accumulator into the next invocation and never reads it. An error accumulator — arriving as `initial` or as a previous step's result — is passed onward as an ordinary bound value, so a closure that does not consult its accumulator returns a non-error and the fold recovers. **`fold` MUST NOT abort on an error accumulator.** This is the one position where the two readings produce a **different value** rather than a different cost.

**A `compute/error` behaves identically however it was produced `[MUST, v3.27]`.** Whether an error was **minted** by a failing operation or arrived as a **value** — a literal, or a `compute/lookup/*` resolving to a stored one, each returned unchanged by SA-1 — makes no difference to any disposition in this section. **This is a restatement of §2.4, not a new rule:** minted-versus-value-form is precisely an *in-flight representation*, and §2.4 already holds that only the materialized form is normative while the in-flight representation is implementation-private. §4.1's `is_error` is kind-based for the same reason. An implementation whose contained positions behave one way for a minted error and another for a value-form one is **non-conformant against §2.4**, and lets a private representation decide a boundary hash.

**The contained set is defined by a rule, and its current extension is five positions `[v3.27]`.** A position is **contained** when the primitive **places** the value without reading it, and **consumed** when the primitive **reads** it to decide control flow, ordering, membership, or a write location. Today that is `assoc`'s `value`, `concat`'s elements, `group-by`'s `members`, **`map`'s output element**, and **`fold`'s accumulator**. **A new primitive adds rows to the table above by applying the rule — never by amending a count.** An error reaching materialization from a position that is *consumed* remains the §4.1 defect it has always been.

> *(v3.26 stated this as* "the contained set is exactly three positions" *. That enumeration was taken over the four v3.25 primitives, whose positions the table above enumerates; `map`/`filter`/`fold` are not in that table and predate it. The count was replaced rather than incremented because it read as a closed structural claim about the language and would be wrong again at the next primitive with an output position.)*

#### Evaluation-limit codes — the counter decides, not the code's "limit-ness" `[MUST, v3.27]`

`budget_exhausted`, `depth_exceeded` and `cascade_limit` (§9.1) are not ordinary errors-as-value in the contained positions, and they do not all behave alike. **The discriminator is whether the counter that produced the code is restored when an element finishes.**

| Code | Counter | Disposition in a CONTAINED position |
|---|---|---|
| `depth_exceeded` | `depth` — decremented on entry, **restored on return** (§5.1, §4.1) | **contain**, exactly like any other error |
| `budget_exhausted` | `operations` — decremented per `evaluate()`, **never restored** | **short-circuit**, in every position |
| `cascade_limit` | the cascade counter — shared across the **entire causal chain** and tracked cross-peer (§7.3, SYSTEM-COMPOSITION.md §3) | **short-circuit**, in every position |

**Why `depth_exceeded` contains.** §5.1 restores `depth` on return, so each element of a collection begins its evaluation at the same depth. Whether element *i* exceeds is a property of that element's own sub-expression and of nothing evaluated before it — so `map(f, xs)` where `f` recurses too deeply on one element yields `[a, E, c]`, identically at every peer. It is element-local, and the element-wise model applies unchanged.

**Why `budget_exhausted` does not.** `operations` is cumulative and monotonic, so whether element *i* exhausts the budget depends entirely on what elements 1…*i*−1 cost — and **the cost accounting is not pinned**: §10.4 makes memoization table size and eviction policy implementation-defined, and a memoization hit skips an `evaluate()` call and therefore an `operations` decrement. Two conformant peers given identical IR, identical inputs and an identical budget may therefore exhaust at **different elements**. Contained, that is a different array per peer — different boundary bytes for the same program, which §8.1 and §11.1 (AE-1) both forbid. Short-circuited, every peer that exhausts answers with the one code. **Independently of determinism:** an array of contained `budget_exhausted` elements is a well-formed, readable result reported for an evaluation the peer **aborted**, which is the failure this section already refused when it declined to clamp a negative `range(n)` to the empty array.

**Why `cascade_limit` does not.** Its counter is not merely shared across elements but across the whole causal chain, and reaching it **freezes the subgraph** (§7.3) — recovery is re-installation. A frozen subgraph that nonetheless emitted a well-formed array of element-wise `cascade_limit` values would be reporting a value for a computation that is structurally halted. §7.3 draws this line itself when it contrasts the freeze against budget exhaustion, which *"does NOT freeze… may be transient."*

**The disposition is keyed on the `code`, in both arms `[MUST, v3.27]`.** A `budget_exhausted` or `cascade_limit` short-circuits whether it was minted by this evaluation or arrived as a **value-form** `compute/error` carrying that code. **The value form is not hypothetical: §7.3 requires its creation** — *"budget exhaustion during reactive re-evaluation writes a `compute/error` to the result_path"* — so a downstream expression reading that path through `compute/lookup/tree` receives one, produced by a conformant peer. **An implementation MUST NOT key this behaviour on how the error was produced.** Doing so reinstates exactly the provenance-dependence the `[MUST]` above forbids, and §2.4 settles it independently: two errors with the same `code` **are** the same materialized entity, so no rule may distinguish them. *(Consequence, stated so it is not read as an oversight: a program may store a literal `compute/error{code: "budget_exhausted"}` and thereby short-circuit a collection that would otherwise contain its errors. That is correct — the stored and the minted value are the same entity by the protocol's own identity rule, and an author could already halt an expression by placing an error in a consumed position.)*

**How a CONTAINED error materializes `[MUST, v3.26]`.** Where the table above says **contain**, the error is present in the value when that value crosses a materialization boundary (§2.3 N1). It materializes **code-only** — content-hashed over `code` alone per §2.4, with `message`/`at`/`expression` excluded as in-flight diagnostics — and is **referenced by a bare `system/hash`** like any other entity-valued element. **The code-only form is load-bearing, not tidiness:** if the contained element carried `message`, two conformant peers whose diagnostics differ would produce **different bytes for the containing array**, so the array's content hash would fork cross-impl on a string no spec pins. **The contained set is defined by the places-without-reading rule above, and today extends to five positions** — `assoc`'s `value`, `concat`'s elements, `group-by`'s `members`, `map`'s output element, and `fold`'s accumulator `[v3.27]`. An error reaching materialization from a **consumed** position remains the §4.1 defect it has always been.

**Adopting `concat` does not bless an in-compute sharded step `[not ruled]`.** A self-dispatch fan-out rejoined by `concat` additionally requires the tick contract to state a fairness posture — either a bound on synchronous fan-out width, or a nested-eval yield guarantee. **Termination was never the question; occupancy of the serve loop is.** Adopting the primitive and blessing the pattern are two decisions and only the first is made here.

**Collection-builtin evaluation (SHOULD).** Because `map`/`filter`/`fold` apply a caller-provided closure per element, they need the evaluator's scope/budget/context — a real handler-dispatch boundary would lose these. Implementations SHOULD therefore evaluate the collection builtins *internally within the evaluator* (as the inline expression types are), not via a separate dispatched handler. Consequently `system/compute/builtins/{map,filter,fold,range,group-by,concat,assoc}` is a **canonical/logical operation name**; on such implementations it MAY NOT resolve to a distinct handler entity in the tree (a `tree:get` of that path need not return a handler). The pinned args types + observable semantics above are the contract; dispatch-vs-internal is an implementation detail.

The `store-args` type is defined here as well — `store` is the one impure builtin tied to core semantics:

**`system/compute/store-args` type definition:**

```
system/compute/store-args := {
  fields: {
    path:  {type_ref: "system/tree/path"}   ; Target write path
    value: {type_ref: "system/hash"}        ; Hash of entity to write
  }
}
```

**`store` value semantics (SA-9).** `store` **evaluates** the `value` expression and writes the result — not the unevaluated entity at a literal hash; a bare-primitive result is wrapped in `primitive/any`. **Write mechanism (SA-10):** implementations dispatch the write via `system/tree:put`, so capability-gating, path normalization, history, and reactive cascade are uniform with all other tree writes (a direct capability-checked `emit` is equally compliant, but `tree:put` keeps attribution uniform across impls).

**Sequencing side effects.** Multiple side-effecting operations (e.g., two `store` builtin calls) are sequenced using `compute/let` with bindings that evaluate each operation in declaration order. No explicit sequencing form is provided — the language is expression-oriented, and `compute/let`'s sequential (`let*`) semantics (§2.1) provide the ordering guarantee:

```
let _1 = apply(store, {path: "a", value: x})
    _2 = apply(store, {path: "b", value: y})
in _2
```

The underscore-prefixed binding names are a convention for "I don't care about this value, but I need it evaluated for its side effect." Because `let*` is sequential (V22), `_1` evaluates before `_2`, so the first store completes before the second begins. The final `in _2` returns the second store's result (or any expression — the return value of a sequencing chain is whatever the last `in` clause computes).

---

## 4. Evaluation

### 4.1 Evaluation Algorithm

#### `is_error(v)` — the predicate the whole evaluator branches on `[cross-peer seam — MUST]`

The pseudocode below guards **every** sub-evaluation with `if is_error(x): return x`. That predicate
is normative and it is **kind-based, not outcome-based**:

> **`is_error(v)` is true if and only if `kind_of(v)` is `compute/error`. `[MUST]`**
>
> It does **not** mean "evaluation failed". A `compute/error` **value** that evaluated *successfully*
> — a literal, or a `compute/lookup/hash` resolving to a stored one, each returned unchanged by
> **SA-1** — **is an error for every purpose in this section.** SA-1 governs what `evaluate` returns;
> this predicate governs what the consumer does with it, and the guard sits between them.

**Why this is pinned rather than left to the obvious reading.** Both readings are self-consistent, so
each is invisible to same-implementation testing, and the two split at the cross-peer seam. Under the
outcome-based reading a `compute/error` reached by evaluation falls past the guard and is embedded
and materialized into the consuming expression; under the kind-based reading it short-circuits. **The
same input then yields an entity-kind boundary in one peer and an error-kind outcome in another** —
observed three ways, no two alike, with the non-error control case byte-identical.

**This predicate is local to `EXTENSION-COMPUTE`.** `EXTENSION-CONTINUATION` defines a different
`is_error` over HTTP status (`status >= 400`); the two are unrelated and neither is a reference to the
other. A reader grepping the corpus for one will find the other.

```
evaluate(entity, scope, budget, ctx):
  if budget.depth <= 0:
    return error("depth_exceeded", "Maximum evaluation depth exceeded")
  budget.depth -= 1

  while true:
    budget.operations -= 1
    if budget.operations <= 0:
      budget.depth += 1
      return error("budget_exhausted", "Computation budget exhausted")

    result = evaluate_inner(entity, scope, budget, ctx)

    ; Trampoline: tail calls return a continuation instead of recursing.
    ; The loop reuses the current depth frame — tail calls don't consume depth.
    if is_tail_call(result):
      entity = result.entity
      scope  = result.scope
      continue

    budget.depth += 1
    return result

evaluate_inner(entity, scope, budget, ctx):
  match entity.type:

    "compute/literal":
      return entity.data.value

    "compute/lookup/scope":
      name = entity.data.name
      if scope.has(name):
        return scope.get(name)
      return error("not_found", "No scope binding: " + name)

    "compute/lookup/tree":
      path = entity.data.path
      if entity.data.relative == true:
        path = clean_path(ctx.subgraph_root + "/" + path)
      else:
        path = canonicalize(path, ctx.local_peer_id)   ; V7 §5.4 — peer-relative -> /{local_peer_id}/path; absolute used as-is
      ; Capability check — ctx.capability must cover the tree read (v3.9, §7.2)
      if not check_path_permission("get", path, ctx.capability, "system/tree", ctx.local_peer_id):
        return error("permission_denied", "Capability does not cover tree read: " + path)
      ; Tree lookup — impure
      ctx.register_dependency(path)               ; For reactive mode (§7.1)
      tree_entity = ctx.entity_tree.get(path)
      if tree_entity is null:
        return error("not_found", "No entity at path: " + path)
      if is_compute_expression(tree_entity):
        return tail_call(tree_entity, scope)
      return tree_entity

    "compute/lookup/hash":
      ; Hash lookup — pure, authorized via sealed set or content_store_access
      ; No reactive dependency registered — hash is immutable
      ; The `relative` field applies to the path hint at install time (§3.3 Phase 2b),
      ; not at eval time. Eval resolves by hash only — the path has no runtime role.
      target = resolve_or_error(entity.data.hash, ctx, "hash lookup")
      if is_error(target): return target
      if is_compute_expression(target):
        return tail_call(target, scope)
      return target

    "compute/apply":
      if entity.data.path:
        ; Handler dispatch mode — build typed params entity from args
        if entity.data.operation is null:
          return error("invalid_expression", "compute/apply handler mode requires operation")
        handler = resolve_handler(entity.data.path, ctx)
        if handler is null:
          return error("not_found", "No handler at path: " + entity.data.path)
        operation_spec = handler.operations[entity.data.operation]
        if operation_spec is null:
          return error("invalid_expression", "Handler has no operation: " + entity.data.operation)
        input_type = operation_spec.input_type

        ; Evaluate args in ECF canonical map key order (§8.2)
        resolved_args = {}
        for name, hash in canonical_sorted(entity.data.args):
          target = resolve_or_error(hash, ctx, "arg " + name)
          if is_error(target): return target
          value = evaluate(target, scope, budget, ctx)
          if is_error(value): return value
          ; Encode into field position based on declared type (§2.1 "Value encoding")
          encoded = encode_arg_for_field(name, value, input_type, ctx)
          if is_error(encoded): return encoded
          resolved_args[name] = encoded

        ; Construct params entity with the handler's declared input type
        params_entity = {
          type: input_type,
          data: resolved_args
        }

        ; Optional type validation (if type extension is present)
        if type_extension_present and not validate_type(params_entity):
          return error("type_mismatch",
            "Constructed params do not match declared input type: " + input_type)

        ; ctx.capability is the caller's capability to system/compute. From system/
        ; compute's perspective, every eval is the same — evaluate under the caller's
        ; capability. The caller differs per path:
        ;   - Explicit eval: the external caller (their cap authorizes the expression)
        ;   - Entity-native dispatch: the handler (handler grant authorizes the expression)
        ;   - Reactive: the reactive engine (installation grant, autonomous)
        ;
        ; dispatch_execute MUST propagate the full execution context (author,
        ; caller_capability, chain_id) alongside the dispatch capability, per V7 §6.8
        ; context propagation. The mechanism is implementation-defined.

        ; A builtin path dispatches no EXECUTE, so the override fields have no
        ; referent. Reject rather than ignore: the dual-check only ever NARROWS,
        ; so silently dropping a provided capability runs the operation WIDER
        ; than the caller asked — and `store` writes to a caller-specified path.
        ;
        ; ORDERING IS NORMATIVE — this is a SHAPE check and it runs BEFORE any
        ; field is resolved or evaluated. Rejecting after evaluation would make
        ; the outcome depend on the field's VALUE: an error-valued `resource`
        ; would short-circuit to THAT error instead of `invalid_expression`, so
        ; two conformant impls would return different codes for one malformed
        ; expression. Evaluating a field the expression is not allowed to carry
        ; also performs tree reads on the strength of an expression already
        ; known to be invalid.
        if is_builtin_path(entity.data.path)
           and (entity.data.capability is not null
                or entity.data.resource is not null):
          return error("invalid_expression",
            "compute/apply on a builtin path MUST NOT carry capability or resource")

        ; Resolve resource target (if present) — F1/F2/F4 (v3.10)
        resource = null
        if entity.data.resource is not null:
          resource_ref = resolve_or_error(entity.data.resource, ctx, "apply resource")
          if is_error(resource_ref): return resource_ref
          resource = evaluate(resource_ref, scope, budget, ctx)
          if is_error(resource): return resource

        ; Determine dispatch capability (v3.10, F2 dual-check at full resolution)
        dispatch_cap = ctx.capability
        if entity.data.capability is not null:
          ; F5: capability override requires resource — without it, the dual-check
          ; below would see null resource and the handler-grant ceiling would not
          ; be enforced at the resource level.
          if entity.data.resource is null:
            return error("invalid_expression",
              "compute/apply with capability field MUST also have resource field")

          cap_ref = resolve_or_error(entity.data.capability, ctx, "apply capability")
          if is_error(cap_ref): return cap_ref
          provided_cap = evaluate(cap_ref, scope, budget, ctx)
          if is_error(provided_cap): return provided_cap

          ; DUAL CHECK: ctx.capability (handler grant) must also cover the target
          ; INCLUDING the resource. Without the resource here, an admin caller's
          ; broader capability could escape the handler's declared scope by
          ; targeting paths outside internal_scope.
          if not check_grant_covers(entity.data.path, entity.data.operation,
                                     resource, ctx.capability, ctx.local_peer_id):
            return error("permission_denied",
              "Handler grant does not cover target: " + entity.data.path + "." + entity.data.operation)
          dispatch_cap = provided_cap

        ; F4: dispatch_execute carries resource through to the constructed EXECUTE.
        ; The constructed EXECUTE's `resource` field is set from this argument.
        ; When `resource` is null, the EXECUTE has no resource field and dispatch
        ; falls back to handler-only check (V7 §5.2).
        return ctx.dispatch_execute(entity.data.path, entity.data.operation,
          resource, params_entity, dispatch_cap)

      if entity.data.fn:
        ; Closure application mode
        fn_target = resolve_or_error(entity.data.fn, ctx, "closure fn")
        if is_error(fn_target): return fn_target
        fn_value = evaluate(fn_target, scope, budget, ctx)
        if is_error(fn_value): return fn_value
        if fn_value.type != "compute/closure":
          return error("type_mismatch", "Apply target is not a closure")

        new_scope = load_scope(fn_value.data.env, ctx)
        if is_error(new_scope): return new_scope
        for param in fn_value.data.params:
          arg_hash = entity.data.args[param]
          if arg_hash is null:
            return error("missing_argument", "Missing argument: " + param)
          arg_target = resolve_or_error(arg_hash, ctx, "closure arg " + param)
          if is_error(arg_target): return arg_target
          arg = evaluate(arg_target, scope, budget, ctx)
          if is_error(arg): return arg
          new_scope.set(param, arg)

        body_target = resolve_or_error(fn_value.data.body, ctx, "closure body")
        if is_error(body_target): return body_target
        return tail_call(body_target, new_scope)

      return error("invalid_expression", "compute/apply requires path or fn")

    "compute/if":
      cond_target = resolve_or_error(entity.data.condition, ctx, "if condition")
      if is_error(cond_target): return cond_target
      condition = evaluate(cond_target, scope, budget, ctx)
      if is_error(condition): return condition
      if truthy(condition):
        then_target = resolve_or_error(entity.data.then, ctx, "if then")
        if is_error(then_target): return then_target
        return tail_call(then_target, scope)
      else if entity.data.else:
        else_target = resolve_or_error(entity.data.else, ctx, "if else")
        if is_error(else_target): return else_target
        return tail_call(else_target, scope)
      else:
        return null

    "compute/let":
      new_scope = scope.copy()
      for binding in entity.data.bindings:
        ; Sequential binding — each binding's value is evaluated in the accumulated
        ; scope, so later bindings can reference earlier ones (like Scheme's let*).
        value_target = resolve_or_error(binding.value, ctx, "let binding " + binding.name)
        if is_error(value_target): return value_target
        value = evaluate(value_target, new_scope, budget, ctx)
        if is_error(value): return value
        new_scope.set(binding.name, value)
      body_target = resolve_or_error(entity.data.body, ctx, "let body")
      if is_error(body_target): return body_target
      return tail_call(body_target, new_scope)

    "compute/lambda":
      ; Capture scope, produce closure — do NOT evaluate body
      env_hash = capture_scope(scope, entity.data.body, ctx)
      return {
        type: "compute/closure"
        data: {
          params: entity.data.params
          body:   entity.data.body
          env:    env_hash    ; null if scope was empty, otherwise content hash
        }
      }

    ; Inline types — evaluated directly
    "compute/arithmetic":
      left_target = resolve_or_error(entity.data.left, ctx, "arithmetic left")
      if is_error(left_target): return left_target
      left = evaluate(left_target, scope, budget, ctx)
      if is_error(left): return left
      right_target = resolve_or_error(entity.data.right, ctx, "arithmetic right")
      if is_error(right_target): return right_target
      right = evaluate(right_target, scope, budget, ctx)
      if is_error(right): return right
      return apply_arithmetic(entity.data.op, left, right)

    "compute/compare":
      left_target = resolve_or_error(entity.data.left, ctx, "compare left")
      if is_error(left_target): return left_target
      left = evaluate(left_target, scope, budget, ctx)
      if is_error(left): return left
      right_target = resolve_or_error(entity.data.right, ctx, "compare right")
      if is_error(right_target): return right_target
      right = evaluate(right_target, scope, budget, ctx)
      if is_error(right): return right
      return apply_compare(entity.data.op, left, right)

    "compute/logic":
      left_target = resolve_or_error(entity.data.left, ctx, "logic left")
      if is_error(left_target): return left_target
      left = evaluate(left_target, scope, budget, ctx)
      if is_error(left): return left
      if entity.data.op == "not":
        return !truthy(left)
      right_target = resolve_or_error(entity.data.right, ctx, "logic right")
      if is_error(right_target): return right_target
      right = evaluate(right_target, scope, budget, ctx)
      if is_error(right): return right
      if entity.data.op == "and": return truthy(left) and truthy(right)
      if entity.data.op == "or": return truthy(left) or truthy(right)

    "compute/field":
      target_ref = resolve_or_error(entity.data.entity, ctx, "field target")
      if is_error(target_ref): return target_ref
      target = evaluate(target_ref, scope, budget, ctx)
      if is_error(target): return target
      if target.data is null:
        return error("type_mismatch", "Field access requires an entity with data, got: " + type(target))
      if target.data[entity.data.name] is null:
        return error("not_found", "Field not found: " + entity.data.name)
      return target.data[entity.data.name]

    "compute/construct":
      result_fields = {}
      for name, hash in canonical_sorted(entity.data.fields):
        value_target = resolve_or_error(hash, ctx, "construct field " + name)
        if is_error(value_target): return value_target
        value = evaluate(value_target, scope, budget, ctx)
        if is_error(value): return value
        ; Materialize by RUNTIME KIND (v3.19c, option α) — never the declared type
        ; schema (keeps it type-extension-independent). An entity/closure value is
        ; recursively materialized to bare, stored, and referenced by a bare
        ; system/hash (V7 §1.4); a primitive/record value is inlined. No kind-tags in
        ; the materialized data — kind-tagging is confined to compute/scope (§2.3).
        ;
        ; compute/error is NOT in this set, and its absence is normative (v3.23).
        ; The guard above returns first, so an error can never reach here — listing
        ; it was unreachable text, and three implementations read the two lines in
        ; two different orders. An error materializes where it is WRITTEN (§7.2
        ; result_path, SA-9 store), never where it is CONSUMED.
        if kind_of(value) in {entity, compute/closure}:
          result_fields[name] = ctx.content_store.put(materialize(value, ctx))
        else:
          result_fields[name] = value
      constructed = {type: entity.data.entity_type, data: result_fields}
      ; Optional type validation (symmetric with compute/apply V30 encoding).
      ; SHOULD validate when the type extension is present. Unknown fields are
      ; permitted per V7 §2.10. The interop observability consideration from
      ; §2.1 (Value encoding) applies: peers with and without type extension
      ; agree on valid inputs, differ on invalid ones.
      if type_extension_present and not validate_type(constructed):
        return error("type_mismatch",
          "Constructed entity does not match declared type: " + entity.data.entity_type)
      return constructed

    default:
      return error("unknown_type", "Unknown compute type: " + entity.type)

; Iteration helper: produce map entries in ECF canonical map key order —
; sort by encoded byte length of the key, then lexicographically by byte value.
; Matches ENTITY-CBOR-ENCODING.md §4.1 Rule 2 (canonical map ordering).
canonical_sorted(map):
  entries = list(map.entries)
  sort(entries, key = lambda (k, _): (encoded_byte_length(k), byte_sequence(k)))
  return entries

; V31 helper: wrap resolve() with a not_found error on null return
resolve_or_error(hash, ctx, label):
  entity = resolve(hash, ctx)
  if entity is null:
    return error("not_found", "Cannot resolve hash for " + label + ": " + hash)
  return entity

; V30 helper: encode an evaluated value into a field position based on declared type
encode_arg_for_field(name, value, input_type, ctx):
  field_spec = input_type.fields?[name]
  if field_spec is null:
    ; Open type — preserve as-is per V7 §2.10
    return value

  declared = field_spec.type_ref
  if declared == "system/hash":
    ; Field expects a hash reference. Primitives cannot take hash positions.
    if is_primitive(value):
      return error("type_mismatch",
        "Field " + name + " expects system/hash, got primitive")
    ; Entity/closure value: compute its content hash. The entity is added to
    ; the local content store if not already present — content store writes
    ; are local storage operations (content addressing makes them idempotent
    ; and self-authenticating). The dispatch layer carries referenced entities
    ; in the EXECUTE envelope's included map; the authorization check happens
    ; at dispatch_execute using ctx.capability, not at this helper.
    hash = ctx.content_store.put(value)
    return hash
  if declared starts_with "primitive/":
    if declared == "primitive/any":
      return value    ; Open primitive position
    if not matches_primitive_type(value, declared):
      return error("type_mismatch",
        "Field " + name + " expects " + declared + ", got " + describe(value))
    return value
  ; User-defined structural type — inline by default.
  ; Type extension MAY refine this during validation; see §2.1 value encoding table.
  return value

; Arithmetic helper — normative (v3.6, PROPOSAL-COMPUTE-SPEC-AMBIGUITIES A1)
apply_arithmetic(op, left, right):
  if is_float(left) or is_float(right):
    left  = to_float(left)
    right = to_float(right)
  if not is_numeric(left) or not is_numeric(right):
    return error("type_mismatch", "Arithmetic requires numeric operands")
  match op:
    "add": return left + right
    "sub": return left - right
    "mul": return left * right
    "div":
      if right == 0:
        if is_float(left) or is_float(right):
          return ieee754_div(left, right)
        return error("division_by_zero", "Division by zero")
      if is_integer(left) and is_integer(right):
        if left % right == 0:
          return left / right
        return to_float(left) / to_float(right)
      return left / right
    "mod":
      if right == 0:
        return error("division_by_zero", "Modulo by zero")
      return truncated_remainder(left, right)

; Comparison helper — normative (v3.6, PROPOSAL-COMPUTE-SPEC-AMBIGUITIES A2)
apply_compare(op, left, right):
  match op:
    "eq":
      if not same_type_class(left, right): return false
      return left == right
    "neq":
      if not same_type_class(left, right): return true
      return left != right
    "lt", "gt", "lte", "gte":
      if not is_numeric(left) or not is_numeric(right):
        if is_string(left) and is_string(right):
          return string_compare(op, left, right)
        return error("type_mismatch",
          "Ordering comparison requires numeric or string operands")
      if is_float(left) or is_float(right):
        left  = to_float(left)
        right = to_float(right)
      match op:
        "lt":  return left < right
        "gt":  return left > right
        "lte": return left <= right
        "gte": return left >= right

same_type_class(a, b):
  if is_numeric(a) and is_numeric(b): return true
  return primitive_type(a) == primitive_type(b)

; Type/coercion helpers — normative (v3.6)
is_numeric(value):  return is_integer(value) or is_float(value)
is_integer(value):  return value is primitive/int or primitive/uint
is_float(value):    return value is primitive/float
to_float(value):    if is_integer(value): return ieee754_convert(value)
                    return value

truncated_remainder(a, b):
  return a - (truncate_toward_zero(a / b) * b)

; Tail call continuation — internal to the evaluator, never escapes evaluate().
; (v3.8, PROPOSAL-COMPUTE-TAIL-CALL-OPTIMIZATION T2)
tail_call(entity, scope):
  return {_tail_call: true, entity: entity, scope: scope}

is_tail_call(result):
  return result is not null and result._tail_call == true

; String comparison — lexicographic UTF-8 byte order, no Unicode normalization
string_compare(op, left, right):
  cmp = byte_compare(utf8_bytes(left), utf8_bytes(right))
  match op:
    "lt":  return cmp < 0
    "gt":  return cmp > 0
    "lte": return cmp <= 0
    "gte": return cmp >= 0
```

### 4.2 Entity Resolution

`system/hash` values in compute expression data fields reference other entities by content hash. During evaluation, these are resolved through a layered access model.

```
resolve(hash, ctx):
  ; 1. Check envelope's included map (pre-authorized)
  entity = lookup(hash, ctx.included)
  if entity is not null:
    return validate_compute_resolvable(entity, hash, ctx)

  ; 2. Check content store (access-gated)
  ;    Default: tree-scoped — resolve only if the hash corresponds to an entity
  ;    reachable through tree paths covered by the evaluation capability.
  ;    Extended: if the evaluation capability includes content_store_access
  ;    allowance, resolve directly from the content store.
  if ctx.has_content_store_access:
    entity = ctx.content_store.get(hash)
  else:
    ; Tree-scoped: hash resolvable if it is the content hash of an entity
    ; bound at any tree path covered by the evaluation capability.
    ; Mechanism is implementation-defined (reverse index, scan, encountered
    ; during prior tree reads). The semantic contract is fixed: if the hash
    ; corresponds to a tree-bound entity within capability scope, resolution
    ; MUST succeed.
    entity = ctx.resolve_via_tree(hash)

  if entity is null: return null
  return validate_compute_resolvable(entity, hash, ctx)

; Expression-graph scoping — prevents compute from being a content store oracle.
; Non-compute entities are not resolvable via hash references in expression data.
; External data access uses compute/lookup/tree (capability-checked) instead.
; (v3.6, PROPOSAL-COMPUTE-SPEC-AMBIGUITIES D2)
validate_compute_resolvable(entity, hash, ctx):
  ; Tier 0: content_store_access allowance bypasses all checks
  if ctx.has_content_store_access:
    return entity
  ; Tier 1: expression subgraph membership
  if is_compute_type(entity):
    return entity
  ; Tier 2: sealed set — installed subgraph authorized data (v3.7, D5)
  ; The authorized_data_hashes set is populated at install time (§3.3 Phase 2b)
  ; via path-hint validation. No runtime re-checking — the hash is immutable,
  ; so the install-time authorization covers all future evaluations.
  if ctx.subgraph is not null and hash in ctx.subgraph.data.authorized_data_hashes:
    return entity
  return null

is_compute_type(entity):
  return entity.type in [
    "compute/literal",
    "compute/lookup/scope", "compute/lookup/tree", "compute/lookup/hash",
    "compute/apply", "compute/if", "compute/let", "compute/lambda",
    "compute/arithmetic", "compute/compare", "compute/logic",
    "compute/field", "compute/construct",
    "compute/closure", "compute/scope",
    "compute/result", "compute/error",
    "system/compute/subgraph",
    "system/compute/install-request", "system/compute/install-result"
    ; system/compute/uninstall-request eliminated in v3.12 — uninstall uses
    ; the path-as-resource convention (V7 §3.2) with empty params.
  ]
```

Implementations SHOULD ensure entity resolution is O(1) per hash (e.g., via reverse index).

**The observable operation budget charges `evaluate()` steps only (normative — cross-impl determinism; v3.21, `PROPOSAL-COMPUTE-BUDGET-CEILING-DETERMINISM`, validated three-way by the corpus LOCK 330/330).** The
`operations` ceiling of §5.1 — whose exhaustion is the hard `budget_exhausted` — is decremented **one per
`evaluate()` step and nothing else** (the §4.1 pseudocode `budget.operations -= 1`). `resolve()` calls cost
**zero** in this observable budget. Given the same `(IR, inputs, budget)`, two conformant implementations MUST
therefore reach `budget_exhausted` at the **same** `evaluate()`-step count — the value-vs-`budget_exhausted`
outcome is a cross-impl-deterministic function of the inputs, and is a gated conformance outcome (GUIDE-CONFORMANCE §7c.5).

**Scan-based DoS protection is a private guard, out of band (normative).** An expression that constructs deep
reference chains can force unbounded I/O on an implementation without O(1) reverse-index resolution. Such an
implementation MAY impose an **additional, implementation-private** resource guard (a scan-depth or wall-clock
bound). That guard **MUST NOT alter the observable budget outcome**: if it trips, it surfaces as a **distinct
resource-limit condition** (a transport/resource failure, out of band), **never** as the in-band
`compute/error{budget_exhausted}` value at a shifted stop-point. This keeps the DoS mitigation while leaving the
budget outcome deterministic. Implementations with reverse-index or content-store-direct resolution (§1613 —
scope resolution is O(1)) or encountered-during-read minimum resolution need no such guard.

This is why cross-implementation determinism holds: because `resolve()` cost never enters the observable
`operations` ceiling, both the number of `evaluate()` steps **and** the stop-point are identical across impls —
result values *and* the `budget_exhausted` boundary agree. *(Ruled from the compute corpus's first cross-impl
run — `ARCH-RESPONSE-COMPUTE-CORPUS-FIRST-RUN`, Q2; supersedes the prior "deduction factor is
implementation-defined" guidance, which let impl-defined cost leak into the observable ceiling and made the
`budget_exhausted` boundary non-deterministic at the budget edge.)*

**Content store access model.** Hash resolution follows a layered access model consistent with EXTENSION-QUERY.md §5.5:

| Tier | Mechanism | When |
|------|-----------|------|
| Envelope included | Pre-authorized (sent together) | Always available during EXECUTE eval |
| Tree-scoped (default) | Hash reachable via tree paths under the capability | Default for reactive re-evaluation |
| Content store (allowance) | Direct hash resolution from content store | Requires `allowances.content_store_access` on the installation grant |

The tree-scoped default prevents compute from being a content store bypass vector. The `content_store_access` allowance is opt-in — the installer explicitly grants it at installation time.

**Minimum resolution guarantee (normative).** Implementations operating without the `content_store_access` allowance MUST at minimum support **encountered-during-read** resolution: any hash that appears as a `system/hash`-typed field value during a prior tree read within the same evaluation, and that resolves to a compute-typed entity (per `is_compute_type`), MUST be resolvable via `resolve()` for the remainder of that evaluation. Hash values embedded in non-hash-typed fields (e.g., a string that happens to look like a hash) do not trigger the guarantee. Implementations MAY additionally support:

- **Reverse index** (`hash → tree_path` lookup) — enables resolving any hash bound in the tree, even if not previously read
- **Scan** — walks tree paths in capability scope to find the hash on demand (slow but complete)

Expressions that rely on resolving hashes not previously read (and therefore need reverse index or scan) MAY fail on conformant implementations with only the minimum resolution guarantee. **Portable expressions SHOULD reference entities by path (`compute/lookup/tree`) rather than by hash** when possible. Using `compute/lookup/tree` guarantees the referenced entity is read (triggering the encountered-during-read guarantee) before any hash-typed field on it is dereferenced.

This biases the language toward path references for portability while leaving richer resolution as a permitted optimization. Implementations advertising richer resolution (reverse index or scan) SHOULD document the capability so compute authors know which expressions are portable.

### 4.3 Scope and Binding

```
empty_scope():
  return {bindings: {}}

scope.has(name):
  return name in scope.bindings

scope.get(name):
  return scope.bindings[name]

scope.set(name, value):
  scope.bindings[name] = value

scope.copy():
  return {bindings: shallow_copy(scope.bindings)}

load_scope(env_hash, ctx):
  if env_hash is null: return empty_scope()
  ; Scope entities are structurally part of the referencing closure.
  ; Direct content store access — the closure was already authorized.
  ; (v3.6, PROPOSAL-COMPUTE-SPEC-AMBIGUITIES D1)
  env = ctx.content_store.get(env_hash)
  if env is null:
    return error("not_found", "Closure scope entity not found: " + env_hash)
  ctx.mark_encountered(env_hash)
  return {bindings: copy(env.data.bindings)}
```

### 4.4 Scope Capture

When evaluating `compute/lambda`, the evaluator captures bindings from the current scope that the body references.

```
capture_scope(scope, body_hash, ctx):
  ; Implementation MAY capture all bindings (simple but less efficient)
  ; Implementation SHOULD capture only bindings referenced by the body (requires static analysis)
  if scope.bindings is empty: return null

  scope_entity = {
    type: "compute/scope"
    data: {bindings: scope.bindings}
  }
  h = ctx.content_store.put(scope_entity)
  ctx.mark_encountered(h)
  return h    ; Returns content hash, not the entity object
```

The captured scope entity is content-addressed. Identical captures produce the same hash.

**Scope resolution is content-store-direct (normative; v3.19b N6 — supersedes the earlier "encountered-during-read" wording for scope).** `load_scope` (§4.3) resolves `closure.data.env` and each `kind:"entity"` binding hash via **direct content store access** — scope entities and their binding entities are structurally part of the referencing closure (they ride the closure's authorization, §2.3 N4) and bypass the tree-scoped resolution tiers. During *same-eval capture*, the evaluator still calls `ctx.mark_encountered(content_hash(scope_entity))` so a just-written scope is locally resolvable; for *cross-peer transfer* the scope subtree arrives via the envelope `included` map (§2.3 N7), not `mark_encountered`. (Reconciles the v3.6 D1 wording — which read as global — with §2.3's content-store-direct model.)

Captured environments are frozen snapshots of evaluated values at capture time. They do not maintain live references to tree paths. A closure transferred to another peer carries its captured values (its reachable scope subtree, materialized into the envelope `included` map per §2.3 N7), not the paths they originated from. *(The cross-peer wire that populates `included` for closures is deferred until a consumer exists, §2.3 N7; same-peer is the path provided today.)*

**Closure scope persistence.** The captured `compute/scope` entity MUST be written to the content store before the enclosing `compute/closure` is returned as an evaluation result. A subsequent `compute/apply` operation resolves `closure.data.env` via `load_scope` (§4.3), which uses direct content store access for the scope hash — scope entities are structurally part of the referencing closure and bypass the tree-scoped resolution tiers. This implies every `compute/lambda` evaluation that captures a non-empty scope produces at least one content store write (for the scope entity) in addition to producing the closure value. Implementations MAY skip the write when the captured scope is empty (`env is null` on the closure).

### 4.5 Truthiness

```
truthy(value):
  if value is null: return false
  if value is false: return false
  if value is 0: return false
  if value is "": return false
  if value is []: return false
  return true
```

### 4.6 Memoization

Implementations **SHOULD** maintain a memoization table for pure expressions:

```
memo_table: (expression_hash, scope_hash) → result_hash
```

The memo key **MUST** include both the expression hash and the active scope hash. For top-level expressions with no active scope, use `hash(empty_scope)` as the scope component.

Before evaluating an expression, compute the scope hash from the current evaluation scope, then check the memo table. If the composite key has a cached result, return the cached result without re-evaluation.

Memoization **MUST** only apply to pure expressions (§6.1). Expressions containing `compute/lookup/tree` are impure and **MUST NOT** be memoized, regardless of scope.

**Why scope is part of the key.** Consider two identical `compute/lookup/scope` expressions in different `let` blocks:

```
let x = 5 in (lookup/scope "x")    → 5
let x = 6 in (lookup/scope "x")    → 6
```

Both `(lookup/scope "x")` sub-expressions have identical content hashes but produce different results depending on the surrounding scope. Memoizing on expression hash alone would return the wrong result. Including the scope hash in the key makes memoization sound. The trade-off: memoization is less effective for let-heavy code because every distinct surrounding scope produces a distinct memo key. Correctness wins.

**Scope hash computation.** The scope is a map of name → value. To compute a stable hash:
1. Canonicalize the map (sort by name)
2. Encode as ECF (Entity Canonical Form, ENTITY-CBOR-ENCODING.md)
3. SHA-256 the encoded bytes

The canonicalization and encoding MUST be deterministic — same scope bindings produce the same scope hash across implementations.

### 4.7 Expression Detection

```
is_compute_expression(entity):
  return entity.type in [
    "compute/literal",
    "compute/lookup/scope", "compute/lookup/tree", "compute/lookup/hash",
    "compute/apply",
    "compute/if", "compute/let", "compute/lambda",
    "compute/arithmetic", "compute/compare", "compute/logic",
    "compute/field", "compute/construct"
  ]
```

Note that `compute/closure`, `compute/scope`, `compute/result`, and `compute/error` are value types, not expression types. A stored `compute/closure` at a tree path is returned as a value by `compute/lookup/tree`, not re-evaluated.

---

## 5. Budget and Resource Model

### 5.1 Budget Structure

```
budget := {
  operations: uint      ; Remaining operation count
  depth:      uint      ; Remaining recursion depth
}
```

Every call to `evaluate()` decrements `operations` by 1. Recursive calls decrement `depth` by 1 (restored on return).

### 5.2 Budget Initialization

Compute resource limits are carried on capability tokens via the existing `constraints` field (ENTITY-CORE-PROTOCOL.md §5) under the `system/compute` namespace key. This uses the established core protocol mechanism for handler-interpreted narrowing fields without introducing a new capability field.

```
init_budget(params, capability, bounds):
  ; Request budget (from explicit params) and bounds budget (from wire)
  request_budget = params.budget or infinity
  bounds_budget  = bounds.budget or peer_default_max_ops

  ; Compute-specific resource limits from capability constraints
  ; Constraint key is the full extension namespace: "system/compute"
  compute_constraints = capability.data.constraints?["system/compute"] or {}
  compute_ops_limit   = compute_constraints.max_compute_operations or peer_default_max_ops
  compute_depth_limit = compute_constraints.max_compute_depth or peer_default_max_depth

  return {
    operations: min(request_budget, bounds_budget, compute_ops_limit)
    depth:      compute_depth_limit
  }
```

### 5.3 Budget Consumption

**Summary.** Default: independent per-peer budgets. Optional: `budget_consumed` metadata for trusted cross-peer accounting (deferred to V6 core protocol amendment).

Handler dispatch from `compute/apply` has different budget semantics depending on whether the target handler is in-process (same peer) or cross-peer (via the wire). The `ctx.dispatch_execute` call in the §4.1 evaluation pseudocode dispatches via `dispatch_inprocess` (target path resolves to a local handler) or `dispatch_crosspeer` (target is on another peer per V7 routing) — selection is internal to the dispatch layer and invisible to the expression.

**In-process dispatch (same peer).** Budget flows through the in-process call via a shared context object. The compute evaluator and the target handler share the same budget pool. Implementation-defined mechanism (e.g., a reference to the caller's budget struct threaded through the handler context).

```
dispatch_inprocess(path, operation, params, ctx):
  ; ctx.budget is the same pool shared with the caller.
  ; Target handler's own evaluate() decrements ctx.budget.operations,
  ; which propagates back to the caller because ctx is passed by reference.
  sub_ctx = ctx.clone_for_dispatch(path, operation)  ; preserves budget reference
  return dispatch(path, operation, params, sub_ctx)
```

If the handler at the target path is itself a compute expression (entity-defined handler), it consumes from the same budget pool via the shared ctx.

**Cross-peer dispatch (wire).** By default, each peer enforces its own budget independently. The sending peer's budget is NOT carried on the wire. The receiving peer enforces its own budget based on the EXECUTE's bounds field (ENTITY-CORE-PROTOCOL.md §5.9).

```
dispatch_crosspeer(path, operation, params, ctx):
  ; Receiving peer uses its own budget per V7 bounds
  response = dispatch_wire(path, operation, params, ctx)
  ; Optional: if response includes budget_consumed, deduct from local pool
  if response.budget_consumed is not null and ctx.trust_budget_reporting(response.sender):
    ctx.budget.operations -= response.budget_consumed
  return response.result
```

**Optional cross-peer budget accounting.** Peers in trusted relationships MAY exchange budget consumption metadata via the optional `budget_consumed` field on EXECUTE_RESPONSE (ENTITY-CORE-PROTOCOL.md §3.3, landed via V2 V6). When present, the caller MAY deduct `budget_consumed` from its local budget pool. When absent (the default), no cross-peer accounting occurs.

Implementations MUST NOT assume cross-peer budget accounting unless the `budget_consumed` field is present in the response AND the caller trusts the sender's reporting. This is a trust relationship, not a protocol requirement.

### 5.4 Depth Limits

| Limit | Recommended Value | Purpose |
|---|---|---|
| `RECOMMENDED_MAX_DEPTH` | 1024 | Maximum evaluation recursion depth |
| `RECOMMENDED_MAX_CASCADE_DEPTH` | 16 | Maximum reactive cascade depth (§7.3) |

### 5.5 Compute Resource Limits via Capability Constraints

The compute extension places resource limits on the existing `constraints` field of `system/capability` (ENTITY-CORE-PROTOCOL.md §5), using the `system/compute` namespace key. This is the established core protocol mechanism for handler-interpreted narrowing fields.

```
capability.data.constraints["system/compute"] := {
  max_compute_operations: uint   ; Maximum evaluation steps per invocation
  max_compute_depth:      uint   ; Maximum recursion depth
}
```

**Namespace convention.** The constraint key is the full extension namespace (`system/compute`, not bare `compute`) to avoid collision with other extensions. Any extension adding constraints SHOULD use its full `system/{extension}` path as the constraint key.

**Per-key fallback.** Each constraint key is independently optional. Absent keys fall back to peer-wide defaults (§9.3):
- `peer_default_max_ops` — default 100,000
- `peer_default_max_depth` — default 1,024

Setting only `max_compute_operations` without `max_compute_depth` means compute uses the capability's ops limit but the peer's default depth limit. If the capability has no `system/compute` constraint entry, both limits fall back to peer defaults.

**Byte-equal preservation during delegation.** Per ENTITY-CORE-PROTOCOL.md §5.6, `constraints` values are preserved byte-equal during delegation. Child capabilities cannot narrow compute resource limits — the root's values apply throughout the delegation chain. This is a deliberate limitation in V3.3 (the "strict form" of constraint preservation). See the deferred architectural proposal on capability constraint evaluation for future narrowing semantics (PROPOSAL-COMPUTE-AMENDMENTS-V2 §7.3).

**Allowances for resource limits.** V3.3 compute resource limits use `constraints` only (narrowing semantics). It does NOT use `allowances` for resource limits — expanding semantics for compute resource limits are not needed in V3.3. Note that compute DOES use `allowances.content_store_access` for opting into the content store access tier (§4.2); that is a separate concern from resource limits.

**Forward compatibility.** Since types are open (ENTITY-CORE-PROTOCOL.md §2.7), peers that do not implement the compute extension preserve the `system/compute` constraint key on capability entities without interpreting it. Compute-aware peers read and enforce it; compute-unaware peers carry it through.

**First extension to exercise core constraints load-bearingly.** Compute is the first extension to use the core protocol `constraints` field as a load-bearing mechanism — root sets a value, delegation preserves it, handler interprets it during enforcement. Prior extensions have used `constraints` informally; compute is the first concrete consumer at the core protocol layer. This exposes architectural questions about handler-interpreted constraint evaluation that are deferred to a separate proposal.

---

## 6. Purity Model

### 6.1 Classification

| Type | Purity | Reason |
|---|---|---|
| `compute/literal` | Pure | No external access |
| `compute/arithmetic` | Pure | Operates on refs only |
| `compute/compare` | Pure | Operates on refs only |
| `compute/logic` | Pure | Operates on refs only |
| `compute/if` | Pure* | Pure if all branches are pure |
| `compute/let` | Pure* | Pure if bindings and body are pure |
| `compute/lambda` | Pure | Does not evaluate body |
| `compute/field` | Pure | Operates on refs only |
| `compute/construct` | Pure | Operates on refs only |
| `compute/lookup/scope` | Pure | Reads from evaluation scope, no tree access |
| `compute/lookup/tree` | Impure | Reads from entity tree |
| `compute/lookup/hash` | Pure | Hash is immutable; authorization is a gate, not a data source |
| `compute/apply` (handler) | Impure | Dispatches to handler |
| `compute/apply` (closure) | Pure* | Pure if closure body is pure |

An expression is pure if it and all its subexpressions are pure. A pure expression with identical inputs **MUST** produce an identical result on any peer at any time.

### 6.2 Capability Requirements

Compute applies **ENTITY-CORE-PROTOCOL.md §6.8's caller-specified-paths rule** to its impure operations: any operation whose target is determined by caller-supplied expression data MUST be authorized against the caller's capability (explicit eval path) or the installation grant (reactive path) using canonical core helpers (`check_path_permission` per ENTITY-CORE-PROTOCOL.md §6.3 for path-level probes, `check_grant_covers` per ENTITY-CORE-PROTOCOL.md §5.2 for handler+operation probes). The compute handler does not perform compute-specific capability verification — it calls the canonical core helpers for the actual checks, and follows the same handler-authorship pattern as other handlers (e.g., the history extension §4.2).

The compute handler **MUST** verify the caller's capability before executing impure operations:

| Operation | Required Access |
|---|---|
| `compute/lookup/tree` | Read access to target path |
| `compute/apply` (handler) | Execute access to target handler path |
| `system/compute/builtins/store` | Write access to target path |

`compute/lookup/scope` never requires a capability check — scope bindings are local to the evaluation and do not access any external state.

The compute handler **MUST** reject impure operations when the caller's capability does not cover the target resource. Without this check, computation becomes a capability bypass vector.

**Narrow compute handler grant.** The compute handler's own grant (issued at registration per ENTITY-CORE-PROTOCOL.md §6.2) MUST cover only:
- Operations on `system/compute/*` — the handler's operations (`eval`, `install`, `uninstall`) and the builtin dispatch namespace
- Writes to `system/compute/processes/*` — subgraph metadata lifecycle

The compute handler MUST NOT hold a wildcard resource grant. All writes outside `system/compute/processes/*` (including reactive result writes to user-specified `result_path` locations and store builtin writes to arbitrary paths) MUST be authorized by the installation grant or caller capability per §6.3, NOT by the handler's own grant. The no-silent-escalation principle (ENTITY-CORE-PROTOCOL.md §6.8) forbids the handler from substituting its own grant for impure operations targeting caller-owned paths.

**`store` builtin and no-silent-escalation.** The `store` builtin writes to a tree path specified by the compute expression. The compute handler MUST verify the caller's capability (EXECUTE path) or installation grant (reactive path) covers the write path using `check_path_permission("put", path, capability)`. The compute handler MUST NOT substitute its own grant to authorize a `store` write. This follows the no-silent-escalation principle (ENTITY-CORE-PROTOCOL.md §6.8).

If the capability does not cover the write path, the `store` operation MUST return a `compute/error` with code `permission_denied`.

### 6.3 Write Authorization

Compute operations produce tree writes in multiple authorization modes. The compute handler's own grant covers its managed namespace (`system/compute/*`). Impure operations within expressions use the caller's capability (EXECUTE path) or the installation grant (reactive path).

| Operation | Write target | Authorization | Capability recorded |
|-----------|-------------|---------------|-------------------|
| eval (pure expressions) | No writes | — | — |
| eval (store builtin) | Caller-specified path | Caller capability | Caller capability |
| eval (handler dispatch) | Target handler's writes | Per target handler (caller cap propagated) | Per target handler |
| install (subgraph metadata) | `system/compute/processes/*` | Handler grant | Handler grant |
| uninstall (metadata removal) | `system/compute/processes/*` | Handler grant | Handler grant |
| reactive result write | `subgraph.result_path` | Installation grant | Installation grant |
| reactive handler dispatch | Target handler's writes | Installation grant | Installation grant |

**Caller-authorized writes** (store builtin): The compute handler MUST verify the caller's capability covers the write path using `check_path_permission("put", path, capability)`. The handler MUST NOT substitute its own grant (no-silent-escalation principle, ENTITY-CORE-PROTOCOL.md §6.8).

**Handler-authorized writes** (subgraph metadata at `system/compute/*`): The handler's own grant covers its managed namespace.

**Installation-grant-authorized writes** (reactive results): The installation grant recorded at subgraph installation time authorizes all reactive writes. The installation grant is verified for validity (not expired, not revoked) at each re-evaluation.

See ENTITY-CORE-PROTOCOL.md §6.8 for the general write authorization model.

---

## 7. Reactive Mode

### 7.1 Dependency Registration

During evaluation, every `compute/lookup/tree` registers a dependency on its path. The dependency index maps tree paths to tuples of `(expression_uri, subgraph_path)`. When a tree path changes, the index identifies which expressions need re-evaluation and which subgraph's installation grant authorizes the re-evaluation.

```
register_subgraph_dependencies(subgraph_path, root_path, expression, ctx):
  for dependency_path in walk_tree_lookups(expression, root_path, ctx):
    dependency_index.add(dependency_path, {
      expression_uri: root_path,
      subgraph_path:  subgraph_path
    })

walk_tree_lookups(expression, root_path, ctx):
  deps = []
  visited = set()
  walk(expression, deps, root_path, visited, ctx)
  return deps

walk(entity, deps, root_path, visited, ctx):
  if entity.hash in visited: return
  visited.add(entity.hash)

  ; Collect tree dependencies from compute/lookup/tree
  ; Resolve relative paths against root_path before registering (v3.8, R2)
  if entity.type == "compute/lookup/tree":
    path = entity.data.path
    if entity.data.relative == true:
      path = clean_path(root_path + "/" + path)
    else:
      path = canonicalize(path, ctx.local_peer_id)   ; V7 §5.4 — match the absolute-at-rest path tree writes notify on
    deps.append(path)
    return

  ; Recursively walk all hash references in expression data, wherever they sit.
  ; v3.27: references are NOT always scalar field values — compute/apply.args is a
  ; map of hashes and compute/let.bindings is an array of maps carrying one. A walk
  ; that descends only into scalar fields registers nothing inside any function
  ; argument or any let binding, which is most of every non-trivial expression.
  for field_value in entity.data.values():
    walk_value(field_value, deps, root_path, visited, ctx)

  ; For closures, walk captured environment
  if entity.type == "compute/closure" and entity.data.env is not null:
    env = resolve(entity.data.env, ctx)
    if env is not null:
      walk(env, deps, root_path, visited, ctx)

walk_value(value, deps, root_path, visited, ctx):
  if value is system/hash:
    referenced = resolve(value, ctx)
    if referenced is not null:
      walk(referenced, deps, root_path, visited, ctx)
  else if value is array:
    for item in value:
      walk_value(item, deps, root_path, visited, ctx)
  else if value is map:
    for member in value.values():
      walk_value(member, deps, root_path, visited, ctx)
```

**The completeness property is the normative one; this pseudocode is its illustration `[MUST, v3.27]`.**
An implementation is measured against the rule — **every `compute/lookup/tree` reachable in the
expression graph is registered** (see *Conservative static collection* below) — and never against the
shape of the walker above. A walker that reaches every reference by a different traversal is
conformant; one that misses a reachable reference is not, however closely it mirrors this listing.
**The failure this pins is silent and no boundary-hash vector can observe it:** dependency
registration produces no boundary, so a subgraph with an unregistered dependency evaluates correctly
exactly once and is then never woken again.

**Reference fields in the expression grammar are scalar `system/hash`, with two enumerated exceptions
`[v3.27]`.** The exceptions are `compute/apply.args` (`map_of: system/hash`) and `compute/let.bindings`
(an array of `{name, value: system/hash}`), both declared in §2.1. **A new expression or args type that
places a reference inside a container is a defect unless it is added to that enumeration in the same
edit** — the invariant exists so the traversal's obligations can be stated and checked rather than
rediscovered, and it is what keeps a walker's coverage a property of the grammar instead of a list of
shapes someone happened to enumerate.

With the `compute/lookup/scope` vs `compute/lookup/tree` type split (§2.1), dependency collection is unambiguous — only `compute/lookup/tree` registers tree dependencies. Scope lookups (`compute/lookup/scope`) never produce tree dependencies.

**Exact-match dependencies.** `compute/lookup/tree` registers an **exact-path** dependency. The dependency index `match(path)` returns entries where `entry.path == path` — no prefix or subtree matching. A tree write at `app/data/sheet1/cells/A1` does NOT trigger re-evaluation of expressions depending on `app/data/sheet1`. Each watched path must be registered explicitly. Comparison is on **canonical absolute-at-rest paths** (§5.4): both registration (above) and tree-write notification canonicalize peer-relative paths to `/{local_peer_id}/…`, so a dependency authored as `app/x` matches a write to `/{local_peer_id}/app/x` — they are the same node.

**Pattern for subtree observation.** Applications that need "re-evaluate when any entity under X changes" compose from existing primitives rather than requesting a subtree lookup form:

1. **Content-addressed parent entity.** Store the parent as an entity whose data contains hash references to children. When a child changes, an application handler updates the parent entity, so the parent's content hash changes when any child changes. Compute expressions depend on the parent path (exact match).

2. **Subscription + aggregation.** Use `EXTENSION-SUBSCRIPTION.md §4` to subscribe to `app/data/sheet1/*`. The delivery target (a handler or continuation) reads affected entries and writes an aggregated value to `app/data/sheet1/summary`. Compute expressions depend on the summary path (exact match).

3. **History query for bounded reads.** For read-only subtree inspection, use `EXTENSION-HISTORY.md` query operations. Not reactive.

Each pattern uses existing extensions. Compute does not need its own subtree primitive.

**Relationship to `audit_subgraph` (§3.3).** `walk_tree_lookups` collects tree-read dependencies for the runtime dependency index. `audit_subgraph` collects read_paths, handler_targets, and write_paths for installation-time capability checking. Both walkers share cycle-detection structure and both walk closures' bodies and captured environments. Implementations MAY factor them into a single walker parameterized by visitor.

**Conservative static collection `[MUST]`.** `walk_tree_lookups` is conservative: **all `compute/lookup/tree` paths reachable in the expression graph are registered**, including paths behind untaken `compute/if` branches, and including paths reached only through a container-valued field (§2.1's `compute/apply.args`, `compute/let.bindings`). **This sentence is the conformance surface for dependency registration** — v3.27 promoted it from a description to the `[MUST]` because the pseudocode above previously implemented something strictly weaker than it, and an implementation written to the listing rather than to this rule can be complete for the grammar as it stands and silently incomplete for the next type added to it. The convergence check (§7.2) prevents spurious cascades — if a re-evaluation produces the same result hash, no tree write occurs. Implementations MAY refine this by recording only runtime-observed paths during the first evaluation, at the cost of potentially missing dependencies when conditional branches change. Static collection is the recommended default for simplicity and predictability.

**Index persistence and rebuild.** The dependency index is a peer-local runtime structure. It is NOT required to be persisted as entities in the tree.

On peer restart, the compute handler MUST rebuild the dependency index by scanning for installed subgraphs:

```
rebuild_dependency_index():
  for subgraph_path in entity_tree.list("system/compute/processes"):
    subgraph = entity_tree.get(subgraph_path)
    if subgraph.type == "system/compute/subgraph":
      ; Read the CURRENT expression at the tree path, not the original hash.
      ; The expression may have been modified since installation — per-operation
      ; checks catch unauthorized operations at evaluation time.
      expression = entity_tree.get(subgraph.data.root_expression_path)
      if expression is not null and is_compute_expression(expression):
        register_subgraph_dependencies(subgraph_path,
          subgraph.data.root_expression_path, expression, local_ctx)
```

The scan covers `system/compute/processes/*` — the compute handler's managed namespace. This is O(installed subgraphs), not O(tree size). The `root_expression_path` field on the subgraph metadata provides the tree path to the expression; the `root_expression` hash field records what was audited at installation time but is not used for rebuild.

### 7.2 Re-evaluation Trigger

When an entity tree path changes, the compute handler checks the dependency index and re-evaluates affected expressions.

```
on_tree_change(event_type, uri, new_hash, previous_hash, emission_context):
  for entry in dependency_index.match(uri):
    subgraph = entity_tree.get(entry.subgraph_path)

    if subgraph.data.status == "frozen":
      ; Frozen subgraph — skip, error already at result_path
      continue

    if cascade_depth(emission_context) >= RECOMMENDED_MAX_CASCADE_DEPTH:
      ; Cascade limit exceeded — error and freeze
      ; Materialized form is code-only (§2.4) — message/at are in-flight diagnostics, not
      ; part of the tree-written entity's content hash (cross-impl determinism).
      error_entity = {type: "compute/error", data: {code: "cascade_limit"}}
      entity_tree.put(subgraph.data.result_path, error_entity, emission_context)
      subgraph.data.status = "frozen"
      entity_tree.put(entry.subgraph_path, subgraph)
      continue

    re_evaluate(entry.expression_uri, entry.subgraph_path, emission_context)

re_evaluate(expression_uri, subgraph_path, emission_context):
  ; Caller (on_tree_change) has already verified subgraph is not frozen.
  ; Look up the subgraph metadata from handler namespace
  subgraph = entity_tree.get(subgraph_path)
  if subgraph is null or subgraph.type != "system/compute/subgraph":
    ; Subgraph uninstalled — clean up stale dependency registrations
    dependency_index.remove_subgraph(subgraph_path)
    return

  ; Verify installation grant is still available and not expired.
  ; Revocation is checked automatically by dispatch-layer verify_request
  ; (V7 §5.2 step 4, integrated per V3 C2) — compute does not need to call
  ; is_revoked explicitly. If the grant is revoked, the first dispatched
  ; impure op fails with permission_denied, the compute/error propagates
  ; through normal error handling, and the subgraph freezes via the usual
  ; reactive error path. Implementations MAY call is_revoked here as a
  ; fail-fast optimization to avoid wasted eval cycles on a doomed re-eval.
  installation_grant = content_store.get(subgraph.data.installation_grant)
  if installation_grant is null or is_expired(installation_grant):
    ; Grant missing or expired — write error to result path, freeze subgraph
    ; Materialized form is code-only (§2.4) — message/at are in-flight diagnostics.
    error_entity = {type: "compute/error", data: {code: "installation_grant_invalid"}}
    entity_tree.put(subgraph.data.result_path, error_entity, emission_context)
    subgraph.data.status = "frozen"
    entity_tree.put(subgraph_path, subgraph)
    return

  expression = entity_tree.get(expression_uri)
  if expression is null:
    dependency_index.remove_subgraph(subgraph_path)
    return

  ; Build evaluation context with installation grant as capability source
  eval_ctx = {
    capability: installation_grant,
    author: local_peer_identity,
    chain_id: emission_context.chain_id
  }

  budget = reactive_budget(emission_context, installation_grant)
  scope = empty_scope()
  result = evaluate(expression, scope, budget, eval_ctx)

  ; Handle evaluation errors
  if result.type == "compute/error":
    entity_tree.put(subgraph.data.result_path, result, emission_context)
    return

  result_path = subgraph.data.result_path
  old_result_hash = entity_tree.get_hash(result_path)
  new_result_hash = content_hash(result)

  if old_result_hash != new_result_hash:
    next_context = increment_cascade(emission_context)
    entity_tree.put(result_path, result, next_context)
```

**Convergence check**: If the new result hash equals the old result hash, the expression has converged and no tree write occurs. This prevents unnecessary cascades.

**Result writes MUST use the standard tree write path** (`entity_tree.put`) that participates in the emit pipeline and notification layer (SYSTEM-COMPOSITION.md §1.1). Writes that bypass the notification layer (e.g., direct content store + location index writes) will not trigger downstream reactive re-evaluations, breaking cascade chains. This is the mechanism that connects compute subgraphs into pipelines — subgraph A's result write notifies the emit pipeline, which triggers subgraph B's re-evaluation if B depends on A's result path.

**Result path.** The result path is set at installation time and stored on the subgraph metadata entity (§2.5). The default convention is `{root_expression_path}/result`. The installer MAY override this via the install request's `result_path` field. The result path MUST be covered by the installation grant with write access.

**Authorization source.** Reactive re-evaluation uses the subgraph's installation grant (§3.3) as the authorization for all impure operations — tree reads, handler dispatches, and result writes. The installation grant was verified at installation time to cover all impure operations in the subgraph. At reactive time, the grant is checked for validity (not expired, not revoked) but not re-audited against the subgraph's operations. If the installation grant is no longer valid, re-evaluation writes a `compute/error` entity to the result path and the subgraph freezes.

**Reactive error handling.** When reactive re-evaluation produces a `compute/error` entity:

1. The error entity is written to the subgraph's `result_path`. This is an entity like any other — content-addressed, storable, inspectable.
2. The error entity's hash differs from the previous result's hash (unless the same error was already stored). The convergence check treats it as a new result — downstream dependencies see the change.
3. Downstream expressions that depend on the result path will re-evaluate. If they attempt to use the error entity as input (e.g., `compute/field` on a `compute/error`), they produce their own errors. Errors propagate through the dependency graph.
4. Error propagation terminates when: (a) an error hash matches an already-stored error (convergence check), or (b) cascade depth limit is reached.

This is the same model as NaN propagation in IEEE 754 arithmetic — errors are values that flow through computation and are detectable at any point.

**Error short-circuit normative.** Once a `compute/error` enters a value position, all expression types that consume values MUST short-circuit and propagate the error rather than attempting to read its fields. This includes `compute/arithmetic`, `compute/compare`, `compute/logic`, `compute/field`, `compute/construct`, `compute/apply` (both handler and closure modes — **over the operands the apply consumes**: `resource`, `capability`, and closure arguments bound to parameters; **a builtin's write payload is not a consumed operand — see the SA-9 `store` worked example below**), and `compute/if` (condition position — a `compute/error` condition short-circuits the `if` to the error, neither branch is evaluated). The §4.1 pseudocode enforces this via `if is_error(x): return x` after every sub-evaluation, where **`is_error` is the kind-based predicate §4.1 defines** — a `compute/error` that evaluated *successfully* under SA-1 is still an error here. Implementations MUST produce the same short-circuit behavior regardless of how they structure their evaluator.

> **Worked example — an error in a `compute/construct` field `[the case that diverged three ways]`.**
> A `compute/error` literal is the `value` field of a `compute/construct`, construct as root.
>
> - **SA-1** returns it unchanged from `evaluate` — it did not *fail*, it *is* an error value.
> - The construct branch's guard `if is_error(value): return value` **fires**, because the predicate
>   is kind-based.
> - **The construct's whole result is that error.** No entity boundary is produced, nothing is
>   materialized, and the construct's other fields are irrelevant.
>
> **The two wrong answers, named so they are recognizable.** *Embedding* it — materializing a bare
> code-only `compute/error` entity and referencing it by `system/hash` from the construct's field —
> is what the old N1 listing and the old `kind_of` set read as licensing; that is now foreclosed.
> *Embedding without materializing* leaves an in-flight value in a field, which reaches the encoder
> and is a fault under any reading: **an unmaterialized value MUST NOT reach the wire encoder.**
>
> **Where an error does materialize:** only where it is written — the §7.2 `result_path` and SA-9
> `store`. That is the sole surface §2.4's code-only content-hash rule governs.

> **Worked example — an error as SA-9 `store`'s `value` `[the case the two readings answer oppositely; MUST]`.**
> The store builtin is dispatched as a `compute/apply` in **handler mode**, so the rule above appears
> to reach its `value`. **It does not, and the boundary is what this example pins.**
>
> **An apply short-circuits on the operands it *consumes* — `resource`, `capability`, and closure
> arguments bound to parameters. A builtin's *write payload* is not consumed.** SA-9 `store`'s
> `value` is handed opaquely to the handler and materialized at the write site, so:
>
> - **`store(path, <a compute/error>)` writes a code-only `compute/error` to `path`** and the store
>   succeeds. It does **not** propagate and write nothing.
> - **Both in-language forms behave identically** — a minted error and one that evaluated successfully
>   as a value under SA-1 — because `is_error` is kind-based (§4.1). One value, one behaviour.
> - An error in the apply's `resource` or `capability` **does** short-circuit, unchanged — **on the
>   handler-dispatch path, which is the only path those fields are legal on.** On a
>   `system/compute/builtins/*` path they are **rejected outright** as `invalid_expression` (§2.1),
>   so the short-circuit is not reached there and is not expected to be.
>
> **The principle, which is this paragraph's own rationale applied honestly.** Short-circuit exists so
> that no expression *reads an error's fields*. A write payload's fields are never read — they are
> materialized under §2.4's code-only rule, which exists precisely to define what those bytes are.
> **The hazard the short-circuit rule guards against does not arise at a write site**, and extending
> the rule there would forbid the one thing §2.4 is written to describe.
>
> **The tell, if the principle is ever doubted.** Under the propagate reading an error could never
> reach the store write, so "stored via SA-9 `store`" in §2.4 — and every statement naming that site —
> becomes text that can never execute. **Unreachable normative text reads as licensing and is how one
> implementation's wrong branch was chosen before.** The write reading is the only one under which the
> whole taxonomy is reachable.

**Installation grant failure** is a special case. When the installation grant is revoked or expired, the error entity written to the result path has code `installation_grant_invalid`. The subgraph freezes — no further re-evaluations occur until a new installation grant is provided (via re-installation).

**Revocation is automatic via ENTITY-CORE-PROTOCOL.md §5.2.** Compute's reactive re-evaluation dispatches sub-operations via `ctx.dispatch_execute` (tree reads via `compute/lookup/tree`, handler calls via `compute/apply`, store writes via the store builtin). Each sub-dispatch goes through `verify_request` (ENTITY-CORE-PROTOCOL.md §5.2), which includes `is_revoked` as step 4 (integrated per V3 C2). If the installation grant has been revoked since subgraph installation, the first sub-dispatch fails with `permission_denied`, the resulting `compute/error` propagates through the normal reactive error-handling path, and the subgraph freezes with `installation_grant_invalid` at its result_path.

Compute does NOT need to call `is_revoked` explicitly — dispatch handles it. The compute handler's §7.2 re_evaluate pseudocode only checks `is_expired` before eval (expiry is a lightweight local check; revocation requires a tree lookup and is best deferred to the dispatch layer anyway).

**Optional fail-fast optimization.** Implementations MAY call `is_revoked(installation_grant, ctx)` in re_evaluate as a fail-fast optimization to avoid wasted eval cycles on a doomed re-evaluation. This is purely an optimization — correctness is preserved either way by ENTITY-CORE-PROTOCOL.md §5.2 step 4 catching the revocation on the first sub-dispatch.

**Implementation helpers** (cross-implementation convention, not required by the spec):
- `is_expired(capability, now)` — check `expires_at` against current time
- `is_revoked(capability, ctx)` — defined in ENTITY-CORE-PROTOCOL.md §5.1, called by ENTITY-CORE-PROTOCOL.md §5.2 `verify_request` automatically

### 7.3 Cascade Limits

Reactive re-evaluation can trigger tree writes, which trigger further re-evaluations. This cascade **MUST** be bounded.

The compute extension participates in the shared cascade depth counter defined in SYSTEM-COMPOSITION.md §3. The cascade depth counter, threshold table (RECOMMENDED defaults: 8 for subscription suppression, 16 for compute freeze, 32 for system refusal), cascade depth initialization rules, and cross-peer `chain_id → cascade_depth` tracking are all specified in SYSTEM-COMPOSITION.md §3.1–§3.4.

When cascade depth reaches the compute threshold (SYSTEM-COMPOSITION.md §3.2, RECOMMENDED default: 16), the subgraph is frozen with a `cascade_limit` error at its result_path (§7.2). This is the same error/freeze pattern used for installation grant failure — both are structural conditions that retry cannot resolve. Budget exhaustion during reactive re-evaluation writes a `compute/error` to the result_path but does NOT freeze the subgraph — budget exhaustion may be transient if dependencies change to reduce the computation's cost, so the subgraph remains active for future triggers. The cascade depth limit is a safety boundary — if normal operation reaches it, the reactive graph should be restructured or the peer's cascade limit increased. Recovery from frozen state is via re-installation (§3.3).

### 7.4 Reactive Budget Model

Reactive re-evaluations get independent budgets, consistent with how subscriptions handle notification budgets (EXTENSION-SUBSCRIPTION.md §4.5). Reactive budgets MUST honor the installation grant's compute constraints (§5.5), consistent with explicit evaluation via `init_budget` (§5.2):

```
reactive_budget(emission_context, installation_grant):
  ; Honor installation grant's compute constraints — same rule as init_budget (§5.2)
  compute_constraints = installation_grant.data.constraints?["system/compute"] or {}
  return {
    operations: compute_constraints.max_compute_operations or peer_default_max_ops
    depth:      compute_constraints.max_compute_depth or peer_default_max_depth
    chain_id:   emission_context.chain_id        ; Inherited for causal tracing
  }
```

- **Budget**: Fresh, independent. NOT derived from the writer's remaining budget. Bounded by the installation grant's `constraints["system/compute"]` entry, falling back to peer-wide defaults per §9.3 when constraint keys are absent.
- **chain_id**: Inherited from the emission context for causal tracing.

A tree write that triggers N re-evaluations does not divide the writer's budget among them. The writer pays for its write; each re-evaluation has its own budget.

**chain_id continuity across cascades.** `chain_id` continuity is a composition-level invariant — all writes in one causal chain share a single `chain_id`, which MUST NOT be regenerated mid-cascade. See SYSTEM-COMPOSITION.md §3.4 for the full chain_id propagation and cross-peer cascade tracking model.

**Why honor installation grant constraints reactively.** V5 places compute resource limits on capability `constraints["system/compute"]`. If reactive re-evaluation ignored these constraints, an installer who issued a narrow capability (e.g., `max_compute_operations: 1000`) would see that bound honored on explicit eval but silently bypassed on reactive re-evaluation — a constraint escalation. The reactive path MUST read the same constraints as the explicit path.

### 7.5 Integration with Subscriptions and Inbox

The compute extension, subscription extension, and inbox extension share an internal tree notification pattern:

```
Tree write occurs
    │
    ├─ Subscription handler: match subscriptions → deliver inbox EXECUTEs to remote peers
    ├─ Compute handler: match dependencies → re-evaluate expressions → store new results
    │
    └─ Both triggered by same tree notification, independent of each other
```

When all three extensions are present:

1. An inbox delivery arrives (EXTENSION-INBOX.md)
2. The inbox handler writes the delivered entity to a local tree path (EXTENSION-INBOX.md §3.2, or stores in tree when no continuation)
3. That tree write triggers internal notifications
4. Subscriptions matching the path fire notifications to remote peers (EXTENSION-SUBSCRIPTION.md §4.1)
5. Compute expressions depending on the path re-evaluate (§7.2)
6. Re-evaluation may produce a new result stored at another path, triggering further notifications

For peers implementing the compute extension, this is the formal continuation model that EXTENSION-INBOX.md §3.3 references: inbox delivery → tree write → reactive re-evaluation through the dependency graph. The dependency graph IS the continuation — no special continuation type is needed.

For peers **without** the compute extension, inbox delivery remains fully functional: the inbox handler writes the delivered entity to a local tree path, completing the synchronization. The peer has an up-to-date copy of remote data. This covers the primary use case of directory sync, replication, and basic inter-peer data exchange. Compute adds reactive processing on top of that foundation, but the foundation stands on its own.

---

## 8. Determinism

### 8.1 Requirements

Pure compute operations **MUST** produce identical result hashes for identical input hashes, regardless of which peer evaluates them or when evaluation occurs.

This enables:
- Cross-implementation verification (Rust and Python produce identical outputs)
- Memoization (same expression hash → same result hash)
- Content-addressed build systems (deterministic from source to output)

Arithmetic and comparison operations have normative result-type and precision rules defined in §2.2. These rules are part of the determinism contract — implementations MUST follow them to produce identical hashes for identical inputs. IEEE 754 special values (`+Inf`, `-Inf`, `NaN`) MUST encode to canonical CBOR representations (§2.2).

### 8.2 Evaluation Order

To ensure deterministic results:

- `compute/let` bindings **MUST** be evaluated sequentially in declaration order (array index order). Each binding's value expression is evaluated in the scope accumulated from all prior bindings (`let*` semantics — see §2.1). This is both a determinism requirement (same order across implementations) and a semantic requirement (later bindings can reference earlier ones).
- `compute/apply` arguments **MUST** be evaluated in ECF canonical map key order: map keys sorted by encoded byte length, then lexicographically (ENTITY-CBOR-ENCODING.md §4.1). This matches the order in which the constructed params entity's fields are encoded on the wire.
- `compute/construct` fields **MUST** be evaluated in ECF canonical map key order (same rule as `compute/apply` above).
- Inline types evaluate `left` before `right`.

ECF encoding (ENTITY-CBOR-ENCODING.md; ENTITY-CORE-PROTOCOL.md §1.3) ensures identical bytes for identical values.

---

## 9. Constants

### 9.1 Error Codes

| Code | Meaning |
|---|---|
| `budget_exhausted` | Computation budget reached 0 |
| `depth_exceeded` | Maximum recursion depth reached |
| `type_mismatch` | Incompatible operand types |
| `division_by_zero` | Division or modulo by zero |
| `not_found` | Lookup path missing in scope and tree, or hash unresolvable during evaluation |
| `unknown_type` | Unrecognized compute entity type |
| `missing_argument` | Required argument not provided to closure |
| `invalid_expression` | Malformed compute expression |
| `cascade_limit` | Reactive cascade depth exceeded |
| `permission_denied` | Capability does not cover the target path or operation |
| `installation_grant_invalid` | Installation grant revoked, expired, or missing |
| `index_out_of_range` | An array index is negative or ≥ array length — `compute/index`, and `compute/builtins/assoc` (§3.5) |
| `cast_out_of_range` | `compute/numeric-cast` float→integer target out of range, `NaN`, or ±`Inf` |
| `count_out_of_range` | `compute/builtins/range` `n` is negative, or exceeds the maximum representable array length (§3.5) |
| `scope_unreachable` | A `kind:"entity"` scope binding's hash resolves in neither the local content store nor the envelope `included` (§2.3 N8) — error-as-value at status 200 |

### 9.2 Standard Operations

| Operation | Handler | Description |
|---|---|---|
| `eval` | `system/compute/*` | Evaluate a compute expression |
| `eval` | `system/compute/builtins/*` | Evaluate a builtin operation |

### 9.3 Recommended Limits

| Limit | Recommended Value | Constant |
|---|---|---|
| Default compute budget | 100,000 operations | `peer_default_max_ops` |
| Maximum evaluation depth | 1,024 | `peer_default_max_depth` / `RECOMMENDED_MAX_DEPTH` |
| Maximum cascade depth | 16 | `RECOMMENDED_MAX_CASCADE_DEPTH` |

These peer-wide defaults apply when the capability's `constraints["system/compute"]` entry is absent or does not set the corresponding key. Per-capability limits (set by the capability issuer) override these defaults per the minimum rule in §5.2. Peers MAY configure these per-deployment.

---

## 10. Conformance

### 10.1 MUST Implement

- All eight core expression types (§2.1): literal, lookup/scope, lookup/tree, lookup/hash, apply, if, let, lambda
- All eight inline expression types (§2.2): field, arithmetic, compare, logic, construct, index, length, numeric-cast
- Closure and scope value types (§2.3)
- Result and error types (§2.4)
- Evaluation algorithm with entity resolution and scope (§4.1, §4.2, §4.3)
- Special form semantics for `compute/if` — non-taken branch not evaluated (§2.1)
- `compute/apply` dual mode — handler dispatch and closure application (§2.1)
- Budget decrementation on every evaluation step (§5.1)
- Budget exhaustion produces `budget_exhausted` error (§5.1)
- Depth limit enforcement (§5.4)
- Capability verification for impure operations (§6.2)
- Deterministic evaluation order (§8.2)
- Identical result hashes for identical inputs on pure expressions (§8.1)
- Normative arithmetic semantics: float promotion for non-exact division, truncated mod, IEEE 754 binary64, canonical CBOR encoding of special values (§2.2)
- Normative comparison semantics: type compatibility rules, float promotion for mixed numeric operands, lexicographic string ordering without Unicode normalization (§2.2)
- Eval handler `is_compute_expression` pre-check for non-null entities (§3.2)
- `capture_scope` MUST call `ctx.mark_encountered` after content store write (§4.4)
- `load_scope` MUST use direct content store access for `closure.data.env` hash, MUST mark encountered, MUST return error if missing (§4.3)
- `resolve()` MUST validate resolved entities via `validate_compute_resolvable` — Tier 0 (`content_store_access`) and Tier 1 (`is_compute_type`) (§4.2)
- `is_compute_type` function — includes `compute/lookup/hash` (§4.2)
- Encountered-during-read minimum resolution guarantee — scoped to `system/hash`-typed fields and compute-typed entities (§4.2)
- `compute/lookup/hash` evaluation: resolve hash, return non-expressions as values (§4.1)
- Install audit collects `compute/lookup/hash` targets and validates path hints against caller's tree GET grant (§3.3 Phase 2b)
- Sealed `authorized_data_hashes` on subgraph metadata (§3.3)
- `validate_compute_resolvable` Tier 2: sealed set check for installed subgraphs (§4.2)
- Tail calls in identified tail positions (closure body, if branches, let body, lookup/tree expression, lookup/hash expression) MUST NOT consume depth (§4.1)
- Budget MUST still decrement for tail calls (§4.1)
- `compute/lookup/tree` MUST support optional `relative` field; relative paths resolve against `ctx.subgraph_root` via `clean_path` (§2.1, §4.1)
- `compute/lookup/hash` path hint MUST support optional `relative` field (§2.1)
- Install audit and dependency walker MUST resolve relative paths **and canonicalize peer-relative paths to `/{local_peer_id}/…` (ENTITY-CORE-PROTOCOL.md §5.4)** before collecting/registering, so dependencies key on the absolute-at-rest path tree writes notify on (§3.3, §7.1)
- `compute/lookup/tree` MUST check `ctx.capability` covers the target path before reading (§4.1)
- `compute/apply` handler mode with `capability` field MUST dual-check: `ctx.capability` must cover the target — including the resource — before dispatching with the provided capability (§4.1) (v3.10 — F2 full-resolution)
- `compute/apply` MUST support optional `resource` field carrying a `system/hash` reference resolving to a `system/protocol/resource-target` (§2.1) (v3.10 — F1)
- When `compute/apply.capability` is present, `compute/apply.resource` MUST also be present; absent → `invalid_expression` at both eval-time (§4.1) and install-time audit (§3.3) (v3.10 — F5)
- `dispatch_execute` MUST carry the resource through to the constructed EXECUTE's `resource` field (§4.1) (v3.10 — F4)
- Install audit MUST collect static-literal resource targets from `compute/apply.resource` and use them in `check_grant_covers` (§3.3) (v3.10 — F3)
- Install audit MUST verify that `ctx.execute.data.author` appears **as a granter anywhere in** the static-literal `compute/apply.capability` authority chain, via `check_creator_authority` (ENTITY-CORE-PROTOCOL.md §5.5 — in-chain, *not* rooted-at-author); reject with 403 `embedded_cap_unauthorized` when it does not (§3.3) (v3.11 — CP1)

  > **In-chain, not chain-root (correction).** The label above read *"chain-root against `ctx.execute.data.author`"*, while the §3.3 pseudocode has always performed the in-chain check (*"checks whether the installer's identity is in the granter chain"*) and V7 §5.5 states the rule generally. Same pre-correction residue `EXTENSION-CONTINUATION.md` §3.1a swept for `dispatch_capability`, unswept here. It is silent for a locally-installed `compute/apply` — the installer is both author and chain root — and load-bearing the moment the capability was attenuated to the installer by another peer, which a chain-root reading rejects outright.
- Install audit MUST run the CP1 in-chain check BEFORE F3 resource-coverage check on the same `compute/apply` entity (v3.11)
- `dispatch_execute` MUST propagate full execution context (author, caller_capability, chain_id) per ENTITY-CORE-PROTOCOL.md §6.8 (§4.1)
- Eval can be invoked with pre-populated scope for entity-native handler dispatch (§3.2)
- Builtin handler override prohibition — registration targeting `system/compute/builtins/*` MUST be rejected (§3.5)
- Collection builtins `map`/`filter`/`fold` with the spec-pinned args types + observable semantics (§3.5)
- The v3.24 collection primitives `range`/`group-by`/`concat`/`assoc` with their pinned args types, result shapes and error codes (§3.5) — `concat-args.collections` is **one** `system/hash` (v3.27)
- The consumed/contained disposition table and the rule that generates it — placed-without-reading contains, read-to-decide consumes (§3.5) (v3.27 — D2)
- A `compute/error` behaves identically minted or value-form; no disposition may key on how it was produced (§3.5, restating §2.4) (v3.27 — D1)
- Evaluation-limit dispositions: `depth_exceeded` contains; `budget_exhausted` and `cascade_limit` short-circuit in every position, **keyed on the `code` in both arms** (§3.5) (v3.27 — D5/D6)
- `group-by` entity-valued key equality is byte-identity over the **materialized** encoding (§3.5) (v3.27 — D4)
- Dependency registration completeness — every `compute/lookup/tree` reachable in the expression graph is registered, **including references inside container-valued fields** (§7.1) (v3.27 — D8)
- `store` builtin for tree writes, capability-gated per §6.3 (§3.5)
- Entity-defined handler evaluation — handlers whose logic is a compute expression (`expression_path`, ENTITY-CORE-PROTOCOL.md §3.7)
- Integer `add`/`sub`/`mul` sign-agnostic 64-bit two's-complement (truncate to 64 bits on arbitrary-precision hosts); `div`/`mod`/`compare` signed-default; integer results canonically encoded by their signed interpretation; `numeric-cast` eager / point-of-use (§2.2 rules 8–11)
- `compute/numeric-cast` conversion semantics — intra-numeric, with the pinned edge cases (§2.2)
- All error codes (§9.1)

### 10.2 SHOULD Implement

- Compute handler at `system/compute/*` (§3.1)
- The inline-equivalent builtin handler aliases at `system/compute/builtins/{arithmetic,compare,logic,field,construct}` (§3.5) — the collection builtins and `store` are now MUST (§10.1)
- Install and uninstall operations (§3.3, §3.4) — required if reactive mode is implemented
- Subgraph metadata at `system/compute/processes/*` (§2.5)
- Memoization for pure expressions (§4.6)
- Scope capture optimization — capture only referenced bindings (§4.4)
- `max_compute_operations` and `max_compute_depth` resource limit enforcement (§5.5)
- Write authorization checks per §6.3 table
- Content store access gating (§4.2)
- Reactive mode with exact-match dependency registration keyed by `(expression_uri, subgraph_path)` tuples (§7.1)
- Installation grant verification on reactive re-evaluation (§7.2)
- Convergence check before tree write on re-evaluation (§7.2)
- Cascade depth limiting via shared counter (§7.3)
- Subgraph status field (`active`/`frozen`) on metadata (§2.5)
- Frozen subgraph skip in reactive trigger handling (§7.2)
- Freeze on cascade depth exceeded (§7.2)
- Re-installation recovery for frozen subgraphs (§3.3)
- Independent reactive budget (§7.4)
- Dependency index rebuild on restart (§7.1)
- Type definitions for all compute types (§2.1–§2.6) registered at `system/type/{type_name}` tree paths, enabling type-aware tooling discovery

### 10.3 MAY Implement

- Peer-configurable cascade depth limit *value* (§7.3) — a local resource bound, not a determinism concern. (Per the standard-IR-floor convergence, v3.14: every compute-deterministic capability is MUST-given-COMPUTE — §10.1 — and only resource bounds stay flexible. The collection builtins, `store`, and entity-native handler evaluation were promoted out of this section into §10.1.)

### 10.4 Implementation-Defined

- Compute process tree layout (where expressions and results are stored)
- Default compute budget value
- Reactive re-evaluation scheduling (synchronous vs queued)
- Memoization table size limits and eviction policy
- Scope capture strategy (full capture vs referenced-only)
- Builtin handler registration mechanism
- Subgraph ID derivation from root expression path (§3.3)
- Tree-scoped hash resolution mechanism beyond the minimum guarantee — encountered-during-read is required (§4.2); reverse index and scan are permitted enhancements
- Cascade depth limit value (§7.3) — recommended 16, implementations MAY allow configuration
- The evaluation strategy itself — the reference tree-walk (§4) or an admitted alternate engine (§11); the representation of any alternate engine stays implementation-local (§11.5)

## 11. Alternate-Engine Admission

The reference evaluation algorithm (§4) is the **conformance floor**: a peer that implements it (and §10.1) is
fully conformant, and the cross-impl conformance LOCK is over reference evaluators. A peer **MAY** additionally
add an **alternate execution strategy** for the same content-addressed IR — a faster interpreter (decode-once /
resolved-node), a compiled or fused handler, a memoizing backend, a defunctionalized walker. Because the IR is
content-addressed and the conformance surface is the *materialized* boundary, every such engine is governed by
**one** admission rule (AE-1) plus the invariants and evidence that make it hold (AE-2–AE-6). Stating the rule
once, over "any engine," is deliberate — an equivalence pinned per-engine-kind springs apart at the next kind
nobody wrote a rule for.

An alternate engine is **optional and per-implementation** — a performance choice, never a conformance
requirement. This section governs any engine a peer chooses to add; it does not require peers to build one, and
does not call for the cohort to build the *same* one (three transcriptions of one engine would be
cohort-consistent, not independent convergence).

### 11.1 AE-1 — materialized-boundary equivalence (the admission MUST)

An alternate execution strategy is **conformant iff**, for the same IR over the same inputs, it produces the
**byte-identical materialized boundary** the spec defines: the same canonical CBOR encoding and the same content
hash at every compute→non-compute crossing, plus the same terminal outcome. The boundary set is exactly the
crossings of §2.3 (one home — no new surface) together with the two outcome forms:

1. **Materialization crossings** — the §2.3 N1 placement sites (a `compute/scope` binding, a `compute/construct`
   field, a `compute/apply` argument) and the four compute→non-compute crossings (a constructed/evaluated value
   **stored to the tree / a `result_path`**, **returned from a handler**, **passed as a `compute/apply` arg**, or
   **sent on the wire**) — each materialized as a **bare** entity per V7 §1.4, byte-identical to the hand-built
   entity.
2. **The cross-peer materialized subtree** — a `compute/closure`'s reachable scope materialized into the envelope
   `included` map on peer handoff (§2.3 N7): the bytes another peer resolves MUST match.
3. **A materialized `compute/error`** — content-hashed over **`code` alone** (§2.4); `message`/`at`/`expression`
   are in-flight diagnostics, **not** part of the boundary. This is the ~40% of the input space where an
   alternate engine is most likely to diverge (error paths are re-derived, not shared), so it is named explicitly.
4. **The terminal resource outcome** — value vs. a resource-limit `compute/error`, **and its trigger point**:
   `budget_exhausted` (§5.1), `depth_exceeded` (§5.4, raised §4.1), and `cascade_limit` (§7.2) MUST each fire at
   the **same logical point** on every engine.

**The boundary bytes are fixed by the spec, not by any implementation** — the canonical CBOR encoding (V7 §1.4),
the value model (§2.2/§2.3), and the frozen conformance corpus (§10 / `GUIDE-CONFORMANCE §7c`) are the authority;
no implementation is privileged. An alternate engine is admitted against the frozen corpus's pinned boundary
hashes, which independent ground-up implementations have confirmed (the three-way LOCK), never against one
runtime's bytes.

Equivalence is defined **only** at that boundary. It is **NOT** required — and MUST NOT be assumed — at
**intermediate steps** (per-node content-addressing the reference does internally is an interpretation artifact
an alternate engine may drop) or at **content-store contents** (an alternate engine legitimately leaves *fewer*
entities in the store; a byte-for-byte store-equality test is a *false* conformance test that rejects a valid
engine). An engine that changes any boundary hash — or a terminal trigger point — is **non-conformant** (a
mis-evaluation), not an optimization.

### 11.2 AE-2 / AE-3 / AE-4 — the cross-engine invariants

Boundary-equivalence is the observable; three invariants are what an engine MUST preserve to achieve it.

- **AE-2 — impure-frontier preservation.** An alternate engine MUST NOT reorder, elide, duplicate, or introduce
  an impure operation (`tree.get` / `tree.put` / dispatch / `check_permission`), and MUST register the **same
  reactive dependency set** the reference registers (§7.1). A fast interpreter that resolves hashes by a
  different tier (reverse index vs. encountered-during-read) MUST still record the dependency edges the reference
  records, or reactive re-evaluation forks across engines.
- **AE-3 — demand (laziness) equivalence.** An alternate engine MUST evaluate exactly the **demanded** subgraph —
  no more (speculative evaluation of an undemanded branch could materialize or fault where the reference does not)
  and no less. **Error-driven demand is part of demand:** the §4.1 short-circuits are demand boundaries an engine
  MUST replicate exactly — a `compute/if` whose condition evaluates to a `compute/error` short-circuits to that
  error with **neither branch evaluated**; a short-circuiting `compute/logic` and the `if is_error(x): return x`
  after every sub-evaluation likewise cut demand.
- **AE-4 — metering at the logical boundary.** The observable operation budget is metered over **logical
  `evaluate()` steps**, not host/engine steps — one decrement per `evaluate()` step, `resolve()` at zero
  (§5.1/§4.2). A faster interpreter still decrements `operations` once per logical step; a fused/compiled handler
  that runs a pure interior natively MUST account **the logical step count the reference would charge on the same
  demanded path** (data-dependent loops included). A handler that counted itself as ≈1 op would complete where
  the reference `budget_exhausted`s — a boundary divergence, not a speedup. Eval-depth is likewise logical: the
  **tail-call trampoline** (tail calls do not consume depth, §4.1) is a spec semantic every engine MUST
  reproduce — an engine that recurses on the host stack where the reference trampolines will hit `depth_exceeded`
  (or overflow) where the reference loops or completes.

### 11.3 AE-5 / AE-6 — admission evidence

- **AE-5 — admission is demonstrated in-process, never over the wire.** An alternate engine is admitted only by
  running the frozen conformance corpus **in-process with that engine as the evaluator** and matching the pinned
  boundary (AE-1). A wire/handler-path conformance run cannot attest *which engine ran* inside a peer, so it
  cannot distinguish the alternate engine from a reference fallback and is **not** admission evidence. Admission
  requires the in-process (`inproc`) corpus profile (`GUIDE-CONFORMANCE §7c.3`).
- **AE-6 — the alternate engine MUST run every vector; no per-vector fallback.** Every corpus vector in an
  admission run MUST be evaluated by the alternate engine on each side — never silently deopted to the reference
  for the hard cases (a run that falls back compares the reference to itself; the agreement is circular). Deopt
  at *production* runtime is a correctness-preserving safety net (the lowering contract's L-3); deopt during an
  *admission run* voids the evidence for that vector.

### 11.4 Engine-specific requirements (compiled backends)

AE-1–AE-6 govern every engine. A **compiled** backend additionally carries the lowering-specific MUSTs of the
lowering contract — source-IR preservation (L-2), deopt fallback to interpreting the source IR (L-3), the
pure-interior fusion unit (L-4 — the fusion-specific instance of AE-2), and memoization soundness (L-5 —
pure-only, byte-identical). A fast interpreter with no separate compiled artifact does not need L-2/L-3.

### 11.5 Interpreter architecture (RECOMMENDED)

An **explicit-state / resolved-node** evaluator (versus a recursive host-stack tree-walk) is what makes
preemption (a capturable frame at a yield boundary) and fusion (a stable interior to specialize) tractable.
Implementations SHOULD converge on an explicit-state evaluator for their fast path. This is guidance, **not** a
mandated representation — AE-1 admits any engine that is boundary-equivalent, however structured; the engine's
representation stays implementation-local, and MAY live in a separate research/experiment repo (the admission
*run*, not the engine, is what crosses into the conformance tier).

### 11.6 Conformance vectors

The alternate-engine vectors run over the differential corpus (§10 / `GUIDE-CONFORMANCE §7c`), which MUST
exercise the divergence-prone classes: numeric-intent **through indirection** (§2.2 rule 11, materialized),
materialized **error paths** (code-only), **budget-edge**, **deep tail recursion** (past the host limit, within
the depth budget), **float-carrying** entities (canonical CBOR), and **cross-peer** closure transfer.

- `ae_boundary_equivalence` — same IR + inputs ⇒ identical boundary-hash sequence on the reference and the
  alternate engine, **in-process** (AE-5). A skip counts as a failure.
- `ae_error_boundary` — a materialized `compute/error` compares **code-only** across engines (AE-1 outcome 3).
- `ae_resource_stoppoint` — a resource-edge workload reaches the same terminal outcome at the same **logical
  point**: `budget_exhausted`, `depth_exceeded`, `cascade_limit` (AE-1 outcome 4 / AE-4).
- `ae_no_intermediate_leak` — the alternate engine's store contents **may differ** (fewer entities) while the
  boundary hashes match (the test does **not** over-assert store equality).
- `ae_demand_equivalence` — an undemanded branch that would fault/materialize is **not** evaluated, including an
  error-short-circuited `if` branch (AE-3).
- `ae_metering_parity` — the `operations` decrement sequence matches per logical step (AE-4).
- `ae_dependency_parity` — the reactive dependency set an engine registers matches the reference (AE-2 / §7.1).

> **§7.1's completeness `[MUST]` is NOT satisfied by `ae_dependency_parity`, and the two must not be confused `[v3.27]`.** This row compares an alternate engine against **its own peer's reference walker**, so a peer whose reference walker misses a reachable reference passes it with both engines wrong in the same way. §7.1's rule is a property of the walker against the **grammar**, it is cross-impl-observable, and it belongs to the **`validate-peer` register** (`GUIDE-CONFORMANCE` §7.0's behavioral class) rather than to the differential corpus — **dependency registration produces no boundary**, which is precisely why a corpus vector cannot see it. The discriminating construction is a subgraph whose only `compute/lookup/tree` sits inside a `compute/apply` argument, since a walker that handles `compute/let.bindings` alone passes the `let` case.

### 11.7 Admission status

**Axis-1** — a Go decode-once resolved-node fast interpreter (research/experiment tier) — is the **first admitted
alternate engine** (2026-07-23). The frozen `inproc` corpus (330 vectors) run in-process through Axis-1 produced
the byte-identical materialized boundary of the reference on **all 330 vectors, 0 fallbacks**, with
`engine-role==alternate` enforced and 6 distinct error codes matching the reference. The run also demonstrated
AE-5's teeth: it caught a `numeric-cast → uint` **index-code drift** (Axis-1 had been transcribed from the
reference before the §9.1 out-of-range-index ruling landed and answered `type_mismatch` where the reference
answers `index_out_of_range`); the corpus surfaced the drift and the fix closed it. *(This is one implementation's
alternate engine admitted against the spec-arbitrated boundary — the admission procedure is proven; a second,
independent alternate engine is what would upgrade the evidence to independent convergence. See the compute
conformance ledger for the residual coverage items.)*

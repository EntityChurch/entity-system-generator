# System Composition Guide

**Version**: 1.9
**Status**: Active (v1.9 naming normalization — the lone core-spec straggler, the peer-id type-ref at §90, renamed snake → kebab to `system/peer-id` (casing only), per `STYLE-NAMING-CONVENTIONS.md` + the V8 identifier-naming-normalization proposal; placement `system/` vs `system/identity/` is a separate identity-namespace review, not changed here; v1.8 baseline)
**Depends**: ENTITY-CORE-PROTOCOL.md (v7.20+), EXTENSION-COMPUTE.md (v3.5+), EXTENSION-HISTORY.md (v1.4+), EXTENSION-SUBSCRIPTION.md (v3.8+), EXTENSION-CLOCK.md (v1.2+), EXTENSION-QUERY.md (v1.4+), EXTENSION-REVISION.md (v2.5+)
**Source**: PROPOSAL-EMIT-PATHWAY-AND-SYSTEM-COMPOSITION.md (E2-E9); PROPOSAL-REVISION-AUTO-VERSION-FIX.md (§6C); PROPOSAL-CASCADE-SEMANTICS-AND-STATE-MANAGEMENT.md (§§10.1-10.7); PROPOSAL-RESTART-EQUIVALENCE.md (RE-1)

---

> **Path notation.** Paths in this document use peer-relative notation (without leading `/{peer_id}/`). All peer-relative paths resolve to the local peer's namespace: `system/tree` means `/{local_peer_id}/system/tree`. Every path in the entity tree is absolute at rest — rooted at a peer identity. See ENTITY-CORE-PROTOCOL.md §1.4 for the path model.

This document describes cross-extension emergent properties — the behaviors that arise when multiple system extensions compose through the emit pathway. Individual extension specs define what each extension does when a tree change event fires. This document defines how those extensions interact: consumer ordering, shared cascade depth tracking, execution context threading, convergence behavior, and well-behaved consumer patterns.

This document is normative for peers implementing multiple system extensions. A peer implementing only the core protocol (no system extensions) has a trivial emit pathway with no consumers and is not affected by anything in this document.

---

## 1. Emit Pathway Model

### 1.1 The Emit Primitive

Emit is the atomic state crossing that introduces time to the entity system. Every mutation executes up to two steps, each with its own no-op suppression:

1. **Store**: Write the entity to the content store (content-addressed, idempotent). If the entity's hash is new to the store, this step fires a **content-store event** carrying `(hash, entity)`. If the hash is already stored, the put is a no-op and no event fires.
2. **Bind**: Update the tree binding at the target path (location index mutation). If the new hash differs from the current binding at `path`, this step fires a **tree-change event** carrying `(event_type, path, new_hash, previous_hash)` plus execution context per §1.4. If the binding already points to the new hash, the bind is a no-op and no event fires.

A `tree_put(path, entity)` executes both steps in sequence — Store then Bind. A direct `content_store.put` (envelope handling, merge material, extension state writes, etc.) executes only the Store step.

The two steps produce independent events. Possible outcomes for a `tree_put`:

| Entity already stored? | Binding already at this hash? | Events fired |
|---|---|---|
| No | No | content-store, then tree-change |
| Yes | No (rebind) | tree-change only |
| Yes | Yes (full no-op) | none |

**Consumer observation.** Content-store events are observable by consumers that need to react to every content addition regardless of tree binding (persistence, query content-side indexes, etc.). Tree-change events are observable by consumers that react to tree mutations (query path annotation, history, subscription, compute, clock, structural summaries). Each event dispatches to its own consumer list through the same emit-pipeline infrastructure (§2). Everything downstream — history recording, subscription notification, compute re-evaluation, index maintenance, persistence — is a consumer of one or both.

### 1.2 Consumer Registration

Extensions register as emit pathway consumers during peer initialization. Each consumer provides a processing function that receives tree change events.

**Ordering is by registration order.** The peer initialization code registers consumers in the order specified by §2.2. No runtime priority dispatch is needed — static ordering at init time is sufficient. The peer builder/wiring code is responsible for registering consumers in the correct order.

**Registration metadata.** Each consumer registers with its processing function and metadata identifying its handler context: handler pattern, handler grant hash, and a default operation name. The emit pathway dispatcher uses this metadata to set per-write context fields (§1.4) before invoking each consumer.

Consumers are invoked synchronously, in registration order, for each tree change event. When a consumer's processing writes to the tree, those writes trigger nested consumer invocations on the same call stack (all registered consumers, in order).

### 1.3 Two-Phase Delivery

Tree change events are delivered in two phases:

**Phase 1 — Synchronous consumers.** All registered synchronous consumers fire inline during the tree write, in priority order. Each consumer runs to completion before the next starts. Consumer writes trigger nested Phase 1 delivery (recursive). When the last synchronous consumer completes, the cascade has settled.

**Phase 2 — Asynchronous notification.** After each tree write's synchronous consumers have completed (including any nested cascading triggered by those consumers), an asynchronous broadcast fires for that write. Phase 2 fires once per tree write, not once per outermost cascade. Nested writes from hook processing fire their own broadcast when their hooks complete, before the parent write's hooks continue. The outermost write's broadcast fires last. Application-level consumers (UI frameworks, FFI bindings, remote notification delivery, telemetry) observe settled state at each depth.

```
tree_put(path, entity, context)
  │
  ├─ content_store.put(entity)           → store
  ├─ location_index.set(path, hash)      → bind
  │
  ├─ if hash == previous_hash: return    → no-op suppression
  │
  ├─ event = TreeChangeEvent { event_type, path, new_hash, previous_hash,
  │                            context: snapshot(context) }  → captures current context values
  │
  ├─ for consumer in sync_consumers:     → Phase 1 (synchronous, ordered)
  │     set per-write fields on live context for this consumer
  │     consumer.on_tree_change(event, live_context)
  │     │
  │     └─ consumer may call tree_put(...)  → nested Phase 1 (new event, new snapshot)
  │     restore per-write fields on live context
  │
  └─ broadcast.send(event)               → Phase 2 (async, after settlement)
```

### 1.4 Execution Context

Every tree change event carries an execution context that consumers can read and that nested writes inherit. The execution context accumulates fields from the handler dispatch chain and the emit pathway.

**Structure definition (informative).** The execution context is a runtime structure. Implementations represent it in whatever form is natural for their language (struct, record, map). The field names, types, and semantics are normative for cross-implementation consistency:

```
execution_context := {
  ; --- Immutable fields (preserved through entire cascade) ---
  chain_id:            string              ; Causal correlation — all writes in one chain share this
  parent_chain_id:     string | null       ; Parent chain's chain_id (for sub-chain fan-out)
  author:              system/peer-id      ; Identity that initiated the request chain
  caller_capability:   system/hash | null  ; Original caller's capability from EXECUTE envelope
  request_id:          string | null       ; Correlation ID from originating EXECUTE
  bounds:              system/bounds | null; TTL, budget, await_stack from originating request

  ; --- Managed by emit pathway ---
  cascade_depth:       uint                ; Current depth in the recursive emit cascade

  ; --- Per-write fields (set by dispatcher for each consumer) ---
  capability:          system/hash | null  ; Authorization that produced THIS specific write
  handler_grant:       system/hash | null  ; Grant of the handler/consumer producing the write
  handler_pattern:     string | null       ; Pattern of the handler/consumer producing the write
  operation:           string | null       ; Operation that produced this write

  ; --- Extension-contributed (see §1.5) ---
  clock:               system/clock/state | null
                       ; Current clock state, advanced by CLOCK extension.
                       ; Type defined in EXTENSION-CLOCK.md §2.6.
                       ; Access subfields: ctx.clock.timestamp, ctx.clock.logical,
                       ; ctx.clock.vector, ctx.clock.hlc (presence depends on mode).
}
```

| Field | Source | Mutability during cascade |
|-------|--------|--------------------------|
| `chain_id` | Bounds (ENTITY-CORE-PROTOCOL.md §5.9) | Immutable — preserved through entire cascade |
| `parent_chain_id` | Bounds (ENTITY-CORE-PROTOCOL.md §3.11) | Immutable — parent chain relationship, absent for root chains |
| `author` | Handler dispatch (ENTITY-CORE-PROTOCOL.md §6.8) | Immutable — preserved from original request |
| `caller_capability` | Handler dispatch (ENTITY-CORE-PROTOCOL.md §6.8) | Immutable — the original caller's capability from the EXECUTE that started this chain |
| `request_id` | Wire protocol (ENTITY-CORE-PROTOCOL.md §3.4) | Immutable — correlation ID from originating EXECUTE |
| `bounds` | Wire protocol (ENTITY-CORE-PROTOCOL.md §5.9) | Immutable — preserved from originating request |
| `cascade_depth` | Emit pathway (§3) | Incremented per nesting depth, decremented on return |
| `capability` | Emit dispatcher | **Per-write** — set by dispatcher to the writing consumer's authorization |
| `handler_grant` | Emit dispatcher | **Per-write** — set by dispatcher to the writing consumer's grant |
| `handler_pattern` | Emit dispatcher | **Per-write** — set by dispatcher to the writing consumer's handler pattern |
| `operation` | Emit dispatcher | **Per-write** — set by dispatcher to the writing consumer's current operation |
| `clock` | CLOCK extension via §1.5 | **Single-owner writable** — only CLOCK writes, only at position 2 (§2.2); other consumers MAY read, MUST NOT write |

**Event context vs live context.** The TreeChangeEvent captures a **snapshot** of the execution context at event creation time. This snapshot records the per-write fields of the original writer (handler_pattern, operation, capability) as they were when the write occurred. During consumer processing, the live context evolves: the dispatcher sets per-write fields to each consumer's values, and the clock consumer advances the clock. Consumers receive BOTH the event (with the original writer's snapshot) and the live context (with the current consumer's per-write fields and the advanced clock). This distinction matters for history: it reads the original writer's provenance from the event snapshot (who wrote this path?) and the current clock from the live context (what logical time is it now?). Each consumer's own tree writes create new events that snapshot the live context at that point — including the consumer's per-write fields and the advanced clock.

**Extension-contributed fields.** The `clock` field is contributed by the CLOCK extension under the mechanism specified in §1.5. §1.5 defines registration, single-owner write discipline, contribution position, read access, absent-extension behavior, cross-peer reset, inheritance, and undefined-behavior conditions. The `clock` field's type is `system/clock/state` (EXTENSION-CLOCK.md §2.6) — a structured value with optional `timestamp`, `logical`, `vector`, and `hlc` subfields per CLOCK's configured mode. Consumers reading `clock` MUST handle the null case (CLOCK not installed) and the absent-subfield case (CLOCK in a mode that doesn't populate the requested subfield). CLOCK is the currently-documented instance; future extensions registering context fields follow §1.5.

**In-place mutation model.** The execution context is shared across consumers at a given depth. When a consumer modifies the context (clock advancement), subsequent consumers at the same depth observe the modification. This is intentional — history at position 4 records the clock value advanced at position 2. The observable behavior MUST be equivalent to in-place mutation of a single shared context. Implementations MAY use copy-on-write or other internal representations as long as the observable outcome matches serial in-place mutation. Implementations that explore subtree parallelism (§4.3) may need to partition or merge the context per independent subtree; the normative requirement is equivalent observable behavior.

**Per-write fields and dispatcher responsibility.** The `capability`, `handler_grant`, `handler_pattern`, and `operation` fields are per-write, not per-cascade. When a compute consumer writes a reactive result, `capability` is the installation grant and `handler_pattern` is `system/compute`. When a history consumer records a transition, `capability` is the history handler's grant and `handler_pattern` is `system/history`. Each consumer produces writes under its own authorization.

The emit pathway dispatcher sets these per-write fields before invoking each consumer, based on the consumer's registration metadata (which handler it belongs to, what its grant is). The consumer's tree writes inherit these values automatically. When the consumer returns, the dispatcher restores the per-write fields for the next consumer. This ensures each consumer's writes are correctly attributed without requiring individual consumers to manage context fields.

Extensions that record execution context (e.g., EXTENSION-HISTORY) record the per-write values (`capability`, `handler_pattern`, `operation`) that were active when each specific write occurred. The `caller_capability` field (immutable, from the original EXECUTE) is available for audit: history can record it alongside the per-write `capability` to distinguish "the tree handler wrote this under the caller's authority" from "the history handler wrote this under its own grant."

**Inheritance rule.** When a synchronous consumer writes to the tree during emit processing, the nested write's execution context inherits the current context with these modifications:

- `cascade_depth` incremented by 1
- `chain_id` preserved (MUST NOT be regenerated mid-cascade)
- `parent_chain_id` preserved from originating bounds
- `author` preserved from the original request chain
- `caller_capability` preserved from the original EXECUTE
- `request_id` preserved from the originating request
- `bounds` preserved from the originating request
- `clock` carries the current (possibly advanced) `system/clock/state` value; see §1.5 for contributed-field inheritance
- `capability`, `handler_grant`, `handler_pattern`, `operation` set by the dispatcher for the writing consumer

**External writes.** Writes originating from the wire (external EXECUTE) initialize the execution context with `cascade_depth: 0` and `chain_id` from the request's bounds. Writes originating from application code (peer-level writes, ENTITY-CORE-PROTOCOL.md §6.8) SHOULD provide an execution context with at minimum `chain_id` (for causal tracing) and `author` (for attribution).

**Relationship to entity types.** The execution context is a runtime structure, not a stored entity type. It does not appear in `system/type/*` and is not content-addressed. However, the field names and semantics defined here are the canonical vocabulary — extensions that persist execution context fields (EXTENSION-HISTORY records `author`, `capability`, `caller_capability`, `handler_pattern`, `operation`, `clock`, `chain_id`, `parent_chain_id` in transition entities) use these names. A future peer implemented entirely in entity compute would need to represent the execution context as entities; the structure defined here provides the schema for that representation.

### 1.5 Extension-Contributed Context Fields

System extensions MAY register cascade-scoped fields on the execution context, subject to the strict rules in this section. This mechanism exists for extensions whose state (a) is needed by multiple downstream consumers within the same cascade, and (b) cannot be read from the tree because deferred persistence makes tree values stale during the cascade. **Use sparingly.** Extensions SHOULD prefer tree-readable state when feasible; the mechanism here is a narrow tool, not a general plugin interface. The CLOCK extension's `clock` field is the currently-documented instance.

#### 1.5.1 Registration

An extension registers a context-field contribution at peer initialization time by providing:

- **Field name.** Namespaced with the extension's name as prefix when the extension is new (e.g., `tracing.span_id`). The `clock` field is grandfathered without a prefix.
- **Field type.** E.g., `system/clock/state | null`. The type SHOULD be referenceable — either a primitive or a declared entity type.
- **Owner.** The registering extension, identified by its handler pattern (or a synthetic pattern for consumer-only extensions per §2.7).

Implementations SHOULD reject registrations that conflict with existing fields (core or contributed).

#### 1.5.2 Single-Owner Ownership

Each contributed field has exactly one owning extension. Only the owning extension MAY write (mutate) its field. Other extensions, handlers, and consumers MAY read the field but MUST NOT write it. Implementations SHOULD enforce this in debug builds via runtime assertion; release-build enforcement is OPTIONAL.

#### 1.5.3 Writes Only at the Owner's Consumer Position

The owning extension MUST write its contributed field only during its own consumer position in the emit pipeline (§2.2). Writes at any other point in the cascade — during downstream consumer processing, during nested writes, during handler execution — are **undefined behavior**.

#### 1.5.4 Additive Only

Contributed fields are additive. Registering a new contributed field MUST NOT modify, shadow, or redefine any existing context field. In particular, contributed fields MUST NOT collide with core context field names: `chain_id`, `parent_chain_id`, `author`, `caller_capability`, `request_id`, `bounds`, `cascade_depth`, `capability`, `handler_grant`, `handler_pattern`, `operation`. Implementations MUST reject such registrations.

#### 1.5.5 Absent-Extension Behavior

When a contributing extension is not installed on a peer, its registered field is not present on the execution context (or is present with a null value — implementation-defined). Consumers that read a contributed field MUST handle the null/absent case. Consumers depending on a contributed field to function MUST declare the contributing extension as a dependency.

#### 1.5.6 Cross-Peer Reset

Contributed fields are cascade-scoped and local to the peer. Cross-peer boundaries (subscription notification, inbox delivery) do not carry contributed fields across the wire. The receiving peer's own cascade constructs its own execution context, including its own contributed-field values derived from its own registered extensions.

#### 1.5.7 Inheritance

The inheritance rule in §1.4 extends to contributed fields: when a synchronous consumer writes to the tree during emit processing, the nested write's execution context inherits the current value of each contributed field at the moment of nesting. The owner's subsequent writes (at its consumer position in the nested cascade) can advance the field further.

#### 1.5.8 Undefined Behavior

The following are undefined behavior. Implementations are not required to detect or handle them, but SHOULD treat observed violations as bugs:

- Writing to a contributed field from code other than its owning extension (§1.5.2).
- Writing to a contributed field outside the owning extension's consumer position (§1.5.3).
- Registering a field name that collides with a core field (§1.5.4) or an already-registered contributed field (§1.5.1).
- Reading a contributed field whose owner's consumer position has not yet fired for the current cascade (the field may be null or carry a stale inherited value).

#### 1.5.9 Guidance: When to Register a Context Field

Extensions SHOULD register context fields only when all three conditions apply:

- The extension produces cascade-scoped state that multiple downstream consumers within the same cascade need to read.
- Reading the state from the tree (at the extension's state paths) is insufficient — e.g., the tree is intentionally deferred-persistence and lags the authoritative in-flight value.
- No cross-peer transfer of the state is needed (contributed fields are local to a peer's cascade).

Extensions that do not meet all three conditions SHOULD expose state through the tree, handler operations, or private-extension APIs instead.

#### 1.5.10 Current Instances

As of SYSTEM-COMPOSITION v1.4, the following context fields are registered under this mechanism:

| Field | Owner | Type | Purpose |
|-------|-------|------|---------|
| `clock` | EXTENSION-CLOCK | `system/clock/state` | Current clock state (timestamp / logical / vector / hlc per mode). Advanced by CLOCK at position 2. Consumed by HISTORY (transition clock); optionally by COMPUTE and SUBSCRIPTION. |

Future extensions registering context fields SHOULD add entries to this table when proposed.

---

## 2. Consumer Classification and Ordering

### 2.1 Consumer Classification

Emit consumers fall into three classes based on their computational characteristics:

| Class | Characteristic | Examples |
|-------|---------------|----------|
| **Transparent** | Does not produce tree writes. Pure reflection or context update. | Entity persistence (§2.7, §6.7), query index maintenance, clock context advance |
| **Bounded reactive** | Produces tree writes, but direct self-recursion is structurally prevented by a self-guard. | Clock persistence, history recording |
| **Unbounded reactive** | Produces tree writes that may trigger arbitrary further cascading. Bounded by cascade depth limit as a safety net. | Compute re-evaluation, subscription delivery |

### 2.2 Consumer Ordering

System extension consumers MUST fire in the following order:

```
0. Entity persistence     — transparent (mirror store+bind to durable backend; absent if memory-only)
1. Query indexes          — transparent (no emission)
2. Clock context          — transparent (advance ctx.clock for subsequent consumers)
3. Clock persistence      — bounded reactive (write clock state, self-guarded)
4. History                — bounded reactive (record transition, self-guarded)
5. Compute                — unbounded reactive (re-evaluate, convergence-checked)
6. Structural summaries   — bounded reactive (e.g., incremental Merkle root, self-guarded)
7. Auto-version           — bounded reactive (record version entry, self-guarded via exclude)
8. Subscription           — unbounded reactive (deliver notifications via inbox)
```

**Ordering principle.** Transparent consumers first. Bounded-recursion consumers next. Unbounded-recursion consumers last. Within each class, order by downstream dependency (consumers that produce state read by later consumers fire first).

**Position 0 is conditional.** A peer with no persistence consumer registered behaves identically to a peer with persistence at position 0 that succeeds trivially — the position is reserved for when persistence is configured. Implementations MUST run a persistence consumer (when registered) at position 0, before any other consumer. Implementations without persistence MUST NOT introduce arbitrary consumers between the protocol-defined positions. See §2.7 for the consumer-only extension classification and §6.7 for the durability/recovery analysis.

**Content-store event consumer ordering** (separate consumer list, dispatched on the Store step per §1.1):

```
0. Persistence           — transparent (durability before visibility; if configured)
1. Query content indexes — transparent (hash, type, reverse hash, field, zone summaries)
```

Both consumers are Phase 1 synchronous. Persistence fires first so that content is durable before any consumer observes it. Query runs after persistence so that an index lookup is never stale relative to what's on disk.

The content-event ordering is independent of the tree-event ordering above. Consumers register for one or both event types. Persistence registers for both (mirrors content on content events; mirrors location-index updates on tree events). Query registers for both with different work at each phase (EXTENSION-QUERY.md §3.1).

**Phase 2 for content events.** After Phase 1 consumers complete, an optional asynchronous broadcast fires for application-level content-event consumers (telemetry, audit logging, external event bridges). Phase 2 is optional — a peer with no Phase 2 content-event consumers skips the broadcast.

**Rationale for each position:**

1. **Query indexes first.** Query indexes are a pure reflection of tree state. They don't emit. They must be current before any consumer that might dispatch to the query handler (e.g., compute calling `system/query` to find entities by type).

2. **Clock context second.** Advances the context clock value that subsequent consumers read. History records clock values; subscription delivers timestamps; compute may read clock state. The context update doesn't emit — it's a pure context mutation.

3. **Clock persistence third.** If the clock extension persists state to the tree (writes to `system/clock/*`), these writes produce new events that cascade recursively. The self-guard prevents clock advance on clock-path writes. Implementations MAY defer persistence (periodic or tick-only) to reduce emission volume (§6.2). The clock extension MAY register as two consumers (one transparent for context advance at position 2, one bounded-reactive for persistence at position 3) or as a single consumer that performs both steps. The ordering requirement is that context advance completes before any subsequent consumer reads the clock value.

4. **History fourth.** Records the transition. Writes a history entity, which produces a new event, but the self-guard prevents history recording its own writes. History doesn't read tree state beyond the event — it records what the event carries.

5. **Compute fifth.** Re-evaluates derived state. Compute's result writes cascade through the full consumer list (including clock, history, and further compute). Running compute before structural summaries and subscription ensures derived state has settled before summaries and notifications reflect it.

6. **Structural summaries sixth.** Consumers that maintain derived structural representations of tree state — such as incremental Merkle trie roots. These fire after compute so the summary reflects settled derived state, not intermediate cascade state. If the summary writes a root hash to a tree path, that write cascades through all consumers (including auto-version at position 7 and subscription at position 8), making the root subscribable. Self-guarded by the summary's output paths.

7. **Auto-version seventh.** Records a version entry for writes under a tracked prefix (EXTENSION-REVISION). Auto-version reads the tracked root maintained by structural summaries at position 6 — the summary MUST have settled before auto-version reads it, so auto-version fires after position 6. Auto-version creates a version entry in the content store and advances `system/revision/head/{prefix}`; the head advance and any DAG entity writes must be in place before subscription at position 8 observes the change, so subscribers see post-auto-version settled state. Self-guarded via the extension's `exclude` configuration, which MUST cover the revision extension's own metadata paths (see EXTENSION-REVISION).

8. **Subscription eighth.** Delivers notifications to remote peers. By firing after compute, structural summaries, and auto-version at each depth level, the notification for a given path fires only after all reactive re-evaluation, summary maintenance, and version DAG updates triggered by that path have settled. Note: nested cascade writes fire their own subscription notifications at their depth — so a compute result's notification fires before the triggering write's notification. Notification ordering across depths is inverted (effect before cause), but all tree state is current when any notification fires.

**Why compute before subscription.** If subscription fires before compute, a remote peer could receive a notification about `app/data/x` changing, read the compute result at `app/results/a`, and get the old result because compute hasn't re-evaluated yet. With compute-before-subscription ordering, this race is eliminated — when subscription fires for `app/data/x` at the outermost depth, all derived results from that write have already been computed and written. Nested writes (e.g., compute result at `app/results/a`) fire their own subscription notifications at their depth during the cascade, before the outermost notification fires. This produces inverted causal order in notifications (derived result notified before original cause) but no stale reads — all tree mutations precede all notifications at every depth.

**Position 7 (Auto-version) and Position 8 (Subscription) ordering.** Auto-version MUST fire before subscription. Auto-version reads the tracked root (maintained at position 6), creates a version entry in the content store, and advances `system/revision/head/{prefix}`. Subscription at position 8 observes the settled post-auto-version state: subscribers on head see the newly-advanced pointer; subscribers on the original path see the write with the corresponding DAG entry already in place. Reversing the order produces observable inconsistency — subscribers seeing a change without a version entry, or a head pointer that doesn't reflect the write.

**Backward compatibility.** Peers that do not install the revision extension do not register a position-7 consumer. For those peers, subscription runs at what is effectively position 7 (the next registered consumer after structural summaries), with no behavioral change from earlier versions of this spec. Peers that DO install revision register auto-version at position 7 and subscription at position 8 per the ordering above.

### 2.3 Extension-Authored Consumers

Third-party extensions and application-authored consumers register at positions consistent with their classification:

| Consumer type | Position | Rationale |
|--------------|----------|-----------|
| State maintenance (clock-like) | Before history | Other consumers may read maintained state |
| Audit/recording (history-like) | After state maintenance, before compute | Record the triggering write, not cascading effects |
| Reactive evaluation (compute-like) | After audit, before summaries | Cascade must settle before summaries reflect it |
| Structural summary (Merkle-like) | After reactive evaluation, before notification | Summarize settled state; subscribable root |
| Notification (subscription-like) | After summaries | Notify about settled state only |
| Application callbacks | Phase 2 (async broadcast) | No causal ordering needed |

### 2.4 Optional Consumers

Not every peer runs every consumer. A peer without the compute extension has no compute consumer. A peer without subscriptions has no subscription consumer. The ordering applies to whichever consumers are present — absent consumers are simply not in the list.

A peer implementing only the core protocol (no system extensions) has zero synchronous consumers. The emit pathway fires, finds no consumers, and returns immediately.

**Default tree scope.** The consumer ordering in §2.2 applies to the default tree's emit chain. Non-default trees (EXTENSION-TREE.md §7) have their own location indexes but do not participate in the default tree's emit chain unless the implementation explicitly wires consumers to them. See EXTENSION-TREE.md §7.5 for multi-tree emit considerations.

### 2.5 Phase 2 Consumers

Some extension engines belong in Phase 2 (async broadcast) rather than Phase 1 (sync hooks). The distinguishing criterion: does the consumer need to participate in the causal cascade, or does it benefit from observing settled state?

**Revision — two consumer categories.** The revision extension's auto-version consumer is Phase 1 (position 7) — see §2.2. It produces a version entry per tree write to a tracked prefix, participating in the synchronous cascade so that subscribers observing version-DAG paths (`system/revision/head/*`) see settled post-version state. Application-level revision observers (UI, SDK, sync orchestrators) that want settled state after the full cascade completes register as Phase 2 consumers, using the post-return broadcast. Both patterns are valid; they serve different consumer needs.

**Application UI/SDK** consumers are Phase 2. They observe settled state for rendering or caching.

The general rule: if a consumer's output should reflect the full cascade result (not intermediate steps), it belongs in Phase 2.

### 2.6 Extensions as Both Handler and Consumer

Some extensions expose both a handler (for explicit EXECUTE dispatch) and a synchronous emit consumer (for reactive processing). The query extension is the primary example: the `system/query` handler processes explicit query EXECUTEs, while a separate sync hook maintains secondary indexes on every tree write. These are distinct code paths within the same extension. The sync hook does NOT dispatch to the handler — it updates implementation-level index structures directly.

### 2.7 Consumer-Only Extensions

Some extensions register only as emit consumers, with no handler for explicit EXECUTE dispatch. Persistence is the canonical example: the persistence consumer mirrors tree writes to a durable backend (SQLite, IndexedDB, filesystem, etc.) but does not respond to direct EXECUTEs. There is no `system/persistence` handler.

A consumer-only extension provides only the consumer registration and processing function. It does not need a handler manifest, capability grants for incoming EXECUTEs, or operation specifications. Its registration metadata for the emit pathway dispatcher (§1.2) uses a synthetic handler pattern (e.g., `system/persistence/{backend_name}`) for context attribution, but no entity exists at that path.

**Examples of consumer-only extensions:**

| Extension | Event type | Position | Purpose |
|-----------|------------|----------|---------|
| Entity persistence (content) | Content-store | 0 | Mirror entity to durable backend |
| Query content indexes | Content-store | 1 | Maintain hash/type/reverse/field/zone indexes |
| Entity persistence (location) | Tree-change | 0 | Mirror location-index update to durable backend |
| Telemetry / observability | Either | Phase 2 | Emit metrics or traces from settled state |
| External event bridge | Either | Phase 2 | Mirror events to external pub/sub systems |

Consumer-only extensions may register on either content-store events, tree-change events, or both. Persistence is the canonical example registering on both: content-store event mirrors entity content; tree-change event mirrors the location-index update.

**Failure semantics.** The cascade model is post-commit: the authoritative state update (location-index binding for tree events; content-store entry for content events) commits before any consumer runs. There is no transactional rollback primitive in the tree layer. A write that lands cannot be un-landed except by another write that overwrites it.

**Halt the cascade.** A synchronous (Phase 1) consumer that returns a non-200 status causes subsequent synchronous consumers for this event to be skipped. The cascade for this event ends. The originating tree.put's binding update is NOT reversed — it remains in the location index and is visible to all future reads.

**Error return to tree.put.** The error from the halting consumer propagates to tree.put's return via status 207 (Multi-Status) with a `system/tree/partial-result` envelope (see §2.7A). Status 207 distinguishes "binding landed, cascade incomplete" from "write rejected" (4xx/5xx). Callers treating status as binary accept/reject SHOULD accept both 200 and 207; callers needing strict cascade completion distinguish them.

**Phase 1 consumers that return non-200 halt the cascade.** Consumer-internal errors that should not halt MUST NOT be returned as non-200 status; handle them inside the consumer. Non-200 is the intentional-halt signal, not a general error channel.

**Phase 2 consumers.** Asynchronous consumers (subscription at position 8, telemetry, audit, external bridges) run post-return. They cannot propagate errors to the original tree.put caller — the call stack is gone. They follow log-and-continue semantics. Errors in Phase 2 consumers are observable only through the consumer's own error pathway: local Phase 2 consumers that need structured error surfacing SHOULD use `on_error` delivery-specs (EXTENSION-CONTINUATION.md §3.3); lightweight telemetry consumers SHOULD log and continue.

**Peer-level audit.** Cascade halts are an implementation-peer-level concern, not only the calling handler's problem. Peers MUST surface cascade halts somewhere the operator can observe — the specific mechanism is implementation-defined (telemetry, metrics, file-logging, or a future EXTENSION-HISTORY event variant).

**Persistence at position 0** on either event type MUST be Phase 1 with abort-on-failure: a write that didn't persist must not be visible to downstream consumers.

### 2.7A Cascade-Halt Response Envelope

When a Phase 1 consumer halts the cascade, the originating tree.put (or content_store.put) returns status 207 with a `system/tree/partial-result` as the result entity. This type is defined here (not in EXTENSION-TREE) because it applies to both tree.put and content_store.put emissions.

```
system/tree/partial-result := {
  binding_committed:    primitive/bool                ; the write landed
  consumers_completed:  [primitive/string]            ; names, in execution order
  consumers_halted:     [{ name: primitive/string,
                           error: system/protocol/error }]
                                                      ; consumer(s) that returned non-200
  consumers_skipped:    [primitive/string]            ; names, didn't run due to halt
  nested_cascade_ids:   [system/hash]                 ; audit refs for cascades triggered
                                                      ; by the halted consumer before returning
  cascade_depth:        primitive/uint                ; operator diagnostics
}
```

**Consumer names, not positions.** The response identifies consumers by stable name (e.g., `"revision/auto-version"`, `"history/transition-recorder"`, `"compute/reevaluator"`, `"subscription/notifier"`), not by position number. Position numbers are implementation bookkeeping — different peers install different consumer sets, so position numbers aren't portable across deployments. Consumer names MUST be stable identifiers. Implementations SHOULD document the names their peer exposes. Names SHOULD be prefixed with the owning extension's handler pattern to avoid collisions.

**Status 207 (Multi-Status).** Following the HTTP convention, 207 signals a genuinely partial outcome — the data-plane operation succeeded (binding landed) but the reactive cascade didn't complete. Callers that only need binary success/failure SHOULD treat both 200 and 207 as success. Callers that need to know which consumers ran read the `system/tree/partial-result` envelope.

**No protocol footprint.** Consumer-only extensions are pure implementation. They don't appear in capability grants, type definitions, or wire messages. Two peers can have entirely different consumer-only extensions configured and still interoperate normally — the consumers operate on local state, below the protocol layer.

### 2.8 Consumer Writes Are Ordinary

Consumers MAY issue tree.put or content_store.put during their processing. Such writes are ordinary primitives inheriting the standard cascade semantics — depth counting, emit cascade, 207-on-halt. The spec does not define a forward-correction contract: reentrancy detection, idempotence, retry discipline, and correction observability are handler concerns. The cascade-depth refusal (§3.2, system refusal threshold) is the system-level backstop against pathological recursion; first-line protection is the consumer's own responsibility and uses whatever mechanism fits its domain (path-prefix filters, context tags, origin checks, or simply not issuing nested writes from within cascade processing).

### 2.9 State Management Patterns

Extensions that persist state callers produce SHOULD choose between two patterns based on whether transient visibility of invalid state causes observable harm. This is guidance (SHOULD-level), not a mandate.

**Pattern A: named handler operation.** Caller invokes `extension/config` (or `extension/set-X`) with the entity as params. Handler validates, performs coordination (writes to multiple paths, updates derived state), then either succeeds or fails. No transient visibility of invalid state. Capability is checked per-operation at dispatch. Use when: transient visibility of invalid state causes downstream harm, validation errors have multiple shapes callers need to distinguish, the write is really a multi-path coordinated update, or the caller needs rich return data beyond accepted/rejected.

**Pattern B: tree.put + sync emit consumer.** Caller issues tree.put directly. An extension MAY register a Phase 1 consumer that observes the write post-commit and halts the cascade (§2.7) on whatever condition it chooses. The invalid state remains in the tree until a subsequent write overwrites it. Recovery is handler/operator domain — the spec does not prescribe a correction discipline. Use when: transient visibility is harmless (readers self-correct on next read, or invalid state is idempotent), the write is single-path, capability-per-path provides adequate access control, and simplicity matters.

**Decision criterion.** Does the transient visibility of invalid state cause observable harm? Harm means downstream consumers acting on invalid state commit that action (e.g., auto-version creating a version entry based on invalid config), readers caching a briefly-invalid value, or subscribers notifying remote peers before correction. For most configuration entities, transient visibility IS harm because configs gate other behavior — named operations are the safer default for config writes. For entities that are self-describing data (logs, measurements, events), transient visibility is usually harmless and tree.put + consumer is fine. If an extension needs validation or coordination before a write lands, the write belongs behind a named handler operation — tree.put is a data-plane primitive, not a validation boundary (see EXTENSION-TREE.md §2 for tree.put's contract).

### 2.10 Consumer Ordering Constraints

Extensions SHOULD declare ordering constraints on their emit pathway consumers. A constraint names another consumer that this consumer MUST run after.

**Declaration.** Ordering constraints are declared in the extension's handler manifest (the `system/handler` entity at the extension's pattern path), in an optional `composition` field:

```
system/handler/composition := {
  fields: {
    emit_consumer:  {type_ref: "primitive/bool", optional: true}
        ; true if this extension registers an emit pathway consumer
    run_after:      {type_ref: "list/string", optional: true}
        ; List of handler patterns this consumer must run after.
        ; e.g., ["system/tree/root-tracker"] means "I read root-tracker's output"
  }
}
```

Added as an optional `composition` field on `system/handler` (type_ref: `system/handler/composition`).

**Peer builder guarantee.** The peer builder MUST respect declared `run_after` constraints when ordering emit pathway consumers. If the declared constraints form a cycle, the peer builder MUST reject the configuration with an error at build time — cycles in consumer ordering are a configuration error, not a runtime condition. When no constraint applies between two consumers, registration order is the tiebreaker.

**Current ordering constraints.** The canonical ordering from §2.2, with the `run_after` constraints that make it load-bearing:

| Position | Consumer | Run-after constraint | Reason |
|----------|----------|---------------------|--------|
| 0 | persistence | (none) | Must observe every event before any consumer can fail |
| 1 | query/index-maintainer | persistence | Index updates reference stored entities |
| 2 | clock/context | (none) | Independent — pure context mutation |
| 3 | clock/persistence | clock/context | Must follow context advance |
| 4 | history/recorder | persistence | History entries reference stored entities |
| 5 | compute | (none) | Independent — reactive evaluation |
| 6 | structural summaries | compute | Must reflect settled derived state |
| 7 | revision/auto-version | structural summaries | Must read settled root hash |
| 8 | subscription/matcher | (none) | Independent — delivers asynchronously |

Consumers not listed in `run_after` constraints are position-independent relative to each other. An implementation MAY reorder them as long as declared constraints are satisfied.

Implementations that do not support user-installable extensions MAY hardcode the §2.2 ordering. The `composition` type exists for forward compatibility with plugin systems and dynamic extension loading.

---

## 3. Cascade Depth

### 3.1 The Shared Counter

Cascade depth is a **single counter** shared across all tree-event consumers. It is NOT per-extension. The counter tracks how many levels of nested tree-event processing the current write sits within.

With the synchronous emit model (§1.3), cascade depth is the nesting depth of the call stack. Each nested `tree_put` during consumer processing increments the counter; returning from the consumer processing decrements it.

**Scope.** Cascade depth applies to tree-event cascades. The standard content-event consumers (persistence, query content indexes) don't produce writes and therefore don't cascade. Implementations that register cascade-producing consumers on content events enter unexplored territory — see §6.6 for guidance.

```
User writes app/data/x                                    cascade_depth = 0
  ├─ [sync] clock advances                                cascade_depth = 0
  ├─ [sync] history records transition                    cascade_depth = 0
  ├─ [sync] compute re-evaluates A → writes app/results/a
  │    cascade_depth = 1 for the nested write
  │    ├─ [sync] clock advances                           cascade_depth = 1
  │    ├─ [sync] history records transition               cascade_depth = 1
  │    ├─ [sync] compute re-evaluates B → writes app/results/b
  │    │    cascade_depth = 2 for the nested write
  │    │    ├─ ... (cascade continues)
  │    │    └─ convergence check: same hash → no write → cascade stops
  │    ├─ [sync] structural summaries (e.g., Merkle root) cascade_depth = 1
  │    └─ [sync] subscription fires notifications         cascade_depth = 1
  ├─ [sync] structural summaries (e.g., Merkle root)      cascade_depth = 0
  ├─ [sync] subscription fires notifications              cascade_depth = 0
  └─ [async] broadcast (settled state)
```

### 3.2 Threshold Table

The cascade depth counter has three normative thresholds:

| Depth | Consumer | Action |
|-------|----------|--------|
| 8 | Subscription | Suppress same-peer notification delivery |
| 16 | Compute | Freeze subgraph with `cascade_limit` error |
| 32 | System | Refuse the tree write |

**Threshold 8 — subscription suppression.** When cascade depth reaches 8, the subscription consumer stops delivering notifications for the remainder of this cascade branch. This prevents notification storms from deep cascades. Remote peers will eventually learn of the settled state through subsequent notifications or sync.

**Threshold 16 — compute freeze.** When cascade depth reaches 16, the compute consumer freezes the triggering subgraph with a `cascade_limit` error at its result path (EXTENSION-COMPUTE.md §7.2). The subgraph is structurally broken — retry cannot help. Recovery is via re-installation (EXTENSION-COMPUTE.md §3.3).

**Threshold 32 — system refusal.** When cascade depth reaches 32, the tree write itself is refused. This is the absolute safety boundary — no consumer, no extension, and no handler can produce writes beyond this depth. The refused write returns an error to the consumer that attempted it.

Implementations MAY configure different threshold values. The values above are RECOMMENDED defaults. If customized, the invariant MUST hold: subscription threshold < compute threshold < system threshold.

### 3.3 Initialization

| Write source | Initial cascade_depth |
|-------------|----------------------|
| External EXECUTE from the wire | 0 |
| Application-level peer write | 0 |
| Synchronous consumer's tree write during emit processing | parent cascade_depth + 1 |
| Cross-peer notification arrival (chain_id tracked) | Tracked value from §3.4 |

### 3.4 Cross-Peer Cascade Tracking

Synchronous hooks provide cascade depth tracking within a single peer. Across peer boundaries (subscription notification → remote inbox delivery → remote tree write → remote compute re-evaluation), the synchronous call stack breaks. Cross-peer cascade depth is tracked via two mechanisms: `cascade_depth` on bounds (primary) and a peer-local `chain_id → cascade_depth` tracking map (supplementary).

**cascade_depth on bounds.** The `cascade_depth` field on `system/bounds` (ENTITY-CORE-PROTOCOL.md §3.11) carries the current cascade depth across the wire. When subscription delivers a notification to a remote peer, the notification bounds inherit `cascade_depth` from the emission context (EXTENSION-SUBSCRIPTION.md §4.5). The receiving peer reads `cascade_depth` from the incoming EXECUTE's bounds and initializes its local cascade from that value. This is the primary mechanism — it works on the first cross-peer hop without any prior state.

**chain_id propagation.** The `chain_id` field propagates across peer boundaries via subscription notifications and inbox deliveries. All writes in one causal chain share a `chain_id`. Implementations MUST NOT regenerate `chain_id` mid-cascade.

**Peer-local tracking map.** Each peer SHOULD additionally maintain a `chain_id → cascade_depth` map for supplementary tracking. This map records the highest cascade depth seen for each chain_id. When a notification arrives, the receiving peer uses `max(bounds.cascade_depth, tracked_depth_for_chain_id)` as the initial cascade depth. This handles cases where the bounds cascade_depth is stale (e.g., a notification that was delayed while a faster path already delivered a deeper cascade for the same chain_id).

**Eviction.** The tracking map is bounded by TTL. Peers SHOULD evict entries when the associated bounds TTL would have expired. Chain_ids are UUIDs — without eviction the map grows without bound. Default TTL: same as system bounds TTL.

**Cross-peer guarantees.** Cross-peer cascade tracking provides cascade depth continuity across peer boundaries. The combination of bounds-carried `cascade_depth` (immediate, on first hop) and the tracking map (supplementary, for delayed/reordered notifications) ensures thresholds apply across the full cross-peer chain. TTL on bounds provides the hard limit for cross-peer cascade termination.

---

## 4. Recursive Emit Model

### 4.1 Same-Peer Recursion

The emit pathway is recursive — a tree write during consumer processing fires a nested emit on the same call stack. The full consumer list fires for each nested write.

```
tree_put("app/data/x", entity_x, ctx)          — depth 0
  ├─ [query] update type index for entity_x
  ├─ [clock] advance ctx.clock
  ├─ [history] record transition for app/data/x
  │    └─ tree_put("system/history/...", transition, ctx{depth:1})   — depth 1
  │         ├─ [query] update type index for transition
  │         ├─ [clock] advance ctx.clock
  │         ├─ [history] SKIP (self-guard: system/history/* prefix)
  │         ├─ [compute] no dependencies on this path → skip
  │         ├─ [subscription] any subscribers to system/history/* → notify
  │         └─ [broadcast]
  ├─ [compute] dependency on app/data/x → re-evaluate → writes app/results/a
  │    └─ tree_put("app/results/a", result, ctx{depth:1})           — depth 1
  │         ├─ [query] update type index
  │         ├─ [clock] advance ctx.clock
  │         ├─ [history] record transition for app/results/a
  │         ├─ [compute] dependency on app/results/a → re-evaluate B
  │         │    └─ convergence check: same hash → no write → stops
  │         ├─ [subscription] notify
  │         └─ [broadcast]
  ├─ [subscription] notify subscribers of app/data/x
  └─ [broadcast]                                                     — settled
```

**Settled state.** When the outermost `tree_put` returns, all synchronous consumers — including all nested cascading writes — have completed. The caller can immediately read the settled state. The Phase 2 broadcast fires with this settled state.

**Notification ordering across depths.** In the trace above, subscription fires for `app/results/a` at depth 1 (during compute's processing) before subscription fires for `app/data/x` at depth 0. Remote peers receive derived-result notifications before the original-cause notification. This inverted causal order is a structural consequence of the recursive model — each depth's consumers run to completion before the parent depth continues. It is safe because all tree mutations (store + bind) occur before their emit events, so any read triggered by any notification observes current state. No stale reads occur at any depth.

### 4.2 Cross-Peer Boundary

Cross-peer subscription notifications escape the synchronous recursion. Notification delivery goes through the network — the remote peer receives the notification asynchronously. Cross-peer cascades are bounded by TTL (ENTITY-CORE-PROTOCOL.md §5.9), not by the local cascade depth counter.

### 4.3 Subtree Parallelism

Independent subtrees with no shared dependencies MAY be processed concurrently. This is an implementation-defined optimization. The normative requirement is that the observable outcome is equivalent to serial processing in the defined consumer order. Implementations that parallelize MUST ensure:

- Consumer ordering is preserved within each subtree
- Cascade depth is tracked correctly across parallel branches
- Settled-state observation remains valid (all branches complete before return)

---

## 5. Convergence and Termination

### 5.1 Convergence Check

The primary termination mechanism for reactive cascades is the **convergence check**: before writing a reactive result to the tree, compare the new result's content hash against the hash already stored at the target path. If they are equal, the result has converged — suppress the write. No event fires, no further cascading occurs.

This check is normative for the compute extension (EXTENSION-COMPUTE.md §7.2) and RECOMMENDED for any extension that writes reactive results. It catches:

- Idempotent re-evaluations (same input → same output)
- Cycles where the fixed point has been reached
- Spurious triggers from over-approximated dependencies

### 5.2 Convergence Classes

Reactive configurations produce different convergence behaviors:

| Class | Description | Termination |
|-------|-------------|-------------|
| 1 — Structural | Acyclic dependency graph, all pure operations | Guaranteed in O(graph depth) |
| 2 — Configuration | Acyclic graph, handler dispatches involved | Guaranteed if handlers are deterministic |
| 3 — Bounded | Cyclic graph, operations on finite lattice | May converge (fixed point), bounded by cascade depth |
| 4 — Divergent | Cyclic graph, operations that grow state | Does not converge; bounded only by cascade depth limit |

Class 1 and 2 are the normal cases. Class 3 occurs when compute expressions form cycles (A depends on B, B depends on A) but operate over bounded domains. Class 4 is pathological and will hit the cascade depth limit.

### 5.3 Cascade Limit as Safety Net

The cascade depth threshold table (§3.2) is the safety net when convergence check fails. The behavior at each threshold:

- **Subscription suppression (depth 8):** Graceful degradation — local processing continues, remote notifications deferred.
- **Compute freeze (depth 16):** The triggering subgraph is frozen with a `cascade_limit` error. Other subgraphs continue operating. Recovery is via re-installation.
- **System refusal (depth 32):** Hard stop. The write is refused. This prevents stack overflow from unbounded recursion.

Budget exhaustion during compute re-evaluation is NOT a structural failure — it writes a `compute/error` to the result path but does not freeze the subgraph. The subgraph remains active for future triggers (the next trigger may involve less computation). See EXTENSION-COMPUTE.md §7.3 for the distinction between structural and transient errors.

---

## 6. Well-Behaved Consumer Patterns

### 6.1 Self-Guard Against Direct Recursion

An extension that writes to the tree during emit consumption MUST have a mechanism to prevent direct self-recursion. Without a self-guard, the first emit triggers a write to the extension's namespace, which triggers the extension again, until the cascade depth limit is hit.

**Engine output paths vs configuration paths.** Each extension namespace contains both engine-written paths (recursion risk) and handler-written configuration paths (no recursion risk). Self-guards SHOULD target the specific paths the engine writes to, not the entire extension namespace. Configuration paths (`system/{extension}/config/*`) are written by handlers via explicit EXECUTE, not by the emit consumer, and do not create recursion risk. Implementations SHOULD allow configuration changes to be recorded by history and to advance the clock.

| Extension | Engine output paths (MUST guard) | Configuration paths (SHOULD track) |
|-----------|----------------------------------|-------------------------------------|
| History | `system/history/head*` (transition records) | `system/history/config/*` (recording rules) |
| Clock | `system/clock/logical`, `system/clock/vector`, `system/clock/hlc` (clock state) | `system/clock/config` (clock mode, intervals) |
| Compute | Result paths (per-subgraph) | `system/compute/processes/*` (subgraph metadata) |

Existing guard mechanisms:

| Extension | Guard mechanism | How it works |
|-----------|----------------|--------------|
| History | Engine path prefix skip | Skip recording when path starts with `system/history/head` |
| Clock | Engine path prefix skip | Skip clock advance when path starts with clock state paths (`system/clock/logical`, `system/clock/vector`, `system/clock/hlc`) |
| Compute | Convergence check | Skip write when result hash equals stored hash |

Both clock and history use narrow guards targeting engine output paths. Configuration changes (`system/clock/config`, `system/history/config/*`) advance the clock and are recorded by history, respectively — they are tree mutations like any other.

Extensions MAY rely on the cascade depth counter as a backstop, but MUST NOT rely on it as the primary termination mechanism. The counter is a safety net, not flow control.

### 6.2 Emission Frequency Discipline

Extensions vary in emission frequency:

| Extension | Emission frequency | Notes |
|-----------|-------------------|-------|
| Query indexes | Never (impl-level) | No tree writes |
| Clock (context) | Never | Pure context mutation |
| Clock (persistence) | Potentially every emit | Implementation SHOULD allow deferral |
| History | Every emit (except self) | One entry per tree write |
| Subscription | Only on matching patterns | Bounded by subscription count |
| Compute | Only on registered dependencies | Bounded by dependency count |

Clock persistence has the highest potential impact on emission volume. The clock extension SHOULD support:
- **Every-emit persistence** (strictest, highest emission overhead)
- **Periodic persistence** (slightly stale tree clock, lower overhead)
- **Tick-only persistence** (clock value for deliberate tick events, minimal overhead)

### 6.3 High-Frequency Path Hazard

`system/clock/*` and `system/history/*` paths update on nearly every emit. Subscriptions or compute expressions that depend on these paths produce high-frequency triggering:

- A subscription on `system/history/*` fires on every tree write
- A compute expression reading `system/clock/state` re-evaluates on every clock advance

Users subscribing to or computing against clock/history paths SHOULD scope their patterns narrowly (e.g., `system/clock/tick/*` for deliberate timer events, not `system/clock/*`). General subscriptions or compute expressions over these paths produce high-frequency triggering and may approach cascade depth limits on active systems.

### 6.4 Scoped Consumption

Extensions that consume emits SHOULD provide a way for users to scope consumption:

- **Subscription**: Subscribers declare patterns — good default
- **Compute**: Dependencies are specific tree paths from `compute/lookup/tree` — good default
- **Query**: Index updates are per-affected-index — good default
- **History**: Records every tree write (except own paths) — intentionally comprehensive
- **Clock**: Advances on every write — inexpensive for context, expensive if persisting per-emit

Extensions that consume unconditionally (history, clock) SHOULD be efficient per-emit because they run on every write.

### 6.5 Idempotence Under Retry

Emit consumers SHOULD be idempotent. If the same event is delivered twice (implementation retry, failover), the consumer's effect should be the same as delivering it once.

- Query index updates: idempotent by construction (setting a value twice produces same state)
- History recording: idempotent IF the history entry hash depends only on the transition
- Subscription notification: NOT naturally idempotent (sending twice delivers twice). Subscribers handle duplicates via inbox deduplication.
- Compute re-evaluation: idempotent for pure expressions. Impure expressions may not be.

### 6.6 Cascade-Producing Consumers: Prefer Tree Events

Consumers that respond to events by producing further writes (compute re-evaluation, history recording, subscription delivery, structural summary updates) SHOULD register on tree-change events. The tree-event pipeline has been designed and tested with cascade semantics: cascade depth thresholds (§3.2), convergence checks (§5.1), execution context threading (§1.4), and self-guard patterns (§6.1).

Content-event consumers are designed for transparent reflection (persistence, indexing, logging). The standard content-event consumers (persistence, query indexes) do not produce further writes. A content-event consumer that does produce writes (`content_store.put` or `tree_put` during its processing) dispatches recursively through the same emit pipeline, but cascade-depth interaction, execution-context threading across content-event → tree-event boundaries, and convergence behavior have not been validated for this case. Implementations that cascade from content events may encounter unforeseen interactions.

This is guidance, not prohibition. The emit pipeline's recursive composition does not forbid cascading from content events. Implementations that need cascade-producing behavior should prefer tree events where the behavior is specified and tested.

### 6.7 Persistence and Implementation Freedom

Persistence is treated as a transparent consumer-only extension (§2.7). Persistence registers on both content-store events and tree-change events:

- **Content-store event consumer** (position 0): mirrors entity content to the durable backend. Catches all entity additions — tree-bound and content-only (envelope ingestion, merge material, subscription verification chains, extension state writes).
- **Tree-change event consumer** (position 0): mirrors the location-index update to the durable backend.

Together these two consumers capture canonical peer state — content + tree. A peer with no persistence configured simply doesn't register either consumer; memory-only behavior is unchanged.

#### 6.7.1 Crash safety from existing properties

A baseline crash-safety property emerges from the combination of:

1. Synchronous persistence consumers (on both content-store and tree-change events) — caller sees OK only after persistence commits.
2. Content-addressed entity writes (identical retry produces identical hash; idempotent).
3. Startup hydration (memory rebuilds from persistence on peer init).
4. Backend transactional atomicity (SQLite, IndexedDB, and most embedded KVs provide ACID writes for a single key).

Together these are sufficient for crash safety to last-committed state in the patterns explored so far. After a crash, memory rebuilds from persistence; either the backend committed the failed write (caller's retry is a no-op by hash) or it didn't (caller's retry writes fresh). State converges either way.

Implementations MAY add a write-ahead log if their workload calls for it. Traditional accumulating WALs typically address scenarios such as: high-throughput batched persistence (fsync the WAL append, defer the data-file flush), accept-before-durable semantics (returning OK before persistence completes), or multi-row atomicity beyond a single backend transaction. The entity protocol does not require any of these, but it does not preclude them either — a WAL slots in as a pre-emit layer wrapping `tree_put` without changing the consumer model.

A separate concern sometimes associated with WALs is **point-in-time recovery to arbitrary historical timestamps** (PITR-style replay). EXTENSION-REVISION provides historical versioning via content-addressed snapshots, but only for paths within configured revision-tracked scopes — same scoping applies to EXTENSION-HISTORY and EXTENSION-TREE snapshots. These are not universal substitutes for WAL-based PITR across the whole tree; untracked paths have no historical recovery beyond what's currently in the content store and persistent backend. Implementations needing universal PITR would build it themselves; the entity-system primitives do not provide it.

#### 6.7.2 Concurrent-reader safety via path-scoped locking

If the memory store is accessed concurrently with emit processing, a reader could observe state between memory-write and persistence-commit. If the system then crashes before persistence completes, that reader acted on state that's "rolled back."

The fix is path-scoped locking: hold a lock on the affected path for the duration of the emit (memory write through final consumer). Reads to other paths are unaffected; reads to the in-flight path block briefly. This is row-level locking from the database tradition, not a global lock.

Implementation shapes (informative): per-path lock pool with sharding; concurrent hash map with per-entry synchronization (e.g., `dashmap`); `RwLock` per path for high-contention scenarios. Content store needs less synchronization than location index — content store writes are hash-keyed and idempotent (same hash = same content); only location index requires per-path serialization.

#### 6.7.3 Scoping policy for external-backed entities

Some entities are views over external state — `local/files/*` entities reflect filesystem files, `system/peer/status` reflects connection state, `local/process` reflects OS process state. The canonical representation lives outside the entity system; the entity is synthesized by a handler.

Persistence consumers SHOULD provide a scoping mechanism so external-backed entities are not redundantly persisted:

- **URI-prefix filter.** Persistence skips writes under configured prefixes (e.g., `local/*`).
- **Handler-declared flag.** Handlers carry a "persist: false" indicator in their manifest; the persistence consumer checks the entity's source handler.
- **Type-declared flag.** Types in `system/type/*` carry an "ephemeral: true" flag; entities of ephemeral types are memory-only.

Any of these mechanisms suffices. The choice is implementation-defined. The principle is: the persistence consumer is a filter, and the filter policy can be expressed in type/handler metadata.

#### 6.7.4 Restart equivalence

A peer with durable storage that stops and restarts MUST produce externally observable behavior equivalent to a continuously-running peer holding the same durable state. The tree (content store + location index) is the authoritative state.

"Equivalent observable behavior" applies to the peer's externally visible interface: tree reads, query results, subscription delivery, capability checks, attestation lookups, role-derived authorization, compute re-evaluation, and remote-peer state observation. Internal state representations are not constrained — implementations may persist derived indexes alongside the tree, rebuild them at start, or refill lazily. Storage backend, persistence selection, rebuild mechanism, and startup sequencing are all implementation-defined (see §6.7.5).

Memory-only peers (peers with no durable storage) cannot satisfy this invariant: when the process exits, the tree state is gone; when a new process starts, it is a fresh peer regardless of identity. The invariant therefore applies to peers that retain durable state across restart. For memory-only peers it is vacuous. This is a deployment choice, not a conformance failure — the spec does not require any peer to use durable storage.

The mechanism that satisfies this invariant is the combination of §6.7.4.1 below (store-level hydration) plus the per-extension restart-consistency requirements already in place: EXTENSION-ATTESTATION.md §5.7 requires index lookups consistent with current tree state across restarts; EXTENSION-COMPUTE.md §7.1 requires dependency-index rebuild from `system/compute/processes/*` on restart; EXTENSION-SUBSCRIPTION states that the subscription entity is source of truth and internal indexes are caches over those entities. The blanket clause in §6.7.4.1 ("query indexes and other derived state rebuild after hydration completes") covers handlers whose extension specs don't restate the requirement.

Patterns for satisfying this invariant — including the descriptive Class D/I/L vocabulary for canonical peer-internal entities and the handler-state rebuild patterns — live in `GUIDE-RESTART-AND-PERSISTENCE.md`. The patterns are advisory; this section's invariant is the normative requirement.

#### 6.7.4.1 Store-level hydration

Persistence implementations MUST hydrate the in-memory stores at peer startup, before the peer accepts external EXECUTEs. Hydration reads both persisted content and persisted location-index entries into memory. Query indexes and other derived state rebuild after hydration completes.

Hydration is NOT an emit consumer — it runs during peer initialization, outside the emit pathway. It is the inverse of the persistence consumers' normal operation: read from backend → populate memory.

#### 6.7.5 Implementation freedom — the boundary

The protocol specifies behavior at boundaries: wire format, handler dispatch semantics, content addressing invariants, the emit pathway model (§1), capability rules. Implementations are wide open within these boundaries:

- Whether any given entity is stored in memory, persisted, synthesized on demand, or cached with TTL.
- How memory relates to persistence (selection, caching wrapper, emit consumer pattern from §2.7).
- Backend choice (SQLite, IndexedDB, embedded KV, flat files, mmap, none).
- Index representation, maintenance, promotion, demotion policies.
- Duplication levels — a peer may store an entity multiple times across layers if latency demands it, or deduplicate aggressively if memory demands it.

This freedom is essential to the system's deployment range. Browser peers, native peers, and cluster-backed peers have radically different storage economics; mandating a single storage model would constrain deployments unnecessarily. Peer-to-peer interop is preserved through the boundary guarantees, not through shared internal implementation.

---

## 7. Observability and Resilience

### 7.1 The Tree IS the Monitoring Surface

Everything about the system's reactive configuration is an entity in the tree:

| What | Where |
|------|-------|
| Installed compute subgraphs | `system/compute/processes/*` |
| Subgraph status | `system/compute/processes/{id}.data.status` |
| Subscription registrations | `system/subscription/*` |
| Handler manifests | `system/handler/*` |
| Capability grants | `system/capability/grants/*` |
| Peer connections | `system/connection/*` |
| Subscriber capacity config | `system/config/subscription` |

No separate monitoring database is needed. Any observability tool can query the tree directly. Meta-subscriptions work naturally: a monitoring peer can subscribe to `system/compute/processes/*` and receive notifications when subgraph state changes.

### 7.2 Graceful Degradation

The system degrades gracefully under pathological configurations:

| Mechanism | What it prevents |
|-----------|-----------------|
| Cascade depth thresholds (§3.2) | Stack overflow from recursive emit |
| Compute budget exhaustion | Runaway evaluation consuming CPU |
| Installation grant revocation | Orphaned reactive computation |
| Subscription capacity redirect | Fan-out overload on a single peer |
| TTL on bounds | Unbounded cross-peer cascades |
| Convergence check (§5.1) | Useless cascade work |
| No-op suppression (§1.1) | Events for writes that don't change state |

The common pattern: **bound the damage, surface the problem, keep running**. Errors are entities (inspectable, storable). Every resource limit has a defined failure mode (freeze, error, redirect, refuse). Extensions are independent — one failing doesn't break others.

### 7.3 Known Failure Modes

Scenarios where operational intervention may be needed:

- **Memory exhaustion from high-frequency writes.** External callers sending EXECUTEs faster than the peer processes them. Mitigation: rate limiting at connection level, 429 backpressure.
- **Disk exhaustion from history growth.** History records every tree write. Mitigation: history pruning, compaction.
- **Cross-peer loops not caught by TTL.** TTL set too high, cycle produces new content each iteration. Mitigation: shorter TTLs for reactive paths, install-time cycle detection.
- **Cross-peer cascade tracking eviction gap.** The `chain_id → cascade_depth` map evicts entries by TTL. If eviction TTL < bounds TTL and a cross-peer loop has long intervals between notifications, the tracking entry may be evicted before the next notification arrives. The next notification initializes cascade_depth at 0, bypassing the threshold. Mitigation: eviction TTL should match or exceed bounds TTL; TTL on bounds remains the hard limit.
- **Pathological cascade staying under thresholds.** Attacker designs reactive graph maximizing work per emit without triggering freeze. Mitigation: per-caller rate limiting, dispatch budgets.
- **Dynamic expressions hiding cycles.** `compute/if` branches can create runtime cycles invisible to static analysis. Mitigation: runtime cycle detection via `chain_id`.

---

## 8. Extension Combinations

### 8.1 Common Compositions

| Combination | What it enables |
|-------------|----------------|
| Core only | Request/response, no reactive behavior |
| Inbox alone | Basic sync — remote data arrives, written to local tree |
| Inbox + subscription | Reactive sync — change notifications propagate |
| Inbox + subscription + compute | Full reactive pipeline — derived state auto-updates |
| Compute + history | Inspectable derived state with audit trail |
| Revision + history | Version control with per-write audit |
| Subscription + compute (cross-peer) | Distributed reactive computation |

### 8.2 Known Gaps

- Cross-peer compute cycles: bounded by TTL, not convergence. Cascades across peer boundaries may not converge within the TTL window.
- Cross-peer installation grant revocation propagation: when an installation grant is revoked on the granting peer, dependent peers' subgraphs should freeze. The propagation mechanism is not yet specified.

---

## 9. Implementer Checklist

For a peer combining N system extensions:

- [ ] Does your emit pathway invoke consumers synchronously, in the order specified in §2.2?
- [ ] Does your execution context carry all required fields (§1.4)?
- [ ] Is cascade depth shared across extension boundaries (not per-extension)?
- [ ] Is cascade depth initialized to 0 on external writes and incremented on nested writes?
- [ ] Do you maintain a `chain_id → cascade_depth` map for cross-peer tracking (§3.4)?
- [ ] Does `chain_id` propagate unchanged through the entire cascade?
- [ ] Does each emitting consumer have a self-guard against direct recursion (§6.1)?
- [ ] Does the Phase 2 broadcast fire only after all synchronous consumers complete?
- [ ] Are the cascade depth thresholds enforced (§3.2)?
- [ ] Does your tree write suppress events when the new hash equals the previous hash (no-op suppression, §1.1)?
- [ ] Does your TreeChangeEvent snapshot the execution context at creation time (not reference the live mutable context)? (§1.3)
- [ ] If your peer has persistence, does it register persistence consumers at position 0 on both content-store and tree-change events (§2.2, §6.7)?
- [ ] Does your emit pipeline fire content-store events on `content_store.put` (§1.1)?
- [ ] Does your emit pipeline fire tree-change events on `location_index.set`/`delete` (§1.1)?
- [ ] Are content-store event consumers dispatched in the order specified in §2.2 (persistence, then query content indexes)?
- [ ] Do content-event Phase 1 consumers run synchronously during `content_store.put`, completing before the put returns?
- [ ] Do your persistence consumers abort the operation on failure (Phase 1 semantics, §2.7)?
- [ ] Does your peer perform startup hydration of both content store and location index before accepting requests (§6.7.4)?
- [ ] Do your persistence consumers respect a scoping policy for external-backed entities (§6.7.3)?
- [ ] If your peer is multithreaded, do you hold path-scoped locks across the emit (§6.7.2)?
- [ ] Does a Phase 1 consumer returning non-200 skip all subsequent consumers for that event (§2.7)?
- [ ] Does your tree.put return status 207 with `system/tree/partial-result` when a Phase 1 consumer halts (§2.7A)?
- [ ] Are cascade halts surfaced to the peer operator via some observable mechanism (§2.7)?
- [ ] Do your Phase 1 consumers return non-200 only for intentional halts, not for internal errors they can handle (§2.7)?

---

## 10. Cross-Implementation Conformance

Implementations SHOULD fail-fast on non-spec paths, field shapes, and protocol constructs rather than normalize them away. Tolerance of non-conforming inputs hides bugs in peers and lets wrong conventions propagate silently across the ecosystem. Cross-peer conformance benefits more from strict fail-fast behavior than from silent correction.

Specific cases MAY warrant tolerance — for example, accepting deprecated fields during a documented transition window. Such tolerance SHOULD be explicit: a documented tolerance window with a scheduled removal date, not ambient permissiveness. Implementations SHOULD log non-conforming inputs that they tolerate, so that the tolerance is observable rather than silent.

# System History Extension

**Version**: 1.8
**Status**: Active
**Depends**: ENTITY-CORE-PROTOCOL.md (v7.19+)
**Encoding**: ENTITY-CBOR-ENCODING.md (ECF)

---

> **Path notation.** Paths in this document use peer-relative notation (without leading `/{peer_id}/`). All peer-relative paths resolve to the local peer's namespace: `system/tree` means `/{local_peer_id}/system/tree`. Every path in the entity tree is absolute at rest — rooted at a peer identity. See ENTITY-CORE-PROTOCOL.md §1.4 for the path model. Cross-peer examples use absolute paths with explicit peer identities.

## 1. Overview

This extension provides path-level transition recording for the entity tree. When an entity is written to a history-enabled path, the emit pathway records the transition with full execution context — who changed it, when, under what authority, through which handler, and the causal chain_id.

History is per-path, per-peer, and automatic. It does not provide cross-peer coordination, multi-path atomicity, or merge semantics — those are the revision extension's concerns. History provides audit, rollback, and fine-grained undo.

### 1.1 Scope

This extension covers:

- **Transition recording** — capturing entity changes with execution context
- **History traversal** — walking the transition chain for any path
- **Rollback** — restoring a path to a previous state
- **Audit** — recording access events (reads), not just mutations (writes)
- **Configuration** — enabling/disabling history per path pattern

This extension does **not** cover:

- Multi-path snapshots or versions (revision extension)
- Cross-peer synchronization (revision extension)
- Merge semantics (revision extension)

### 1.2 Relationship to Other Extensions

**Tree extension.** History records transitions to tree bindings. The tree handler's `put` operation triggers history recording via the emit pathway. History configuration and head pointers are stored as tree bindings at `system/history/` paths.

**Subscription extension.** Subscriptions fire notifications on tree changes. History records the change itself, with richer metadata than notifications carry. A subscription notification includes event type, URI, new hash, previous hash, and chain_id. A history transition includes all of that plus author, capability, handler, operation, and timestamp.

**Revision extension.** History provides fine-grained per-path detail. The revision extension provides coarse-grained multi-path coordination. Between two revision entries, history shows every individual write. The revision extension can use history for detailed diff and audit, but doesn't require it.

---

## 2. Types

### 2.1 Transition Entity

A transition records a single change to a tree binding:

```
system/history/transition := {
  fields: {
    path:          {type_ref: "system/tree/path"}
    event:         {type_ref: "primitive/string"}
                    ; "created", "updated", "deleted", "accessed"
    hash:          {type_ref: "system/hash", optional: true}
                    ; New entity hash. Present for created/updated/accessed. Absent for deleted.
    previous_hash: {type_ref: "system/hash", optional: true}
                    ; Previous entity hash. Present for updated/deleted. Absent for created.
    author:        {type_ref: "system/hash"}
                    ; Identity that initiated the request chain leading to this
                    ; write. For external requests, the remote peer's identity
                    ; hash. For autonomous operations (no external request), the
                    ; local peer's identity hash. Propagated through handler
                    ; chains — see V7 §6.8 context propagation.
    capability:    {type_ref: "system/hash"}
                    ; Grant that authorized this specific tree write. For caller-
                    ; authorized writes, the external caller's capability from
                    ; the EXECUTE envelope. For handler-authorized writes, the
                    ; handler's own grant. For autonomous operations, the handler
                    ; grant. See V7 §6.8 write authorization.
    caller_capability: {type_ref: "system/hash", optional: true}
                    ; Grant that initiated the request chain leading to this
                    ; write. Present only when it differs from capability —
                    ; i.e., handler-authorized writes within externally-
                    ; triggered chains. Absent when redundant (caller-
                    ; authorized writes where capability IS the caller's
                    ; grant) and absent for autonomous operations (no
                    ; external request).
    handler:       {type_ref: "system/tree/path"}
                    ; Handler's registered pattern — the bare pattern from the
                    ; handler manifest's pattern field (e.g., "system/tree",
                    ; "local/files"). Not an absolute path. The handler is always
                    ; a local handler (history is recorded by the local peer).
    operation:     {type_ref: "primitive/string"}
                    ; Operation name (e.g., "put", "merge", "get")
    timestamp:     {type_ref: "primitive/uint"}
                    ; Wall-clock milliseconds since epoch
    clock:         {type_ref: "system/clock/state", optional: true}
                    ; Full clock state from the live execution context at
                    ; recording time — advanced by the CLOCK extension at
                    ; emit position 2 before history fires. Embeds the
                    ; timestamp / logical / vector / hlc subfields that were
                    ; populated by CLOCK's current mode (EXTENSION-CLOCK §2.6).
                    ; Absent when the clock extension is not installed. See
                    ; SYSTEM-COMPOSITION.md §1.4 and §1.5, and EXTENSION-CLOCK §4.
    chain_id:      {type_ref: "primitive/string", optional: true}
                    ; Causal correlation from bounds context
    parent_chain_id:{type_ref: "primitive/string", optional: true}
                    ; Parent chain's chain_id from bounds context. Enables
                    ; querying "everything this user action triggered" across
                    ; all sub-chains. Absent for root chains.
    previous:      {type_ref: "system/hash", optional: true}
                    ; Hash of the prior transition for this path (forms the history chain)
  }
}
```

A transition entity is content-addressed. Its `content_hash` is computed per ENTITY-CORE-PROTOCOL.md §1.2 using the peer's configured `content_hash_format` over the canonical encoding of `{type: "system/history/transition", data: ...}`. Transitions are stored in the content store and chained via the `previous` field.

The `path` field records the path of the entity that changed (e.g., `"/{peer_id}/docs/report"`, not `"docs/report"`). All paths in stored entities are peer-namespaced per ENTITY-CORE-PROTOCOL.md §1.4. The `handler` field similarly records the handler's tree location as a path (e.g., `"/{peer_id}/system/tree"`).

**Event types:**

| Event | Meaning | `hash` | `previous_hash` |
|-------|---------|--------|-----------------|
| `created` | Entity placed at a previously empty path | New entity hash | Absent |
| `updated` | Entity replaced at a path | New entity hash | Old entity hash |
| `deleted` | Binding removed from path | Absent | Removed entity hash |
| `accessed` | Entity read at a path (audit mode) | Read entity hash | Absent |

The `accessed` event is optional — only recorded when the history configuration includes `"accessed"` in its events list. This enables read audit for security-sensitive paths.

### 2.2 History Configuration

Per-path-pattern configuration for history recording:

```
system/history/config := {
  fields: {
    pattern:    {type_ref: "system/tree/path"}
                 ; Path pattern. Uses core pattern syntax (V7 §5.4).
                 ; E.g., "docs/*", "local/files/*", "/*/project/*"
    enabled:    {type_ref: "primitive/bool"}
                 ; Whether to record transitions for matching paths
    events:     {array_of: {type_ref: "primitive/string"}, optional: true}
                 ; Which events to record. Default: ["created", "updated", "deleted"]
    max_depth:  {type_ref: "primitive/uint", optional: true}
                 ; Maximum transitions to retain per path. Older transitions
                 ; may be pruned. Absent = no limit (retain all).
  }
}
```

Stored at `system/history/config/{config_name}`.

**Pattern syntax.** Config patterns use the core pattern syntax (ENTITY-CORE-PROTOCOL.md §5.4):

| Pattern | Meaning |
|---------|---------|
| `project/*` | Subtree under `project/` (short-form → canonicalized to `/{local}/project/*`) |
| `/{peerB}/project/*` | Subtree under peerB's `project/` |
| `/*/project/*` | Peer wildcard — `project/*` subtree in any peer's namespace |
| `*` | Match everything |
| `project/readme` | Exact match (short-form → `/{local}/project/readme`) |

**The wildcard is in the peer position or at the tail — there is no mid-path wildcard.**
ENTITY-CORE-PROTOCOL.md §5.4's `matches_pattern` recognises exactly bare `*`, a leading `/*/`
peer wildcard, and a trailing `/*` subtree; **anything else is compared as an exact string.**
A `*` in a middle segment is therefore not a wildcard at all — `a/*/c` matches the literal
three-character-segment path and nothing else. The peer wildcard is spelled `/*/rest` and
**never `*/rest`**, which `canonicalize` rejects by name.

**Pattern canonicalization.** Config patterns are stored as-is in entity data (entity data is content-addressed and immutable). When evaluating patterns, the history recorder canonicalizes them using `canonicalize_pattern`:

```
canonicalize_pattern(pattern, local_peer_id):
  if starts_with(pattern, "/"):
    return pattern                          ; already absolute
  ; Bare "*" is match-everything, NOT a peer wildcard: it canonicalizes to the
  ; local namespace per ENTITY-CORE-PROTOCOL.md §5.4. Tested before the
  ; first-segment check, which would otherwise read it as a peer wildcard and
  ; emit the degenerate "/*/".
  if pattern == "*":
    return "/" + local_peer_id + "/*"
  first_segment = first_segment_of(pattern)
  if first_segment == "*":
    ; Peer wildcard. Emit the CANONICAL spelling "/*/" + rest — a bare leading
    ; "*/" is rejected by core canonicalize and is not recognized by
    ; matches_pattern, so returning it unchanged produces a pattern that
    ; stores, resolves, and silently matches nothing.
    return "/*/" + rest_after_first_segment(pattern)
  return "/" + local_peer_id + "/" + pattern ; short-form → local namespace
```

Short-form patterns like `"project/*"` are canonicalized to `"/{local_peer_id}/project/*"` at evaluation time. Patterns starting with `*/` pass through unchanged — `*` is recognized as the peer wildcard, not a short-form path segment. Patterns already starting with `/` pass through unchanged.

This function is specific to history config pattern evaluation. The core `canonicalize` (ENTITY-CORE-PROTOCOL.md §5.4) is unchanged.

**Pattern specificity.** When multiple configurations match a path, the most specific pattern wins. Specificity is determined by: (1) number of literal (non-wildcard) segments, then (2) total segment depth. A pattern with more literal segments is more specific. A pattern with an explicit peer ID (e.g., `"/{peerA}/project/*"`) is more specific than a wildcard peer ID (e.g., `"*/project/*"`) at the same depth. If history is not configured for a path, no transitions are recorded (history is opt-in).

**Default events:** `["created", "updated", "deleted"]`. To enable read audit, add `"accessed"` to the events list.

### 2.3 Query Parameters

The `path` field in query and rollback parameters accepts short-form input. The handler canonicalizes it before processing. To query or rollback history for a remote peer's path (if tracked), provide the full path.

```
system/history/query-params := {
  fields: {
    path:    {type_ref: "system/tree/path"}
              ; The path to query history for
    limit:   {type_ref: "primitive/uint", optional: true}
              ; Maximum transitions to return. Default: 50
    since:   {type_ref: "system/hash", optional: true}
              ; Return transitions after this transition hash (exclusive)
    before:  {type_ref: "primitive/uint", optional: true}
              ; Return transitions before this timestamp (ms since epoch)
    events:  {array_of: {type_ref: "primitive/string"}, optional: true}
              ; Filter by event type. Default: all events.
  }
}
```

### 2.4 Query Result

```
system/history/query-result := {
  fields: {
    path:         {type_ref: "system/tree/path"}
    head:         {type_ref: "system/hash", optional: true}
                   ; Hash of most recent transition. Absent if no history.
    transitions:  {array_of: {type_ref: "system/history/transition"}}
                   ; Transitions in reverse chronological order (newest first)
    has_more:     {type_ref: "primitive/bool"}
                   ; Whether more transitions exist beyond the returned set
  }
}
```

---

## 3. Storage Model

### 3.1 Entity-Native Storage

Transition entities are regular entities in the content store. Head pointers are tree bindings at `system/history/` paths. No external indexes are required — the tree IS the index.

**Head pointers.** For each path with history, a head pointer is stored at:

```
system/history/head/{path}  →  hash of latest transition entity
```

Where `{path}` is the full peer-namespaced path being tracked. The head pointer is itself in the local peer's namespace — it is the local peer's record of changes, regardless of which namespace the tracked path is in.

**Example — local path:**
```
/{local_peer_id}/docs/report                                      →  hash_of_current_entity
system/history/head/{local_peer_id}/docs/report                   →  hash_of_latest_transition
; In the tree: /{local_peer_id}/system/history/head/{local_peer_id}/docs/report
```

**Example — tracking remote peer's synced content:**
```
system/history/head/{remote_peer_id}/project/readme              →  hash_of_latest_transition
; In the tree: /{local_peer_id}/system/history/head/{remote_peer_id}/project/readme
```

**Transition chain.** Each transition entity contains a `previous` field pointing to the prior transition's content hash. Walking the chain from the head gives the complete history:

```
system/history/head/{peerA}/docs/report → T3 (latest)
  T3.data.path = "/{peerA}/docs/report"
  T3.previous → T2
    T2.data.path = "/{peerA}/docs/report"
    T2.previous → T1
      T1.data.path = "/{peerA}/docs/report"
      T1.previous → null (first write)
```

All transition entities are in the content store. Only the head pointer is in the tree.

### 3.2 Recursion Prevention

Writing to the **local peer's** `system/history/` paths MUST NOT trigger history recording. This prevents infinite recursion: the history recorder writes head pointers to `system/history/head/...`, which are local-namespace system paths.

```
is_local_history_path(path, local_peer_id):
  if not starts_with(path, "/" + local_peer_id + "/"):
    return false   ; remote namespace — no recursion risk
  suffix = path[len(local_peer_id) + 2:]
  return starts_with(suffix, "system/history/head")
```

The self-guard targets engine-written paths (`system/history/head*`) rather than the entire history namespace. Configuration paths (`system/history/config/*`) are handler-written via explicit EXECUTE and do not create recursion risk — they SHOULD be recorded as normal transitions for audit purposes. See SYSTEM-COMPOSITION.md §6.1 for the engine-output vs configuration path distinction.

Remote peers' `system/history/` paths arriving via sync MAY be tracked if a configuration pattern matches them. There is no recursion risk: the sync event is a one-shot write. The local peer's resulting head pointer update is at `/{local}/system/history/head/{remote}/system/history/...`, which is in the local `system/history/head` namespace and therefore excluded by the check above.

### 3.3 GC Interaction

Transition entities in the content store are subject to the same GC policies as other entities. The `max_depth` configuration bounds how many transitions per path are **retained** — how many the peer undertakes to keep, not how many it must destroy.

**`max_depth` is a retention policy. The chain is never rewritten and the head is never re-pointed `[v1.8]`.** A transition chain is hash-linked: reachability from the head **is carried by** the `previous` fields, so making the `(N+1)`-th transition unreachable would require a version of the `N`-th without its `previous` — a different entity with a different content hash — which changes what the `(N−1)`-th points at, and so on to the head. **Truncating a hash-linked chain means rewriting all of it, and rewriting an audit chain defeats the purpose of keeping one.** Re-pointing the head at the last-kept transition is worse still: it orphans the *newest* entries rather than the oldest.

```
prune_history(path, max_depth):
  ; path is peer-namespaced (e.g., "/{peer_id}/docs/report")
  ; Walks the chain and marks the retention boundary. It MUTATES NOTHING:
  ; no entity is rewritten, the head pointer is not moved, and the chain
  ; stays fully linked from head to origin.
  head_hash = tree.get("system/history/head/" + path)
  if head_hash is null: return

  transition = content_store.get(head_hash)
  count = 1
  while transition.data.previous is not null and count < max_depth:
    transition = content_store.get(transition.data.previous)
    count += 1

  ; `transition` is the oldest RETAINED entry. Everything reachable through
  ; its `previous` is beyond the retention bound and is no longer held by
  ; this policy — it becomes collectable under the peer's ordinary
  ; collection policy, exactly as any other unreferenced content.
  return transition
```

**A peer that collects nothing is conformant.** `max_depth` is `SHOULD` (§9.1); a peer that retains every transition forever has satisfied it, because the bound is a floor on what is kept and never a ceiling. Consequently a `query` MAY return transitions older than `max_depth` — they were never required to be gone — and a caller MUST NOT infer from their absence that they were pruned rather than never written.

---

## 4. Handler

### 4.1 Handler Manifest

```
system/handler := {
  data: {
    pattern:    "system/history"
    name:       "history"
    operations: {
      query:    {input_type: "system/history/query-params",    output_type: "system/history/query-result"}
      rollback: {input_type: "system/history/rollback-params", output_type: "system/history/rollback-result"}
    }
  }
}
```

Manifest at pattern path `system/history`. Index entry at `system/handler/system/history`.

### 4.2 Dual Capability Model

History operations require **two** authorization checks:

1. **History handler capability** — caller must have a grant covering `system/history` with the requested operation
2. **Target path capability** — caller must have capability to access the target path

This prevents using the history system to access data the caller couldn't otherwise read. The history handler validates target access by checking the caller's capability against the target path (using `check_path_permission` from ENTITY-CORE-PROTOCOL.md §6.3).

```
check_history_access(capability, operation, target_path, handler_pattern, local_peer_id):
  ; Check 1: can caller use the history handler?
  if not check_permission(execute, capability, handler_pattern, local_peer_id):
    return DENY

  ; Check 2: can caller access the target path?
  target_operation = "get"   ; history requires at minimum read access to the target
  if operation == "rollback":
    target_operation = "put"  ; rollback requires write access
  if not check_path_permission(target_operation, target_path, capability, "system/tree", local_peer_id):
    return DENY

  return ALLOW
```

### 4.3 Operations

#### 4.3.1 query

Retrieve the transition history for a path.

```
EXECUTE system/history  operation: "query"
  resource: {targets: ["system/history"]}
  params: {
    type: "system/history/query-params"
    data: {
      path: "/{peer_id}/docs/report"    ; or short-form "docs/report"
      limit: 10
    }
  }
```

**Algorithm:**

```
handle_query(ctx, params):
  path = canonicalize(params.data.path, local_peer_id)

  ; Dual capability check
  if not check_history_access(ctx.capability, "query", path, ...):
    return error(403, "access_denied")

  head_hash = tree.get("system/history/head/" + path)
  if head_hash is null:
    return {type: "system/history/query-result", data: {path: path, transitions: [], has_more: false}}

  transitions = []
  current_hash = head_hash
  while current_hash is not null and len(transitions) < params.data.limit:
    transition = content_store.get(current_hash)
    if transition is null: break

    ; Apply filters
    if params.data.since is not null and current_hash == params.data.since:
      break
    if params.data.before is not null and transition.data.timestamp >= params.data.before:
      current_hash = transition.data.previous
      continue
    if params.data.events is not null and transition.data.event not in params.data.events:
      current_hash = transition.data.previous
      continue

    transitions.append(transition)
    current_hash = transition.data.previous

  has_more = current_hash is not null
  return {
    type: "system/history/query-result",
    data: {path: path, head: head_hash, transitions: transitions, has_more: has_more}
  }
```

When the handler includes full transition entities for efficiency, it SHOULD return a `system/envelope` result (root = the `system/history/query-result`, included = transition entities) rather than placing them in the outer protocol envelope.

#### 4.3.2 rollback

Restore a path to a previous state.

```
EXECUTE system/history  operation: "rollback"
  resource: {targets: ["system/history", "/{peer_id}/docs/report"]}
  params: {
    type: "system/history/rollback-params"
    data: {
      path: "/{peer_id}/docs/report"    ; or short-form "docs/report"
      target_hash: <hash of entity to restore>
    }
  }
```

```
system/history/rollback-params := {
  fields: {
    path:        {type_ref: "system/tree/path"}
    target_hash: {type_ref: "system/hash"}
                  ; Content hash of the entity to restore at this path
  }
}

system/history/rollback-result := {
  fields: {
    path:     {type_ref: "system/tree/path"}    ; The path that was restored
    restored: {type_ref: "system/hash"}         ; Content hash of the restored entity
  }
}
```

**Algorithm:**

```
handle_rollback(ctx, params):
  path = canonicalize(params.data.path, local_peer_id)
  target_hash = params.data.target_hash

  ; Dual capability check (needs write access to target path)
  if not check_history_access(ctx.capability, "rollback", path, ...):
    return error(403, "access_denied")

  ; Verify target_hash is in this path's history (prevents restoring arbitrary content)
  if not is_in_history(path, target_hash):
    return error(404, "not_in_history", "Target hash not found in history for this path")

  ; Restore by rebinding the path to the old entity's content hash.
  ; The entity is already in the content store — we rebind the path to it.
  ; This goes through normal put, which will itself be recorded in history.
  tree.put(path, target_hash)

  return {type: "system/history/rollback-result", data: {path: path, restored: target_hash}}
```

```
is_in_history(path, target_hash):
  head_hash = tree.get("system/history/head/" + path)
  current = head_hash
  while current is not null:
    transition = content_store.get(current)
    if transition.data.hash == target_hash or transition.data.previous_hash == target_hash:
      return true
    current = transition.data.previous
  return false
```

The rollback itself is a normal `put`, so it creates a new history transition: event `"updated"`, hash = target_hash, previous_hash = whatever was at the path before rollback. The history chain records the rollback as a regular write — the transition's `operation` field will reflect the rollback operation.

**Advisory — remote namespace rollback.** Rollback operates on the local tree. Rolling back a remote namespace path (e.g., `/{peerB}/project/readme`) modifies the local cached copy of that peer's data. This causes the local tree to diverge from the remote peer's actual state. The next sync from that peer would overwrite the rolled-back value. Remote namespace rollback is not prohibited — the local peer has authority over its own tree — but it is rarely the intended operation.

---

## 5. Emit Pathway Integration

### 5.1 Recording Transitions

The emit pathway is triggered by **any tree mutation** — `put`, `merge`, `delete` (put with null entity), or any handler operation that writes to the location index. The `emit_entity` function is called by the tree handler (or any tree-mutating handler) after each binding change, with the execution context from the current handler operation.

History's position in the emit pathway consumer ordering (after clock, before compute and subscription) is specified in SYSTEM-COMPOSITION.md §2.2. The execution context fields recorded in history transitions are defined in SYSTEM-COMPOSITION.md §1.4. History reads the original writer's provenance (handler_pattern, operation, capability) from the event snapshot and the current clock state from the live execution context. The `clock` field is an extension-contributed context field per SYSTEM-COMPOSITION.md §1.5 (owner: CLOCK), typed `system/clock/state` (EXTENSION-CLOCK.md §2.6) — history records the full structured value including whichever of `timestamp`, `logical`, `vector`, `hlc` subfields CLOCK's current mode populates. See also "Event context vs live context" in SYSTEM-COMPOSITION.md §1.4 for the snapshot/live-context distinction.

```
emit_entity(path, new_entity, execution_context):
  ; path is peer-namespaced (already canonicalized by the tree handler)
  new_hash = content_store.put(new_entity)   ; or null for delete
  previous_hash = tree.get(path)              ; current binding, before update
  tree.set(path, new_hash)                    ; update binding (or remove if null)

  ; Determine event type
  if previous_hash is null and new_hash is not null:
    event = "created"
  elif previous_hash is not null and new_hash is not null:
    event = "updated"
  elif previous_hash is not null and new_hash is null:
    event = "deleted"
  else:
    return  ; null → null, no-op

  ; Recursion prevention (local namespace only — see §3.2)
  if is_local_history_path(path, local_peer_id):
    return

  config = find_history_config(path)
  if config is null or not config.data.enabled:
    return  ; history not enabled for this path

  if event not in (config.data.events or ["created", "updated", "deleted"]):
    return  ; event type not configured

  ; Build transition entity
  head_pointer_path = "system/history/head/" + path
  previous_transition_hash = tree.get(head_pointer_path)

  transition = {
    type: "system/history/transition"
    data: {
      path:          path
      event:         event
      hash:          new_hash          ; null for deleted
      previous_hash: previous_hash     ; null for created
      author:        execution_context.author
      capability:    execution_context.capability
      caller_capability: caller_cap    ; only when differs from capability (see below)
      handler:       execution_context.handler_pattern
      operation:     execution_context.operation
      timestamp:     system_clock_ms()
      chain_id:      execution_context.bounds.chain_id    ; may be null
      previous:      previous_transition_hash              ; may be null
    }
  }

  transition_hash = content_store.put(transition)
  tree.set(head_pointer_path, transition_hash)

  ; Pruning
  if config.data.max_depth is not null:
    prune_history(path, config.data.max_depth)

  ; Normal notification pathway continues
  fire_events(event, path, new_hash, previous_hash, execution_context)

  ; caller_capability computation:
  ;   caller_cap = null
  ;   if execution_context.caller_capability is not null
  ;      AND execution_context.caller_capability != execution_context.capability:
  ;     caller_cap = execution_context.caller_capability
```

**Execution context authorization.** The `execution_context.capability` carries whichever capability authorized the specific tree write, per ENTITY-CORE-PROTOCOL.md §6.8 write authorization. The history extension records this value without interpretation — it does not select between caller capability and handler grant. The handler that performed the write is responsible for providing the correct authorizing capability in its execution context.

The `caller_capability` field is recorded only when it differs from `capability` — indicating a handler-authorized write within an externally-triggered chain. When `caller_capability` would equal `capability` (caller-authorized writes), it is omitted. When there is no external caller (autonomous operations), it is absent.

Reading a transition: `caller_capability` present → handler-authorized write in external chain, this is the external caller's grant. `caller_capability` absent with remote `author` → caller-authorized write, `capability` IS the caller's grant. `caller_capability` absent with local `author` → autonomous, no external caller.

For autonomous writes (subscription delivery, file watcher, clock advancement), the execution context carries the handler grant as the authorizing capability and the local peer identity as the author.

### 5.2 Recording Read Events (Audit Mode)

For paths with `"accessed"` in the events configuration, the tree handler's `get` operation records a transition:

```
handle_get(path, execution_context):
  hash = tree.get(path)
  if hash is null:
    return not_found

  ; Audit recording (if enabled)
  ; path is peer-namespaced (already canonicalized by the tree handler)
  config = find_history_config(path)
  if config is not null and config.data.enabled and "accessed" in config.data.events:
    head_pointer_path = "system/history/head/" + path
    previous_transition_hash = tree.get(head_pointer_path)
    transition = {
      type: "system/history/transition"
      data: {
        path:          path
        event:         "accessed"
        hash:          hash
        previous_hash: null           ; not a mutation
        author:        execution_context.author
        capability:    execution_context.capability
        handler:       execution_context.handler_pattern
        operation:     execution_context.operation
        timestamp:     system_clock_ms()
        chain_id:      execution_context.bounds.chain_id
        previous:      previous_transition_hash
      }
    }
    transition_hash = content_store.put(transition)
    tree.set(head_pointer_path, transition_hash)

  return content_store.get(hash)
```

**Performance note.** Read audit adds a write (transition + head pointer update) for every read on audited paths. This should only be enabled for security-sensitive paths, not globally.

### 5.3 Chain_id as Multi-Path Correlation

When a handler writes to multiple paths in a single operation, all writes share the same `chain_id` from the bounds context. The history transitions for those paths all carry the same `chain_id`.

This provides multi-path correlation without requiring multi-path atomicity:

```
Handler processes operation with chain_id = "abc123":
  put(config/database_url, new_entity_1)  → transition with chain_id "abc123"
  put(config/cache_size, new_entity_2)    → transition with chain_id "abc123"
  put(config/pool_size, new_entity_3)     → transition with chain_id "abc123"
```

Querying history by `chain_id` reveals all paths modified in the same operation. This is NOT a formal commit (no version entity), but it provides a causal grouping for audit purposes.

---

## 6. Configuration Management

### 6.1 Storing Configuration

History configurations are stored as regular entities at `system/history/config/{name}`:

```
EXECUTE system/tree  operation: "put"
  resource: {targets: ["system/history/config/project-files"]}
  params: {
    type: "system/tree/put-request"
    data: {
      entity: {
        type: "system/history/config"
        data: {
          pattern:   "project/*"             ; short-form → canonicalized to "/{local}/project/*"
          enabled:   true
          events:    ["created", "updated", "deleted"]
          max_depth: 1000
        }
      }
    }
  }
```

No special handler operation is needed — configuration uses the standard tree `put`.

### 6.2 Pattern Matching

When determining whether to record history for a path, the emit pathway evaluates all history configurations:

```
find_history_config(path):
  configs = list_entities(canonicalize("system/history/config/", local_peer_id))
  best_match = null
  best_specificity = -1

  for config in configs:
    ; Canonicalize pattern at evaluation time — entity data stores the raw value
    pattern = canonicalize_pattern(config.data.pattern, local_peer_id)
    if matches_pattern(path, pattern):
      specificity = pattern_specificity(pattern)
      if specificity > best_specificity:
        best_match = config
        best_specificity = specificity

  return best_match
```

Pattern matching uses the core `matches_pattern` algorithm (ENTITY-CORE-PROTOCOL.md §5.4).

**`pattern_specificity` is a TWO-KEY comparison, and the selection MUST NOT depend on enumeration order `[MUST, v1.7]`.** §2.2 already states the order — *"(1) number of literal (non-wildcard) segments, then (2) total segment depth"* — but the pseudocode above compares a single `specificity` value with `>`, and `list_entities` ordering is unspecified. **A scalar cannot carry a two-key order**, so an implementation that collapses the keys into one number manufactures ties §2.2 does not have and then resolves them by whatever the store happened to yield.

Compare as an ordered tuple, most significant first:

| Key | Value |
|---|---|
| 1 | count of **literal** (non-`*`) segments — higher wins |
| 2 | **total** segment depth — higher wins |
| 3 | **lexicographic byte order on the canonicalized pattern** — lower wins |

**§2.2's peer-ID rule needs no separate key** — an explicit peer segment is literal and a `*` peer segment is not, so key 1 already ranks `/{peerA}/project/*` above `/*/project/*`.

**Keys 1–2 are already a total order over the patterns §5.4 admits, and key 3 is a defensive tiebreak no constructible pair reaches `[v1.8]`.** Fix an absolute path `/{P}/s₁…sₙ`. Every pattern the core grammar admits that can match it is one of three families:

| Family | literal segments | depth |
|---|---|---|
| exact `/{P}/s₁…sₙ` | `n+1` | `n+1` |
| `/{P}/s₁…s_k/*`, `0 ≤ k < n` | `k+1` | `k+2` |
| `/*/s₁…s_j/*`, `0 ≤ j < n` | `j` | `j+2` |

A key-1 **and** key-2 tie needs two rows agreeing on both columns: the second and third families agreeing on depth forces `j = k`, which contradicts agreement on literals; the exact family ties neither (`n+1 = k+1` forces `k = n`, excluded because a trailing-`/*` prefix match requires the path to be **strictly deeper** than the prefix; `n+1 = j` and `n+1 = j+2` are inconsistent). **Key 3 is retained so the order stays total if the grammar ever gains a form that reaches a tie** — it is peer-independent, so every conformant peer would resolve such a pair identically.

**The scalar collapse this MUST prevents is likewise not constructible today, and the rule is retained as forward-looking.** With `scalar = 2·literals + 1·wildcards = literals + depth`, the three families score `2n+2`, `2k+3` and `2j+2` — the second is **odd** and the others **even**, so no cross-family tie exists; the one same-parity pair needs `2n+2 = 2j+2`, i.e. `j = n`, which the strictly-deeper rule excludes. **So under §5.4's grammar a scalar and the tuple agree on every pair a peer can construct.** The tuple is required so that they still agree if the grammar widens — not because a peer can exhibit the divergence today. **A specification that claimed otherwise would be asking implementers to defend against a case they cannot write a test for**, which is what v1.7's worked pair did: it used `a/*/c/*/e`, a mid-path spelling that is not a pattern at all (§2.2).

**Conformance vector `HIST-CONFIG-SPECIFICITY-1` (REQUIRED) — selection is by specificity, not by enumeration order.** Configure `a/b/*` and `a/*` with distinguishable settings and write at `a/b/c`. Both match; key 1 is 3 against 2, so the `a/b/*` config MUST be selected. **Write the two configs in both insertion orders and assert the same selection each time** — an implementation that returns the first match rather than the most specific one passes exactly one order, by luck.

**Conformance vector `HIST-CONFIG-SPECIFICITY-2` (REQUIRED) — key 2 is load-bearing.** Configure `*` (canonicalizes to `/{local}/*` — 1 literal, depth 2) and `/*/a/*` (1 literal, depth 3) and write at `a/b`. **Key 1 ties at 1 and only key 2 separates them**, so the `/*/a/*` config MUST be selected. Both insertion orders. This pair fails an implementation that compares literal counts alone and never consults depth.

### 6.3 Default Configuration

No history is recorded by default. History is opt-in. A peer that wants history for all paths can configure:

```
system/history/config/everything := {
  type: "system/history/config"
  data: {
    pattern: "*"              ; match everything
    enabled: true
    max_depth: 10000
  }
}
```

---

## 7. Security Model

### 7.1 Dual Capability Check

All history operations require both history handler capability and target path capability. See §4.2.

### 7.2 Capability Audit Trail

The transition entity records the `capability` hash that authorized the write. Given this hash, the full capability token can be resolved from the content store, revealing:

- The grants (what operations, paths, handlers were authorized)
- The grantee (who holds this capability)
- The delegation chain (attenuated from what parent capability)
- Expiration and constraints

This provides a richer audit trail than recording just the author identity. The question "who changed this?" is answered by the author field. The question "under what authority?" is answered by the capability field.

### 7.3 History Path Scoping

History head pointers at `system/history/head/{path}` mirror the full tree structure including peer namespaces. A head pointer for `/{peerA}/docs/report` is at `system/history/head/{peerA}/docs/report`. Access to these paths follows normal capability scoping. A peer with view tree access only sees history heads for paths within their scope.

### 7.4 Rollback Authorization

Rollback requires write capability for the target path (not just read). The rollback operation restores a previous entity, which is a write. The `check_history_access` function checks for `put` permission on the target path for rollback operations.

### 7.5 History Exfiltration Prevention

The rollback operation validates that the target hash appears in the path's history chain. This prevents using rollback to write arbitrary content to a path — you can only restore entities that were previously at that path.

Similarly, the query operation only returns transitions for the queried path. Cross-path history queries are not supported at the handler level — each path's history is independent.

---

## 8. Relationship to Version Extension

### 8.1 History Informs Versioning

The revision extension operates on revision entries (multi-path snapshots with a parent DAG). Between two version entries, history provides per-path detail:

- Which paths changed (derivable from snapshot diff, but history adds who/when/why per path)
- Causal grouping via chain_id (which paths changed in the same operation)
- Capability audit (under what authority each change was made)

### 8.2 Version Resets Don't Break History

When a version merge writes entities to paths (the merge handler resolving conflicts), those writes appear in history as normal transitions. The history chain is continuous regardless of version operations.

A version rollback to a previous version entry (restoring a snapshot) appears in history as a series of `put` operations restoring old entities. The chain_id groups these rollback writes.

### 8.3 Independence

A peer can have history without versioning (local audit and undo). A peer can have versioning without history (collaboration without per-write audit). They're independent extensions sharing the emit pathway as the integration point.

---

## 9. Conformance

### 9.1 Requirements

| Requirement | Level |
|-------------|-------|
| Store transition entities in content store | MUST |
| Store head pointers at `system/history/head/{path}` | MUST |
| Record `author`, `capability`, `timestamp` in transitions | MUST |
| Record `caller_capability` when it differs from `capability` | SHOULD |
| Record `handler`, `operation`, `chain_id` in transitions | SHOULD |
| Support `"accessed"` event type | MAY |
| Support `max_depth` pruning | SHOULD |
| Exclude local peer's `system/history/*` from history recording | MUST |
| Dual capability check on all operations | MUST |
| Validate rollback target is in path history | MUST |
| Refuse a rollback target absent from the chain with `404 not_in_history` (Appendix A, §7.5) | MUST |
| Emit error codes from Appendix A's set; no other more-specific spelling | MUST |
| Select the most specific matching config, independent of enumeration order (§6.2) | MUST |
| Compare specificity as the §6.2 tuple, not a collapsed scalar (§6.2) | MUST |
| Canonicalize a leading-`*` config pattern to `/*/` + remainder (§2.2) | MUST |

### 9.2 Types Installed

The history extension installs these types:

```
system/history/transition
system/history/config
system/history/query-params
system/history/query-result
system/history/rollback-params
system/history/rollback-result
```

### 9.3 Handler Registered

```
system/handler/system/history := system/handler {
  pattern:    "system/history"
  name:       "history"
  operations: {
    query:    {input_type: "system/history/query-params",    output_type: "system/history/query-result"}
    rollback: {input_type: "system/history/rollback-params", output_type: "system/history/rollback-result"}
  }
}
```

---

## Appendix A: Error Codes

The `system/history` handler's code set, per `ENTITY-CORE-PROTOCOL` §3.3's default-code force:
a more-specific code is conformant only where one is **defined for the operation in a spec code
set**, and this table is that set for this handler. An undefined spelling is non-conformant and
falls back to the status's default.

| Operation | Error Code | Status | Description |
|-----------|-----------|--------|-------------|
| `rollback` | `not_in_history` | 404 | The `target_hash` does not appear in the chain for this path (§4.3.2). **A domain 404 — the handler is registered and the operation ran; the requested restore point is not in this path's history.** §3.3's 404 default is `handler_not_found`, which would be actively wrong here |
| `query`, `rollback` | `access_denied` | 403 | Either half of the §4.2 dual capability check refused — the history handler grant or the target-path grant (§4.2, §7.1) |
| (any) | `path_required` | 400 | `resource` absent on a directly-callable op. **The authority for this status is the extension-development guide's error-code section, not this table** — the code is emitted by more than one extension and its home is a corpus-level question tracked separately |
| (any) | `unexpected_params` | 400 | `ENTITY-CORE-PROTOCOL` §3.3's enumerated 400 specific |
| (any) | `unsupported_operation` | 501 | `ENTITY-CORE-PROTOCOL` §3.3's 501 row default |
| (any) | `storage_error` | 500 | Content-store or tree read/write failure; §3.3's enumerated 500 specific |

**`not_in_history` is security-relevant and is why this appendix exists.** §7.5 makes it the
refusal that stops `rollback` being an unrestricted write primitive — *you can only restore
entities that were previously at that path.* §4.3.2's algorithm spells the token; before v1.8
no code set defined it, so a peer following §3.3's closed-set rule to the letter had to fall
back to the 404 default and lose the distinction the security model depends on.

**The token is the `code`, never a label in the `message`.** `message` is optional and
human-readable (`ENTITY-CORE-PROTOCOL` §3.3); a discriminator a caller must branch on cannot
live there, because a conformant peer may omit the field entirely.

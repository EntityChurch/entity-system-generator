# Guide: Extension Development

**Status**: Active
**Audience:** Extension authors (architecture team, contributors), implementation teams reading specs, future external contributors writing proposals.
**Scope:** How to design, write, and stabilize a new extension to the entity system. The mechanics of any specific extension live in its own spec; this guide is meta — what every extension author should understand before starting.

---

## 1. Read core protocol first

Before writing or proposing an extension, **read `ENTITY-CORE-PROTOCOL.md` end to end**. Every extension lives on top of the V7 surface; concepts the core protocol pins (entity shape, content addressing, capability mechanics, dispatch, signature ingestion, path resolution) are not negotiable from extension territory.

Specifically check:

- §1.1 — entity shape `{type, data, content_hash}` and content-addressing.
- §1.4 / §5.4 — path canonicalization (peer-relative vs absolute; `/{peer}/...` form).
- §3 — protocol message types; §3.2 path-as-resource MUST; §3.7 handler-op type registration convention.
- §5 — capability model; §5.5 chain verification; §5.5a cap-resource canonicalization.
- §6 — handler model; §6.5 envelope-included signature ingestion; §6.10 emit pathway.
- §7 — algorithmic instantiation (SHA-256, CBOR, Ed25519, Base58, Multikey).

If your extension wants something the core protocol forbids or under-specifies, the answer is usually **not** "add it to the extension." Either propose a core-protocol amendment, or rethink whether the constraint is real.

`SYSTEM-ARCHITECTURE.md` is the navigable map across the layered structure (L0 algorithms, L1 core protocol, L2 SYSTEM-COMPOSITION, L2.5 extensions, L3+ SDK). Extensions live at L2.5. Read it for orientation.

---

## 2. What an extension actually is

An extension contributes one or more of:

| Kind | What it adds | Example |
|---|---|---|
| **Entity types** | New `system/<ext>/<type>` definitions consumed by the type system | `system/quorum`, `system/identity/peer-config` |
| **Properties on universal types** | New `properties.kind` values on `system/attestation` (or other open-vocabulary types) with consumer-defined shape | `quorum-update`, `identity-cert`, `revocation` |
| **Handler operations** | New ops at `system/<ext>:<op>` callable via EXECUTE | `system/quorum:create`, `system/identity:configure` |
| **Validators / helpers** | Pure or side-effect-free functions consumed internally or by other extensions | `verify_k_of_n_signatures`, `is_attestation_live` |
| **Storage conventions** | Path layout under `system/<ext>/...` for the extension's own entities | `system/quorum/{q}/event/{h}` |
| **Sync / dispatch hooks** | Subscriptions on specific subtrees that trigger consumer logic on arrival | `process_attestation` on `system/identity/public/cert/...` |
| **Extension points** | Hooks other extensions can register against | `system/quorum:register_resolver` for signer-resolution modes |

Most extensions contribute several of these. The smallest useful extensions contribute one entity type and one handler op (e.g., a single `:create` for a domain-specific entity). The largest contribute deep composition over multiple substrate primitives.

An extension is NOT:
- An application. Applications consume extensions through the SDK; they don't redefine system semantics.
- A replacement for V7 mechanics. If your extension wants to change capability validation or signature verification, propose a V7 amendment, not an extension.
- Infinitely flexible. Conformance levels exist; the extension is part of the conformance contract impl teams test against.

---

## 3. Design principles

### 3.1 Minimize and reduce

Each new entity type, handler op, validator, kind, or storage path is a piece of the conformance surface every implementation must reproduce. The narrower the extension, the cheaper to spec, implement, and validate cross-impl. ACME §14.1 took nine cross-impl rounds because EXTENSION-IDENTITY composes many ops at once; smaller-surface extensions converge in one or two rounds.

When designing:

- **Cut anything not load-bearing.** "Nice to have" fields and ops belong in v.next, not v1.
- **Reuse existing primitives.** If you need K-of-N signatures, use EXTENSION-QUORUM. If you need signed claims, use EXTENSION-ATTESTATION. Don't reinvent.
- **Inline what's small.** A helper that's called from one place stays internal; don't promote to an "extension point" until a second consumer concretely needs it.
- **Defer until needed.** v2.x roadmap items are how you keep v2 small without losing the future.

### 3.2 Keep extensions isolated

An extension should be installable on its own. If extension B depends on extension A, that dependency must be declared explicitly (in the spec's "depends on" header and in §1 overview prose) and the dependency must be a real, named one — not a soft "you'll probably want X too" expectation.

The substrate split (EXTENSION-ATTESTATION + EXTENSION-QUORUM extracted from EXTENSION-IDENTITY in v3.2) is the canonical case. Substrates are kind-agnostic primitives; identity composes them. Future consumers (cluster, transaction, governance, VC, reputation, audit, provenance) consume the same substrates without inheriting identity-specific assumptions.

If your extension can't function without another extension's specific behavior baked in, either:
- The "other extension" is part of yours (merge them), or
- The dependency is real and should be declared up front.

### 3.3 Be explicit about dependencies

Every extension spec MUST state at the top:

- **Depends on:** named extensions and their minimum versions, plus V7 minimum version.
- **Used by:** known consumer extensions (informative; may be empty for new extensions).
- **Owned namespaces:** every `system/<ext>/...` subtree the extension claims. Closed-namespace ownership (per EXTENSION-ATTESTATION §7 / EXTENSION-QUORUM §3.4) means no other extension binds inside.
- **Owned `properties.kind` values:** every `kind` the extension owns in the kind-ownership table per EXTENSION-ATTESTATION §3.2.
- **Owned handler ops:** every `system/<ext>:<op>` the extension defines.
- **Extension points exposed:** any registration hook other extensions can plug into.
- **Extension points consumed:** any registration hook the extension plugs into when installed.

This is the dependency contract. An impl team scanning the spec should be able to answer "what does installing this extension touch" from the header alone.

### 3.4 All extensions composable; any installable

Per the architectural commitment: any extension whose declared dependencies are met can be installed on a peer. There's no "you must install all the standard extensions" floor beyond V7 itself. Single-extension deployments are valid configurations.

This means:

- **No silent assumptions about what else is installed.** If your extension's behavior changes when EXTENSION-X is also present, the conditional behavior must be specified — typically as an extension-point use (your extension registers a hook against EXTENSION-X, gracefully no-ops if X isn't installed) or as a documented mode flag.
- **No cross-extension validators.** Each extension's validators run against entities the extension owns. If you need to validate something that touches another extension's entities, do it through that extension's published validators (e.g., `ATTESTATION.is_attestation_live`), not by reaching into its internals.
- **Graceful absence.** If a soft-dependency extension isn't installed, your extension SHOULD continue to work in a reduced mode rather than refuse to start. Hard dependencies are declared per §3.3 and DO refuse — but that's the contract, not a surprise.

### 3.5 Paths are convention; the entity graph is coherence

When an extension introduces a collection of related entities — types referenced by `extends` / `type_ref` / `array_of`, descriptors-per-blob, signatures-per-target, attestations-per-subject, capabilities-per-principal — the tree path under which any individual entity is bound is a **storage convention**, not the entity's identity. The entity's identity is its content hash. The coherence of the collection lives in **the entity graph** formed by inter-entity references, not in the path layout.

This shows up two ways in extension design.

**Resolution by name vs. resolution by graph traversal.** The default place to look up an entity by a name (e.g., a type by `name: "app/user"`, a config by name, a handler by URI) is the path-convention location (`system/type/app/user`, `system/handler/...`). That convention enables fast O(1) lookup and a stable discovery path. It does **not** mean the entity must live at that path, that there can be only one such entity, or that the name is the entity's identity. Implementations MAY support alternative resolution strategies (configurable base path, type-class iteration via EXTENSION-QUERY, reverse-hash-index walking) — all are normatively-described in extensions that care. **The graph integrity invariants are what conformance walks, not the path layout.**

**Discovery patterns are anchor-and-leaf-keyed paths, not catalogues.** When an extension needs to enumerate "all the descriptors for blob B" or "all the signatures over target T" or "all the attestations about subject S" across publishers, the recurring shape is an invariant-pointer path keyed by the **anchor** (B, T, S) on the publisher's side: `/{publisher_peer}/system/<ext>/{anchor_hex}` (single-level) or `/{publisher_peer}/system/<ext>/{anchor_hex}/{leaf_hex}` (dual-level, when multiple-per-anchor is expected). The path is a discovery scaffold; the **integrity invariant** is that the entity at the leaf carries a reference back to the anchor in its `data`, so a consumer that fetches by path MUST verify the anchor matches.

| Shape | Cardinality | Examples | Discovery from anchor |
|---|---|---|---|
| Single-level | one per (publisher, anchor) | V7 signature pattern (`/{signer}/system/signature/{target_hex}`) | Read the path |
| Dual-level | N per (publisher, anchor) | descriptor pattern (`/{publisher}/system/content/descriptor/{B_hex}/{D_hex}`) | List the `{anchor_hex}/` subtree |

The dual-level keying is a recipe, not a normative protocol obligation; reach for it when N-per-anchor is the cardinality, and require the body→path integrity check (MUST) at the consumer side.

**When to reach for the discipline.** Three signals:

1. You're tempted to introduce a registry / catalogue entity that lists "all X." (Usually wrong — let the anchor-keyed path BE the discovery; the registry adds a second source of truth.)
2. You're tempted to make the path the entity's identity (e.g., "the type at `system/type/app/user` IS `app/user`"). (Wrong — the content hash is the identity; the path is the storage location.)
3. You're tempted to forbid alternate paths or alternate resolution strategies. (Wrong — pin the integrity invariants and the default strategy; let deployments choose other strategies that satisfy the invariants.)

**Worked examples in the corpus:**

- **EXTENSION-CONTENT v3.5 `system/content/descriptor`** — dual-level anchor-and-leaf path keyed by blob hash; consumer-side integrity check (descriptor body `content` field equals `B_hex` from path, MUST); multiple publishers each publish their own subtree.
- **EXTENSION-TYPE v1.1 type graph** — path `system/type/{name}` is the default-strategy convention; type identity is the content hash; resolution strategies are plural; coherence walked on the graph (`extends` / `type_ref` / `array_of` / `map_of` / `constraints`).

If you find yourself building a third instance — recheck whether the pattern fits cleanly. Two instances landed independently is the discipline-locking signal; three is the call to upgrade this section to a fuller worked-pattern reference.

### 3.6 Declare your GC posture

Every extension introduces entities, and every extension's entities interact with the local-storage live-set. Without an explicit declaration, the implementer has to reverse-engineer the GC contract from prose — which is the bug class `GUIDE-GC.md` exists to prevent.

**MUST** include a `Lifecycle and retention` section (recommended near the end of the spec, or inlined into the overview if the extension is small) that answers the eight questions in `GUIDE-GC.md §9`:

1. What entity types does this extension introduce, and where do they bind?
2. Which are roots; which are reachable only via refs?
3. What retention semantics does this extension declare? (Name each knob + default + operational considerations; expose knobs, don't pick values.)
4. Cross-peer obligations — what gets referenced cross-peer; is per-extension grace needed?
5. Cross-extension composition — what other extensions' entities does this reference; what references this?
6. Functional state vs historical metadata — classify each entity type.
7. What can be lost on cleanup; what cannot; what MUST coordinate before lose.
8. Conformance impact — does GC declaration introduce any cross-impl observable behavior?

The point is for an implementer reading the spec to understand the GC contract without deriving it. Specs that don't answer these questions will be flagged in cross-impl review.

**Retroactive sweep open.** No existing extension spec yet has this declaration consolidated. Existing extensions usually declare retention semantics in scattered prose; the sweep collects them into one section per spec. Sweep is not corridor-blocking; new extensions land with the declaration during authoring.

### 3.7 Disambiguate HTTP-as-transport from HTTP-as-foreign-substrate

When an extension touches HTTP, identify which of two structurally-different mechanisms applies. They coexist; conflating them produces phantom spec gaps and false convergence findings.

**Mechanism A — HTTP as storage transport.** Bytes-on-wire ARE entity-encoded bytes; consumer reads, hashes, verifies, decodes as entities. HTTP is transport for opaque verified bytes. Lives in `EXTENSION-NETWORK.md` §6.5 (transport profiles). Examples: static-CDN content fetch (`STORAGE-SUBSTITUTE-HTTP`), workbench-go's `entity-fetch`.

**Mechanism B — HTTP as foreign substrate.** HTTP requests yield foreign content (HTML, API JSON, arbitrary text/*); bridge wraps the response as a `system/bridge/http/fetched` entity for ingestion. Lives in `EXTENSION-BRIDGE-HTTP.md`. Examples: HTML caching, API consumption, fetching arbitrary web documents into the tree.

**Disambiguation discipline.** Before authoring an extension that fetches over HTTP, ask: are the bytes-on-wire ALREADY entity-encoded, or are they foreign content needing wrapping? The first lives in NETWORK; the second in BRIDGE-HTTP. They are not the same mechanism scoped differently; they are two mechanisms sharing a substrate (HTTP). The line may blur in some future full-entity-native-compute setting; until then, distinct mechanisms, distinct extensions.

**Provenance:** identified during CDN corridor-close cross-chain synthesis. Two independent analytical chains initially mis-conflated; user pushback forced the disambiguation. Convergent independent observation is evidence, but two chains can independently miscategorize — run the "same mechanism or two mechanisms sharing a substrate?" question before concluding merge.

### 3.8 Where per-revision metadata goes (commit messages, author, time)

Tree content, per application convention — NOT a new entity type or system path. `EXTENSION-REVISION.md §2.1` ("Metadata is tree content") binds this: store metadata entities at your app's conventional path inside the trie (e.g., `myproject/_commit/{commit_id}`), referenced by the version's trie root. The version DAG commits to them cryptographically via `version.root`. See EXTENSION-REVISION §10.1 for the Git-bridge worked example. **Do not author a companion entity type for this** — it would be a parallel mechanism alongside the one §2.1 already mandates.

---

## 4. Conventions every extension follows

These are normative; impl teams will test against them. They emerged from cross-impl iteration; following them up front saves rounds later.

### 4.1 Path-as-resource (V7 §3.2 MUST)

Every directly-callable handler op operates on a resource path that targets the tree binding location. The op's params carry the operation-specific fields; the op's resource targets the path. Calling a `:create` / `:supersede` / `:revoke` style op without a resource MUST return **`400 path_required`**.

**This section is the authority for that status.** `path_required` is a *more-specific 400* under `ENTITY-CORE-PROTOCOL.md`'s 400 row, which sanctions them by name alongside `invalid_params` and `unexpected_params`. It is **not** a forbidden synonym for `invalid_request`: a synonym is a differently-spelled generic, whereas `path_required` names a specific remediable defect, and the code selects the remedy — *supply a resource* is a different instruction from *fix your request*. Extension specifications restating this rule cite this section rather than re-pinning the status.

This applies uniformly across kernel ops, substrate ops, and consumer-extension ops. Don't invent op surfaces that work without a resource — they break the dispatcher's authorization machinery.

### 4.2 Op-naming discipline

In all spec text, refer to ops by their full handler path: `system/<ext>:<op>`. Don't use colloquial shortenings ("`:supersede_attestation`") in normative prose — the bare name is ambiguous when multiple extensions have ops with the same colloquial name (substrate's `system/attestation:supersede` vs identity's `system/identity:supersede_attestation`).

The R-8' confusion in the ACME convergence was a naming-discipline failure. Avoid it from the start.

In cross-impl test fixtures, the same discipline applies — tests reference ops by full path so test failures can't be misattributed.

### 4.3 Closed-namespace ownership

When an extension chooses paths under its own `system/<ext>/...` subtree, that subtree is OWNED by the extension. No other extension binds paths inside.

Extensions that need to track state derived from another extension's entity (e.g., EXTENSION-HISTORY tracking transitions for a quorum) MUST use their own top-level namespace (`system/history/...`), NOT nest inside the source extension's subtree (`system/quorum/{q}/transitions/...` is wrong; `system/history/transition/{q}/...` is right).

Per EXTENSION-ATTESTATION §7 / EXTENSION-QUORUM §3.4 normative.

### 4.4 Kind-namespacing for cross-extension visibility

`properties.kind` values registered in the kind-ownership table (EXTENSION-ATTESTATION §3.2) MUST use a namespace prefix matching the owning extension domain (`identity-cert`, `quorum-update`, etc.). The single exception is `revocation` — the universal substrate kind.

Within-extension internal kinds (not in the ownership table; not visible to other extensions or generic tooling) MAY be unnamespaced.

Reason: cross-extension tooling (graph explorers, dashboards, audits) dispatches on `properties.kind`. Unnamespaced kinds collide as the system grows.

### 4.5 Type registration per V7 §3.7

Every directly-callable handler op MUST register `input_type` and `output_type` per V7 §3.7's convention: `system/<handler-path>/<op>-request` and `system/<handler-path>/<op>-result`. Type definitions install at `system/type/<type-name>` during handler installation.

Type definitions themselves describe the request and result shapes — fields, presence rules, content invariants. Use EXTENSION-TYPE constraint syntax where possible (per `EXTENSION-TYPE.md` §3-§4).

### 4.6 Signature ingestion is dispatcher-level (V7 §6.5)

Don't define your own signature-ingestion surface. Signatures arriving in `envelope.included` are bound at V7 invariant pointer paths by the dispatcher BEFORE handler dispatch. Your handler op looks up signatures via the standard `find_signature_by_signer` lookup (per `EXTENSION-ATTESTATION.md` §4.0) and finds them already bound.

This applies uniformly: kernel ops, substrate ops, identity ops, your ops. Skipping the convention means duplicating ingestion logic and breaking cross-extension composability.

### 4.7 Capabilities are not routed through your validator

Capability tokens validate via V7 §5.5 chain verification. Your extension's validators NEVER call `verify_capability_chain`, and `verify_capability_chain` NEVER opens an entity from your extension. The three-parallel-mechanisms invariant (V7 caps + `system/attestation` + `system/quorum` per EXTENSION-ATTESTATION §10) is structural; your extension preserves it by not crossing the line.

### 4.8 Capability verdict determinism (Layer 1 vs Layer 2) — V7 §5.10

If your extension wants to interact with capability verification at all — install a hook, add a check, gate a dispatch — you face a fundamental design question:

**Are you modifying the cap-chain verdict (Layer 1), or are you applying an additional gate over a valid verdict (Layer 2)?**

The two cases are not interchangeable. V7 §5.10 pins the architectural rule: Layer 1 must be cross-peer-deterministic; Layer 2 is free to diverge. Extensions MAY install Layer 2 post-gates; extensions MUST NOT introduce a Layer 1 leak.

**Quick decision checklist.** Ask three questions about any hook or check you're considering:

1. **Does the hook consult any state that isn't observable by every conformant peer?**
   → If yes (local-only state — local identity-cert bindings, local banlists, deployment config): **Layer 2.** It MUST live structurally after the Layer 1 verdict.
   → If no (cap-layer state, signatures, attestations visible to all peers): may be Layer 1 — go to question 2.

2. **Does the hook modulate the verdict on a cross-peer-relevant chain (cross-peer dispatch, delegated tokens, collected authority chains, mirror notifications), or only on a strictly-local chain?**
   → If cross-peer-relevant: the verdict MUST match what a peer without your hook would produce. Re-check question 1 — if any local state leaks, you are violating §5.10.
   → If strictly local: safer to express as Layer 2; review carefully.

3. **Could a peer that doesn't install your extension reach a different verdict on the same chain?**
   → If yes: you have a Layer 1 leak. Move the check to Layer 2.

**Worked examples.**

- **`IdentityBindingChecker` (EXTENSION-IDENTITY §12.3) — Layer 2.** Consults local identity-cert binding state (a local-only signal). Implemented as a post-gate that fires *after* the Layer 1 verdict has passed. Scoped to local-identity grantees only; MUST NOT be applied to cross-peer dispatch-cap grantees (v3.8) and MUST NOT modulate any cross-peer-relevant chain verdict (v3.9).

  *Worked failure case — why the scope rule exists.* Consider the chain `X → agent(local to X) → Y`, where `agent` is a sub-controller local to X but appears in a chain that Y also verifies (e.g. cross-peer dispatch where Y is the receiver). If X widened its binding check to walk intermediate grantees: X consults its local identity tree, finds `agent`'s binding revoked, and rejects the chain. Y has no local binding state for `agent` (it is just a peer X delegated through), so Y has nothing to check, and Y accepts. **Same signed chain, two different verdicts — Layer 1 divergence, convergence-breaking.** The fix is the §5.10 rule: cross-peer-relevant chain verdicts come from Layer 1 alone (cap-layer state visible to all peers). If `agent`'s authority must be revoked cross-peer, the mechanism is a cap-layer revocation entry (visible to X and Y), not a local binding state (visible only to X). The local binding check stays a Layer 2 signal for purely-local caps.

- **A hypothetical content-policy filter** — "don't honor caps that authorize ops on certain content categories." Consults the local peer's policy config. **Layer 2.** Post-gate over a valid chain; doesn't touch the chain verdict.

- **A hypothetical "is this signature from a post-quantum-resistant key" check** — consults only the cap chain itself (the signature algorithm is in the cap). **Layer 1.** May modulate the chain verdict; must be cross-peer-deterministic; all peers must agree on the rule (so this is a core-level decision, not an extension hook).

- **A hypothetical group-membership check** ("grantee must be in group G") — depends on whether group membership is determined by attestations visible to all peers (Layer 1, deterministic — the membership-verification algorithm is itself part of the cap-layer contract) or by local-only group config (Layer 2). If Layer 1, the extension must spec the verification algorithm uniformly; if Layer 2, the gate runs after the chain verdict.

**Implementation pattern.** Expose Layer 1 verification as a distinct entry point with no extension state in its closure. Layer 2 post-gates compose around it. This makes Layer 1 determinism auditable by inspection of one function — and prevents accidentally widening a Layer 2 hook into Layer 1 in a future refactor. The Go reference impl's split (`core/capability/delegation.go:VerifyChain` for Layer 1; `core/protocol/auth.go:VerifyRequestWithBinding` for Layer 1 + post-gate) is the recommended shape.

The cost of getting this wrong is concrete: convergent-mirror recipes diverge across peers, cross-peer dispatch chains reject inconsistently, the meaning of "rejected" stops being debuggable. The v3.8 / v3.9 history in `EXTENSION-IDENTITY §12.3` (and the convergent-mirror cross-impl matrix that surfaced it) is the worked failure case if you want a longer read.

### 4.9 Handler registration paths vs spec-advertised patterns

Per `ENTITY-CORE-PROTOCOL.md` §6.6 the dispatcher resolves a handler by walking backward through path segments looking for a bound `system/handler` entity. The path at which the handler entity is bound is the **dispatch prefix**; any path under that prefix dispatches to that handler (longest-prefix match wins). The dispatcher does NOT interpret glob notation — `*` is not a path segment that occurs in any canonical dispatch path.

This produces a recurring authoring pitfall when an extension wants a "catch the whole subtree" handler. A naïve reading of the handler manifest pattern field — e.g., `pattern: "system/type/constraint/*"` — invites the misreading "register the handler entity at `system/type/constraint/*`," which the dispatcher then never finds (because the literal `*` never appears in a canonical path). The dispatch falls through to whatever shorter prefix has a handler bound, and the wrong handler answers.

**The convention** (universal across the codebase; pinned here normatively):

- The handler entity **MUST** be bound at the **literal prefix path** (e.g., `system/type/constraint`, without trailing `/*`).
- The manifest entity **MUST** be bound at `system/handler/{prefix}` (e.g., `system/handler/system/type/constraint`).
- The manifest's `pattern` field **MAY** include glob notation (e.g., `"system/type/constraint/*"`) for human-readable advertisement only. The dispatcher does not interpret this field; the dispatch contract is prefix containment per V7 §6.6.
- The handler at the prefix catches every path under it via the §6.6 longest-prefix walk. Subprefixes with their own bound handlers override the parent.

**Examples in the corpus** (all follow the convention):

- `system/clock` — registered at the bare prefix; catches `system/clock/...` paths.
- `system/query` — bare prefix; catches `system/query/...`.
- `system/tree` — bare prefix; catches `system/tree/...` (including all data under tree paths the `tree:get` / `tree:put` model addresses).
- `system/type` — bare prefix; catches the type-handler ops at the prefix (validate / compare / etc.).
- `system/type/constraint` — bare prefix; catches every standard constraint dispatch (per EXTENSION-TYPE §5.1). The manifest's `pattern` field reads `"system/type/constraint/*"` for advertisement; the registration path is the bare prefix.
- `system/content` — bare prefix; catches the system content handler ops + `system/content/{namespace}/...` namespace-scoped variants (per EXTENSION-CONTENT v3.5 §6.4). Same registration convention.

**Why this matters.** Extensions with "catch the whole subtree" handlers proliferate as the system grows. Each one that reaches for `pattern: "system/<ext>/*"` invites the same misreading on first-pass impl unless the convention is normatively pinned. The convention is independent of any specific extension and applies to every handler that wants subtree coverage.

Surfaced as a recurring cross-impl trip-up by `EXTENSION-TYPE` v1.1's Phase 1 closeout; Rust's first-round `constraint_handler_manifest` FAIL and Go's parallel "type handler greedily catches constraint dispatch" debugging hit the same V7 §6.6 vs. spec-glob mismatch independently. Pinned here so the next extension doesn't re-derive the same fix.

### 4.9a Path-segment encoding (peer IDs, content hashes, reserved characters)

Path segments under `system/<ext>/...` look like opaque strings, but the system has a normative encoding convention that every extension MUST follow. Get it right at design time; renames are cross-impl cycles you don't want.

**Three rules.**

**Rule 1 — Base58 PeerID has exactly one home.** A `peer_id` rendered in Base58 (per V7 §1.5 / §7.4) appears in exactly three surfaces:

| Surface | Form |
|---|---|
| Universal-root path segment `/{peer_id}/rest/...` | Base58 |
| `system/peer` entity's `peer_id` field (the human-shareable handle) | Base58 string |
| Wire-level peer-id strings on connection messages | Base58 |

Everywhere else — **every** `{peer_id}` segment inside `system/<ext>/...` paths, every template substitution, every body field that names a peer — uses **lowercase hex of `system/hash`** (format-code byte ‖ digest), **pinned to the ECFv1-SHA-256 floor** — 66 hex chars beginning `00`, *whatever the peers' home formats are*. This is a **derive-to-meet** value (`SPECIFICATION-FORMAT.md` §8.4.6): every peer must construct it for every other peer, and a home format is not discoverable from a peer-id. This is consistent with V7 §3.5 invariant-pointer paths (`{content_hash_hex}`), EXTENSION-ROLE v1.6 §1.5.1 (`{peer_id_hex}` for assignment/exclusion/derived-tokens/role-derived-cap), EXTENSION-IDENTITY v3.3 (`{contact_id_hex}`, `{cert_hash_hex}`), and EXTENSION-QUORUM v1.1 (`{quorum_id_hex}`, `{event_hash_hex}`).

Why: Base58 PeerID is the human-exchange surface (operators paste it; SDKs marshal it onto the wire). Inside the system, the peer is a content reference like any other entity hash — hex aligns with content-hash conventions and lets generic tooling (entity browsers, tree walkers, conformance harnesses) interpret every non-root path segment uniformly. EXTENSION-ROLE v1.5 drifted into using Base58 for non-root segments; v1.6 reverted explicitly. Don't re-derive that drift.

Validate at proposal time: grep your spec for `{peer_id}` outside the three Base58 surfaces above. If you find any, rename to `{peer_id_hex}` and pin "lowercase hex of `system/hash`" in the path-segment normative paragraph.

**Rule 2 — Reserved characters never appear as literal path segments.** The following are reserved for system-level glob and relative-resolution semantics:

| Token | Meaning | Reserved by |
|---|---|---|
| `*` | The glob wildcard. `pattern/*` is a **subtree prefix match** that crosses `/`; bare `*` matches all; `/*/` is the peer-id strip — the only segment-scoped form in the protocol | V7 §5.4 `matches_pattern`, §6.6 dispatch |
| `./`, `../` | Directory-relative segments — rejected at canonicalization | V7 §5.4 `canonicalize` |

> **`**` is NOT a reserved token and NOT part of the protocol.** An earlier version of this table listed it
> as *"Globstar (future use)"*, attributed to "V7 §1.4 / Document History v7.18". **Neither exists:** §1.4
> contains no reserved-token table, and neither `v7.18` nor the word *globstar* appears anywhere in the core
> spec. The row was unsourced, and because its two neighbours are real it read as authoritative for months —
> which is how `**` spread into six specs and two guides that had no need of it. **Removed; those uses are
> now the §5.4 subtree form.**
>
> The **one** legitimate `**` in the corpus is `EXTENSION-REVISION`'s `exclude` / `exclude_types` fields,
> where an ignore-list over a versioned prefix genuinely wants filename-at-depth matching. **That is a
> domain-specific matcher for a domain-specific application, scoped to those two fields, and it confers no
> reading on `*` anywhere else.** Do not generalize from it. If a second use case ever proves the need, `**`
> gets adopted deliberately — it has not been.

These tokens **MUST NOT** appear as literal path segments under your extension's namespace. If you want a "default" or "fallback" entry, use a literal word (`default`, `any`, `fallback`, etc.). If you want "match everything," that's a glob in the manifest's `pattern` field — not a stored entry. Common authoring pitfall: using `*` as a literal segment to mean "the default entry when no exact match exists" looks innocuous in prose but collides with `*`'s glob role everywhere else (`system/role/{context}/*` reads as "every entry under role's context" everywhere else in the system).

Surfaced as a v7.62 capability-handler bug: the amendment introduced `system/capability/policy/*` as a literal fallback segment, which was the only place in V7 where `*` appeared with non-glob semantics. The closeout cycle renamed it to `default`. Don't re-introduce this overload.

**Rule 3 — Glyph-overload audit.** Before adding any new sigil, reserved word, or literal segment to a path scheme, grep V7 + the extension corpus for the glyph's existing semantics. If your proposed use introduces a NEW semantic for the same glyph (different from how it reads everywhere else), it's an overload — rename. Mechanical check (grep + classify each occurrence); the cost of skipping is a rename-cycle later.

### 4.10 Substrate resolution is a handler step, not a transform (L11 idiom)

Continuation transforms (`extract`, `select`, `*_extract`, `deref_included` per `EXTENSION-CONTINUATION.md`) are pure entity-projection operations. They do not dispatch operations, do not perform I/O, do not engage cap discipline. They are synchronous, pure-CBOR, and operate over the chain's in-flight entity by projecting fields.

A chain step that needs substrate state which is not yet locally available — e.g., a content closure whose chunks haven't been fetched, an entity whose blob hash references chunks that haven't arrived through subscription delivery, or any cross-handler substrate resolution — is **a handler step, not a transform**. This is the **L11 idiom** (named in workbench-go Round 1 feedback; promoted to normative convention in this section).

**The canonical pattern:** the chain dispatches a handler whose job is to ensure the substrate is locally complete. The next chain step then proceeds with the substrate available for purely-local transforms.

```
chain step N:    handler step (e.g., system/content:ensure-closure, or a domain handler
                 like local/files:write content-mode that internally calls EnsureClosure)
                 → returns when the closure is locally complete

chain step N+1:  pure transform — extract fields, project entity, run logic over the
                 now-local closure (no further substrate dispatch needed)
```

**Worked example: cross-peer file sync (workbench-go reference impl).** The chain `revision:fetch-diff → tree:merge → workbench/blob-resolve → [local/files:write fires on subscription]` uses `blob-resolve` as the L11 handler step: it receives the merged file entity and calls `content.EnsureClosure(handlerCtx, fileEntity.Content, "system/content")` against the source peer. The local-files reverse-write then fires once the closure is local. See `entity-workbench-go/workbench/blob_resolve.go` as the canonical implementation.

**Why not a transform op?** A "transform" that dispatches `system/content:get`, does cap-check, handles 503 retry, manages frame-budget batching, and might return either bytes or a non-CBOR stream-handle is a fourth chain-element category wearing the transform-op hat — it's a program, not a projection. Keep transforms pure; put dispatch in handlers. This was the load-bearing pushback in the v1 → v2 cycle of the content-materialization proposal (Rust caught the V7 §6.8 v7.49 cap-flow collision; Python identified the bytes-as-protocol-surface mis-shape; user agreed *"transforms are local, immediate, funneling little pieces — they're not constructing a materialized thing that makes calls and bundles"*).

**Cap discipline of the L11 handler step.** The handler holds its own `internal_scope` grant per V7 §6.8 handler-grant model. Its manifest declares what handler ops + namespaces it needs (typically `system/content:get` on whichever namespaces the use case covers). The chain's propagated cap is verified against handler grants at the *outer* dispatch (chain step N's invocation of the handler); the handler's own sub-dispatches inside its work (e.g., the loop inside `EnsureClosure`) use the handler's grant. V7 §6.8 v7.49 propagated-cap-not-a-gate is honored at every layer — no implicit cap inheritance from the chain to the handler's sub-dispatches.

**No new mechanism.** Handler steps and `internal_scope` grants are existing primitives. L11 names the pattern for substrate-resolution use cases; the runtime needs zero new machinery to support it.

### 4.11 Byte-bearing domain handlers — response convention

Domain handlers whose entities reference byte content (file bytes, image data, dataset bytes, etc.) **SHOULD** follow this response shape so consumers can treat substrate-closure-resolution uniformly:

1. **The entity always carries `content: hash`** referencing the substrate blob (CONTENT §2.1 `system/content/blob`).
2. **Inline-include the closure** (blob + chunks) in the response envelope **when reassembled size ≤ `MIN_CHUNK_SIZE`** (currently 64 KiB per CONTENT v3.6 §4.3 small-content inline-include MUST; reference the named constant rather than the literal so future threshold moves don't drift the convention). Consumers find the closure-complete in `envelope.included` and call their language's local `reassemble_content` helper to obtain bytes — no follow-up dispatch needed.
3. **For larger content, the response carries only the hash;** consumers use `content.EnsureClosure` (SDK-EXTENSION-OPERATIONS content extension §X.1) to drive cap-checked `system/content:get` until the closure is local. After `EnsureClosure` returns, consumers extract bytes via their language's local `reassemble_content` helper (eager) or `stream_reassemble`-style helper (lazy / streaming).
4. **Handlers SHOULD NOT pre-materialize large blobs in their response** — let the consumer drive closure-completion as needed. This preserves wire-level dedup and memory-bounded consumer-side processing.

**The right mental model:** *protocol surface speaks closures; consumers reassemble locally.* The chunking is hidden at the SDK + language-library layer; handlers don't need to do size-specific dispatch beyond the inline-include MUST.

**Worked examples:**

- `local/files:read` (DOMAIN-LOCAL-FILES v1.3) — already follows this pattern (v3.6 §4.3 inline-include for ≤`MIN_CHUNK_SIZE`; larger files: consumer calls `EnsureClosure` then reassembles locally).
- Future media handler — same pattern: media entity carries `content: hash`, inline-include when ≤`MIN_CHUNK_SIZE` (e.g., small icons), consumer uses `EnsureClosure` + per-language streaming reassembly for media files.
- Dataset handler — same pattern: dataset entity carries `content: hash`, large datasets use `EnsureClosure` + memory-bounded chunk-by-chunk processing via per-language streaming helper.

Per the content-materialization proposal's Amendment C (closure-language sharpening per Python's reframe).

### 4.X — Error codes: status is centralized, codes are domain-scoped (v7.71)

When you define a handler operation that can fail, you will write two surfaces: a `status` number (the universal HTTP-style category) and a `result.data.code` string (the specific failure within that category). They have **opposite** correct homes, and writing them in the wrong place is the most common drift trap.

**Status is centralized.** Every numeric `status` value lives in V7 §3.3's single-source table. If your handler needs a status that's already in the table, point at it; do not redefine. If your handler discovers a genuinely new category, propose a §3.3 row (uncommon — the table is already deliberately small). Status semantics are closed: clients branch on them and every conformant peer must agree.

**Codes are domain-scoped.** Your handler's `code` strings live in your extension's own error section — never in a cross-cutting registry. A code like `invalid_strategy`, `missing_chunk`, `invalid_role_name`, `not_found_in_index` is your handler's vocabulary; another handler may legitimately use a different word for an analogous condition, and that is correct. Adding every handler's codes to a central registry is the parallel-edit drift trap — extensions then have to keep a cross-cutting list in sync, and they don't, and codes drift apart by accident. V7 §894 enshrines this distribution deliberately.

**The promotion rule (when a code DOES belong in a central matrix).** A code is promoted to a **MUST-emit conformance vector** — the §4.7 connection-code or §3.3 authorization-code treatment — only when it is part of the **cross-impl behavioral contract**: a closed set, identical across every conformant peer, that a client branches on. The test:

> If two conformant impls could legitimately use different strings for the same condition, it is **vocabulary** — leave it in your domain home, no vector. If they MUST agree or a client breaks, it is **contract** — pin it with a vector in GUIDE-CONFORMANCE.

Connection codes (§4.7) and authorization codes (§3.3-403 / §5.2 AUTHZ-* matrix per v7.71) are contract — they get vectors. The long tail of handler codes (tree, revision, role internals, compute, continuation, …) is vocabulary — it does not. When in doubt, leave it home; promotion is one-way and costly.

**The catch-all anti-pattern.** Never surface a generic catch-all default like `verification_failed` or `error` when your domain has a defined code for the actual failure. The catch-all is a signal that the failure escaped its named code — fix the routing, not the symptom. The v7.71 §3.3 authorization-path MUST is the normative form of this rule for the authorization domain; the same discipline applies in every domain.

### 4.X Pattern menu — recommended shapes, NOT authority (v7.72)

The Keystone-generated C# core peer (the first language-binding generator output; `entity-core-keystone/protocol-generator/csharp/`) surfaced six recurring patterns that worked well and are worth carrying forward for future peers + extension authors. Each is **recommended with stated trade-offs** — peers in different language idioms MAY deviate; this is design-space, not authority. The spec arbitrates correctness; the patterns arbitrate ergonomics.

| Pattern | Recommended for | Trade-off / alternative |
|---|---|---|
| **Render-from-model type registry** — declare types in code via a reflection-style `FieldSpec` builder + an override table for semantic `type_ref` pins; render at startup through the byte-green codec. Single source of truth in code, NOT ingest-from-bytes. | Languages with reflection / metaprogramming idioms (C#, Rust, Go); peers that publish their own types as part of normal operation. | Alternative: **ingest-from-bytes** — load the canonical type-registry vectors at startup, parse, register. Pro: language-independent reproducibility; trivial cross-language bootstrap (Python's `definitions.py` is closer to this). Pick by language idiom. |
| **Dump→author→diff loop** — for any "match the reference shape" task (types, manifests, vectors, fixtures): render the reference impl's output to a readable form (`.diag`), author natively in your language from that form, diff byte-exact against the reference output. | Bootstrapping cross-impl byte-equality on opaque encoders / registries. Worked exemplar: C# peer 53/53 byte-exact first-run via `protocol-generator/shared/tools/dump-type-registry`. | Alternative: hand-guess byte shapes from the spec prose. Slower; opaque error modes. The dump tool is throwaway; payoff is per-shape. |
| **Publish-the-contract-in-the-tree + tree-walk routing** — register the N5 interface pair (`system/handler/interface` published contract at `system/handler/{pattern}` + `system/handler` dispatch target at `{pattern}`). Route by §6.6 tree-walk (`Resolve` walks backward for the longest `system/handler`-typed prefix). The in-memory `pattern→handler` map is an *optimization over the tree*, not the source of truth. | Every conformant peer's handler dispatch (V7 §6.6 requires equivalent results; the tree IS the source per §6.6 "Scope of the contract"). | Alternative: in-memory-only registry. Non-conformant — bypasses entity-native handlers (`expression_path`, §3.7) which exist only as tree entities. |
| **Canonical-value-model codec + omit-empty map builder** — a language-native `EcfValue` value tree mirroring the Go/Rust/C reference model; the canonical encoder does CTAP2 key ordering + Rule-4 float minimization; the map builder (e.g., `Ecf.Map((k, v?)...)`) drops nulls per the §1.3 absent-field convention. | All codec implementations — this is the foundation everything else renders through. | None — this IS the codec contract per ENTITY-CBOR-ENCODING. The pattern is "language-native value model + canonical map builder," not a specific shape. |
| **Registry-seam crypto agility** — `HashFormats` / `KeyTypes` registry tables; adding a new algorithm family is a registry entry. Multiple crypto libraries can sit behind the seam (C# peer: Ed25519 via NSec/libsodium + Ed448 via BouncyCastle). The peer is identity-aware via `PeerIdentity.KeyTypeName`. | Multi-algorithm peers (v7.66+/v7.67+). | None for v7.66+ — required to support the seed-table agility surface. |
| **§5.2 authorization status-code precedence** — implement the authorization domain's status-vs-code matrix exactly as v7.71 pins (PR-3 `unresolvable_grantee`/401 pre-chain; `capability_denied`/403 default; `scope_exceeds_authority`/403 for §6.2 over-ask; expiry/granter-unresolvable/revoked → 403 default; NO catch-all `verification_failed`). `is_revoked` as a dispatcher chain-walk against tree-bound revocation markers. | Every conformant peer (v7.71 §3.3 normative MUST). | None — the matrix is normative. The pattern is the recommended *implementation shape* (chain-walk against tree markers; attenuation-on-issue reuses delegation subset rule). |

**`key_type` at the earliest handshake boundary** (related discipline). When a hello arrives, decode the `peer_id`'s `key_type` prefix and reject unsupported families with `unsupported_key_type` (V7 §4.7) **BEFORE** protocol-version or hash-format negotiation. Reason: the C# peer initially returned `incompatible_protocol` for unknown `key_type` because it checked the protocol version first — a real cross-impl divergence the v7.66 §4.4 surface-6 contract pins as key-type-first. If your handshake order differs, document it as a finding; don't default to protocol-first.

**Spec-first, not oracle-matching** (overarching discipline). Reading the validate-peer oracle's Go source to *learn what is exercised* is tolerated for the first 1–2 peers built from a generator pipeline (you're learning the contract). Beyond that, the behavior MUST come from V7, and a spec-vs-oracle divergence is a finding (route to architecture for ruling), NOT something to mimic. The oracle is the test surface; the spec is the contract. (The Keystone-thesis pin: the spec is load-bearing; the oracle interprets the spec, validates that impls align with the spec, and tells the impl where it fell — the spec stays the source.)

---

## 5. Extension points

An extension point is a registration hook one extension exposes for other extensions to register handlers/resolvers against.

Examples in the system today:

- **EXTENSION-QUORUM `register_resolver`** (§5.2) — signer-resolution mode handlers. EXTENSION-IDENTITY registers `identity-resolved` mode at install time.
- **EXTENSION-ATTESTATION `walk_attesting_chain` parameters** — `terminate_predicate` and `find_authorizing_fn` are consumer-supplied for non-default chain shapes.
- **EXTENSION-ATTESTATION `consumer_revoker_has_authority` predicate pattern** (§4.4) — consumers layer their own authority-revocation rules on top of the substrate's self-revocation.

When you design an extension point:

- **Pin multi-registration semantics.** Calling registration twice for the same key MUST return an error (`*_already_registered`) unless the registration is idempotent for the same handler. Don't silently replace.
- **Bound recursion.** If the extension point can recurse (resolver chains, predicate compositions), specify a maximum depth and a cycle-detection rule. EXTENSION-QUORUM §5.2 sets `max_resolver_depth = 8`.
- **Fail closed on unknown.** If a consumer references a mode/predicate that no extension has registered, fail closed with a specific error. EXTENSION-QUORUM §5.3.1 enumerates the four observable cases (mode-known + resolver-registered / mode-known + resolver-registers-later / mode-known + resolver-never-registered / mode-unknown).
- **Defer until a second consumer needs it.** If only one extension would register against the hook, the hook is premature abstraction. Inline the behavior in the owning extension; promote when a second consumer surfaces.

---

## 6. Drift signals — patterns that mean "reconsider this extension"

These are the recurring shapes in extension proposals that turn out to be design errors. Each is a diagnostic, not a hard rule — when you see one in your own proposal, stop and rethink.

### 6.1 Foreign-concept fields

The extension's spec adds a field that names another extension's concept. e.g., a `quorum_id` field on a non-quorum entity, or a `controller` field on a non-identity entity. Usually means the dependency relationship is upside down or the extension is doing two extensions' jobs.

Fix: invert the dependency, or split the extension.

### 6.2 Parallel imperative paths

The extension defines two handler ops that do almost the same thing for two cases. e.g., `:configure_internal` and `:configure_external` on the same entity. Usually means there's a missing parameter or mode flag that subsumes both.

Fix: unify under one op with a discriminating parameter.

### 6.3 Producer-authority patterns

The extension lets the entity producer self-authorize subsequent operations on the entity ("I created it, I can revoke it"). Usually conflicts with V7's capability model — authority should flow through caps, not through producer identity.

Fix: route through caps. The producer holds a cap (typically a self-cap at install time); subsequent ops verify the cap.

### 6.4 Amplification composition

The extension provides a primitive that a consumer extension uses to bypass V7's authority rules. e.g., a "trusted-issuer" registration that lets caps validate without the standard chain. Usually means the extension is providing a back door.

Fix: don't. If the use case is real, propose a V7 amendment (e.g., multi-sig caps, K-of-N at root); don't smuggle it in via an extension.

### 6.5 Phantom primitives

The extension treats something as a primitive that's actually composable from existing primitives. e.g., a "delegation chain" entity type that's just a sequence of cap entities, or a "K-of-M signature" type that's a quorum + attestations.

Fix: compose with existing primitives. If the composition is hard to express, the friction is a useful signal — either the existing primitives need an amendment or the new concept genuinely needs its own primitive (rare).

---

## 7. Authoring process

Extensions move through stages from first draft to stable cross-impl. Each stage has named owners and outputs.

### Stage 0 — Spec draft (architecture team)

**Output:** initial `EXTENSION-<NAME>.md` containing:
- §1 overview + dependencies (per §3.3 above)
- §2-§N normative content: type definitions, handler ops with ordered-phase pseudocode (per §4 below), validators, storage conventions
- §-conformance: MUST / SHOULD / MAY items
- §-document-history with a single Draft entry

The architecture team writes the normative ordered-phase pseudocode for handler ops. Pseudocode is precise but kept readable — phases with named contracts, error codes, side effects, return shapes. Don't pre-write CBOR-level test vectors; those are an output of cross-impl convergence (per §8 below).

### Stage 1 — Reference impl in flight (impl team)

One implementation team builds the extension against the draft spec. Ambiguities surface as questions; the impl team files them as proposal items or feedback notes against the spec.

The architecture team responds with spec amendments. The amendment cycle continues until the impl is functionally complete.

### Stage 2 — Convergence (impl + arch teams)

Cross-impl validation begins. Other implementations build to the same spec. Divergences surface as findings; each finding is either a real spec gap (amendment needed) or a real impl bug (bug fix).

Per the ACME retrospective: most findings are algorithm-not-pinned (the spec said WHAT but not HOW); some are wire-shape; some are convention-only-in-source. Pin algorithms with ordered-phase pseudocode in spec text; produce TVs at the end of convergence as artifacts.

### Stage 3 — Convention-source audit (pre-promotion)

Before the extension promotes to Stable, run a one-time grep-and-cross-reference across reference impls:

1. Grep the reference impl(s) for all path / naming / signature literals (`Path()` constructors, kind/function/mode constant strings, error-code strings).
2. For each, check that the spec normatively pins it.
3. Items only in code → add to spec, OR remove the convention from the impl if it shouldn't have been there.

This is mechanical work, ~half a day per extension. R-13 / R-14 in ACME surfaced because no one ran this; running it pays for itself in convergence rounds saved.

### Stage 4 — Cross-impl tier validation

Extensions of any complexity run through tiered cross-impl validation. The number of tiers depends on extension complexity (per §8).

Each tier produces TVs that fold back into the spec at conformance lock. TVs are NOT architecture-team-authored inputs; they are byproducts of impls running against each other and the architecture team canonicalizing what surfaced.

### Stage 5 — Stable

The extension's spec text is normative; impls match; cross-impl test vectors are canonical. Spec amendments are version-bumps with explicit before/after.

The proposal that drove the extension moves from `proposals/` to `proposals/implemented/` once Stable is reached.

---

## 8. Validation budget per extension complexity

Use this as a planning tool, not a gate. Extensions that exceed their budget surface a real issue (spec too thin? extension too composite?) — not a problem with the budget.

| Extension size | Surface | Cross-impl tiers | Target rounds | Examples |
|---|---|---|---|---|
| **Small** | 1-3 ops, 1-2 owned types, no extension points | T1 wire-shape + T2 success-path | 2-3 rounds | EXTENSION-CLOCK, EXTENSION-CONTENT |
| **Medium** | 4-8 ops, 3-5 owned types, may expose 1 extension point | T0 + T1 + T2 | 3-5 rounds | EXTENSION-QUERY, EXTENSION-REVISION, EXTENSION-ATTESTATION |
| **Substrate** | 1-4 ops, primitive type, exposes extension points | T0 + T1 + T2 + careful audit | 3-5 rounds | EXTENSION-ATTESTATION, EXTENSION-QUORUM |
| **Composite** | Wraps multiple substrates with consumer rules; flow ops compose 6+ sub-ops | T0 + T1 + T2 + T3 ceremony | 6-9 rounds **EXCEPTIONAL** | EXTENSION-IDENTITY (ACME §14.1) |

**Composite-extension warning.** Composite extensions are the highest-cost class. If your design lands in this row, ask hard whether the composition can be split into smaller user-visible ops with explicit composition at the SDK layer, OR whether the named sub-step contracts (per §4 ordered-phase pseudocode) can pin the internal contract such that impls can't drift. ACME burned 9 rounds; we don't want that as steady-state.

If a composite extension is genuinely necessary (recovery + multi-device + cross-peer recognition for identity makes the composite real), accept the cost up-front and budget accordingly. Don't accidentally walk into a composite extension thinking it's medium.

---

## 9. Grading rubric

Each extension's spec carries an explicit conformance grade. Grades reflect what's been demonstrated, not what's intended.

| Grade | Criteria |
|---|---|
| **Draft** | Spec exists. No reference impl yet, OR reference impl is in flight and ambiguities are still surfacing. Cross-impl validation has not started. |
| **Validated** | Reference impl complete. Cross-impl validation has surfaced findings; spec amendments have absorbed them. At least one cross-impl run is green. |
| **Stable** | Multiple impls cross-impl-green. TVs distilled from convergence are in `VALIDATION-MATRIX-*.md`. Convention-source audit complete. Conformance MUSTs covered by TVs. |
| **Production-Ready** | Stable + deployed in at least one production-class scenario (per the validation surfaces in `PROPOSAL-IDENTITY-INFRASTRUCTURE.md` §8.1 or equivalent for non-identity extensions). Adversarial / edge-case validation complete. |

Each EXTENSION-*.md spec lists its current grade in the document header. Grade transitions are recorded in the document history with a brief justification.

The grade is informative for impl teams (so they know what they're committing to when they implement an extension) and for application developers (so they know which extensions are safe to depend on).

### 9.1 Production-Readiness Review

The Production-Ready grade above is reached through a structured review with five named surfaces. The review is **document-style, not validate-peer-style**: produce a `REVIEW-<EXTENSION>-PRODUCTION-READINESS-<DATE>.md` doc that walks each surface, reports findings by severity (HIGH / MEDIUM / LOW), and recommends either amendments-to-land or grade-transition. The output is one of (a) pass-with-grade-transition to Production-Ready, or (b) amendments-to-land plus a re-review.

The cross-impl conformance gate (the `validate-peer -category <ext>` surface, the per-extension §10.5-style cross-impl gates) measures **consistency across impls** — same input produces same output across the conforming set. It does not measure **deployment quality** — atomicity guarantees on power loss, declared-feature correctness, large-payload behavior, performance asymmetry under realistic load. An extension can pass conformance cleanly and still have hidden deployment hazards; this review is the structured pre-flight that surfaces them before the Production-Ready grade is granted.

**The five review surfaces:**

1. **Performance profile.** Measured throughput / latency at representative input sizes across all conforming impls. Surfaces (a) impl-asymmetry (one impl 10× slower than others at a given size signals a deployment hazard for that impl); (b) regression vs prior versions; (c) bottleneck identification (which layer dominates: chunking, IO, dispatch, serialization). The reviewer authors a benchmark probe; the probe lands in the impl reference repo as a reusable artifact so subsequent reviews compare against the same baseline.

2. **Reliability review.** OS-syscall-level correctness for impls that touch the filesystem, network, OS handles, or other external state. Examples: atomic-write recipes covering both file durability AND containing-directory durability (the parent-dir-fsync POSIX subtlety); lock-file conventions; clock-skew handling; partial-failure error paths; backpressure under bursty load. Documentation-only fixes are acceptable outputs — some properties (power-loss durability, kernel-level race windows) aren't testable without simulating the failure condition and must be addressed by inspection + reference-recipe correctness.

3. **Behavioral conformance.** Does declared capability actually work end-to-end? The validate-peer gate typically only verifies that a manifest operation exists; behavioral checks belong here. Example: an extension lists a `watch` op in its manifest. The conformance check verifies the op accepts the request shape and returns the result shape. The behavioral check writes a file directly to disk, starts a watch, waits, and asserts the tree contains the file entity. Surfaces "declared but doesn't function" patterns — operations that return success while doing nothing observable.

4. **Large-scale / boundary conditions.** Behavior at size limits (envelope max, chunk size boundaries, max file size), under high concurrency (concurrent writes to the same root, high-frequency event streams, deep tree hierarchies), and at exhaustion edges (disk full, content-store full, descriptor budget exceeded). Often surfaces silent-mode-failures (operation returns 200 but with degraded semantics) and undocumented capability ceilings — the kind where a first-pass user hits a hard limit with no spec breadcrumbs because the spec was authored on assumptions the impl quietly relaxes.

5. **Deployment quality.** Operational concerns: error-path coverage (do error paths produce diagnosable signals, or do exceptions get swallowed by bare `except` clauses?); observability (do operators have logs / metrics / tracing hooks for ops failures?); resource bounds (are channels / queues / memory allocations bounded, or can a bursty input exhaust the host?); graceful degradation when soft dependencies are absent; configuration-error reporting (does a malformed config produce a clear error or silently behave-as-default?). Items that don't fit the above four surfaces but matter for production trust.

6. **Security boundary.** Sandbox escape, capability-boundary integrity, TOCTOU windows, input sanitization at protocol boundaries, defense-in-depth. Extensions that touch external state — filesystem, network, OS handles — face an attack surface the conformance gate doesn't probe; security review walks it explicitly. The leaf-symlink TOCTOU surfaced in the DOMAIN-LOCAL-FILES v1.3 cycle (Rust C-1 + Python F-4 with cross-impl PoCs) is the canonical kind of finding: spec-silent vulnerability that multiple sibling reviewers independently surface and the conformance gate can't see. Worth pinning as a distinct surface so reviewers walk it explicitly rather than folding it into reliability or large-scale.

**Convergence signal across sibling reviewers (load-bearing).** When multiple sibling teams independently review the same extension within the same cycle — and the v1.3 cycle shows this is the natural rhythm — the **convergence pattern across reviews is the load-bearing signal**, not any single reviewer's finding in isolation. Three-of-three on atomic-write durability, two-of-three on stat-cache pattern, two-of-three on streaming, two-of-three on leaf-symlink TOCTOU: each multi-reviewer convergence is amendment material. One-of-three findings need careful evaluation — sometimes impl-specific (Python's pure-Python perf cliff is Python's concern), sometimes cross-cutting that one reviewer noticed first (Unicode normalization in the v1.3 cycle started as 1-of-3 and landed as interim SHOULD pending Stage 3 signal). Reviewers SHOULD compare findings across sibling reviews before recommending amendments; arch SHOULD weigh convergence count when prioritizing what lands.

**Convergence-angle-diversity discipline (MUST when topology / security / cross-trust-domain implications are in scope).** Convergence on the same finding across reviewers is signal only if the reviewers approached from independent angles. Three code-read reviews from impl teams reading their own code are *one angle multiplied*, not three angles converged. Multi-angle convergence — code-read + threat-model + performance + cross-platform — is the load-bearing signal; single-angle convergence is calibration-of-impl-fidelity-to-spec, which is valuable but different. The L10 substrate-primitive-promotion cycle, the L10 unified-feedback cycle, and the CONTENT v3.6 v1→v2 default-everything-topology cycle each cost an extra round because three code-read reviews were treated as three-angle concurrence; in each case an independent threat-model review later overturned the apparent consensus. When circulating a review request, arch SHOULD name the angle being asked for ("code-read concurrence on §X"; "threat-model concurrence on §Y") and, when the question has multi-angle implications (anything touching capability boundaries, default-permissions topology, cross-trust-domain access, or wire-shape contracts between mutually-distrusting parties), arch MUST request the angles separately. Failing to do so produces single-angle convergence that costs a round to correct.

**Pre-closure consumption discipline (MUST).** Closure of the Stable → Production-Ready grade transition requires arch confirms **all sibling reviews in flight have been consumed**. The premature-closure failure mode from the v1.3 cycle (arch closed on one impl's signal alone before reading the other two) forfeits the convergence signal the gate exists to produce. The discipline: arch keeps the production-readiness review in flight until all sibling teams have reviewed OR explicitly declined to review within a stated window. "Moved to `implemented/`" is not the closure signal; convergence across reviews is.

**When the review fires.** When an extension reaches Stable per §9 (multiple impls cross-impl-green; TVs distilled into the validation matrix; convention-source audit complete), the maintaining team requests a production-readiness review. The reviewer (typically an impl team that didn't author the extension, or arch) walks the five surfaces. Findings either resolve in-cycle (amendments + re-review) or block the grade transition.

**Authorship convention.** The review doc lives in the reviewing impl's `docs/reviews/` directory (e.g., `entity-core-go/docs/reviews/REVIEW-<EXT>-PRODUCTION-READINESS-<DATE>.md`), not in the architecture corpus — it is an empirical review of running impls, not a normative artifact. Arch absorbs the findings as spec amendments via the normal proposal cycle if they warrant spec changes; many will be impl-side deployment-quality items that don't touch normative text.

**Persistent artifacts per review surface (SHOULD).** Each of the six review surfaces SHOULD have a persistent artifact that re-runs on re-review and produces acceptance evidence. Without this discipline, "Production-Ready" decays to a one-time claim that nobody can re-verify. Concrete artifact shapes:

- **Performance profile:** a bench script in the impl repo (e.g., `entity-core-go/cmd/bench-localfiles/`) with documented acceptance criteria (throughput targets per size class, regression thresholds). Re-runs on re-review.
- **Reliability review:** regression tests for the failure modes the spec text addresses (atomic-write durability via fault-injection harness where testable; non-testable properties via inspection of the reference recipe + impl).
- **Behavioral conformance:** validate-peer checks in the impl's validation suite (e.g., `entity-core-go/cmd/internal/validate/local_files.go` V1/V2/V3 added in v1.3).
- **Large-scale / boundary conditions:** bench probes at boundary sizes (e.g., 16 MiB frame cliff, 64 MiB inline threshold, multi-GB streaming).
- **Deployment quality:** static analysis on bare `except` clauses, channel-bound audits, log-coverage review.
- **Security boundary:** regression tests for known vulnerabilities (e.g., `TestRead/WriteRejectsLeafSymlink` added Go-side in commit `ba21372` for L5).

The discipline: when an amendment lands, the artifact lands or updates alongside. When the production-readiness review re-runs, every artifact re-runs and produces a fresh result. This is what distinguishes "production-ready at a point in time" from "production-ready as an attested ongoing property."

**Grade-transition artifact form (the canonical output).** The Production-Ready grade transition produces three artifacts:

1. **Per-impl production-readiness review doc** at `<impl-repo>/docs/reviews/REVIEW-<EXT>-PRODUCTION-READINESS-<DATE>.md` for each sibling team that reviewed. Walks the six surfaces; reports findings; cites the persistent artifacts above.
2. **Arch-team summary doc** at `entity-system-architecture/.../reviews/PRODUCTION-READINESS-SUMMARY-<EXT>-<DATE>.md` consolidating the per-impl reviews, identifying the convergence pattern across them, and recording the disposition of every finding (amendment-landed, deferred to next cycle, impl-side only).
3. **Spec doc-history entry** recording the grade transition: "**202X-XX-XX (Grade transition Stable → Production-Ready).** Per `REVIEW-<EXT>-PRODUCTION-READINESS-<DATE>.md` from each of {Go, Rust, Python} + `PRODUCTION-READINESS-SUMMARY-<EXT>-<DATE>.md`. Persistent artifacts per §9.1 in place. Convergence signal: <Nx3-of-3 findings, Mx2-of-3 findings, all amendment-resolved or deferred per spec text>."

Without this artifact form, "Production-Ready" risks being a casual claim ("we shipped the amendments, we're production-ready") rather than an attested status that anyone can re-verify against the persistent artifacts.

**What this is not.** Not a validate-peer category — it produces a doc, not test output. Not a one-time test run — extensions re-review on major-version bumps or when a previously-deferred deployment concern surfaces in practice. Not a substitute for ongoing operational discipline — the review is the pre-flight, not the steady-state monitoring. It bridges "all impls do the same thing" (Stable) and "this thing is safe to depend on in production" (Production-Ready); the first production-class deployment is the empirical confirmation that production-readiness was reached.

**Worked example — the rationale.** `DOMAIN-LOCAL-FILES v1.2` reached Stable via the §10.5 cross-impl conformance gate (Phase 4: 44/44 PASS each + 154/154 cross-peer convergence three-way). A subsequent reliability + performance review found four issues — a silent 16 MiB ceiling on bytes-mode write, Python's `handle_watch` returning success without monitoring the filesystem, a parent-directory fsync gap in all three impls' atomic-write recipes (including the spec's reference recipe), and Python's 10× performance regression at scale — that the conformance gate hadn't surfaced. The findings drove the v1.3 production-hardening cycle; v1.3 landed first, then the production-readiness review re-ran to confirm grade transition. This GUIDE section formalizes the pattern so subsequent extensions don't re-derive what "production-ready" means each time.

**Stage placement in §7 authoring process.** §7's existing stages are Spec draft → Reference impl → Convergence → Convention-source audit → Cross-impl tier validation → Stable. The Production-Readiness Review fits **between Stable (§7 Stage 5) and the Production-Ready grade in §9** — it is the gate of that transition, not a numbered stage in the §7 sequence. §9.1 is the canonical reference.

---

## 10. Common questions

**Q: Should this be an extension or a V7 amendment?**

If your concept changes how V7 mechanics work (capability validation, signature verification, dispatch, content addressing, path resolution) → V7 amendment. If your concept is new entity types, new ops, new validators that compose over V7 mechanics → extension.

When in doubt: try writing it as an extension first. If the extension can't function without changing V7 itself, the answer is V7 amendment.

**Q: How do I know if my extension is too big?**

If you find yourself writing more than ~10 directly-callable handler ops, or more than ~5 owned entity types, or more than ~8 owned `properties.kind` values, you're probably composing two extensions into one. Split them.

If you can't split — the composition is structurally inseparable — you're in composite territory (per §8). Accept the budget.

**Q: My extension needs a thing extension X has internally; can I just call X's internals?**

No. Use X's published surface (handler ops, validators, helpers documented in §-conformance MUSTs). If you need something X doesn't expose, propose an amendment to X to expose it. The principle: every cross-extension dependency goes through declared surfaces, never through internals.

**Q: I want extensions Y and Z to coordinate — should I add a registration hook?**

Premature, probably. Extension points are expensive (§5). Inline the coordination in whichever extension owns the surface, OR specify the contract via spec text only (Y's spec describes how Z's entities flow through it; Z doesn't need to know about Y). Promote to a registration hook when a second consumer concretely needs the same coordination shape.

**Q: My spec has a section that's getting long with examples and rationale. Should I split?**

Probably yes. The normative spec stays focused on contracts; examples, walkthroughs, and rationale live in a separate `GUIDE-<EXT>.md` file. The convention is: spec is what impls test against; guide is what readers read to understand. Most established extensions (IDENTITY, ROLE, ATTESTATION, QUORUM, MULTISIG) have both.

**Q: How do I handle "this is a deployment-policy decision, not a protocol mandate"?**

If it's a real policy axis (not a spec gap), document it as MAY in the conformance section, with the reasoning. Don't promote deployment-policy items to MUST without architecture-team review — locking in policy-flavored decisions at protocol level is a class of drift (§6.4 amplification composition).

If you find yourself writing "deployments handle this" repeatedly, audit: are these real deployment-policy axes or are they spec gaps you don't want to close? The latter is the failure mode.

---

## 11. Where to look

| If you want to… | Start here |
|---|---|
| Understand the architecture | `SYSTEM-ARCHITECTURE.md` |
| Read the core protocol | `ENTITY-CORE-PROTOCOL.md` |
| Understand layered composition / cascade | `SYSTEM-COMPOSITION.md` |
| Understand the type system | `ENTITY-NATIVE-TYPE-SYSTEM.md` + `extensions/EXTENSION-TYPE.md` |
| See a clean substrate-extension example | `extensions/network-peer-extensions/EXTENSION-ATTESTATION.md`, `EXTENSION-QUORUM.md` |
| See a composite-extension example | `extensions/network-peer-extensions/EXTENSION-IDENTITY.md` |
| See a guide-format example | `GUIDE-ATTESTATION.md`, `GUIDE-QUORUM.md`, `GUIDE-IDENTITY.md` |
| See a cross-impl validation matrix | `reviews/VALIDATION-MATRIX-IDENTITY-FOUNDATIONS.md` |
| Look at recent extension-design lessons | the identity-stack audit review |
| Cross-impl convergence loop in practice | the cross-impl ACME convergence retrospective |

---

## 12. Document history

- **§4.10 + §4.11 — L11 idiom + byte-bearing handler convention paired with materialization proposal landing.** Per the content-materialization proposal's Amendments B and C. §4.10 promotes the L11 idiom (substrate resolution is a handler step, not a transform) to normative GUIDE convention — names the pattern workbench-go originally identified, with the closure-think reframe absorbed from Python's review + Rust's transform-op pushback in the v1 → v2 cycle. Worked example references workbench's `blob_resolve.go`; cap discipline pinned to the existing V7 §6.8 handler-grant model with no implicit cap inheritance from chains. §4.11 lifts the byte-bearing domain-handler convention from a single-extension (local/files) pattern to a cross-extension SHOULD — names the inline-include-when-≤`MIN_CHUNK_SIZE` + EnsureClosure-for-larger pattern so future image/dataset/media handlers don't re-derive. The two §4.10 + §4.11 additions are paired because they're the two sides of "protocol surface speaks closures; consumers reassemble locally" — handlers expose the convention, chains compose it via the L11 idiom. No version bump on the GUIDE itself.
- **§9.1 convergence-angle-diversity addition.** Third cycle this lesson has surfaced (L10 absorption, L10 unified feedback, CONTENT v3.6 v1→v2): three impl teams reviewing the same surface from the same code-read angle produced apparent three-way concurrence on framings that an independent threat-model angle later overturned. §9.1 gains a normative MUST that arch SHOULD name the review angle when circulating, and MUST request angles separately when the question touches capability boundaries, default-permissions topology, cross-trust-domain access, or wire-shape contracts between mutually-distrusting parties. Lands paired with CONTENT v3.6 (§9b). The CONTENT v3.6 default-everything-topology cycle is the immediate forcing example — three-impl code-read concurrence said "default-everything-by-default is fine" because each impl had built it that way; threat-model review surfaced that production multi-party default-permissions-to-everything is a security defect. Landing the discipline now prevents a fourth recurrence.
- **§9.1 refinements:** Five refinements absorbed from the DOMAIN-LOCAL-FILES v1.3 cycle experience and Go's OS-bridge amendment-1 review concurrence + pushback. (1) Added review surface #6 — **security boundary** (sandbox escape, capability-boundary integrity, TOCTOU windows, input sanitization at protocol boundaries). The leaf-symlink TOCTOU surfaced in v1.3 (Rust C-1 + Python F-4 PoCs) is the canonical kind of finding the security surface walks. (2) Added **convergence-signal-across-reviewers** as load-bearing — multi-reviewer convergence (3-of-3, 2-of-3) is amendment material; 1-of-3 findings need careful evaluation. (3) Added **pre-closure consumption discipline** — arch confirms all sibling reviews in flight have been consumed before grade transition; "moved to implemented/" is not the closure signal. Both lessons from v1.3's premature-closure mistake. (4) Added **persistent artifacts per review surface SHOULD** — each surface has a re-runnable artifact (bench script, regression test, validate-peer check) so "Production-Ready" doesn't decay to a one-time claim. (5) Added **grade-transition artifact form** — Production-Ready transition produces per-impl review doc + arch-team summary + spec doc-history entry; without this the grade is casual rather than attested. Per the OS-bridge continuation exploration §5 + Go's review §6.3 + §6.5.
- **Added §9.1 "Production-Readiness Review."** Defines the five named review surfaces (performance profile, reliability review, behavioral conformance, large-scale / boundary, deployment quality) that constitute the gate between the Stable grade and the Production-Ready grade. Document-style review per extension, not validate-peer-style; output is pass-with-grade-transition or amendments-to-land plus a re-review. Driven by the local-files Phase 4 experience — `DOMAIN-LOCAL-FILES v1.2` reached Stable cleanly via the cross-impl conformance gate but a deeper reliability+performance review surfaced four issues the conformance signal hadn't (silent 16 MiB ceiling, Python watcher silent-failure, parent-dir fsync gap across all three impls + the reference recipe, Python performance regression at scale). Lifted from local-files-specific review pattern to GUIDE convention so future extensions inherit a structured target rather than ad-hoc adversarial testing. Per the v1.3 production-hardening proposal G1.
- **Added §4.9 "Handler registration paths vs spec-advertised patterns."** Pins the convention universal across the codebase (`system/clock`, `system/query`, `system/tree`, etc.) but never normatively documented: handler entities register at the bare prefix; the manifest's `pattern` field carries advertisement-only glob notation; the dispatcher does not interpret globs (per V7 §6.6 longest-prefix walk). Surfaced by Rust's first-round `constraint_handler_manifest` FAIL + Go's parallel "type handler greedily catches constraint dispatch" debugging during EXTENSION-TYPE v1.1 cross-impl Phase 1 closeout. Companion: `EXTENSION-TYPE.md` §5.1 callout and `ENTITY-CORE-PROTOCOL.md` §6.6 cross-ref. Per the TYPE v1.1 cross-impl closeout proposal, Ask 2.
- **Added §3.5 "Paths are convention; the entity graph is coherence."** Two independent landings in the same design cycle (CONTENT v3.5 `system/content/descriptor` + TYPE v1.1 type-graph reframe) both leaned on the principle; Go-side review (Q4/O9) recommended lifting the discipline to GUIDE now rather than waiting for a third instance. Companion landings: the CONTENT v3.5 proposal A9 + the TYPE v1.1 proposal B6.
- **Initial draft:** Pulled together from BACKLOG.md A1 (extension-design rubric); the substrate-cleanup proposal (closed-namespace, kind-namespacing MUST, type registration, op-naming discipline); the ACME convergence retrospective (TVs as outputs of cross-impl, not architecture-team inputs; convention-source audit pre-promotion; validation budget by extension size); REVIEW-IDENTITY-STACK-AUDIT (drift signals from §13.3 / §13.7 / §13.8 of the underlying primitives exploration). Will refine over time. Open follow-ups: more concrete worked examples for §6 drift signals; a reference template for new extension specs (front-matter + §-structure); the SDK Layer-3 promotion story (when does a guide pattern become an SDK method).

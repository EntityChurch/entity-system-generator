/**
 * COMPUTE — the owned entity types (§2.1–§2.6 and §3.5), for the `typescript` peer.
 *
 * Rendered through the PEER'S OWN `TypeDef` / `FSpec` builder, same as CONTENT and
 * HISTORY, for the same reason: our type entities cannot drift from the peer's
 * rendering convention in a way a review would miss, and the oracle reads them by
 * content hash.
 *
 * THIS IS THE LARGEST TYPE SET IN THE CORPUS — 33 types against HISTORY's six and
 * CONTENT's seven — and it is also the one where a wrong field map is most silent.
 * Every expression entity is content-addressed and referenced BY HASH from its
 * parent, so a single extra or missing field does not produce an error anywhere:
 * it produces an expression graph that hashes differently from every other
 * implementation's, and `compute/lookup/hash` then resolves nothing. That is the
 * `EXTENSION-CONTENT` §2.1 dedup failure one level up, and it is why every field
 * below cites its section and is in the spec's own declaration order.
 *
 * TWO THINGS FOUND BY WRITING THIS FILE, both recorded in `EXTENSION.toml` and
 * routed:
 *
 *  1. **§2.1 says "Seven primitive expression types" and defines EIGHT.** The
 *     parenthetical gives the provenance — *"the `compute/lookup` family has two
 *     members — scope and tree"* — which stopped being true when
 *     `compute/lookup/hash` was added. §10.1 says eight and lists all eight. The
 *     oracle transcribed the seven: `types_expression` requires 7 of the 8 and its
 *     own pass message reads *"all 7 core expression types registered"*, so a peer
 *     that never registers `compute/lookup/hash` passes it — the one type §10.1
 *     separately MUSTs by name (*"`is_compute_type` function — includes
 *     `compute/lookup/hash`"*). **We register all eight.**
 *
 *  2. **`system/compute/subgraph` is missing a field its own spec MUSTs.** §2.5
 *     declares six; §3.3 Phase 3 writes SEVEN, the seventh being
 *     `authorized_data_hashes`, which §4.2 reads, §1.1 names as load-bearing, and
 *     §10.1 MUSTs as *"Sealed `authorized_data_hashes` on subgraph metadata"*. We
 *     render seven — see {@link computeTypeDefs} at the subgraph entry, including
 *     what changed the decision, which was reading the reference implementation
 *     after this file had already made the other choice.
 *
 *  3. **Both membership predicates are three types short, and one of them breaks
 *     programs.** §4.7's `is_compute_expression` lists thirteen of the sixteen
 *     expression types and §4.2's `is_compute_type` lists twenty of the
 *     twenty-three; both omit `compute/index`, `compute/length` and
 *     `compute/numeric-cast`. The N.1 and N.4 amendments that added those three
 *     updated §2.2 and §10.1 and did not update either predicate. See
 *     {@link isComputeType} for why the §4.2 omission is a live functional break
 *     rather than a documentation defect.
 */

import { Entity, FSpec, TypeDef, type EntityTree } from "entity-core-protocol-typescript";

const ref = FSpec.ref;
const arrayOf = FSpec.array;
const mapOf = FSpec.map;

// ── §2.1 core expression types — EIGHT, not the seven §2.1's prose says ──────────
export const LITERAL = "compute/literal";
export const LOOKUP_SCOPE = "compute/lookup/scope";
export const LOOKUP_TREE = "compute/lookup/tree";
export const LOOKUP_HASH = "compute/lookup/hash";
export const APPLY = "compute/apply";
export const IF = "compute/if";
export const LET = "compute/let";
export const LAMBDA = "compute/lambda";

// ── §2.2 inline expression types — eight ────────────────────────────────────────
export const ARITHMETIC = "compute/arithmetic";
export const COMPARE = "compute/compare";
export const LOGIC = "compute/logic";
export const FIELD = "compute/field";
export const CONSTRUCT = "compute/construct";
export const INDEX = "compute/index";
export const LENGTH = "compute/length";
export const NUMERIC_CAST = "compute/numeric-cast";

// ── §2.3 value types ────────────────────────────────────────────────────────────
export const CLOSURE = "compute/closure";
export const SCOPE = "compute/scope";
export const SCOPE_BINDING = "system/compute/scope-binding";

// ── §2.4 result and error ───────────────────────────────────────────────────────
export const RESULT = "compute/result";
export const ERROR = "compute/error";

// ── §2.5 / §2.6 subgraph and install ────────────────────────────────────────────
export const SUBGRAPH = "system/compute/subgraph";
export const INSTALL_REQUEST = "system/compute/install-request";
export const INSTALL_RESULT = "system/compute/install-result";

// ── §3.5 builtin argument types ─────────────────────────────────────────────────
export const MAP_ARGS = "system/compute/map-args";
export const FILTER_ARGS = "system/compute/filter-args";
export const FOLD_ARGS = "system/compute/fold-args";
export const RANGE_ARGS = "system/compute/range-args";
export const GROUP_BY_ARGS = "system/compute/group-by-args";
export const GROUP = "system/compute/group";
export const CONCAT_ARGS = "system/compute/concat-args";
export const ASSOC_ARGS = "system/compute/assoc-args";
export const STORE_ARGS = "system/compute/store-args";

/**
 * §10.1's eight core expression types, in the order §10.1 lists them.
 *
 * Exported as its own constant rather than sliced out of {@link ALL_TYPES} because
 * §4.2's `is_compute_type` and §4.7's expression detection are defined over exactly
 * this set plus §2.2's inline eight — see {@link isComputeType}.
 */
export const CORE_EXPRESSION_TYPES: readonly string[] = [
  LITERAL, LOOKUP_SCOPE, LOOKUP_TREE, LOOKUP_HASH, APPLY, IF, LET, LAMBDA,
];

/** §2.2's eight inline expression types, in §2.2's declaration order. */
export const INLINE_EXPRESSION_TYPES: readonly string[] = [
  ARITHMETIC, COMPARE, LOGIC, FIELD, CONSTRUCT, INDEX, LENGTH, NUMERIC_CAST,
];

/**
 * §4.7 `is_compute_expression` — is this type name a compute EXPRESSION?
 *
 * The sixteen above and nothing else. **`compute/closure` and `compute/scope` are
 * deliberately absent**: §2.1's `lookup/tree` note is explicit that *"closures are
 * values, not expressions, and are not re-evaluated"*, so including them here would
 * make a stored closure evaluate on lookup instead of being returned. `compute/result`
 * and `compute/error` are absent for the same reason — §2.4 values, not programs.
 *
 * **THIS IS SIXTEEN AND §4.7's OWN LIST IS THIRTEEN. A DECLARED DEVIATION, ROUTED.**
 * §4.7's literal list omits `compute/index`, `compute/length` and
 * `compute/numeric-cast` — the three inline types added by the N.1 and N.4
 * amendments, which updated §2.2 and §10.1 and did not update this predicate. See
 * {@link isComputeType} for the same omission with teeth.
 */
export function isComputeExpression(typeName: string): boolean {
  return CORE_EXPRESSION_TYPES.includes(typeName) || INLINE_EXPRESSION_TYPES.includes(typeName);
}

/**
 * §4.2 `is_compute_type` — Tier 1 of `validate_compute_resolvable`.
 *
 * Broader than {@link isComputeExpression}: it admits the §2.3 value types, the §2.4
 * result/error pair and the §2.5/§2.6 subgraph and install types, because Tier 1's
 * job is *"expression subgraph membership"* — is this entity part of a compute
 * program at all — rather than *"is this evaluable"*.
 *
 * **TWENTY-THREE, AND §4.2's OWN LIST IS TWENTY. THE SAME THREE ARE MISSING, AND
 * HERE IT IS A FUNCTIONAL BREAK RATHER THAN A DOCUMENTATION ONE.**
 *
 * Every sub-expression is referenced BY HASH from its parent and resolved through
 * `resolve()` → `validate_compute_resolvable`. Without `content_store_access`
 * (Tier 0) and outside an installed subgraph's sealed set (Tier 2), **Tier 1 is the
 * only thing that admits an ordinary sub-expression** — so transcribing §4.2's list
 * literally produces a peer on which any expression graph containing an `index`,
 * `length` or `numeric-cast` node fails to resolve, and the caller sees
 * `not_found` on a perfectly valid program. §10.1 MUSTs all three types and MUSTs
 * this very function by name for a DIFFERENT addition — *"`is_compute_type` function
 * — includes `compute/lookup/hash` (§4.2)"* — so the list has been corrected once
 * already, for one of the four types that needed it.
 *
 * `entity-core-go`'s `isComputeType` (`ext/compute/eval.go`) carries all three, as
 * does its `IsComputeExpression`. **That is corroboration and not the reason** (L18):
 * the reason is that §2.2 defines them, §10.1 MUSTs them, and a predicate that
 * excludes them contradicts both. Routed as `ROUTING-2026-09-09-d-arch-*`.
 */
export function isComputeType(typeName: string): boolean {
  return (
    isComputeExpression(typeName) ||
    typeName === CLOSURE ||
    typeName === SCOPE ||
    typeName === RESULT ||
    typeName === ERROR ||
    typeName === SUBGRAPH ||
    typeName === INSTALL_REQUEST ||
    typeName === INSTALL_RESULT
  );
}

/** Every type this extension owns and publishes, in spec-section order. */
export const ALL_TYPES: readonly string[] = [
  ...CORE_EXPRESSION_TYPES,
  ...INLINE_EXPRESSION_TYPES,
  CLOSURE, SCOPE, SCOPE_BINDING,
  RESULT, ERROR,
  SUBGRAPH, INSTALL_REQUEST, INSTALL_RESULT,
  MAP_ARGS, FILTER_ARGS, FOLD_ARGS, RANGE_ARGS, GROUP_BY_ARGS, GROUP,
  CONCAT_ARGS, ASSOC_ARGS, STORE_ARGS,
];

/** The handler pattern. §3.1's PROSE, not §3.1's code block — see below. */
export const COMPUTE_PATTERN = "system/compute";

/**
 * §3.5 — the builtin handler prefix, and §4's override prohibition subject.
 *
 * v3.29 is the reason this constant is exported rather than inlined. The prohibition
 * used to describe itself as a subset of core's `system/*` reservation and told
 * implementers that enforcing that reservation needed *"no separate compute-specific
 * guard."* `ENTITY-CORE-PROTOCOL` 0.8.2.13 **withdrew the reservation**, so v3.29
 * restates the rule on its own basis: it binds every installation path because it is
 * a cross-peer determinism requirement. **There is no core rule left to delegate to,
 * so the guard is ours.** See `sdk.ts`.
 */
export const BUILTINS_PREFIX = "system/compute/builtins";

/** §7 reactive mode — where subgraph metadata lives (§3.3 Phase 3). */
export const PROCESSES_PREFIX = "system/compute/processes";

// ── §9.1's error codes, and §9.3's recommended limits ───────────────────────────

/**
 * §9.1's sixteen codes.
 *
 * **Three of them carry a property §9.1's table does not record**, added at v3.27 and
 * transcribed into `EXTENSION.toml [error_surface]`: `depth_exceeded` CONTAINS — its
 * counter is restored on unwind (§5.1) — while `budget_exhausted` and `cascade_limit`
 * SHORT-CIRCUIT everywhere, cumulative and chain-wide respectively. That distinction
 * is not derivable from the table and decides what a collection primitive does with
 * an error in a contained position.
 */
export const CODE_BUDGET_EXHAUSTED = "budget_exhausted";
export const CODE_DEPTH_EXCEEDED = "depth_exceeded";
export const CODE_TYPE_MISMATCH = "type_mismatch";
export const CODE_DIVISION_BY_ZERO = "division_by_zero";
export const CODE_NOT_FOUND = "not_found";
export const CODE_UNKNOWN_TYPE = "unknown_type";
export const CODE_MISSING_ARGUMENT = "missing_argument";
export const CODE_INVALID_EXPRESSION = "invalid_expression";
export const CODE_CASCADE_LIMIT = "cascade_limit";
export const CODE_PERMISSION_DENIED = "permission_denied";
export const CODE_INSTALLATION_GRANT_INVALID = "installation_grant_invalid";
export const CODE_INDEX_OUT_OF_RANGE = "index_out_of_range";
export const CODE_CAST_OUT_OF_RANGE = "cast_out_of_range";
export const CODE_COUNT_OUT_OF_RANGE = "count_out_of_range";
export const CODE_SCOPE_UNREACHABLE = "scope_unreachable";
export const CODE_AMBIGUOUS_RESOURCE = "ambiguous_resource";

/** §9.3 — `peer_default_max_ops`. A peer MAY configure it (§9.3, §10.4). */
export const DEFAULT_MAX_OPS = 100_000;
/** §9.3 — `peer_default_max_depth` / `RECOMMENDED_MAX_DEPTH`. */
export const DEFAULT_MAX_DEPTH = 1_024;
/** §9.3 — `RECOMMENDED_MAX_CASCADE_DEPTH`. §10.3's one MAY is its configurability. */
export const RECOMMENDED_MAX_CASCADE_DEPTH = 16;

/**
 * The type definitions, in §2.1 → §2.2 → §2.3 → §2.4 → §2.5/§2.6 → §3.5 order.
 *
 * Field order inside a definition does not affect the rendered bytes — the codec
 * re-sorts map keys length-then-lex — but it is kept in spec order so a reader can
 * diff this against the spec block by block.
 */
export function computeTypeDefs(): readonly TypeDef[] {
  return [
    // ── §2.1 ────────────────────────────────────────────────────────────────────
    new TypeDef(LITERAL)
      .f("value", ref("primitive/any")),

    new TypeDef(LOOKUP_SCOPE)
      .f("name", ref("primitive/string")),

    new TypeDef(LOOKUP_TREE)
      .f("path", ref("system/tree/path"))
      .f("relative", ref("primitive/bool").opt()),

    // The eighth core type, and the one `types_expression` does not ask for.
    new TypeDef(LOOKUP_HASH)
      .f("hash", ref("system/hash"))
      .f("path", ref("system/tree/path").opt())
      .f("relative", ref("primitive/bool").opt()),

    // §2.1's dual-mode apply. Every field optional, because handler mode uses
    // `path`/`operation`/`resource` and closure mode uses `fn` — which is exactly
    // why §4.1 has to decide the mode from which fields are PRESENT.
    new TypeDef(APPLY)
      .f("path", ref("system/tree/path").opt())
      .f("operation", ref("primitive/string").opt())
      .f("resource", ref("system/hash").opt())
      .f("fn", ref("system/hash").opt())
      .f("args", mapOf(ref("system/hash")).opt())
      .f("capability", ref("system/hash").opt()),

    new TypeDef(IF)
      .f("condition", ref("system/hash"))
      .f("then", ref("system/hash"))
      .f("else", ref("system/hash").opt()),

    // §2.1's own comment describes `bindings` as `[{name, value}, ...]` but declares
    // the element type as `primitive/any`. We render what is DECLARED — the comment
    // is a shape note, and a `TypeDef` naming a type the spec does not would change
    // the published type entity's bytes away from every other port's.
    new TypeDef(LET)
      .f("bindings", arrayOf(ref("primitive/any")))
      .f("body", ref("system/hash")),

    new TypeDef(LAMBDA)
      .f("params", arrayOf(ref("primitive/string")))
      .f("body", ref("system/hash")),

    // ── §2.2 ────────────────────────────────────────────────────────────────────
    //
    // The three `op`-carrying types declare a `constraints: {op: {one_of: [...]}}`
    // block in the spec. `TypeDef` HAS NO CONSTRAINTS RENDERING — `FSpec` carries
    // type_ref / optional / array_of / map_of / union_of / key_type / byte_size and
    // nothing else, and `TypeDef` renders name / extends / fields / layout.
    //
    // So the `one_of` is enforced in the EVALUATOR (`internal/evaluator.ts`) and is
    // absent from the published type entity. That is recorded in `EXTENSION.toml`
    // as `[substrate].type_constraints_unrenderable` rather than silently dropped:
    // it is a per-peer fact about the builder, the same shape as HISTORY's
    // "no public type builder" row, and the three ports must agree on it or their
    // type entities diverge.
    new TypeDef(ARITHMETIC)
      .f("op", ref("primitive/string"))
      .f("left", ref("system/hash"))
      .f("right", ref("system/hash")),

    new TypeDef(COMPARE)
      .f("op", ref("primitive/string"))
      .f("left", ref("system/hash"))
      .f("right", ref("system/hash")),

    // `right` optional — absent for "not" (§2.2).
    new TypeDef(LOGIC)
      .f("op", ref("primitive/string"))
      .f("left", ref("system/hash"))
      .f("right", ref("system/hash").opt()),

    new TypeDef(FIELD)
      .f("name", ref("primitive/string"))
      .f("entity", ref("system/hash")),

    new TypeDef(CONSTRUCT)
      .f("entity_type", ref("system/type/name"))
      .f("fields", mapOf(ref("system/hash"))),

    new TypeDef(INDEX)
      .f("array", ref("system/hash"))
      .f("index", ref("system/hash")),

    new TypeDef(LENGTH)
      .f("array", ref("system/hash")),

    new TypeDef(NUMERIC_CAST)
      .f("value", ref("system/hash"))
      .f("to_type", ref("system/type/name")),

    // ── §2.3 ────────────────────────────────────────────────────────────────────
    new TypeDef(CLOSURE)
      .f("params", arrayOf(ref("primitive/string")))
      .f("body", ref("system/hash"))
      .f("env", ref("system/hash").opt()),

    new TypeDef(SCOPE)
      .f("bindings", mapOf(ref(SCOPE_BINDING))),

    // §2.3's kind-tagged union, v3.19b. The ONLY union in this type set, and the
    // one type whose canonical bytes the spec pins by digest — N2's fixture hashes
    // to `ecf-sha256:3edc5138…` in all three reference implementations. `FSpec.union`
    // renders `union_of`, so this is expressible; N2's ratified hash is over a
    // SCOPE INSTANCE rather than over this definition, so agreeing here is
    // necessary and not sufficient. `gates/type-parity` covers the definition.
    new TypeDef(SCOPE_BINDING)
      .f("kind", ref("primitive/string"))
      .f("entity_hash", ref("system/hash").opt())
      .f("value", ref("primitive/any").opt()),

    // ── §2.4 ────────────────────────────────────────────────────────────────────
    new TypeDef(RESULT)
      .f("value", ref("primitive/any"))
      .f("expression", ref("system/hash")),

    // §2.4 is emphatic that `code` is "the ONLY materialized field" and that
    // `message` / `at` / `expression` are in-flight diagnostics. They are declared
    // here because the TYPE has them; the evaluator never materializes them, which
    // is what keeps a `compute/error` byte-identical across peers (v3.26).
    new TypeDef(ERROR)
      .f("code", ref("primitive/string"))
      .f("message", ref("primitive/string").opt())
      .f("at", ref("primitive/string").opt())
      .f("expression", ref("system/hash").opt()),

    // ── §2.5 / §2.6 ─────────────────────────────────────────────────────────────
    //
    // SEVEN FIELDS, WHICH IS §3.3's SHAPE AND NOT §2.5's SIX. A DECLARED DEVIATION.
    //
    // §2.5's field map has six. Every other site in the spec has seven: §3.3 Phase 3
    // writes `authorized_data_hashes` into the subgraph entity's data, §4.2 reads
    // `ctx.subgraph.data.authorized_data_hashes` to decide whether a hash is in the
    // sealed set, §1.1 names it beside `installation_grant` as one of the fields that
    // "authorize future evaluations and dispatches", and §10.1 MUSTs it by name —
    // "Sealed `authorized_data_hashes` on subgraph metadata (§3.3)".
    //
    // THE FIRST DRAFT OF THIS FILE RENDERED SIX, on the reasoning that a published
    // type should be what the type section declares. That was wrong, and what showed
    // it was reading the reference implementation rather than re-reading the spec:
    // `entity-core-go`'s `ComputeSubgraphData` (core/types/compute.go) carries
    // `AuthorizedDataHashes []hash.Hash` and its type entity is registered by
    // reflection over that struct — so the reference publishes SEVEN. Rendering six
    // would have made us the only implementation whose subgraph type disagrees, and
    // it would have been silent: the oracle's `types_subgraph` check asserts that the
    // type PATH resolves and never reads the field map, which is our own G-3 finding
    // about `type_*` checks arriving from the other side.
    //
    // **The reference agreeing is corroboration and not the reason.** Three normative
    // sites in the spec's own body say seven against one type block that says six
    // (L18: a cohort agreeing is a cohort agreeing). §2.5 is the outlier, it is a
    // defect, and it is routed as one — `ROUTING-2026-09-09-d-arch-*`. If arch rules
    // the other way this is a one-line change and a re-pin.
    new TypeDef(SUBGRAPH)
      .f("root_expression_path", ref("system/tree/path"))
      .f("root_expression", ref("system/hash"))
      .f("installation_grant", ref("system/hash"))
      .f("installed_by", ref("system/hash"))
      .f("result_path", ref("system/tree/path"))
      .f("status", ref("primitive/string"))
      .f("authorized_data_hashes", arrayOf(ref("system/hash")).opt()),

    new TypeDef(INSTALL_REQUEST)
      .f("result_path", ref("system/tree/path").opt()),

    new TypeDef(INSTALL_RESULT)
      .f("subgraph_path", ref("system/tree/path"))
      .f("impure_operations", ref("primitive/any"))
      .f("result_path", ref("system/tree/path")),

    // NOTE: there is no `system/compute/uninstall-request`. The declaration header
    // names one; §3.1's manifest gives `uninstall` an input type of `primitive/any`
    // and the body of the spec says the type was "eliminated in v3.12 — uninstall
    // uses empty params". The header is the stale one. Not routed as its own item:
    // it is the same sentence as the §9.2 operations-table drift already filed.

    // ── §3.5 ────────────────────────────────────────────────────────────────────
    new TypeDef(MAP_ARGS)
      .f("collection", ref("system/hash"))
      .f("fn", ref("system/hash")),

    // `fn`, not `predicate` — renamed at F11 (v3.19) for uniformity with map/fold.
    new TypeDef(FILTER_ARGS)
      .f("collection", ref("system/hash"))
      .f("fn", ref("system/hash")),

    new TypeDef(FOLD_ARGS)
      .f("collection", ref("system/hash"))
      .f("fn", ref("system/hash"))
      .f("initial", ref("system/hash")),

    new TypeDef(RANGE_ARGS)
      .f("n", ref("system/hash")),

    new TypeDef(GROUP_BY_ARGS)
      .f("collection", ref("system/hash"))
      .f("fn", ref("system/hash")),

    // §3.5 v3.25 restored `key` into the result shape; the v3.24 fold had narrowed
    // it away.
    new TypeDef(GROUP)
      .f("key", ref("primitive/any"))
      .f("members", arrayOf(ref("primitive/any"))),

    // v3.27: ONE hash of an expression, uniform with every sibling collection
    // argument — not an array of hashes.
    new TypeDef(CONCAT_ARGS)
      .f("collections", ref("system/hash")),

    new TypeDef(ASSOC_ARGS)
      .f("collection", ref("system/hash"))
      .f("index", ref("system/hash"))
      .f("value", ref("system/hash")),

    new TypeDef(STORE_ARGS)
      .f("path", ref("system/tree/path"))
      .f("value", ref("system/hash")),
  ];
}

/** `(typeName, system/type entity)` for each — the materialised form. */
export function computeTypeEntities(): readonly (readonly [string, Entity])[] {
  return computeTypeDefs().map(
    (def) => [def.treePath.replace(/^system\/type\//, ""), def.toEntity()] as const,
  );
}

/**
 * Publish the type entities into the peer's tree at `system/type/{name}`.
 *
 * Returns the absolute paths written, so the caller can report what it installed
 * rather than assert what it intended to.
 */
export function publishComputeTypes(tree: EntityTree, localPeerId: string): readonly string[] {
  const written: string[] = [];
  for (const def of computeTypeDefs()) {
    const path = "/" + localPeerId + "/" + def.treePath;
    tree.put(path, def.toEntity());
    written.push(path);
  }
  return written;
}

/** Build one of our own entities without reaching for `Entity.create` at each site. */
export function computeEntity(type: string, data: Parameters<typeof Entity.create>[1]): Entity {
  return Entity.create(type, data);
}

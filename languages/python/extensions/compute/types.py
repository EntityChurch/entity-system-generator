"""COMPUTE — the 33 owned entity types (§2.1–§2.6 and §3.5), for the `python` peer.

Same retarget cost CONTENT and HISTORY paid, and the same reason it is paid: this peer's
type-def builders (``_type_def``, ``_fref``, ``_opt``, ``_farray``, ``_fmap_of`` in
``entity_core.peer.typedefs``) are all leading-underscore, and an underscore is this
peer's statement about its own boundary. So these field maps are hand-built, and the
rendered ``system/type`` data map has to come out byte-identical to
``../../../typescript/extensions/compute/types.ts``'s ``TypeDef.toEntity()``.

**THAT IS NOT A STYLE CLAIM HERE, IT IS THE GATE.** 63 of this composition's core
improvements are `entity-core-go`'s ``type_system.type_compute_*_match`` checks, which
compare our published type entity's content hash against the oracle's OWN independent
transcription of the same §2.x block. So unlike HISTORY — where the six ``type_*`` checks
only assert that a path RESOLVES (G-3) — a wrong field map in this file fails loudly and
names the type. This is the one extension in the corpus where the type layer has a real
cross-impl oracle, and it is why this file is a transcription rather than a rendering
convenience.

THE THREE DECLARED DEVIATIONS ARE THE `typescript` PORT'S, UNCHANGED AND RE-DERIVED
RATHER THAN COPIED (L18 — a cohort agreeing is a cohort agreeing, and our own other port
is a cohort of one):

 1. **§2.1 says "Seven primitive expression types" and defines EIGHT.** We register all
    eight; the oracle's ``types_expression`` asks for seven and its pass message says
    seven, so a peer omitting ``compute/lookup/hash`` passes the check that names it.
 2. **``system/compute/subgraph`` gets SEVEN fields, not §2.5's six.** §3.3 Phase 3
    writes ``authorized_data_hashes``, §4.2 reads it, §1.1 names it load-bearing and
    §10.1 MUSTs it by name. Three normative sites against one type block.
 3. **Both membership predicates carry all sixteen expression types.** §4.7's list has
    thirteen and §4.2's has twenty; both omit ``compute/index``, ``compute/length`` and
    ``compute/numeric-cast``. §4.2's omission is a live functional break — see
    :func:`is_compute_type`.

All three are routed as ``ROUTING-2026-09-09-d-arch-*`` /
``ROUTING-2026-09-10-arch-*``; nothing here is a local decision about semantics.
"""

from __future__ import annotations

from typing import Any

from entity_core.peer.model import Entity

# ── §2.1 core expression types — EIGHT, not the seven §2.1's prose says ──────────
LITERAL = "compute/literal"
LOOKUP_SCOPE = "compute/lookup/scope"
LOOKUP_TREE = "compute/lookup/tree"
LOOKUP_HASH = "compute/lookup/hash"
APPLY = "compute/apply"
IF = "compute/if"
LET = "compute/let"
LAMBDA = "compute/lambda"

# ── §2.2 inline expression types — eight ────────────────────────────────────────
ARITHMETIC = "compute/arithmetic"
COMPARE = "compute/compare"
LOGIC = "compute/logic"
FIELD = "compute/field"
CONSTRUCT = "compute/construct"
INDEX = "compute/index"
LENGTH = "compute/length"
NUMERIC_CAST = "compute/numeric-cast"

# ── §2.3 value types ────────────────────────────────────────────────────────────
CLOSURE = "compute/closure"
SCOPE = "compute/scope"
SCOPE_BINDING = "system/compute/scope-binding"

# ── §2.4 result and error ───────────────────────────────────────────────────────
RESULT = "compute/result"
ERROR = "compute/error"

# ── §2.5 / §2.6 subgraph and install ────────────────────────────────────────────
SUBGRAPH = "system/compute/subgraph"
INSTALL_REQUEST = "system/compute/install-request"
INSTALL_RESULT = "system/compute/install-result"

# ── §3.5 builtin argument types ─────────────────────────────────────────────────
MAP_ARGS = "system/compute/map-args"
FILTER_ARGS = "system/compute/filter-args"
FOLD_ARGS = "system/compute/fold-args"
RANGE_ARGS = "system/compute/range-args"
GROUP_BY_ARGS = "system/compute/group-by-args"
GROUP = "system/compute/group"
CONCAT_ARGS = "system/compute/concat-args"
ASSOC_ARGS = "system/compute/assoc-args"
STORE_ARGS = "system/compute/store-args"

#: §10.1's eight core expression types, in the order §10.1 lists them.
CORE_EXPRESSION_TYPES = (
    LITERAL, LOOKUP_SCOPE, LOOKUP_TREE, LOOKUP_HASH, APPLY, IF, LET, LAMBDA,
)

#: §2.2's eight inline expression types, in §2.2's declaration order.
INLINE_EXPRESSION_TYPES = (
    ARITHMETIC, COMPARE, LOGIC, FIELD, CONSTRUCT, INDEX, LENGTH, NUMERIC_CAST,
)


def is_compute_expression(type_name: str) -> bool:
    """§4.7 ``is_compute_expression`` — is this type name a compute EXPRESSION?

    The sixteen above and nothing else. ``compute/closure`` and ``compute/scope`` are
    deliberately absent: §2.1's ``lookup/tree`` note is explicit that *"closures are
    values, not expressions, and are not re-evaluated"*, so including them would make a
    stored closure evaluate on lookup instead of being returned. ``compute/result`` and
    ``compute/error`` are absent for the same reason — §2.4 values, not programs.

    **SIXTEEN, AND §4.7's OWN LIST IS THIRTEEN. A DECLARED DEVIATION, ROUTED.** §4.7
    omits ``compute/index``, ``compute/length`` and ``compute/numeric-cast`` — the three
    inline types the N.1 and N.4 amendments added, which updated §2.2 and §10.1 and did
    not update this predicate.
    """
    return type_name in CORE_EXPRESSION_TYPES or type_name in INLINE_EXPRESSION_TYPES


def is_compute_type(type_name: str) -> bool:
    """§4.2 ``is_compute_type`` — Tier 1 of ``validate_compute_resolvable``.

    Broader than :func:`is_compute_expression`: it admits the §2.3 value types, the §2.4
    result/error pair and the §2.5/§2.6 subgraph and install types, because Tier 1's job
    is *"expression subgraph membership"* rather than *"is this evaluable"*.

    **TWENTY-THREE, AND §4.2's OWN LIST IS TWENTY. THE SAME THREE ARE MISSING, AND HERE
    IT IS A FUNCTIONAL BREAK RATHER THAN A DOCUMENTATION ONE.** Every sub-expression is
    referenced BY HASH and resolved through ``resolve()`` -> ``validate_compute_resolvable``.
    Without ``content_store_access`` (Tier 0) and outside an installed subgraph's sealed
    set (Tier 2), **Tier 1 is the only thing that admits an ordinary sub-expression** — so
    transcribing §4.2's list literally produces a peer on which any expression graph
    containing an ``index``, ``length`` or ``numeric-cast`` node fails to resolve and the
    caller sees ``not_found`` on a valid program.
    """
    return (
        is_compute_expression(type_name)
        or type_name in (CLOSURE, SCOPE, RESULT, ERROR, SUBGRAPH, INSTALL_REQUEST, INSTALL_RESULT)
    )


#: Every type this extension owns and publishes, in spec-section order.
ALL_TYPES = (
    *CORE_EXPRESSION_TYPES,
    *INLINE_EXPRESSION_TYPES,
    CLOSURE, SCOPE, SCOPE_BINDING,
    RESULT, ERROR,
    SUBGRAPH, INSTALL_REQUEST, INSTALL_RESULT,
    MAP_ARGS, FILTER_ARGS, FOLD_ARGS, RANGE_ARGS, GROUP_BY_ARGS, GROUP,
    CONCAT_ARGS, ASSOC_ARGS, STORE_ARGS,
)

#: The handler pattern. §3.1's PROSE, not §3.1's code block — the block spells it
#: `system/compute/*`, which is 2 of 18 across the corpus and is filed as drift.
COMPUTE_PATTERN = "system/compute"

#: §3.5 — the builtin handler prefix, and §4's override prohibition subject.
#:
#: v3.29 is why this is a named constant. The prohibition used to describe itself as a
#: subset of core's `system/*` reservation; `ENTITY-CORE-PROTOCOL` 0.8.2.13 WITHDREW the
#: reservation, so v3.29 restates the rule on its own basis and there is nothing upstream
#: left to delegate to. The guard is ours — see `sdk.assert_not_builtin_override`.
BUILTINS_PREFIX = "system/compute/builtins"

#: §7 reactive mode — where subgraph metadata lives (§3.3 Phase 3).
PROCESSES_PREFIX = "system/compute/processes"

# ── §9.1's sixteen error codes ──────────────────────────────────────────────────
#
# Three carry a property §9.1's table does not record, added at v3.27: `depth_exceeded`
# CONTAINS (its counter is restored on unwind, §5.1) while `budget_exhausted` and
# `cascade_limit` SHORT-CIRCUIT everywhere, cumulative and chain-wide respectively. That
# distinction is not derivable from the table and decides what a collection primitive does
# with an error in a contained position — see `_internal.evaluator._is_halting`.
CODE_BUDGET_EXHAUSTED = "budget_exhausted"
CODE_DEPTH_EXCEEDED = "depth_exceeded"
CODE_TYPE_MISMATCH = "type_mismatch"
CODE_DIVISION_BY_ZERO = "division_by_zero"
CODE_NOT_FOUND = "not_found"
CODE_UNKNOWN_TYPE = "unknown_type"
CODE_MISSING_ARGUMENT = "missing_argument"
CODE_INVALID_EXPRESSION = "invalid_expression"
CODE_CASCADE_LIMIT = "cascade_limit"
CODE_PERMISSION_DENIED = "permission_denied"
CODE_INSTALLATION_GRANT_INVALID = "installation_grant_invalid"
CODE_INDEX_OUT_OF_RANGE = "index_out_of_range"
CODE_CAST_OUT_OF_RANGE = "cast_out_of_range"
CODE_COUNT_OUT_OF_RANGE = "count_out_of_range"
CODE_SCOPE_UNREACHABLE = "scope_unreachable"
CODE_AMBIGUOUS_RESOURCE = "ambiguous_resource"

#: §9.3 — `peer_default_max_ops`. A peer MAY configure it (§9.3, §10.4).
DEFAULT_MAX_OPS = 100_000
#: §9.3 — `peer_default_max_depth` / `RECOMMENDED_MAX_DEPTH`.
DEFAULT_MAX_DEPTH = 1_024
#: §9.3 — `RECOMMENDED_MAX_CASCADE_DEPTH`. §10.3's one MAY is its configurability.
RECOMMENDED_MAX_CASCADE_DEPTH = 16


# ── field-spec builders (omit-empty; the ECF §1.3 absent-key convention) ────────
#
# Mirrors `entity_core.peer.typedefs`'s private `_fref` / `_opt` / `_farray` / `_fmap_of`
# and `typescript`'s `FSpec.ref` / `.opt()` / `FSpec.array` / `FSpec.map`. `_map` omits
# `key_type` because `typescript`'s `FSpec.map(value)` is called with no key type in every
# position below, and a `key_type` key present on one port and absent on the other is a
# different content hash for the same declared type.


def _ref(type_name: str) -> dict[str, Any]:
    return {"type_ref": type_name}


def _opt(spec: dict[str, Any]) -> dict[str, Any]:
    out = dict(spec)
    out["optional"] = True
    return out


def _array(element: dict[str, Any]) -> dict[str, Any]:
    return {"array_of": element}


def _map(value: dict[str, Any]) -> dict[str, Any]:
    return {"map_of": value}


def _type_def(name: str, fields: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name}
    if fields:
        out["fields"] = dict(fields)
    return out


def compute_type_defs() -> list[tuple[str, dict[str, Any]]]:
    """The 33 definitions, in §2.1 -> §2.2 -> §2.3 -> §2.4 -> §2.5/§2.6 -> §3.5 order.

    Field order inside a definition does not affect the rendered bytes — the codec
    re-sorts map keys length-then-lex — but it is kept in spec order so a reader can diff
    this against the spec block by block, and against ``types.ts`` line by line.
    """
    return [
        # ── §2.1 ────────────────────────────────────────────────────────────────
        (LITERAL, _type_def(LITERAL, [
            ("value", _ref("primitive/any")),
        ])),

        (LOOKUP_SCOPE, _type_def(LOOKUP_SCOPE, [
            ("name", _ref("primitive/string")),
        ])),

        (LOOKUP_TREE, _type_def(LOOKUP_TREE, [
            ("path", _ref("system/tree/path")),
            ("relative", _opt(_ref("primitive/bool"))),
        ])),

        # The eighth core type, and the one `types_expression` does not ask for.
        (LOOKUP_HASH, _type_def(LOOKUP_HASH, [
            ("hash", _ref("system/hash")),
            ("path", _opt(_ref("system/tree/path"))),
            ("relative", _opt(_ref("primitive/bool"))),
        ])),

        # §2.1's dual-mode apply. Every field optional, because handler mode uses
        # `path`/`operation`/`resource` and closure mode uses `fn` — which is exactly why
        # §4.1 has to decide the mode from which fields are PRESENT.
        (APPLY, _type_def(APPLY, [
            ("path", _opt(_ref("system/tree/path"))),
            ("operation", _opt(_ref("primitive/string"))),
            ("resource", _opt(_ref("system/hash"))),
            ("fn", _opt(_ref("system/hash"))),
            ("args", _opt(_map(_ref("system/hash")))),
            ("capability", _opt(_ref("system/hash"))),
        ])),

        (IF, _type_def(IF, [
            ("condition", _ref("system/hash")),
            ("then", _ref("system/hash")),
            ("else", _opt(_ref("system/hash"))),
        ])),

        # §2.1's own comment describes `bindings` as `[{name, value}, ...]` but declares
        # the element type as `primitive/any`. We render what is DECLARED — the comment is
        # a shape note, and a type naming something the spec does not would change the
        # published bytes away from every other port's.
        (LET, _type_def(LET, [
            ("bindings", _array(_ref("primitive/any"))),
            ("body", _ref("system/hash")),
        ])),

        (LAMBDA, _type_def(LAMBDA, [
            ("params", _array(_ref("primitive/string"))),
            ("body", _ref("system/hash")),
        ])),

        # ── §2.2 ────────────────────────────────────────────────────────────────
        #
        # The three `op`-carrying types declare a `constraints: {op: {one_of: [...]}}`
        # block in the spec. NEITHER PEER'S TYPE-DEF SHAPE HAS A CONSTRAINTS CARRIER —
        # `field-spec` is type_ref / optional / array_of / map_of / union_of / key_type /
        # byte_size and a `system/type` is name / extends / fields / layout. So the
        # `one_of` is enforced in the EVALUATOR and is absent from the published type
        # entity, on both ports. Recorded as `[substrate].type_constraints_unrenderable`:
        # it is a per-peer fact, and the ports must agree on it or their type entities
        # diverge — which here would show up as a `type_compute_arithmetic_match` failure.
        (ARITHMETIC, _type_def(ARITHMETIC, [
            ("op", _ref("primitive/string")),
            ("left", _ref("system/hash")),
            ("right", _ref("system/hash")),
        ])),

        (COMPARE, _type_def(COMPARE, [
            ("op", _ref("primitive/string")),
            ("left", _ref("system/hash")),
            ("right", _ref("system/hash")),
        ])),

        # `right` optional — absent for "not" (§2.2).
        (LOGIC, _type_def(LOGIC, [
            ("op", _ref("primitive/string")),
            ("left", _ref("system/hash")),
            ("right", _opt(_ref("system/hash"))),
        ])),

        (FIELD, _type_def(FIELD, [
            ("name", _ref("primitive/string")),
            ("entity", _ref("system/hash")),
        ])),

        (CONSTRUCT, _type_def(CONSTRUCT, [
            ("entity_type", _ref("system/type/name")),
            ("fields", _map(_ref("system/hash"))),
        ])),

        (INDEX, _type_def(INDEX, [
            ("array", _ref("system/hash")),
            ("index", _ref("system/hash")),
        ])),

        (LENGTH, _type_def(LENGTH, [
            ("array", _ref("system/hash")),
        ])),

        (NUMERIC_CAST, _type_def(NUMERIC_CAST, [
            ("value", _ref("system/hash")),
            ("to_type", _ref("system/type/name")),
        ])),

        # ── §2.3 ────────────────────────────────────────────────────────────────
        (CLOSURE, _type_def(CLOSURE, [
            ("params", _array(_ref("primitive/string"))),
            ("body", _ref("system/hash")),
            ("env", _opt(_ref("system/hash"))),
        ])),

        (SCOPE, _type_def(SCOPE, [
            ("bindings", _map(_ref(SCOPE_BINDING))),
        ])),

        # §2.3's kind-tagged union, v3.19b. N2's fixture hashes to `ecf-sha256:3edc5138…`
        # in all three reference implementations — but that digest is over a SCOPE
        # INSTANCE, not over this definition, so agreeing here is necessary and not
        # sufficient. `gates/type-parity` covers the definition.
        (SCOPE_BINDING, _type_def(SCOPE_BINDING, [
            ("kind", _ref("primitive/string")),
            ("entity_hash", _opt(_ref("system/hash"))),
            ("value", _opt(_ref("primitive/any"))),
        ])),

        # ── §2.4 ────────────────────────────────────────────────────────────────
        (RESULT, _type_def(RESULT, [
            ("value", _ref("primitive/any")),
            ("expression", _ref("system/hash")),
        ])),

        # §2.4 is emphatic that `code` is "the ONLY materialized field" and that
        # `message` / `at` / `expression` are in-flight diagnostics. They are declared
        # because the TYPE has them; the evaluator never materializes them, which is what
        # keeps a `compute/error` byte-identical across peers (v3.26).
        (ERROR, _type_def(ERROR, [
            ("code", _ref("primitive/string")),
            ("message", _opt(_ref("primitive/string"))),
            ("at", _opt(_ref("primitive/string"))),
            ("expression", _opt(_ref("system/hash"))),
        ])),

        # ── §2.5 / §2.6 ─────────────────────────────────────────────────────────
        #
        # SEVEN FIELDS, WHICH IS §3.3's SHAPE AND NOT §2.5's SIX. A DECLARED DEVIATION.
        # §3.3 Phase 3 writes `authorized_data_hashes`, §4.2 reads
        # `ctx.subgraph.data.authorized_data_hashes`, §1.1 names it beside
        # `installation_grant` as a field that "authorizes future evaluations and
        # dispatches", and §10.1 MUSTs it by name. §2.5's field map is the outlier.
        (SUBGRAPH, _type_def(SUBGRAPH, [
            ("root_expression_path", _ref("system/tree/path")),
            ("root_expression", _ref("system/hash")),
            ("installation_grant", _ref("system/hash")),
            ("installed_by", _ref("system/hash")),
            ("result_path", _ref("system/tree/path")),
            ("status", _ref("primitive/string")),
            ("authorized_data_hashes", _opt(_array(_ref("system/hash")))),
        ])),

        (INSTALL_REQUEST, _type_def(INSTALL_REQUEST, [
            ("result_path", _opt(_ref("system/tree/path"))),
        ])),

        (INSTALL_RESULT, _type_def(INSTALL_RESULT, [
            ("subgraph_path", _ref("system/tree/path")),
            ("impure_operations", _ref("primitive/any")),
            ("result_path", _ref("system/tree/path")),
        ])),

        # NOTE: there is no `system/compute/uninstall-request`. The declaration header
        # names one; §3.1's manifest gives `uninstall` an input type of `primitive/any`
        # and the body says the type was "eliminated in v3.12 — uninstall uses empty
        # params". The header is the stale one, and it is the same sentence as the §9.2
        # operations-table drift already filed.

        # ── §3.5 ────────────────────────────────────────────────────────────────
        (MAP_ARGS, _type_def(MAP_ARGS, [
            ("collection", _ref("system/hash")),
            ("fn", _ref("system/hash")),
        ])),

        # `fn`, not `predicate` — renamed at F11 (v3.19) for uniformity with map/fold.
        (FILTER_ARGS, _type_def(FILTER_ARGS, [
            ("collection", _ref("system/hash")),
            ("fn", _ref("system/hash")),
        ])),

        (FOLD_ARGS, _type_def(FOLD_ARGS, [
            ("collection", _ref("system/hash")),
            ("fn", _ref("system/hash")),
            ("initial", _ref("system/hash")),
        ])),

        (RANGE_ARGS, _type_def(RANGE_ARGS, [
            ("n", _ref("system/hash")),
        ])),

        (GROUP_BY_ARGS, _type_def(GROUP_BY_ARGS, [
            ("collection", _ref("system/hash")),
            ("fn", _ref("system/hash")),
        ])),

        # §3.5 v3.25 restored `key` into the result shape; the v3.24 fold had narrowed it
        # away.
        (GROUP, _type_def(GROUP, [
            ("key", _ref("primitive/any")),
            ("members", _array(_ref("primitive/any"))),
        ])),

        # v3.27: ONE hash of an expression, uniform with every sibling collection
        # argument — not an array of hashes.
        (CONCAT_ARGS, _type_def(CONCAT_ARGS, [
            ("collections", _ref("system/hash")),
        ])),

        (ASSOC_ARGS, _type_def(ASSOC_ARGS, [
            ("collection", _ref("system/hash")),
            ("index", _ref("system/hash")),
            ("value", _ref("system/hash")),
        ])),

        (STORE_ARGS, _type_def(STORE_ARGS, [
            ("path", _ref("system/tree/path")),
            ("value", _ref("system/hash")),
        ])),
    ]


def compute_type_entities() -> list[tuple[str, Entity]]:
    """``(type_name, system/type entity)`` for each of the 33 — the materialised form."""
    return [(name, Entity.make("system/type", data)) for name, data in compute_type_defs()]


def publish_compute_types(peer) -> list[str]:
    """Bind the type entities at ``system/type/{name}``.

    Returns the absolute paths written, so the caller reports what it installed rather
    than asserts what it intended to. I1 (owned-namespace containment) holds structurally:
    every path is ``system/type/`` plus a name from :data:`ALL_TYPES`, and
    ``system/type/*`` is the core's shared type index every extension writes into by
    design.
    """
    written: list[str] = []
    for name, ent in compute_type_entities():
        path = "/" + peer.local_peer + "/system/type/" + name
        peer.store.bind(path, ent)
        written.append(path)
    return written


def compute_entity(entity_type: str, data: Any) -> Entity:
    """Build one of our own entities without reaching for ``Entity.make`` at each site.

    Present in both ports because `tools/sdk-parity.py` compares the union: a helper in
    one port and not the other is drift even when it is trivial, and the class of
    difference that gate exists to catch is exactly the trivial one nobody decided.
    """
    return Entity.make(entity_type, data)

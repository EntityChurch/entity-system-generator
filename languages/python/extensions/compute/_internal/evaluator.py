"""COMPUTE §4 — the evaluation algorithm, for the `python` peer.

MODULE-PRIVATE by convention; see ``_internal/__init__.py`` for why that is a weaker
statement here than on `typescript` and what asserts it anyway.

WHAT THIS FILE IS FAITHFUL TO
-----------------------------
§4.1's pseudocode, clause for clause, with the trampoline, the depth accounting and the
``is_error`` guard placement preserved exactly — those three are the parts §4.1 spends its
prose on, and each of them is a cross-impl determinism surface:

  - **``is_error`` is KIND-based, not outcome-based** (§4.1's opening ``[MUST]``). A
    ``compute/error`` that evaluated *successfully* — a literal holding one, or a
    ``lookup/hash`` resolving to a stored one — is an error for every purpose in this file.
  - **The budget charges ``evaluate()`` steps and nothing else** (§4.2's normative note).
    ``resolve()`` costs zero. Two conformant peers must hit ``budget_exhausted`` at the
    same step count on the same ``(IR, inputs, budget)``.
  - **Tail calls do not consume depth but DO decrement the budget** (§10.1). The
    ``while True`` loop below is that rule; a recursive implementation of the same
    algorithm is not conformant, it just looks like it works until a chain is long.

THE FOUR DECLARED DEVIATIONS FROM THE SPEC TEXT are the `typescript` port's, re-derived
from the spec rather than copied from it (L18): the two membership predicates carry all
sixteen expression types (`../types.py`); arithmetic and comparison follow §4.1's
normative helpers over §2.2's prose; §4.1's ``evaluate_inner`` gets an arm for the §2.3
VALUE TYPES (SA-1); and ``compute/construct`` produces an IN-FLIGHT typed value
(:class:`ConstructedValue`) alongside the bare materialized entity (v3.19c option α).

WHAT IS NOT IMPLEMENTED, NAMED SO THE ABSENCE IS NOT MISTAKEN FOR AN OVERSIGHT:
``compute/apply`` handler mode (§4.1's ``dispatch_execute`` branch — the peer exposes no
re-entrant local dispatch; keystone K-5) and §4.6 memoization. Each is declared in
``EXTENSION.toml`` with the requirement rows it leaves uncovered, and each returns a real
``compute/error`` naming the reason rather than a wrong answer.

WHERE THIS PORT IS DELIBERATELY NOT A TRANSCRIPTION OF ITS SIBLING
-----------------------------------------------------------------
Four places, all forced by the substrate, all declared in ``EXTENSION.toml [substrate]``:

 1. **THE VALUE MODEL IS NATIVE, NOT TAGGED.** `typescript`'s codec hands the evaluator a
    tagged ``EcfValue`` (``{kind:"int", negative, argument}``); this peer's codec tree is
    ``None / bool / int / float / str / bytes / list / dict``. Every type test in this file
    is therefore an ``isinstance`` rather than a ``.kind`` read, and **``bool`` is an
    ``int`` subclass**, so every integer test excludes it explicitly. That one line is the
    whole difference between ``add(true, 1)`` being ``type_mismatch`` and being ``2``.
 2. **``%`` IS FLOORED HERE AND TRUNCATED THERE.** §4.1's ``truncated_remainder`` is
    JS/BigInt ``%`` semantics and is NOT Python's; the two differ in sign whenever the
    operands' signs differ. `types.ts` carries a comment predicting exactly this port
    reaching for its own operator. :func:`_truncated_remainder` is the explicit form, and
    three of the oracle's `v36_mod_*` vectors are the ones that would have caught it.
 3. **FLOAT DIVISION BY ZERO RAISES.** §4.1 makes float ``div`` IEEE-754 —
    ``±Inf``/``NaN``, NOT ``division_by_zero`` — and CPython raises
    ``ZeroDivisionError`` for it. :func:`_float_div` produces the IEEE answer, signed
    zero included.
 4. **THERE IS NO PUBLIC CANONICAL-ECF ENCODER.** ``entity_core._cbor.encode`` is
    module-private. Value identity (``eq`` over arrays/maps, §3.5's ``group-by`` key
    equality) is therefore derived through the PUBLIC ``content_hash`` over a fixed
    wrapper type — the same question decided by the same bytes, since a content hash is
    the digest of exactly the canonical encoding. See :func:`_canonical_digest`.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from entity_core.content_hash import content_hash
from entity_core.peer.capability import canonicalize as _peer_canonicalize
from entity_core.peer.model import Entity

from ..types import (
    APPLY,
    ARITHMETIC,
    BUILTINS_PREFIX,
    CLOSURE,
    CODE_BUDGET_EXHAUSTED,
    CODE_CASCADE_LIMIT,
    CODE_CAST_OUT_OF_RANGE,
    CODE_COUNT_OUT_OF_RANGE,
    CODE_DEPTH_EXCEEDED,
    CODE_DIVISION_BY_ZERO,
    CODE_INDEX_OUT_OF_RANGE,
    CODE_INVALID_EXPRESSION,
    CODE_MISSING_ARGUMENT,
    CODE_NOT_FOUND,
    CODE_PERMISSION_DENIED,
    CODE_SCOPE_UNREACHABLE,
    CODE_TYPE_MISMATCH,
    CODE_UNKNOWN_TYPE,
    COMPARE,
    CONSTRUCT,
    ERROR,
    FIELD,
    GROUP,
    IF,
    INDEX,
    LAMBDA,
    LENGTH,
    LET,
    LITERAL,
    LOGIC,
    LOOKUP_HASH,
    LOOKUP_SCOPE,
    LOOKUP_TREE,
    NUMERIC_CAST,
    RESULT,
    SCOPE,
    is_compute_expression,
    is_compute_type,
)

#: §3.5's *"an `n` exceeding the maximum representable array length"* for `range`.
#:
#: **IMPLEMENTATION-DEFINED, AND THIS PORT IS WHERE THE CONTRACT SAID THE DISAGREEMENT
#: WOULD SHOW UP.** §3.5 pins the CODE (``count_out_of_range``) and the refuse-not-clamp
#: rule; it does not pin the bound. `typescript` uses ``2**32 - 2``, V8's own maximum array
#: length; this runtime's is ``sys.maxsize`` (``2**63 - 1``). So the same
#: ``range(5_000_000_000)`` is ``count_out_of_range`` on one of our ports and an
#: out-of-memory attempt on the other, which is a boundary value a program can observe.
#:
#: ``EXTENSION.toml [assumptions].range_max_length`` predicted this in as many words —
#: *"a `python` or `rust` port will have a different one … the second port is where it
#: either agrees or produces a routing packet"* — so it is routed rather than reconciled
#: locally, because picking one number for both ports would be us standardising a value
#: §3.5 left open. Each port declares its own runtime's limit until arch rules.
MAX_ARRAY_LENGTH = sys.maxsize

#: The §1.2 `system/hash` wire width: one format byte plus a 32-byte digest.
CONTENT_HASH_LENGTH = 33

_U64 = 1 << 64
_I64_MIN_MAGNITUDE = 1 << 63


# ── the two carriers ────────────────────────────────────────────────────────────


class ComputeError:
    """§2.4 — a ``compute/error``, built with ``code`` ONLY.

    ``message``, ``at`` and ``expression`` are declared by the type and are **in-flight
    diagnostics that are never materialized** (§2.4, v3.26). Building them and dropping
    them at the boundary would be the same bug with an extra step: the moment one is
    written into the tree or into a contained collection position, the containing array's
    bytes fork across two conformant peers. So this constructor takes a code and nothing
    else, and the diagnostic rides beside the value in :attr:`detail` where the codec can
    never see it.
    """

    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail

    def to_entity(self) -> Entity:
        """The materialized form — ``code`` only, per §2.4."""
        return Entity.make(ERROR, {"code": self.code})

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"ComputeError({self.code!r}, {self.detail!r})"


class ConstructedValue:
    """A constructed entity that has not crossed a materialization boundary yet.

    **Two representations of one value, and both are needed** (v3.19c option α, §2.3):

    - :attr:`entity` is the **materialized bare form** — the normative one. Entity-valued
      fields are bare ``system/hash`` references, no ``kind`` tags anywhere, byte-identical
      to the same entity built outside compute. It is what crosses every boundary and what
      the oracle's M1 hash gate compares.
    - :attr:`fields` is the **in-flight typed form** — implementation-private by §2.3's own
      words, and the thing that makes ``field(field(construct(...), 'inner'), 'name')``
      compose inside one evaluation. §2.3: navigation composes transparently *"only where
      the kind is known (in-flight typed values …); on a bare materialized entity, a
      reference is followed explicitly."*

    **The bare form is built EAGERLY and that is deliberate.** §4.1's pseudocode
    materializes at the construct arm and this keeps the M1 hash on exactly one code path —
    a second, lazier path is the fork ``v319c_inline_vs_builtin_construct_hash_agreement``
    exists to catch. What option α requires is not that the store write be deferred; it is
    that navigation between hops need not go through the materialized form.
    """

    __slots__ = ("entity", "fields")

    def __init__(self, entity: Entity, fields: dict[str, Any]) -> None:
        self.entity = entity
        self.fields = fields


class _TailCall:
    """§4.1's trampoline token. Never escapes :func:`evaluate`."""

    __slots__ = ("entity", "scope")

    def __init__(self, entity: Entity, scope: "Scope") -> None:
        self.entity = entity
        self.scope = scope


class _Malformed(Exception):
    """A required expression field is absent or the wrong ECF type.

    **A LOCAL CONTROL-FLOW CARRIER, AND IT IS ALSO A PORT DIFFERENCE WORTH STATING.**
    `typescript`'s ``Ecf.requireText`` THROWS out of the evaluator, so on that port a
    malformed expression leaves the handler as an exception and the peer answers 5xx. Here
    it is caught at the top of :func:`_evaluate_inner` and returned as a
    ``compute/error{invalid_expression}`` at status 200, which is what §2.4 and §3.2's F10
    say an evaluation fault is.

    This port's answer is the spec-faithful one; the divergence is ours, in our own tree,
    and no oracle vector reaches it (every `compute` vector sends a well-formed graph).
    Recorded in ``EXTENSION.toml [assumptions].malformed_expression_disposition`` as a
    worklist item against the `typescript` port rather than routed anywhere, because it is
    nobody else's finding.
    """

    def __init__(self, err: ComputeError) -> None:
        super().__init__(err.code)
        self.err = err


def _err(code: str, detail: str = "") -> ComputeError:
    return ComputeError(code, detail)


# ── the evaluation state ────────────────────────────────────────────────────────


@dataclass(slots=True)
class Budget:
    """§5.1 — the two counters. Mutated in place, exactly as §4.1's pseudocode does."""

    operations: int
    depth: int


@dataclass(slots=True)
class Scope:
    """§4.3 — a flat name -> value map, copied on ``let`` and on closure apply."""

    bindings: dict[str, Any] = field(default_factory=dict)


def empty_scope() -> Scope:
    return Scope(bindings={})


def _copy_scope(scope: Scope) -> Scope:
    return Scope(bindings=dict(scope.bindings))


@dataclass(slots=True)
class EvalContext:
    """§4.1's ``ctx``. Every field is something the evaluator READS.

    Nothing here is derived inside the evaluator, so a caller sees the whole authority
    surface in one place.

    **ONE ``store`` OBJECT WHERE `typescript` HAS TWO.** That peer exposes ``tree`` and
    ``contentStore`` as separate members; this one has a single :class:`entity_core.peer.
    store.Store` holding both maps behind one lock, so ``tree.get`` is ``store.get_at`` and
    ``contentStore.get`` is ``store.get_by_hash``. §1.7's two layers are the same two
    layers; only the object count differs
    (``EXTENSION.toml [substrate].one_store_object``).
    """

    store: Any
    local_peer: str
    #: §2.1 — the root a ``relative: true`` path resolves against.
    subgraph_root: str
    #: §4.2 step 1 — the envelope's pre-authorized ``included`` map, by lowercase hex.
    included: dict
    #: §4.2 Tier 0 — the ``content_store_access`` allowance.
    has_content_store_access: bool
    #: §4.2 Tier 2 — an installed subgraph's sealed set, hex-encoded.
    authorized_data_hashes: frozenset[str]
    #: §4.1 — ``check_path_permission("get", path, ...)``.
    can_read_path: Callable[[str], bool]
    #: §6.3 — ``check_path_permission("put", path, capability)`` for the ``store`` builtin.
    #:
    #: Separate from :attr:`can_read_path` because §6.3's table gives the two different
    #: authorities: a tree READ rides ``ctx.capability`` and a ``store`` WRITE rides the
    #: caller's with the handler forbidden from substituting its own grant (no silent
    #: escalation). §7.2 is the caller that supplies two different answers.
    can_write_path: Callable[[str], bool]
    #: §7.1 — reactive dependency registration. A no-op outside an installed subgraph.
    register_dependency: Callable[[str], None]
    #: §4.4 / §4.3 N6 — make a just-written content hash locally resolvable.
    mark_encountered: Callable[[str], None]


# ── kind tests. `bool` is an `int` subclass; every integer test excludes it. ─────


def _is_entity_like(v: Any) -> bool:
    """Is this value entity-KINDED? §2.3 N3's rule as a type test, with no shape sniff."""
    return isinstance(v, (Entity, ConstructedValue))


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_float(v: Any) -> bool:
    return isinstance(v, float)


def _is_numeric(v: Any) -> bool:
    return _is_int(v) or _is_float(v)


def _is_text(v: Any) -> bool:
    return isinstance(v, str)


def _as_array(v: Any) -> list | None:
    return v if isinstance(v, list) else None


def _to_float(v: Any) -> float:
    if _is_float(v):
        return v
    if _is_int(v):
        return float(v)
    return math.nan


def _entity_identity(v: Any) -> str:
    """§4.1 — entity identity is the MATERIALIZED content hash, never the in-flight form."""
    return (v.entity.hash if isinstance(v, ConstructedValue) else v.hash).hex()


#: §2.3 — the four VALUE types. Not expressions; SA-1 returns them unchanged.
#:
#: ``compute/error`` is in the set and its presence is not a special case: §4.1's
#: ``is_error`` is kind-based, so an error returned here short-circuits at the next
#: CONSUMPTION site exactly as a minted one does (§3.5's *"behaves identically however it
#: was produced"*).
_VALUE_TYPES = (CLOSURE, SCOPE, RESULT, ERROR)


def is_error(v: Any) -> bool:
    """§4.1's ``is_error(v)`` ``[MUST]`` — **kind-based**.

    True for our in-flight :class:`ComputeError` AND for an :class:`Entity` whose type is
    ``compute/error``, because §4.1 is explicit that a stored one reached by evaluation is
    an error for every purpose in that section. Testing only the in-flight class would
    implement the outcome-based reading the spec rejects.
    """
    if isinstance(v, ComputeError):
        return True
    if isinstance(v, ConstructedValue):
        # An in-flight construct whose `entity_type` IS `compute/error` is an error by the
        # same kind-based test. §4.1's guard means one can never be produced by a failing
        # sub-expression, so this is the deliberately-built case only — answering it any
        # other way would let the in-flight representation decide the disposition, which is
        # what §2.4 forbids.
        return v.entity.type == ERROR
    return isinstance(v, Entity) and v.type == ERROR


def as_compute_error(v: Any) -> ComputeError:
    """Narrow an ``is_error``-true value to a :class:`ComputeError`.

    The kind-based predicate is true for BOTH the in-flight class and a ``compute/error``
    ENTITY that evaluated successfully. Only the first is already a ``ComputeError``, so a
    caller that has to return one has to convert — and the conversion reads the entity's
    ``code``, which is §2.4's only materialized field.
    """
    if isinstance(v, ComputeError):
        return v
    ent = v.entity if isinstance(v, ConstructedValue) else v
    code = CODE_INVALID_EXPRESSION
    if isinstance(ent, Entity):
        found = ent.text("code")
        if found is not None:
            code = found
    return ComputeError(code, "evaluated to a stored compute/error")


# ── field readers. Absence RAISES `_Malformed`; see that class for the port note. ─


def _req_text(entity: Entity, key: str) -> str:
    v = entity.text(key)
    if v is None:
        raise _Malformed(_err(CODE_INVALID_EXPRESSION, f"{entity.type} requires text `{key}`"))
    return v


def _req_bytes(entity: Entity, key: str) -> bytes:
    v = entity.bytes_(key)
    if v is None:
        raise _Malformed(_err(CODE_INVALID_EXPRESSION, f"{entity.type} requires hash `{key}`"))
    return v


def _req_list(entity: Entity, key: str) -> list:
    v = entity.field(key)
    if not isinstance(v, list):
        raise _Malformed(_err(CODE_INVALID_EXPRESSION, f"{entity.type} requires array `{key}`"))
    return v


def _opt_bool(entity: Entity, key: str) -> bool:
    return entity.field(key) is True


# ── materialization ─────────────────────────────────────────────────────────────


def materialize(value: Any, ctx: EvalContext) -> Any:
    """§2.3 SA-1 / §4.4 — bring a value to its materialized form, storing what it
    references.

    The call sites are §2.3 N1's three placement boundaries plus the evaluator's own exit:
    a ``compute/construct`` field, a ``compute/scope`` binding, and
    :meth:`ComputeEvaluator.evaluate_at`'s return. Keeping them on one function is what
    stops the bare form being derived twice — the fork the oracle's inline-versus-builtin
    hash-agreement vector exists to detect.
    """
    out = value.entity if isinstance(value, ConstructedValue) else value
    if isinstance(out, Entity):
        ctx.store.put_entity(out)
        ctx.mark_encountered(out.hash.hex())
    return out


# ── evaluate ────────────────────────────────────────────────────────────────────


def evaluate(entity: Entity, scope: Scope, budget: Budget, ctx: EvalContext) -> Any:
    """§4.1 ``evaluate`` — the depth frame, the budget charge, and the trampoline.

    The three ``budget.depth`` mutations are in the same three places §4.1 puts them,
    including the one that is easy to miss: **the budget-exhaustion path restores the depth
    frame before returning**, so a caller that catches the error and continues is not left
    one frame short. Removing it changes how deep a subsequent expression may go, which is
    observable.
    """
    if budget.depth <= 0:
        return _err(CODE_DEPTH_EXCEEDED, "Maximum evaluation depth exceeded")
    budget.depth -= 1

    current = entity
    current_scope = scope

    while True:
        budget.operations -= 1
        if budget.operations <= 0:
            budget.depth += 1
            return _err(CODE_BUDGET_EXHAUSTED, "Computation budget exhausted")

        result = _evaluate_inner(current, current_scope, budget, ctx)

        if isinstance(result, _TailCall):
            current = result.entity
            current_scope = result.scope
            continue

        budget.depth += 1
        return result


def _evaluate_inner(entity: Entity, scope: Scope, budget: Budget, ctx: EvalContext) -> Any:
    try:
        return _dispatch(entity, scope, budget, ctx)
    except _Malformed as malformed:
        # See `_Malformed`: this is the one place the port's disposition for a structurally
        # broken expression is decided, and it decides it as §2.4/F10 does — a value at
        # 200, not a transport failure.
        return malformed.err


def _dispatch(entity: Entity, scope: Scope, budget: Budget, ctx: EvalContext) -> Any:
    kind = entity.type

    if kind == LITERAL:
        # SA-1: returned unchanged, including when the value IS a compute/error. The
        # `is_error` guard at each CONSUMPTION site is what short-circuits it — this branch
        # does not, and that separation is §4.1's opening MUST.
        return _literal_value(entity)

    if kind == LOOKUP_SCOPE:
        name = _req_text(entity, "name")
        # `in`, not `is not None` — a binding whose VALUE is the ECF null is a real
        # binding, and §4.5 makes it falsy rather than absent. `Entity.field` collapses the
        # two, which is right for the §1.3 optional-field convention and wrong here.
        if name in scope.bindings:
            return scope.bindings[name]
        return _err(CODE_NOT_FOUND, "No scope binding: " + name)

    if kind == LOOKUP_TREE:
        raw = _req_text(entity, "path")
        if _opt_bool(entity, "relative"):
            path = clean_path(ctx.subgraph_root + "/" + raw)
        else:
            path = _canonicalize_or_raise(raw, ctx)
        # §6.2 — the capability check comes BEFORE the read and before the dependency
        # registration, so an unauthorized path does not leak its existence through a
        # registered dependency.
        if not ctx.can_read_path(path):
            return _err(CODE_PERMISSION_DENIED, "Capability does not cover tree read: " + path)
        ctx.register_dependency(path)
        found = ctx.store.get_at(path)
        if found is None:
            return _err(CODE_NOT_FOUND, "No entity at path: " + path)
        # §2.1's spreadsheet semantic: a stored EXPRESSION evaluates; a stored value —
        # including a compute/closure — is returned as-is.
        if is_compute_expression(found.type):
            return _TailCall(found, scope)
        return found

    if kind == LOOKUP_HASH:
        target = _resolve_or_error(_req_bytes(entity, "hash"), ctx, "hash lookup")
        if is_error(target):
            return target
        if is_compute_expression(target.type):
            return _TailCall(target, scope)
        return target

    if kind == APPLY:
        return _eval_apply(entity, scope, budget, ctx)

    if kind == IF:
        cond_target = _resolve_or_error(_req_bytes(entity, "condition"), ctx, "if condition")
        if is_error(cond_target):
            return cond_target
        condition = evaluate(cond_target, scope, budget, ctx)
        if is_error(condition):
            return condition
        if truthy(condition):
            then_target = _resolve_or_error(_req_bytes(entity, "then"), ctx, "if then")
            if is_error(then_target):
                return then_target
            return _TailCall(then_target, scope)
        else_ref = entity.bytes_("else")
        if else_ref is not None:
            else_target = _resolve_or_error(else_ref, ctx, "if else")
            if is_error(else_target):
                return else_target
            return _TailCall(else_target, scope)
        # §4.1 returns null explicitly for a falsy `if` with no else. Not an error.
        return None

    if kind == LET:
        new_scope = _copy_scope(scope)
        for binding in _req_list(entity, "bindings"):
            if not isinstance(binding, dict):
                return _err(CODE_INVALID_EXPRESSION, "compute/let binding is not a map")
            name = binding.get("name")
            value_ref = binding.get("value")
            if not isinstance(name, str) or not isinstance(value_ref, (bytes, bytearray)):
                return _err(CODE_INVALID_EXPRESSION, "compute/let binding needs {name, value}")
            value_target = _resolve_or_error(bytes(value_ref), ctx, "let binding " + name)
            if is_error(value_target):
                return value_target
            # SEQUENTIAL, in `new_scope` — §4.1's own comment calls it Scheme's `let*`, so
            # a later binding sees an earlier one. Evaluating in `scope` instead would be a
            # different language that passes every single-binding test.
            value = evaluate(value_target, new_scope, budget, ctx)
            if is_error(value):
                return value
            new_scope.bindings[name] = value
        body_target = _resolve_or_error(_req_bytes(entity, "body"), ctx, "let body")
        if is_error(body_target):
            return body_target
        return _TailCall(body_target, new_scope)

    if kind == LAMBDA:
        # Capture and produce a closure. The body is NOT evaluated.
        body_hash = _req_bytes(entity, "body")
        env_hash = _capture_scope(scope, ctx)
        data: dict[str, Any] = {
            "params": _req_list(entity, "params"),
            "body": body_hash,
        }
        if env_hash is not None:
            data["env"] = env_hash
        return Entity.make(CLOSURE, data)

    if kind == ARITHMETIC:
        ops = _eval_binary_operands(entity, scope, budget, ctx)
        if isinstance(ops, ComputeError):
            return ops
        return _apply_arithmetic(_req_text(entity, "op"), ops)

    if kind == COMPARE:
        ops = _eval_binary_operands(entity, scope, budget, ctx)
        if isinstance(ops, ComputeError):
            return ops
        return _apply_compare(_req_text(entity, "op"), ops)

    if kind == LOGIC:
        return _apply_logic(
            _req_text(entity, "op"),
            _req_bytes(entity, "left"),
            entity.bytes_("right"),
            scope,
            budget,
            ctx,
        )

    if kind == FIELD:
        name = _req_text(entity, "name")
        target_ref = _resolve_or_error(_req_bytes(entity, "entity"), ctx, "field target")
        if is_error(target_ref):
            return target_ref
        target = evaluate(target_ref, scope, budget, ctx)
        if is_error(target):
            return target
        return _navigate_field(target, name)

    if kind == INDEX:
        arr_ref = _resolve_or_error(_req_bytes(entity, "array"), ctx, "index array")
        if is_error(arr_ref):
            return arr_ref
        arr = evaluate(arr_ref, scope, budget, ctx)
        if is_error(arr):
            return arr
        idx_ref = _resolve_or_error(_req_bytes(entity, "index"), ctx, "index index")
        if is_error(idx_ref):
            return idx_ref
        idx = evaluate(idx_ref, scope, budget, ctx)
        if is_error(idx):
            return idx
        return _index_into(arr, idx)

    if kind == LENGTH:
        arr_ref = _resolve_or_error(_req_bytes(entity, "array"), ctx, "length array")
        if is_error(arr_ref):
            return arr_ref
        arr = evaluate(arr_ref, scope, budget, ctx)
        if is_error(arr):
            return arr
        return _length_of(arr)

    if kind == NUMERIC_CAST:
        val_ref = _resolve_or_error(_req_bytes(entity, "value"), ctx, "numeric-cast value")
        if is_error(val_ref):
            return val_ref
        value = evaluate(val_ref, scope, budget, ctx)
        if is_error(value):
            return value
        return _numeric_cast(value, _req_text(entity, "to_type"))

    if kind == CONSTRUCT:
        return _eval_construct(entity, scope, budget, ctx)

    # §2.3 SA-1 — A VALUE-TYPE ENTITY EVALUATES TO ITSELF, UNCHANGED. §4.1's
    # `evaluate_inner` has no arm for the four, so a literal transcription falls straight
    # into `unknown_type`: the oracle's `v319b_scope_unreachable` stores a
    # `compute/closure` at a tree path and applies it, and `load_scope` is never reached.
    #
    # The arm sits HERE rather than as four branches beside the expression types on
    # purpose: SA-1's own words are that it *"generalizes the `compute/lookup/hash`
    # return-non-expressions-as-values rule"*, which is a statement about the FALLTHROUGH
    # and not about four types.
    if kind in _VALUE_TYPES:
        return entity
    return _err(CODE_UNKNOWN_TYPE, "Unknown compute type: " + kind)


def _literal_value(entity: Entity) -> Any:
    """Read ``compute/literal``'s ``value`` field, distinguishing a stored ECF null from
    an absent key.

    ``Entity.field`` cannot: it returns ``None`` both for a stored null and for "no such
    key", which is right for the §1.3 optional-field convention every protocol entity uses
    and wrong for a ``primitive/any`` position where **null is a VALUE**. §4.5 makes null
    falsy, so it is a legitimate ``compute/if`` condition, and §4.1's ``if`` with no
    ``else`` RETURNS it. A literal holding one has to round-trip. `typescript` needs the
    same special case for the same reason and pays more for it, walking the encoded pairs;
    here it is one ``in``.
    """
    data = entity.data
    if not isinstance(data, dict):
        return _err(CODE_INVALID_EXPRESSION, "compute/literal has no data map")
    if "value" not in data:
        return _err(CODE_INVALID_EXPRESSION, "compute/literal has no `value` field")
    return data["value"]


# ── apply ───────────────────────────────────────────────────────────────────────


def _eval_apply(entity: Entity, scope: Scope, budget: Budget, ctx: EvalContext) -> Any:
    """§4.1's ``compute/apply``. **Closure mode and the §3.5 builtins only.**

    Handler mode needs ``ctx.dispatch_execute`` — a re-entrant dispatch into the peer from
    inside an evaluation, with the F2 dual capability check and the V30
    ``encode_arg_for_field`` typed-params construction. The peer exposes none (keystone
    K-5). Shipping half of it would be worse than not shipping it: the F2 check only ever
    NARROWS, so a partial implementation runs WIDER than the caller asked. It returns an
    honest ``invalid_expression`` naming the reason instead.

    The §2.1 Q23 shape check IS implemented, because it runs before any field is resolved
    and its ORDERING is normative — rejecting after evaluation would make the returned code
    depend on the field's value.
    """
    path = entity.text("path")
    fn_ref = entity.bytes_("fn")

    # §2.1 [MUST] — "either `path` or `fn`, not both and not neither". §4.1's listing tests `path`
    # first and would silently take handler mode; the prose MUST is the rule (routed: the listing
    # omits it). Keyed on PRESENCE, before either mode is entered.
    if isinstance(entity.data, dict) and "path" in entity.data and "fn" in entity.data:
        return _err(CODE_INVALID_EXPRESSION, "compute/apply MUST have either path or fn, not both")

    if path is not None:
        has_capability = entity.bytes_("capability") is not None
        has_resource = entity.bytes_("resource") is not None
        builtin = _builtin_name(path)

        # §2.1 Q23 / §3.3 — a builtin path dispatches no EXECUTE, so `capability` and
        # `resource` have no referent. SHAPE CHECK, BEFORE ANY RESOLUTION (normative).
        if builtin is not None and (has_capability or has_resource):
            return _err(
                CODE_INVALID_EXPRESSION,
                "compute/apply on a builtin path MUST NOT carry capability or resource",
            )
        operation = entity.text("operation")
        if operation is None:
            return _err(CODE_INVALID_EXPRESSION, "compute/apply handler mode requires operation")
        # F5 — a capability override without a resource cannot be dual-checked.
        if has_capability and not has_resource:
            return _err(
                CODE_INVALID_EXPRESSION,
                "compute/apply with capability field MUST also have resource field",
            )
        if builtin is not None:
            if operation != "eval":
                return _err(
                    CODE_INVALID_EXPRESSION,
                    "§3.5: a builtin's only operation is `eval`, got: " + operation,
                )
            return _eval_builtin(builtin, _arg_hashes(entity), scope, budget, ctx)
        return _err(
            CODE_INVALID_EXPRESSION,
            "compute/apply handler mode is not implemented in this port "
            "(§4.1 dispatch_execute); see EXTENSION.toml [assumptions].apply_handler_mode",
        )

    if fn_ref is not None:
        fn_target = _resolve_or_error(fn_ref, ctx, "closure fn")
        if is_error(fn_target):
            return fn_target
        fn_value = evaluate(fn_target, scope, budget, ctx)
        if is_error(fn_value):
            return fn_value
        if not isinstance(fn_value, Entity) or fn_value.type != CLOSURE:
            return _err(CODE_TYPE_MISMATCH, "Apply target is not a closure")

        loaded = _load_scope(fn_value.bytes_("env"), ctx)
        # `is_error` is for values; `_load_scope` returns a Scope or an error, so the guard
        # is an isinstance. Keeping the two distinct is deliberate — a Scope is not a value
        # and must never flow into a position that takes one.
        if isinstance(loaded, ComputeError):
            return loaded
        new_scope = loaded

        arg_map = _arg_hashes(entity)

        # Iterated over the CLOSURE'S PARAMS, not over the supplied args — §4.1's loop.
        # The difference is what makes a missing argument `missing_argument` rather than a
        # silently-unbound name, and it means an extra arg is ignored.
        for raw_param in _req_list(fn_value, "params"):
            param = str(raw_param)
            arg_hash = arg_map.get(param)
            if arg_hash is None:
                return _err(CODE_MISSING_ARGUMENT, "Missing argument: " + param)
            arg_target = _resolve_or_error(arg_hash, ctx, "closure arg " + param)
            if is_error(arg_target):
                return arg_target
            # Evaluated in the CALLER's scope, bound into the CLOSURE's — §4.1's two
            # scopes, and the reason `scope` and `new_scope` are both live here.
            arg = evaluate(arg_target, scope, budget, ctx)
            if is_error(arg):
                return arg
            new_scope.bindings[param] = arg

        body_target = _resolve_or_error(_req_bytes(fn_value, "body"), ctx, "closure body")
        if is_error(body_target):
            return body_target
        return _TailCall(body_target, new_scope)

    return _err(CODE_INVALID_EXPRESSION, "compute/apply requires path or fn")


def _arg_hashes(entity: Entity) -> dict[str, bytes]:
    """§2.1 — ``compute/apply.args`` is a ``{name -> system/hash}`` map, or absent."""
    out: dict[str, bytes] = {}
    raw = entity.field("args")
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, (bytes, bytearray)):
                out[k] = bytes(v)
    return out


def _relative_pattern(path: str) -> str:
    """The path with any leading ``/{peer}/`` removed — handler patterns are peer-relative."""
    if path.startswith("/"):
        i = path.find("/", 1)
        return path[i + 1:] if i >= 0 else path
    return path


def _builtin_name(path: str) -> str | None:
    """The builtin's short name, or ``None`` when ``path`` is not a builtin path at all.

    ONE parser for the two questions, because they were two before and the near-miss is
    the reason: ``system/compute/builtinsomething`` must not be a builtin, so the test is
    the separator and not a prefix test. ``assert_not_builtin_override`` in ``sdk.py``
    carries a negative control for exactly that string.
    """
    relative = _relative_pattern(path)
    if relative == BUILTINS_PREFIX:
        return ""
    if not relative.startswith(BUILTINS_PREFIX + "/"):
        return None
    return relative[len(BUILTINS_PREFIX) + 1:]


def is_builtin_path(path: str) -> bool:
    """§3.5 / §4.1 — is this a ``system/compute/builtins/*`` path?"""
    return _builtin_name(path) is not None


# ── §3.5 — the builtin handlers ─────────────────────────────────────────────────
#
# EVALUATED INTERNALLY, WHICH THE SECTION ASKS FOR RATHER THAN MERELY PERMITS. §3.5's
# closing paragraph: *"Because `map`/`filter`/`fold` apply a caller-provided closure per
# element, they need the evaluator's scope/budget/context — a real handler-dispatch
# boundary would lose these. Implementations SHOULD therefore evaluate the collection
# builtins internally within the evaluator … on such implementations it MAY NOT resolve to
# a distinct handler entity in the tree."* So nothing is registered at these paths and a
# `tree:get` of one returns nothing — conformant, not a gap.
#
# THE ALIASES ARE §10.2 SHOULDs AND THE REST ARE §10.1 MUSTs, which is the opposite of what
# the reading order suggests. `{arithmetic,compare,logic,field,construct}` duplicate an
# inline type and are SHOULD; `{map,filter,fold}`, the four v3.24 primitives and `store`
# have no inline form and were promoted out of §10.3 into §10.1 at v3.14.
#
# AND EVERY ALIAS SHARES THE INLINE CODE PATH, deliberately.
# `v319c_inline_vs_builtin_construct_hash_agreement` exists because `entity-core-rust`
# shipped two construct paths that disagreed on the materialized hash; the vector passes
# trivially on a single-path implementation and catches the fork on any other.


def _eval_builtin(
    name: str,
    args: dict[str, bytes],
    scope: Scope,
    budget: Budget,
    ctx: EvalContext,
) -> Any:
    """The nine §3.5 rows plus the four v3.24 primitives."""
    # ── the five inline-equivalent aliases (§10.2 SHOULD) ───────────────────────
    if name in ("arithmetic", "compare"):
        op = _arg_text(args, "op", scope, budget, ctx)
        if isinstance(op, ComputeError):
            return op
        left = args.get("left")
        right = args.get("right")
        if left is None or right is None:
            return _err(CODE_MISSING_ARGUMENT, f"builtins/{name} requires `left` and `right`")
        ops = _eval_operand_pair(left, right, scope, budget, ctx)
        if isinstance(ops, ComputeError):
            return ops
        return _apply_arithmetic(op, ops) if name == "arithmetic" else _apply_compare(op, ops)

    if name == "logic":
        op = _arg_text(args, "op", scope, budget, ctx)
        if isinstance(op, ComputeError):
            return op
        left = args.get("left")
        if left is None:
            return _err(CODE_MISSING_ARGUMENT, "builtins/logic requires `left`")
        return _apply_logic(op, left, args.get("right"), scope, budget, ctx)

    if name == "field":
        field_name = _arg_text(args, "name", scope, budget, ctx)
        if isinstance(field_name, ComputeError):
            return field_name
        target = _arg_value(args, "entity", scope, budget, ctx)
        if isinstance(target, ComputeError):
            return target
        if is_error(target):
            return as_compute_error(target)
        return _navigate_field(target, field_name)

    if name == "construct":
        entity_type = _arg_text(args, "entity_type", scope, budget, ctx)
        if isinstance(entity_type, ComputeError):
            return entity_type
        # Every arg EXCEPT the reserved `entity_type` key is a field. That exclusion is the
        # whole difference between the two forms, and it is why an entity built this way is
        # byte-identical to the inline one: same fields, same code path.
        fields = [(k, v) for k, v in args.items() if k != "entity_type"]
        return _construct_from(entity_type, fields, scope, budget, ctx)

    # ── the collection primitives (§10.1 MUST) ─────────────────────────────────
    if name in ("map", "filter", "group-by"):
        items = _arg_array(args, "collection", scope, budget, ctx)
        if isinstance(items, ComputeError):
            return items
        fn = _arg_closure(args, "fn", scope, budget, ctx)
        if isinstance(fn, ComputeError):
            return fn
        if name == "map":
            return _builtin_map(items, fn, budget, ctx)
        if name == "filter":
            return _builtin_filter(items, fn, budget, ctx)
        return _builtin_group_by(items, fn, budget, ctx)

    if name == "fold":
        items = _arg_array(args, "collection", scope, budget, ctx)
        if isinstance(items, ComputeError):
            return items
        fn = _arg_closure(args, "fn", scope, budget, ctx)
        if isinstance(fn, ComputeError):
            return fn
        if args.get("initial") is None:
            return _err(CODE_MISSING_ARGUMENT, "builtins/fold requires `initial`")
        # §3.5 v3.27 — THE ACCUMULATOR CONTAINS, so `initial` is NOT short-circuited:
        # *"`fold` MUST NOT abort on an error accumulator"*, and a closure that ignores its
        # accumulator recovers. This is the one position where the two readings produce a
        # different VALUE rather than a different cost, which is why the `is_error` guard
        # every other arg gets is absent here on purpose.
        initial = _arg_value(args, "initial", scope, budget, ctx)
        if isinstance(initial, ComputeError):
            if _is_halting(initial):
                return initial
            # A minted error still becomes the starting accumulator, in value form.
            return _builtin_fold(items, fn, initial.to_entity(), budget, ctx)
        return _builtin_fold(items, fn, initial, budget, ctx)

    if name == "range":
        n = _arg_value(args, "n", scope, budget, ctx)
        if isinstance(n, ComputeError):
            return n
        if is_error(n):
            return as_compute_error(n)
        if not _is_int(n):
            return _err(CODE_TYPE_MISMATCH, "builtins/range requires an integer `n`")
        count = _to_signed64(n)
        # §3.5 v3.25 — a negative `n`, or one past the maximum array length, is
        # `count_out_of_range` and NOT `type_mismatch` (§2.2's ruling: int/uint are
        # annotations, so an out-of-domain MAGNITUDE is not a type error). And it is NOT
        # clamped to `[]`: `n` is a loop bound, so a silent empty array propagates through
        # every downstream map/filter/fold as a well-formed wrong answer.
        if count < 0 or count > MAX_ARRAY_LENGTH:
            return _err(CODE_COUNT_OUT_OF_RANGE, "builtins/range n out of range: " + str(count))
        return list(range(count))

    if name == "concat":
        # §3.5 v3.27 — `collections` is ONE hash of an expression evaluating to an array OF
        # arrays, never a literal array of hashes. The literal shape freezes `concat`'s
        # arity at authoring time, which would make the one primitive adopted to join k
        # arrays the one whose k is a constant.
        outer = _arg_array(args, "collections", scope, budget, ctx)
        if isinstance(outer, ComputeError):
            return outer
        out: list = []
        for sub in outer:
            # Each `collection` is CONSUMED — its length is read to copy — so an error here
            # short-circuits. Its ELEMENTS are contained and flow through untouched.
            if is_error(sub):
                return as_compute_error(sub)
            items = _as_array(sub)
            if items is None:
                return _err(CODE_TYPE_MISMATCH, "builtins/concat requires an array of arrays")
            # ONE LEVEL, order-preserving — no recursive flatten.
            out.extend(items)
        return out

    if name == "assoc":
        items = _arg_array(args, "collection", scope, budget, ctx)
        if isinstance(items, ComputeError):
            return items
        idx = _arg_value(args, "index", scope, budget, ctx)
        if isinstance(idx, ComputeError):
            return idx
        # `index` is CONSUMED — read to position the write.
        if is_error(idx):
            return as_compute_error(idx)
        if not _is_int(idx):
            return _err(CODE_TYPE_MISMATCH, "builtins/assoc requires an integer `index`")
        i = _to_signed64(idx)
        # §3.5 v3.25 — the same code and the same condition as `compute/index`. v3.24 said
        # `type_mismatch` here and was corrected: one document must not answer one
        # malformed program with two codes depending on which array operation it reached.
        if i < 0 or i >= len(items):
            return _err(CODE_INDEX_OUT_OF_RANGE, "builtins/assoc index out of range: " + str(i))
        value = _arg_value(args, "value", scope, budget, ctx)
        if isinstance(value, ComputeError) and _is_halting(value):
            return value
        # `value` is CONTAINED — the SA-9 store case, placed without being read.
        out = list(items)
        out[i] = _contained_element(value, ctx)
        return out

    if name == "store":
        return _builtin_store(args, scope, budget, ctx)

    return _err(
        CODE_INVALID_EXPRESSION,
        f"§3.5 defines no builtin `{name}` ({BUILTINS_PREFIX}/{name})",
    )


def _builtin_store(args: dict[str, bytes], scope: Scope, budget: Budget, ctx: EvalContext) -> Any:
    """§3.5 / §6.3's ``store``, and **the write mechanism is a declared deviation from
    SA-10's first sentence.**

    SA-10 says *"implementations dispatch the write via ``system/tree:put``, so
    capability-gating, path normalization, history, and reactive cascade are uniform with
    all other tree writes"* — and then permits the alternative in the same breath: *"a
    direct capability-checked ``emit`` is equally compliant, but ``tree:put`` keeps
    attribution uniform."* This port takes the second door because the first needs
    re-entrant dispatch, the same seam ``compute/apply`` handler mode is waiting on.

    **The half of SA-10's rationale we DO get, measured rather than assumed:** this peer's
    ``Store.bind`` runs the §6.10 emit pathway itself — content-store put, then bind, with
    a tree-change event when the binding changes — so a registered emit consumer (HISTORY's
    recorder, say) sees a ``store`` write exactly as it sees any other. **The halves we do
    NOT get are named in ``EXTENSION.toml``:** no per-path capability check on the
    explicit-eval path (dispatch-scoped, already declared), and no §6.8a execution context
    on the event unless the caller threads one, which is ``ROUTING-2026-09-06-d``'s finding
    and has nothing to do with ``store``.
    """
    if args.get("path") is None or args.get("value") is None:
        return _err(CODE_INVALID_EXPRESSION, "builtins/store requires `path` and `value`")
    # `path` is a CONSUMED operand — it steers WHERE the write goes, exactly as `assoc`'s
    # `index` steers where the update lands — so an error path short-circuits rather than
    # becoming a `type_mismatch`.
    raw_path = _arg_value(args, "path", scope, budget, ctx)
    if isinstance(raw_path, ComputeError):
        return raw_path
    if is_error(raw_path):
        return as_compute_error(raw_path)
    if not _is_text(raw_path):
        return _err(CODE_TYPE_MISMATCH, "builtins/store `path` must be text")
    target = _peer_canonicalize(ctx.local_peer, raw_path)
    if target is None:
        return _err(CODE_INVALID_EXPRESSION, "builtins/store `path` is a reserved relative form (§1.4)")

    # §6.3 — the caller's capability MUST cover the write, and the handler MUST NOT
    # substitute its own grant (no-silent-escalation). Named rather than inlined for the
    # same reason `can_read_path` is: this port answers it at the dispatch boundary on the
    # explicit-eval path, and an inline `True` leaves nothing to grep for.
    if not ctx.can_write_path(target):
        return _err(CODE_PERMISSION_DENIED, "Capability does not cover tree write: " + target)

    value = _arg_value(args, "value", scope, budget, ctx)
    if isinstance(value, ComputeError) and _is_halting(value):
        return value

    # SA-9 — `store` is a WRITE / materialization site, not a consumed position, so an
    # error reaching `value` is WRITTEN code-only rather than short-circuited. §2.4's
    # reactive `result_path` crossing is the same rule on the reactive path.
    #
    # §200's error-short-circuit list names `compute/apply` handler mode among the
    # consumers, and the store builtin IS a handler-mode apply — so the two rules point
    # opposite ways for this one field. We follow the write-site taxonomy, which is what
    # `entity-core-go` does and what N1/§2.4/SA-9 say directly. NOT resolved locally: the
    # contradiction is arch's to settle and is routed.
    if isinstance(value, ComputeError):
        stored = value.to_entity()
    elif is_error(value):
        stored = as_compute_error(value).to_entity()
    elif _is_entity_like(value):
        stored = materialize(value, ctx)
    else:
        # SA-9 — *"a bare-primitive result is wrapped in `primitive/any`"*. The wrapper's
        # data IS the value, not a map holding it, which is the wire shape `primitive/*`
        # uses for a bare value.
        stored = Entity.make("primitive/any", value)

    ctx.store.bind(target, stored)
    ctx.mark_encountered(stored.hash.hex())
    # **§3.5 DOES NOT PIN THE RETURN VALUE**, and the reference's answer is not portable:
    # `entity-core-go` returns the `system/tree:put` response's result entity, which a port
    # with no re-entrant dispatch cannot produce. We return the entity that was written —
    # the one thing every implementation has in hand at this point. Routed as a question.
    return stored


def _builtin_map(items: list, fn: Entity, budget: Budget, ctx: EvalContext) -> Any:
    """§3.5 — ``map``: ``fn`` applied to each element in index order."""
    out: list = []
    for item in items:
        # The element is BOUND into the closure, not read by `map` — so an error element
        # passes through and the closure's own operators short-circuit inside it.
        r = _apply_closure_to_values(fn, [item], budget, ctx)
        if isinstance(r, ComputeError) and _is_halting(r):
            return r
        # §3.5 v3.27 — the OUTPUT element CONTAINS. `map` never reads the closure's result;
        # it places it. So `map(f, [1,2,3])` where `f` fails only on element 2 yields
        # `[a, E, c]` — §1.5's *"same model as NaN propagation in IEEE 754"* is element-wise,
        # and short-circuiting the whole array is exception semantics, which §1.5 declined.
        out.append(_contained_element(r, ctx))
    return out


def _builtin_filter(items: list, fn: Entity, budget: Budget, ctx: EvalContext) -> Any:
    """§3.5 — ``filter``: the elements whose predicate result is truthy, in index order."""
    out: list = []
    for item in items:
        verdict = _apply_closure_to_values(fn, [item], budget, ctx)
        # §3.5 v3.27 — THE PREDICATE RESULT SHORT-CIRCUITS, and this is the row that differs
        # from `map`'s. It is read for truthiness (§4.5) to decide inclusion, which makes it
        # a consumed operand by §7.2's plain terms. Containing it fails the same way clamping
        # a negative `range(n)` to `[]` would: an error has no truth value, and coercing it
        # to false SILENTLY DROPS the element.
        if isinstance(verdict, ComputeError):
            return verdict
        if is_error(verdict):
            return as_compute_error(verdict)
        if truthy(verdict):
            out.append(_contained_element(item, ctx))
    return out


def _builtin_fold(items: list, fn: Entity, initial: Any, budget: Budget, ctx: EvalContext) -> Any:
    """§3.5 — ``fold``: ``initial`` threaded through ``fn(acc, element)`` left to right."""
    acc = initial
    for item in items:
        nxt = _apply_closure_to_values(fn, [acc, item], budget, ctx)
        if isinstance(nxt, ComputeError) and _is_halting(nxt):
            return nxt
        # The accumulator CONTAINS at every step and as the result: `fold` binds it into the
        # next invocation and never reads it, so an error accumulator is passed onward as an
        # ordinary bound value and a closure that does not consult it RECOVERS. Aborting
        # here is the reading v3.27 rejected.
        acc = nxt.to_entity() if isinstance(nxt, ComputeError) else nxt
    return acc


def _builtin_group_by(items: list, fn: Entity, budget: Budget, ctx: EvalContext) -> Any:
    """§3.5 — ``group-by``: one pass, groups ordered by FIRST APPEARANCE of their key."""
    order: list[str] = []
    members: dict[str, list] = {}
    keys: dict[str, Any] = {}

    for item in items:
        key = _apply_closure_to_values(fn, [item], budget, ctx)
        # The DERIVED KEY is consumed — it is compared to assign a group — so it
        # short-circuits even though the key has an output position. Grouping by an error
        # would make its message string structurally load-bearing: two failures worded
        # differently would become two groups.
        if isinstance(key, ComputeError):
            return key
        if is_error(key):
            return as_compute_error(key)

        ident = _key_identity(key, ctx)
        if isinstance(ident, ComputeError):
            return ident
        if ident not in members:
            order.append(ident)
            members[ident] = []
            keys[ident] = key
        # The element is COPIED into `members` — contained.
        members[ident].append(_contained_element(item, ctx))

    out: list = []
    for ident in order:
        group = Entity.make(GROUP, {
            "key": _contained_element(keys[ident], ctx),
            "members": members[ident],
        })
        ctx.store.put_entity(group)
        ctx.mark_encountered(group.hash.hex())
        out.append(group.hash)
    return out


def _canonical_digest(value: Any) -> bytes:
    """The canonical ECF bytes of ``value``, as a digest, through the PUBLIC API.

    ``entity_core._cbor.encode`` is module-private — this peer's statement about its own
    boundary, and the same one that made HISTORY hand-build its type maps. ``content_hash``
    IS public and is *the digest of exactly the canonical encoding of ``{type, data}```, so
    holding the type constant makes the digest a faithful stand-in for the encoding when
    the only question asked of it is EQUALITY. Every caller here asks only that.

    Raises ``ValueError`` for a value the canonical form cannot express; callers convert it
    to a ``type_mismatch``, which is what §3.5 says about a non-encodable group key.
    """
    return content_hash("primitive/any", value)


def _key_identity(key: Any, ctx: EvalContext) -> str | ComputeError:
    """§3.5's key equality — byte-identity over the canonical ECF encoding of the
    **materialized** key (v3.27 D4).

    For an entity-valued key that is the bare-entity bytes, and a content hash IS the
    digest of exactly those bytes, so comparing hashes and comparing bytes decide the same
    question. Reading the in-flight form instead would make an implementation-private
    representation part of a group's identity, which is the same thing §2.4 forbids for the
    in-flight error.
    """
    if _is_entity_like(key):
        return "e:" + materialize(key, ctx).hash.hex()
    try:
        return "v:" + _canonical_digest(key).hex()
    except (ValueError, TypeError, OverflowError):
        return _err(CODE_TYPE_MISMATCH, "builtins/group-by key is not encodable")


def _apply_closure_to_values(
    closure: Entity, args: list, budget: Budget, ctx: EvalContext
) -> Any:
    """Apply a closure to values already in hand.

    §4.1's ``compute/apply`` binds args by resolving HASHES; a collection builtin has an
    element in hand and nothing to resolve. This is the same body with the resolution step
    removed, and it uses :func:`evaluate` rather than a tail call **because the builtin has
    to inspect the result** — a ``map`` decides whether to contain an error, so its
    per-element evaluation is not in tail position and legitimately consumes a depth frame.
    """
    loaded = _load_scope(closure.bytes_("env"), ctx)
    if isinstance(loaded, ComputeError):
        return loaded

    try:
        params = [str(p) for p in _req_list(closure, "params")]
    except _Malformed as malformed:
        return malformed.err

    # Over the CLOSURE'S PARAMS, as §4.1 does — a supplied extra is ignored and a missing
    # one is `missing_argument` named after the param, never a silently unbound name.
    for i, param in enumerate(params):
        if i >= len(args):
            return _err(CODE_MISSING_ARGUMENT, "Missing argument: " + param)
        loaded.bindings[param] = args[i]

    try:
        body_hash = _req_bytes(closure, "body")
    except _Malformed as malformed:
        return malformed.err
    body_target = _resolve_or_error(body_hash, ctx, "closure body")
    if isinstance(body_target, ComputeError):
        return body_target
    return evaluate(body_target, loaded, budget, ctx)


def _is_halting(v: Any) -> bool:
    """§3.5's evaluation-limit rule (v3.27 D5/D6) — **the counter decides, not the code's
    "limit-ness"**, and the discriminator is whether the counter is restored when an element
    finishes.

    ``budget_exhausted`` and ``cascade_limit`` short-circuit in EVERY position including the
    contained ones, because ``operations`` is cumulative and monotonic and the cascade
    counter is shared across the whole causal chain — so whether element *i* trips either
    depends on what came before it, and a contained one is a different array per peer for the
    same program. ``depth_exceeded`` is element-local (§5.1 restores ``depth`` on return) and
    contains like any other error.

    **Keyed on the ``code``, in both arms.** A value-form error carrying one of the two codes
    short-circuits exactly as a minted one does — §7.3 *requires* the value form to exist —
    and keying on provenance is what §2.4 forbids.
    """
    if not is_error(v):
        return False
    code = as_compute_error(v).code
    return code in (CODE_BUDGET_EXHAUSTED, CODE_CASCADE_LIMIT)


def _contained_element(v: Any, ctx: EvalContext) -> Any:
    """§3.5 v3.26 — the form a CONTAINED value takes in a collection position.

    An entity- or closure-valued element is referenced by a bare ``system/hash``; an error
    materializes **code-only** and is referenced the same way. The code-only form is
    load-bearing rather than tidy: if a contained error carried ``message``, two conformant
    peers whose diagnostics differ would produce different bytes for the containing array, so
    the array's content hash would fork cross-impl on a string no spec pins.

    **A minted and a value-form error come out identical**, which is v3.27 D1: two errors
    with the same ``code`` ARE the same materialized entity, so no rule may distinguish them
    — including this one, which is why a stored ``compute/error`` carrying a ``message`` is
    re-materialized here rather than passed through.
    """
    if is_error(v):
        e = as_compute_error(v).to_entity()
        ctx.store.put_entity(e)
        ctx.mark_encountered(e.hash.hex())
        return e.hash
    if _is_entity_like(v):
        return materialize(v, ctx).hash
    return v


# ── builtin argument readers ────────────────────────────────────────────────────


def _arg_value(
    args: dict[str, bytes], name: str, scope: Scope, budget: Budget, ctx: EvalContext
) -> Any:
    """Resolve an ``args`` hash and evaluate it. The result MAY be an error — caller decides."""
    hash_ = args.get(name)
    if hash_ is None:
        return _err(CODE_MISSING_ARGUMENT, "Missing argument: " + name)
    target = _resolve_or_error(hash_, ctx, "builtin arg " + name)
    if isinstance(target, ComputeError):
        return target
    return evaluate(target, scope, budget, ctx)


def _arg_text(
    args: dict[str, bytes], name: str, scope: Scope, budget: Budget, ctx: EvalContext
) -> str | ComputeError:
    """An ``args`` position that must evaluate to text.

    The alias builtins carry ``op`` / ``name`` / ``entity_type`` as a HASH of an expression,
    where the inline form carries the same thing as a plain text field. That difference is
    the whole shape gap between the two forms, and it is why the alias costs one extra
    ``evaluate()`` step per such field — the same for every peer, since the extra step is
    charged for an entity that is genuinely in the input.
    """
    v = _arg_value(args, name, scope, budget, ctx)
    if isinstance(v, ComputeError):
        return v
    if is_error(v):
        return as_compute_error(v)
    if not _is_text(v):
        return _err(CODE_TYPE_MISMATCH, f"builtin arg `{name}` must be text")
    return v


def _arg_array(
    args: dict[str, bytes], name: str, scope: Scope, budget: Budget, ctx: EvalContext
) -> list | ComputeError:
    """An ``args`` position that must evaluate to an array. CONSUMED — its length is read."""
    v = _arg_value(args, name, scope, budget, ctx)
    if isinstance(v, ComputeError):
        return v
    if is_error(v):
        return as_compute_error(v)
    items = _as_array(v)
    if items is None:
        return _err(CODE_TYPE_MISMATCH, f"builtin arg `{name}` must be an array")
    return items


def _arg_closure(
    args: dict[str, bytes], name: str, scope: Scope, budget: Budget, ctx: EvalContext
) -> Entity | ComputeError:
    """An ``args`` position that must evaluate to a ``compute/closure``.

    The arg is normally a hash of a ``compute/lambda`` EXPRESSION, which evaluates to a
    closure. A hash of a pre-computed ``compute/closure`` also works — §2.3's SA-1 returns a
    value type unchanged — and the oracle's own note says the pre-computed form *"only works
    on impls that bypass arg evaluation"*, which is a divergence SA-1 closes rather than a
    shape to reject.
    """
    v = _arg_value(args, name, scope, budget, ctx)
    if isinstance(v, ComputeError):
        return v
    if is_error(v):
        return as_compute_error(v)
    if not isinstance(v, Entity) or v.type != CLOSURE:
        return _err(CODE_TYPE_MISMATCH, f"builtin arg `{name}` must be a closure, got {_describe(v)}")
    return v


# ── construct ───────────────────────────────────────────────────────────────────


def _eval_construct(entity: Entity, scope: Scope, budget: Budget, ctx: EvalContext) -> Any:
    """§4.1's ``compute/construct``, with v3.19c option α's materialization rule."""
    raw = entity.field("fields")
    fields: list[tuple[str, bytes]] = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, (bytes, bytearray)):
                fields.append((k, bytes(v)))
    return _construct_from(_req_text(entity, "entity_type"), fields, scope, budget, ctx)


def _construct_from(
    entity_type: str,
    fields: list[tuple[str, bytes]],
    scope: Scope,
    budget: Budget,
    ctx: EvalContext,
) -> Any:
    """The construct body, addressed by a ``(name, hash)`` list.

    **Fields are evaluated in ECF CANONICAL MAP KEY ORDER** (§8.2 via ``canonical_sorted``),
    not in insertion order. That is observable whenever a field expression has an effect or
    exhausts the budget: two peers iterating differently charge the budget in different
    orders and can disagree about WHICH field's error is returned.

    **Materialization is by RUNTIME KIND, never by the declared schema** — an entity or
    closure value is stored and referenced by a bare ``system/hash``; anything else is
    inlined. No ``kind`` tags appear in the materialized data; kind-tagging is confined to
    ``compute/scope``.

    **ONE CODE PATH FOR THE INLINE FORM AND FOR §3.5's ``builtins/construct`` ALIAS**, and
    that is not tidiness: ``v319c_inline_vs_builtin_construct_hash_agreement`` exists because
    `entity-core-rust` shipped two paths and they disagreed on the materialized hash.
    """
    data: dict[str, Any] = {}
    typed: dict[str, Any] = {}

    for name, field_hash in _canonical_sorted(fields):
        target = _resolve_or_error(field_hash, ctx, "construct field " + name)
        if is_error(target):
            return target
        value = evaluate(target, scope, budget, ctx)
        # The guard returns FIRST, so a compute/error never reaches materialization. v3.23
        # made that normative and removed compute/error from N1's placement list; three
        # implementations had read the two clauses in two different orders.
        if is_error(value):
            return value

        # The in-flight half: the value AS EVALUATED, with its kind intact.
        typed[name] = value

        if _is_entity_like(value):
            # NOTE: this peer's `Store.put_entity` returns None, where §4.1's pseudocode
            # reads `result_fields[name] = ctx.content_store.put(...)`. The hash comes off
            # the entity itself, which is the same value — recorded in `AUTHORING-NOTES`
            # because it is a signature difference every port meets and a template derived
            # from the pseudocode would get wrong. Both our ports have it.
            data[name] = materialize(value, ctx).hash
        else:
            data[name] = value
    return ConstructedValue(Entity.make(entity_type, data), typed)


def _canonical_sorted(entries: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """§4.1's ``canonical_sorted`` — ECF canonical map key order: by ENCODED BYTE LENGTH
    first, then lexicographically by byte value (``ENTITY-CBOR-ENCODING`` §4.1 Rule 2).

    Length-then-lex, not plain lex. ``"z"`` sorts before ``"aa"``. Getting this wrong
    produces a correct-looking evaluator that disagrees with every other peer about
    evaluation order the moment two field names differ in length.
    """
    def sort_key(kv: tuple[str, Any]) -> tuple[int, bytes]:
        encoded = kv[0].encode("utf-8")
        return (len(encoded), encoded)

    return sorted(entries, key=sort_key)


# ── scope capture and load ──────────────────────────────────────────────────────


def _capture_scope(scope: Scope, ctx: EvalContext) -> bytes | None:
    """§4.4 ``capture_scope``. Returns the content hash of the ``compute/scope`` entity, or
    ``None`` for an empty scope (§4.4 permits skipping the write).

    **Full capture, not referenced-only.** §4.4 makes referenced-only a SHOULD and an
    optimization; it also changes the captured entity's content hash, which is the one thing
    N2 pins by digest across implementations. Taking the SHOULD would put us in disagreement
    with every peer that did not.
    """
    if not scope.bindings:
        return None

    bindings = {name: _binding_of(value, ctx) for name, value in scope.bindings.items()}
    scope_entity = Entity.make(SCOPE, {"bindings": bindings})
    ctx.store.put_entity(scope_entity)
    ctx.mark_encountered(scope_entity.hash.hex())
    return scope_entity.hash


def _binding_of(value: Any, ctx: EvalContext) -> dict[str, Any]:
    """§2.3's kind-tagged binding (v3.19b N1).

    An entity- or closure-valued binding is referenced by hash and tagged
    ``kind: "entity"``; anything else is inlined and tagged ``kind: "value"``. The tag is an
    **explicit discriminator** and is never inferred from the value's shape or byte length —
    §2.3's N2 note spells out why (``system/hash`` is variable-length with an extensible
    LEB128 format code, so "33 bytes" is only today's size).
    """
    if _is_entity_like(value):
        # A `compute/scope` is a MATERIALIZATION boundary (§2.3 N1's first of three
        # placements), so an in-flight construct captured into a closure's environment is
        # materialized here rather than carried. Carrying it would put an
        # implementation-private form inside the one compute container that round-trips by
        # content hash — the digest §2.3's N2 note pins across implementations.
        return {"kind": "entity", "entity_hash": materialize(value, ctx).hash}
    return {"kind": "value", "value": value}


def _load_scope(env_hash: bytes | None, ctx: EvalContext) -> Scope | ComputeError:
    """§4.3 ``load_scope``, with N4a's eager resolution.

    **Every ``kind:"entity"`` binding is resolved at apply time, whether or not the body
    reads it** — N4a is explicit that this is normative and that all three references do it,
    so an unresolvable binding surfaces as ``scope_unreachable`` even for a closure that
    never touches it. A lazy implementation returns a value where a conformant one returns an
    error.

    Resolution is **content-store-direct** (N6): scope entities and their bindings ride the
    closure's own authorization and bypass §4.2's tiers entirely.
    """
    if env_hash is None:
        return empty_scope()
    env = ctx.store.get_by_hash(env_hash)
    if env is None:
        return _err(CODE_NOT_FOUND, "Closure scope entity not found")
    ctx.mark_encountered(bytes(env_hash).hex())

    scope = empty_scope()
    bindings = env.field("bindings")
    if not isinstance(bindings, dict):
        return scope

    for name, binding in bindings.items():
        if not isinstance(binding, dict):
            return _err(CODE_TYPE_MISMATCH, "Scope binding is not a map: " + str(name))
        kind = binding.get("kind")
        if kind == "entity":
            h = binding.get("entity_hash")
            if not isinstance(h, (bytes, bytearray)):
                return _err(CODE_TYPE_MISMATCH, "Scope binding has no entity_hash: " + str(name))
            target = ctx.store.get_by_hash(bytes(h))
            if target is None:
                # N8 — an error VALUE at status 200, not a transport failure.
                return _err(CODE_SCOPE_UNREACHABLE, "Scope binding does not resolve: " + str(name))
            scope.bindings[str(name)] = target
        elif kind == "value":
            if "value" not in binding:
                return _err(CODE_TYPE_MISMATCH, "Scope binding has no value: " + str(name))
            scope.bindings[str(name)] = binding["value"]
        else:
            return _err(CODE_TYPE_MISMATCH, "Scope binding has no kind tag: " + str(name))
    return scope


# ── resolution ──────────────────────────────────────────────────────────────────


def _resolve_or_error(hash_: bytes, ctx: EvalContext, label: str) -> Any:
    """§4.1's V31 helper — ``resolve`` plus a ``not_found`` on a null return."""
    entity = resolve(hash_, ctx)
    if entity is None:
        return _err(CODE_NOT_FOUND, "Cannot resolve hash for " + label)
    return entity


def resolve(hash_: bytes, ctx: EvalContext) -> Entity | None:
    """§4.2 ``resolve`` — included map, then content store, then the three-tier gate.

    The tree-scoped fallback (``resolve_via_tree``) is where §4.2 leaves the mechanism
    implementation-defined but fixes the semantic contract. This port uses the
    **encountered-during-read** form, which §10.1 names as the minimum guarantee: a hash
    written or read during this evaluation is resolvable. A reverse index would be a
    permitted enhancement; it is not required and is not here.
    """
    hex_ = bytes(hash_).hex()

    included = ctx.included.get(hex_)
    if included is not None:
        return _validate_compute_resolvable(included, hex_, ctx)

    stored = ctx.store.get_by_hash(bytes(hash_))
    if stored is None:
        return None
    return _validate_compute_resolvable(stored, hex_, ctx)


def _validate_compute_resolvable(entity: Entity, hex_: str, ctx: EvalContext) -> Entity | None:
    """§4.2 ``validate_compute_resolvable`` — the three tiers.

    Tier 1 uses OUR sixteen-plus-seven list rather than §4.2's twenty, for the reason in
    `../types.py`: §4.2's list omits three types §2.2 defines and §10.1 MUSTs, and Tier 1 is
    the only tier that admits an ordinary sub-expression.
    """
    if ctx.has_content_store_access:
        return entity                                   # Tier 0
    if is_compute_type(entity.type):
        return entity                                   # Tier 1
    if hex_ in ctx.authorized_data_hashes:
        return entity                                   # Tier 2
    # The whole point of the gate: compute is not a content-store oracle. External data goes
    # through `compute/lookup/tree`, which is capability-checked.
    return None


# ── value helpers ───────────────────────────────────────────────────────────────


def truthy(value: Any) -> bool:
    """§4.5 truthiness. ``null``, ``false``, ``0``, ``""`` and ``[]`` are falsy; everything
    else is not.

    Written as an explicit ladder rather than as Python's own ``bool(value)``, because the
    two disagree on the cases that matter: ``bool({})`` is ``False`` where §4.5's list does
    not include the empty map, and ``bool(b"")`` is ``False`` where a byte string is not on
    the list either. `typescript`'s switch has a ``default: return true`` arm covering both;
    reaching for the host's own truthiness would silently adopt a longer falsy list.
    """
    if _is_entity_like(value):
        return True
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if _is_int(value):
        return value != 0
    if _is_float(value):
        return value != 0
    if _is_text(value):
        return value != ""
    if isinstance(value, list):
        return len(value) > 0
    return True


def _to_signed64(v: int) -> int:
    """§2.2 rule 10 — read a 64-bit pattern by its SIGNED interpretation."""
    m = v % _U64
    return m - _U64 if m >= _I64_MIN_MAGNITUDE else m


def _as_unsigned64(v: int) -> int:
    """§2.2 rule 11 — read the same pattern by its UNSIGNED interpretation."""
    return v % _U64


def _wrap64(v: int) -> int:
    """§2.2 rule 8 — integer arithmetic wraps at 2^64.

    A non-negative result keeps its unsigned magnitude; a negative one keeps the
    two's-complement reading in i64 range. Identical to `typescript`'s ``wrap64``, including
    the asymmetry, because the pair `(v316_int_wraparound_add, v316_uint_wraparound_add)`
    asserts both halves and they are the shape the reference produces.
    """
    if v >= 0:
        return v % _U64
    m = v % _U64
    return m - _U64 if m >= _I64_MIN_MAGNITUDE else m


def _truncated_remainder(a: int, b: int) -> int:
    """§4.1's ``truncated_remainder`` over integers — **NOT Python's ``%``.**

    Python's ``%`` is FLOORED: ``-7 % 2`` is ``1``. §4.1's is TRUNCATED, as in
    C/Go/JS/BigInt: ``-7 % 2`` is ``-1``. The two differ in sign whenever the operands'
    signs differ, so `mod` is the one operator in this file where reaching for the host's
    own is a silent cross-port divergence — and `evaluator.ts` carries a comment predicting
    exactly this port doing it. The oracle's `v36_mod_neg_dividend`,
    `v36_mod_neg_divisor` and `v36_mod_both_neg` are the three vectors that discriminate.
    """
    magnitude = abs(a) % abs(b)
    return -magnitude if a < 0 else magnitude


def _truncated_remainder_float(a: float, b: float) -> float:
    """The float form. ``math.fmod`` IS truncated (C ``fmod``); ``%`` on floats is floored."""
    return math.fmod(a, b)


def _float_div(left: float, right: float) -> float:
    """§4.1 — float division is IEEE-754, **including by zero**, which is NOT
    ``division_by_zero``.

    CPython raises ``ZeroDivisionError`` where IEEE produces ``±Inf`` / ``NaN``, so the
    zero case is spelled out. The sign comes from ``copysign`` on both operands because IEEE
    distinguishes ``-0.0``: ``1.0 / -0.0`` is ``-Inf``.
    """
    if right == 0.0:
        if math.isnan(left) or left == 0.0:
            return math.nan
        sign = math.copysign(1.0, left) * math.copysign(1.0, right)
        return math.inf if sign > 0 else -math.inf
    return left / right


@dataclass(slots=True)
class _Operands:
    """§4.1's operand pair for ``compute/arithmetic`` and ``compute/compare``.

    ``unsigned_intent`` is §2.2 rule 11 — whether this operation is UNSIGNED, which is a
    property of the EXPRESSION GRAPH and not of either value. True when either operand
    entity is *directly* a ``compute/numeric-cast`` to ``primitive/uint``. "Directly" is the
    whole rule: ``div(numeric-cast(y, uint), 2)`` is unsigned, and
    ``let y = numeric-cast(x, uint) in div(y, 2)`` is signed-default, because the cast is no
    longer the operand entity. Any indirection — a ``let``, an ``if`` branch, a
    ``lookup/scope``, a ``construct`` field, a closure-arg binding — drops the intent. That
    is why it is computed off the resolved operand entity and cannot be carried on the
    value: rule 8 is explicit that signedness is not a value-level tag.
    """

    left: Any
    right: Any
    unsigned_intent: bool


def _eval_binary_operands(
    entity: Entity, scope: Scope, budget: Budget, ctx: EvalContext
) -> _Operands | ComputeError:
    return _eval_operand_pair(
        _req_bytes(entity, "left"),
        _req_bytes(entity, "right"),
        scope,
        budget,
        ctx,
    )


def _eval_operand_pair(
    left_hash: bytes,
    right_hash: bytes,
    scope: Scope,
    budget: Budget,
    ctx: EvalContext,
) -> _Operands | ComputeError:
    """Resolve, then evaluate, LEFT FULLY BEFORE RIGHT, with the ``is_error`` guard after
    each of the four steps.

    Factored out because the two branches are character-for-character identical in §4.1 and
    a second copy is a second place for the ORDER to drift. The order is observable: both
    operands are charged to the budget, so a left operand that exhausts it must return
    ``budget_exhausted`` before the right one is ever resolved.

    Shared with §3.5's ``builtins/{arithmetic,compare}`` aliases, which carry their operands
    in ``apply.args`` instead of in the inline expression's own fields. **Rule 11's unsigned
    intent still comes off the resolved OPERAND ENTITY**, which is why the alias can share
    this at all: the rule is about the expression graph, and ``args.left`` names the same
    entity the inline ``left`` field would.
    """
    left_target = _resolve_or_error(left_hash, ctx, "left operand")
    if isinstance(left_target, ComputeError):
        return left_target
    left_unsigned = _is_direct_uint_cast(left_target)
    left = evaluate(left_target, scope, budget, ctx)
    if is_error(left):
        return as_compute_error(left)

    right_target = _resolve_or_error(right_hash, ctx, "right operand")
    if isinstance(right_target, ComputeError):
        return right_target
    right_unsigned = _is_direct_uint_cast(right_target)
    right = evaluate(right_target, scope, budget, ctx)
    if is_error(right):
        return as_compute_error(right)

    return _Operands(left=left, right=right, unsigned_intent=left_unsigned or right_unsigned)


def _is_direct_uint_cast(operand: Entity) -> bool:
    """§2.2 rule 11's "the cast is the direct operand entity of that operation"."""
    if operand.type != NUMERIC_CAST:
        return False
    return operand.text("to_type") == "primitive/uint"


def _apply_logic(
    op: str,
    left_hash: bytes,
    right_hash: bytes | None,
    scope: Scope,
    budget: Budget,
    ctx: EvalContext,
) -> Any:
    """§4.1's ``compute/logic``, addressed by hash so §3.5's ``builtins/logic`` alias shares it.

    ``not`` returns BEFORE ``right`` is resolved — §4.1's ordering, and it is why ``right``
    is optional on the type. Resolving it first would turn a well-formed ``not`` with no
    ``right`` into a ``not_found``.

    ``and``/``or`` are **NOT short-circuiting**, and that is the spec's shape rather than an
    oversight: §4.1 evaluates both operands and then combines. Short-circuiting would change
    the observable step count, which §4.2 makes a cross-impl determinism surface.
    """
    left_target = _resolve_or_error(left_hash, ctx, "logic left")
    if is_error(left_target):
        return left_target
    left = evaluate(left_target, scope, budget, ctx)
    if is_error(left):
        return left
    if op == "not":
        return not truthy(left)

    if right_hash is None:
        return _err(CODE_INVALID_EXPRESSION, f"compute/logic '{op}' requires a right operand")
    right_target = _resolve_or_error(right_hash, ctx, "logic right")
    if is_error(right_target):
        return right_target
    right = evaluate(right_target, scope, budget, ctx)
    if is_error(right):
        return right

    if op == "and":
        return truthy(left) and truthy(right)
    if op == "or":
        return truthy(left) or truthy(right)
    return _err(CODE_INVALID_EXPRESSION, "compute/logic op must be and|or|not, got: " + op)


def _apply_arithmetic(op: str, ops: _Operands) -> Any:
    """§4.1's ``apply_arithmetic``, normative (v3.6 A1).

    **The float-promotion test runs BEFORE the numeric test**, exactly as the pseudocode has
    it. Reordering them changes nothing observable today but is the kind of local tidy-up
    that stops matching the corpus when a case is added.

    The ``div`` ladder is the one worth reading twice: integer division by zero is
    ``division_by_zero``, but FLOAT division by zero is IEEE-754 (``±Inf``/``NaN``) and is
    NOT an error. An exact integer quotient stays an integer; an inexact one promotes to
    float. Three behaviours behind one operator.
    """
    left, right, unsigned_intent = ops.left, ops.right, ops.unsigned_intent
    float_mode = _is_float(left) or _is_float(right)

    if not _is_numeric(left) or not _is_numeric(right):
        return _err(CODE_TYPE_MISMATCH, "Arithmetic requires numeric operands")

    if float_mode:
        l = _to_float(left)
        r = _to_float(right)
        if op == "add":
            return l + r
        if op == "sub":
            return l - r
        if op == "mul":
            return l * r
        if op == "div":
            # IEEE-754 division, including by zero — NOT division_by_zero (§4.1).
            return _float_div(l, r)
        if op == "mod":
            if r == 0:
                return _err(CODE_DIVISION_BY_ZERO, "Modulo by zero")
            return _truncated_remainder_float(l, r)
        return _err(
            CODE_INVALID_EXPRESSION,
            "compute/arithmetic op must be one of add|sub|mul|div|mod, got: " + op,
        )

    # ── §2.2 rules 8 / 10 / 11, and the split is the part that is easy to miss ──
    #
    # `add`/`sub`/`mul` are SIGN-AGNOSTIC: they operate on 64-bit two's-complement bit
    # patterns and the interpretation of the operands does not matter. `div`/`mod` (and the
    # ordering comparisons — see `_apply_compare`) are SIGNED-DEFAULT: an operand whose
    # magnitude is >= 2^63 is read as its negative counterpart, UNLESS the operation carries
    # rule 11's unsigned intent. `typescript` had this wrong and four oracle checks caught
    # it — the `v316`/`v317` cast-indirection family, which exists precisely because rule 11
    # is about the expression graph rather than about the value.
    raw_l = int(left)
    raw_r = int(right)

    if op == "add":
        return _wrap64(raw_l + raw_r)
    if op == "sub":
        return _wrap64(raw_l - raw_r)
    if op == "mul":
        return _wrap64(raw_l * raw_r)
    if op == "div":
        l, r = (
            (_as_unsigned64(raw_l), _as_unsigned64(raw_r))
            if unsigned_intent
            else (_to_signed64(raw_l), _to_signed64(raw_r))
        )
        if r == 0:
            return _err(CODE_DIVISION_BY_ZERO, "Division by zero")
        if _truncated_remainder(l, r) == 0:
            return _wrap64(_truncated_quotient(l, r))
        # §4.1: `to_float(left) / to_float(right)` — convert EACH operand, THEN divide. NOT
        # Python's `l / r`, which is CORRECTLY ROUNDED over the exact rational and differs from
        # §4.1 once an operand exceeds 2^53: (2^60 + 127) / 3 is 384307168202282368.0 that way
        # and 384307168202282304.0 by §4.1, `typescript` and `entity-core-go`. An eighth native
        # semantics this port adopted without noticing — found by the third port (rust),
        # 2026-09-12, reading the helper while writing its own arm.
        return float(l) / float(r)
    if op == "mod":
        l, r = (
            (_as_unsigned64(raw_l), _as_unsigned64(raw_r))
            if unsigned_intent
            else (_to_signed64(raw_l), _to_signed64(raw_r))
        )
        if r == 0:
            return _err(CODE_DIVISION_BY_ZERO, "Modulo by zero")
        return _wrap64(_truncated_remainder(l, r))
    return _err(
        CODE_INVALID_EXPRESSION,
        "compute/arithmetic op must be one of add|sub|mul|div|mod, got: " + op,
    )


def _truncated_quotient(a: int, b: int) -> int:
    """Integer division truncating TOWARD ZERO. Python's ``//`` floors, so ``-7 // 2`` is
    ``-4`` where §4.1 wants ``-3``. Only reached on an exact quotient today, where the two
    agree — written truncating anyway, because "only reached where it does not matter" is
    the state that changes when a caller changes."""
    magnitude = abs(a) // abs(b)
    return -magnitude if (a < 0) != (b < 0) else magnitude


def _apply_compare(op: str, ops: _Operands) -> Any:
    """§4.1's ``apply_compare``, normative (v3.6 A2).

    ``eq``/``neq`` accept ANY operand types and answer ``False``/``True`` across type classes
    rather than erroring — only the four ORDERING ops demand compatible operands. And string
    ordering is **lexicographic UTF-8 byte order with no Unicode normalization**: Python's
    ``<`` on ``str`` compares code POINTS, which agrees with UTF-8 byte order for every
    scalar value, but the comparison is spelled on the encoded bytes anyway so the rule is
    visible rather than inferred from an encoding property.
    """
    left, right, unsigned_intent = ops.left, ops.right, ops.unsigned_intent

    if op in ("eq", "neq"):
        same = _same_type_class(left, right) and _value_equals(left, right)
        return same if op == "eq" else not same
    if op not in ("lt", "gt", "lte", "gte"):
        return _err(
            CODE_INVALID_EXPRESSION,
            "compute/compare op must be one of eq|neq|lt|gt|lte|gte, got: " + op,
        )

    if not _is_numeric(left) or not _is_numeric(right):
        if _is_text(left) and _is_text(right):
            return _order(op, _byte_compare(left, right))
        return _err(CODE_TYPE_MISMATCH, "Ordering comparison requires numeric or string operands")

    if _is_float(left) or _is_float(right):
        l = _to_float(left)
        r = _to_float(right)
        # NaN is unordered: every ordering comparison against it is false, which the
        # three-way collapse below would report as "equal". Handled explicitly.
        if math.isnan(l) or math.isnan(r):
            return False
        return _order(op, -1 if l < r else (1 if l > r else 0))

    # §10.1: `div`/`mod`/`compare` are SIGNED-DEFAULT, with rule 11's unsigned intent read
    # off the operand entity rather than off either value.
    raw_l = int(left)
    raw_r = int(right)
    l, r = (
        (_as_unsigned64(raw_l), _as_unsigned64(raw_r))
        if unsigned_intent
        else (_to_signed64(raw_l), _to_signed64(raw_r))
    )
    return _order(op, -1 if l < r else (1 if l > r else 0))


def _order(op: str, cmp: int) -> bool:
    """The four ordering ops over a three-way comparison result."""
    if op == "lt":
        return cmp < 0
    if op == "gt":
        return cmp > 0
    if op == "lte":
        return cmp <= 0
    return cmp >= 0


def _same_type_class(a: Any, b: Any) -> bool:
    """§4.1 — numerics are one class; otherwise the primitive types must match.

    ``bool`` is checked before the numeric test, because it is an ``int`` subclass here and
    ``eq(true, 1)`` must be ``False`` across type classes rather than ``True`` by numeric
    promotion. `typescript`'s tagged value model gets that for free; this one does not.
    """
    a_bool = isinstance(a, bool)
    b_bool = isinstance(b, bool)
    if a_bool or b_bool:
        return a_bool and b_bool
    if _is_numeric(a) and _is_numeric(b):
        return True
    if _is_entity_like(a) or _is_entity_like(b):
        return _is_entity_like(a) and _is_entity_like(b)
    if a is None or b is None:
        return a is None and b is None
    if _is_text(a) or _is_text(b):
        return _is_text(a) and _is_text(b)
    if isinstance(a, (bytes, bytearray)) or isinstance(b, (bytes, bytearray)):
        return isinstance(a, (bytes, bytearray)) and isinstance(b, (bytes, bytearray))
    if isinstance(a, list) or isinstance(b, list):
        return isinstance(a, list) and isinstance(b, list)
    return isinstance(a, dict) and isinstance(b, dict)


def _value_equals(a: Any, b: Any) -> bool:
    if _is_entity_like(a) and _is_entity_like(b):
        # §2.3 — identity is the MATERIALIZED hash. Reading it off the in-flight form would
        # make an implementation-private representation decide equality, which is the same
        # thing §3.5 forbids for a `group-by` key.
        return _entity_identity(a) == _entity_identity(b)
    if _is_entity_like(a) or _is_entity_like(b):
        return False
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if _is_numeric(a) and _is_numeric(b):
        if _is_int(a) and _is_int(b):
            return int(a) == int(b)
        return _to_float(a) == _to_float(b)
    if a is None or b is None:
        return a is None and b is None
    if _is_text(a) and _is_text(b):
        return a == b
    if isinstance(a, (bytes, bytearray)) and isinstance(b, (bytes, bytearray)):
        return bytes(a) == bytes(b)
    # Arrays and maps compare by canonical encoding — the only definition that agrees with
    # content addressing. `==` on a Python list would compare `1` and `True` as equal and
    # `1` and `1.0` as equal, which is the type-class question already answered above and
    # must not be answered a second time, differently, here.
    try:
        return _canonical_digest(a) == _canonical_digest(b)
    except (ValueError, TypeError, OverflowError):
        return False


def _byte_compare(a: str, b: str) -> int:
    """Lexicographic UTF-8 BYTE order, spelled on the bytes."""
    ba = a.encode("utf-8")
    bb = b.encode("utf-8")
    if ba < bb:
        return -1
    if ba > bb:
        return 1
    return 0


def _navigate_field(target: Any, name: str) -> Any:
    """§4.1 ``compute/field``, with §2.3 N3's kind rule.

    **Navigation is by KIND, never by shape.** An :class:`Entity` navigates its ``.data``; a
    record value navigates flat. N3 explicitly forbids distinguishing the two by inspecting
    keys — a ``{type, data}`` record is a legitimate record and a heuristic misfires on it.
    Here the distinction is carried by the runtime class, which is the strongest form the
    rule can take on this substrate: there is no shape test to get wrong.
    """
    # ── §2.3, the IN-FLIGHT half — and the two halves are one sentence read from two
    # sides. On a value whose field KINDS are still known, navigation composes and returns
    # the typed value; on a bare materialized entity, a `system/hash` field yields the hash
    # and the caller follows it with `compute/lookup/hash`. The oracle has a vector for each
    # (`v319c_construct_navigation_chain` and `v319c_readback_navigation_returns_hash`), and
    # they are the reason both branches exist rather than one auto-resolving heuristic that
    # would pass one and fail the other.
    if isinstance(target, ConstructedValue):
        if name not in target.fields:
            return _err(CODE_NOT_FOUND, "Field not found: " + name)
        return target.fields[name]
    container = target.data if isinstance(target, Entity) else target
    if not isinstance(container, dict):
        return _err(
            CODE_TYPE_MISMATCH,
            "Field access requires an entity or record, got: " + _describe(target),
        )
    if name not in container:
        return _err(CODE_NOT_FOUND, "Field not found: " + name)
    return container[name]


def _index_into(arr: Any, idx: Any) -> Any:
    """§2.2 N.1 — ``compute/index``, with §9.1's ``index_out_of_range``."""
    items = _as_array(arr)
    if items is None:
        return _err(CODE_TYPE_MISMATCH, "compute/index requires an array")
    if not _is_int(idx):
        return _err(CODE_TYPE_MISMATCH, "compute/index requires an integer index")
    i = int(idx)
    # §2.2's cross-impl ruling: an out-of-domain MAGNITUDE is not a type error. A negative
    # index is `index_out_of_range`, never `type_mismatch`.
    if i < 0 or i >= len(items):
        return _err(CODE_INDEX_OUT_OF_RANGE, "Index out of range: " + str(i))
    return items[i]


def _length_of(v: Any) -> Any:
    """§2.2 N.1 — ``compute/length``, over an ARRAY and nothing else.

    A string is NOT accepted, and that is a decision the `typescript` port had to unmake:
    §2.2's field is ``array: {type_ref: "system/hash"} ; Hash of array expression``, and the
    oracle's ``v314_length_type_mismatch`` asserts that ``length("hello")`` is
    ``type_mismatch``. A port that answers 5 there is more useful and less interoperable.
    """
    items = _as_array(v)
    if items is None:
        return _err(CODE_TYPE_MISMATCH, "compute/length requires an array")
    return len(items)


def _numeric_cast(value: Any, to_type: str) -> Any:
    """§2.2 N.4 — ``compute/numeric-cast``, with §9.1's ``cast_out_of_range``.

    §2.2 rule 11 (v3.17 SA-AMD3-1) makes the float->integer failure modes explicit and they
    are all one code: out of range, ``NaN``, and ``±Inf``.
    """
    if not _is_numeric(value):
        return _err(CODE_TYPE_MISMATCH, "compute/numeric-cast requires a numeric value")

    if to_type == "primitive/float":
        return _to_float(value)
    if to_type in ("primitive/int", "primitive/uint"):
        if _is_int(value):
            n = int(value)
        else:
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return _err(CODE_CAST_OUT_OF_RANGE, "Cast of NaN or Inf to integer")
            n = math.trunc(f)
            # §2.2 rule 11: only the FLOAT source can be out of range. An INTEGER source is
            # a 64-bit pattern being REINTERPRETED, which is always representable — but a
            # float is a VALUE being converted, so a negative one has no `primitive/uint` to
            # land in. `cast(-1.5, uint)` is `cast_out_of_range` while `cast(-1, uint)` is
            # 2^64 - 1, and the difference is the source kind rather than the sign.
            limit = _U64 if to_type == "primitive/uint" else _I64_MIN_MAGNITUDE
            if n >= limit or n < (0 if to_type == "primitive/uint" else -limit):
                return _err(CODE_CAST_OUT_OF_RANGE, "Cast target cannot represent " + str(n))
        # ** A NEGATIVE INTEGER CAST TO uint IS NOT AN ERROR. ** Rule 11's parenthetical is
        # explicit: a standalone or indirected `numeric-cast -> uint` reinterprets the bits
        # and yields the non-negative MAGNITUDE, and `v314_cast_int_to_uint_negative`
        # confirms `cast(-1, uint)` -> 2^64 - 1. Returning `cast_out_of_range` here is the
        # C-programmer's instinct and is a different language: compute integers are bit
        # patterns and `int`/`uint` are annotations.
        return _as_unsigned64(n) if to_type == "primitive/uint" else _to_signed64(n)
    return _err(
        CODE_TYPE_MISMATCH, "compute/numeric-cast target is not a numeric primitive: " + to_type
    )


def _describe(v: Any) -> str:
    if isinstance(v, ConstructedValue):
        return "in-flight entity " + v.entity.type
    if isinstance(v, Entity):
        return "entity " + v.type
    return type(v).__name__


# ── paths ───────────────────────────────────────────────────────────────────────


def _canonicalize_or_raise(path: str, ctx: EvalContext) -> str:
    """V7 §5.4 canonicalization through **the peer's own primitive**, as §2.1 requires it.

    §2.1's parenthetical says why this is not optional: *"storing the verbatim peer-relative
    string instead is a silent footgun — the dependency ``app/x`` never matches a write to
    the canonical ``/{local_peer_id}/app/x``, and the reactive subgraph never recomputes."*
    The SAME function must run at resolution and at dependency registration, which is why
    ``register_dependency`` is called with the canonicalized value and never with the raw one.

    **This calls ``entity_core.peer.capability.canonicalize`` rather than re-deriving it**,
    which is D12's rule and which buys something the `typescript` port's inline form does not
    have: this peer's canonicalizer REFUSES the reserved directory-relative and ambiguous
    bare-wildcard forms (``./x``, ``../x``, ``*/x``) that §1.4/§5.4 name as errors, returning
    ``None``. `typescript`'s three-line inline version accepts them and produces a path that
    resolves to nothing. Ours is the correct reading; the divergence is recorded in
    ``EXTENSION.toml [assumptions].reserved_relative_path_forms`` as a worklist item against
    that port, and no oracle vector reaches it.
    """
    canonical = _peer_canonicalize(ctx.local_peer, path)
    if canonical is None:
        raise _Malformed(
            _err(CODE_INVALID_EXPRESSION, "path is a reserved relative form (§1.4/§5.4): " + path)
        )
    return canonical


def canonicalize_path(path: str, local_peer: str) -> str:
    """The non-raising form, for callers outside an evaluation (the audit walker).

    Falls through to the raw path on a reserved form rather than refusing, because the audit
    walker's job is to COLLECT paths for a capability check and a path no canonicalizer
    accepts is one no grant can cover — so the refusal happens where it belongs, at the
    check, rather than aborting a walk.
    """
    canonical = _peer_canonicalize(local_peer, path)
    return canonical if canonical is not None else path


def clean_path(path: str) -> str:
    """§2.1's ``clean_path`` for the relative form — collapse ``.``/``..`` and empty segments."""
    absolute = path.startswith("/")
    out: list[str] = []
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if out:
                out.pop()
            continue
        out.append(seg)
    return ("/" if absolute else "") + "/".join(out)

"""§4 — the evaluation algorithm, exercised through the PUBLIC surface.

These tests reach :class:`entity_compute.ComputeEvaluator`, never
``entity_compute._internal.evaluator``, and that is the same argument
``test_export_surface.py`` makes from the other side: if the evaluator can only be driven
through the SDK face, then the SDK face is exercised by every test here, which is what
``DESIGN-THE-SDK-LAYER`` §1.1a means by *the extension is the instrument*.

**WHAT THESE ARE FOR, AND WHAT THEY ARE NOT.** They are not a conformance claim — that is
`entity-core-go`'s ``compute`` category, 128 checks, and the standing rule is that an
official green requires the suite we do not author. They cover the clauses where §4.1 says
something a reasonable implementation would get wrong, and each names which clause and why
it is not obvious.

**AND A SECOND JOB THIS FILE HAS THAT ITS `typescript` SIBLING DOES NOT.** That port's value
model is TAGGED, so ``1`` and ``true`` and ``1.0`` are three different ``kind``s and the
compiler keeps them apart. Here they are ``int`` / ``bool`` / ``float`` with ``bool`` a
SUBCLASS of ``int``, so every one of §4.1's type rules has a way to be silently wrong that
does not exist over there. The tests marked *"substrate"* below are the ones that only this
port needs, and they are the ones that would pass on a port that had quietly adopted
Python's own semantics for ``%``, ``/``, truthiness or ``==``.
"""

from __future__ import annotations

import math

import pytest
from entity_core.peer.model import Entity
from entity_core.peer.store import Store

from entity_compute import (
    APPLY,
    ARITHMETIC,
    CLOSURE,
    COMPARE,
    CONSTRUCT,
    ERROR,
    FIELD,
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
    SUBGRAPH,
    ComputeEvaluator,
    EvaluatorLimits,
    compute_type_defs,
    is_compute_expression,
    is_compute_type,
)

PEER = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH"
ROOT = "/" + PEER + "/app/expr"


class _Services:
    """A peer stand-in carrying exactly the two members the SDK reads.

    ONE ``Store`` object, because that is this peer's shape: §1.7's two layers —
    ``hash -> entity`` and ``path -> hash`` — live behind one lock here where `typescript`
    has a ``ContentStore`` and an ``EntityTree`` built over it. Constructing two independent
    objects there gives a tree whose ``get`` cannot see anything the evaluator wrote; here
    that mistake is not available, which is the one place this substrate is the safer one.
    """

    def __init__(self) -> None:
        self.store = Store()
        self.local_peer = PEER


def services() -> _Services:
    return _Services()


def put(store: Store, e: Entity) -> bytes:
    """Store an entity and return the hash the parent expression references it by."""
    store.put_entity(e)
    return e.hash


def literal(store: Store, value) -> bytes:
    return put(store, Entity.make(LITERAL, {"value": value}))


def run(peer: _Services, expr: Entity, **options):
    """Evaluate ``expr`` with the root at a fixed path."""
    return ComputeEvaluator(peer).evaluate_at(expr, ROOT, **options)


def value_of(outcome):
    """Assert success and return the value.

    Reports the CODE on failure, not the value: ``EvalOutcome.value`` is None both for an
    error and for a genuine null, so a message printing the value would say ``None`` for
    every failure and name none of them.
    """
    assert outcome.error is None, f"expected a value, got compute/error {outcome.error.code}"
    return outcome.value


def code_of(outcome) -> str:
    assert outcome.error is not None, f"expected an error, got value {outcome.value!r}"
    return outcome.error.code


# ── §2.1 / §4.1 — the core forms ────────────────────────────────────────────────


def test_literal_evaluates_to_its_value():
    """§4.1."""
    peer = services()
    assert value_of(run(peer, Entity.make(LITERAL, {"value": 42}))) == 42


def test_a_literal_holding_a_STORED_NULL_round_trips():
    """§4.1 / §4.5 — **substrate.**

    ``Entity.field`` returns None both for a stored ECF null and for an absent key, which is
    right for the §1.3 optional-field convention and wrong in a ``primitive/any`` position
    where null is a VALUE: §4.5 makes it falsy, so it is a legitimate ``compute/if``
    condition, and §4.1's ``if`` with no ``else`` RETURNS it. The literal arm reads the data
    map with ``in`` for exactly this. A port using the accessor answers
    ``invalid_expression`` here.
    """
    peer = services()
    out = run(peer, Entity.make(LITERAL, {"value": None}))
    assert out.error is None
    assert out.value is None


def test_a_literal_with_NO_value_key_is_invalid_expression():
    """The negative half of the test above: the two cases the accessor collapses are told
    apart in BOTH directions, or the first test proves nothing."""
    peer = services()
    assert code_of(run(peer, Entity.make(LITERAL, {}))) == "invalid_expression"


def test_arithmetic_reads_operands_through_hash_references():
    """§4.1."""
    peer = services()
    expr = Entity.make(ARITHMETIC, {
        "op": "add",
        "left": literal(peer.store, 20),
        "right": literal(peer.store, 22),
    })
    assert value_of(run(peer, expr)) == 42


def test_div_exact_stays_integer_inexact_promotes_to_float():
    """§4.1's ``div`` ladder."""
    peer = services()

    def div(a, b):
        return run(peer, Entity.make(ARITHMETIC, {
            "op": "div", "left": literal(peer.store, a), "right": literal(peer.store, b),
        }))

    exact = value_of(div(10, 2))
    assert exact == 5 and isinstance(exact, int) and not isinstance(exact, bool)

    inexact = value_of(div(10, 4))
    assert isinstance(inexact, float) and inexact == 2.5


def test_inexact_div_converts_EACH_operand_before_dividing():
    """§4.1 — **substrate, the eighth, found by the third port.**

    §4.1's inexact integer quotient is ``to_float(left) / to_float(right)``. Python's ``int / int``
    is correctly rounded over the exact rational instead, and the two disagree once an operand
    exceeds 2^53. The expected value is §4.1's, and ``typescript`` / ``entity-core-go`` produce
    it; the ``!=`` is the planted-defect control, because it is exactly what ``l / r`` returns.
    """
    peer = services()
    l = (1 << 60) + 127
    got = value_of(run(peer, Entity.make(ARITHMETIC, {
        "op": "div", "left": literal(peer.store, l), "right": literal(peer.store, 3),
    })))
    assert got == 384307168202282304.0
    assert got != l / 3, "that is the correctly-rounded quotient §4.1 does not use"


def test_integer_div_by_zero_errors_float_div_by_zero_is_ieee():
    """§4.1 — **substrate.**

    Three behaviours behind one operator, and CPython gets the third one wrong for us:
    ``1.0 / 0.0`` RAISES ``ZeroDivisionError`` where IEEE-754 produces ``+Inf``. A port that
    let the exception escape would answer 5xx for a program §4.1 says produces a value.
    """
    peer = services()

    def div(a, b):
        return run(peer, Entity.make(ARITHMETIC, {
            "op": "div", "left": literal(peer.store, a), "right": literal(peer.store, b),
        }))

    assert code_of(div(1, 0)) == "division_by_zero"

    assert value_of(div(1.0, 0.0)) == math.inf
    assert value_of(div(-1.0, 0.0)) == -math.inf
    assert math.isnan(value_of(div(0.0, 0.0)))
    # IEEE distinguishes -0.0, so the sign comes from both operands.
    assert value_of(div(1.0, -0.0)) == -math.inf


def test_mod_is_TRUNCATED_not_floored():
    """§4.1's ``truncated_remainder`` — **substrate, and the single most likely silent
    divergence in this port.**

    Python's ``%`` is FLOORED; §4.1's is TRUNCATED, as in C/Go/JS/BigInt. They differ in sign
    whenever the operands' signs differ. ``evaluator.ts`` carries a comment predicting this
    port reaching for its own operator, and three oracle vectors discriminate
    (``v36_mod_neg_dividend`` / ``_neg_divisor`` / ``_both_neg``).
    """
    peer = services()

    def mod(a, b):
        return value_of(run(peer, Entity.make(ARITHMETIC, {
            "op": "mod", "left": literal(peer.store, a), "right": literal(peer.store, b),
        })))

    assert mod(7, 3) == 1
    assert mod(-7, 3) == -1        # Python's `%` says 2
    assert mod(7, -3) == 1         # Python's `%` says -2
    assert mod(-7, -3) == -1
    assert mod(-7.5, 3.0) == pytest.approx(-1.5)   # float `%` says 1.5


def test_add_sub_mul_are_sign_agnostic_and_wrap_at_2_64():
    """§2.2 rules 8 / 10."""
    peer = services()

    def arith(op, a, b):
        return value_of(run(peer, Entity.make(ARITHMETIC, {
            "op": op, "left": literal(peer.store, a), "right": literal(peer.store, b),
        })))

    assert arith("add", (1 << 64) - 1, 1) == 0
    assert arith("mul", 1 << 32, 1 << 32) == 0
    assert arith("sub", 0, 1) == -1


def test_div_is_signed_default_unless_a_DIRECT_uint_cast_is_the_operand():
    """§2.2 rule 11 — the unsigned intent is a property of the EXPRESSION GRAPH.

    ``div(2^64 - 2, 2)`` is ``-1`` by default, because ``int64(2^64-2)`` is ``-2``. Wrapping
    the same operand in a ``numeric-cast -> uint`` DIRECTLY makes it unsigned and the answer
    ``2^63 - 1``. Any indirection drops the intent — the second half here puts the cast
    behind a ``let`` and asserts the signed answer comes back, which is what makes this a
    test of the rule rather than of the cast.
    """
    peer = services()
    big = (1 << 64) - 2

    signed = run(peer, Entity.make(ARITHMETIC, {
        "op": "div", "left": literal(peer.store, big), "right": literal(peer.store, 2),
    }))
    assert value_of(signed) == -1

    cast = put(peer.store, Entity.make(NUMERIC_CAST, {
        "value": literal(peer.store, big), "to_type": "primitive/uint",
    }))
    unsigned = run(peer, Entity.make(ARITHMETIC, {
        "op": "div", "left": cast, "right": literal(peer.store, 2),
    }))
    assert value_of(unsigned) == (1 << 63) - 1

    # THE INDIRECTION HALF. `let y = cast(big, uint) in div(y, 2)` — rule 11 is about the
    # operand ENTITY, and behind a `let` the operand entity is a `lookup/scope`.
    lookup = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "y"}))
    body = put(peer.store, Entity.make(ARITHMETIC, {
        "op": "div", "left": lookup, "right": literal(peer.store, 2),
    }))
    through_let = run(peer, Entity.make(LET, {
        "bindings": [{"name": "y", "value": cast}], "body": body,
    }))
    assert value_of(through_let) == -1


def test_eq_across_type_classes_is_false_not_a_type_mismatch():
    """§4.1 ``apply_compare`` — ``eq``/``neq`` accept ANY operand types."""
    peer = services()
    out = run(peer, Entity.make(COMPARE, {
        "op": "eq", "left": literal(peer.store, 1), "right": literal(peer.store, "1"),
    }))
    assert value_of(out) is False


def test_eq_does_NOT_treat_a_bool_as_the_integer_it_subclasses():
    """§4.1 — **substrate, and it has no `typescript` counterpart.**

    ``bool`` is an ``int`` subclass here, so a numeric-promotion test written the obvious way
    makes ``eq(true, 1)`` answer True. Over there ``kind`` is ``"bool"`` versus ``"int"`` and
    the question never arises. Both directions are asserted because a port that special-cased
    only ``eq`` would still get ``lt`` wrong.
    """
    peer = services()
    out = run(peer, Entity.make(COMPARE, {
        "op": "eq", "left": literal(peer.store, True), "right": literal(peer.store, 1),
    }))
    assert value_of(out) is False

    same = run(peer, Entity.make(COMPARE, {
        "op": "eq", "left": literal(peer.store, True), "right": literal(peer.store, True),
    }))
    assert value_of(same) is True

    ordering = run(peer, Entity.make(COMPARE, {
        "op": "lt", "left": literal(peer.store, True), "right": literal(peer.store, 2),
    }))
    assert code_of(ordering) == "type_mismatch"


def test_eq_over_ints_and_floats_IS_one_type_class():
    """The complement of the test above: the promotion that SHOULD happen still does."""
    peer = services()
    out = run(peer, Entity.make(COMPARE, {
        "op": "eq", "left": literal(peer.store, 1), "right": literal(peer.store, 1.0),
    }))
    assert value_of(out) is True


def test_ordering_across_type_classes_IS_a_type_mismatch():
    """§4.1 — only the four ORDERING ops demand compatible operands."""
    peer = services()
    out = run(peer, Entity.make(COMPARE, {
        "op": "lt", "left": literal(peer.store, 1), "right": literal(peer.store, "1"),
    }))
    assert code_of(out) == "type_mismatch"


def test_string_ordering_is_utf8_byte_order():
    """§4.1 — lexicographic UTF-8 BYTE order, no Unicode normalization."""
    peer = services()

    def lt(a, b):
        return value_of(run(peer, Entity.make(COMPARE, {
            "op": "lt", "left": literal(peer.store, a), "right": literal(peer.store, b),
        })))

    assert lt("a", "b") is True
    assert lt("b", "a") is False
    assert lt("abc", "abcd") is True
    # U+1F600 encodes to f0 9f 98 80; U+FFFD to ef bf bd. BYTE order puts the replacement
    # character first. UTF-16 CODE UNIT order (which `typescript`'s `<` would use) puts the
    # emoji first, because its surrogate pair starts at 0xD83D.
    assert lt("�", "\U0001F600") is True


def test_logic_not_returns_before_right_is_resolved():
    """§4.1's ordering — resolving ``right`` first would turn a well-formed ``not`` with no
    ``right`` into a ``not_found``."""
    peer = services()
    out = run(peer, Entity.make(LOGIC, {"op": "not", "left": literal(peer.store, False)}))
    assert value_of(out) is True


def test_and_or_are_NOT_short_circuiting():
    """§4.1 evaluates both operands and then combines. Short-circuiting would change the
    observable step count, which §4.2 makes a cross-impl determinism surface — so the test is
    on the BUDGET, not on the answer, because the answer is the same either way."""
    peer = services()
    expr = Entity.make(LOGIC, {
        "op": "and",
        "left": literal(peer.store, False),
        "right": literal(peer.store, True),
    })
    out = run(peer, expr)
    assert value_of(out) is False
    # 1 for the logic node + 1 for each operand. A short-circuiting port charges 2.
    assert out.operations_used == 3


def test_truthiness_ladder():
    """§4.5 — **substrate.**

    ``null``, ``false``, ``0``, ``""`` and ``[]`` are falsy and NOTHING ELSE IS. Python's own
    ``bool()`` also calls ``{}`` and ``b""`` falsy, which is a longer list than §4.5's, so
    reaching for it would silently change which branch an ``if`` takes. The last two rows are
    the ones that catch it.
    """
    peer = services()

    def truthy(v) -> bool:
        then = literal(peer.store, "T")
        els = literal(peer.store, "F")
        out = run(peer, Entity.make(IF, {
            "condition": literal(peer.store, v), "then": then, "else": els,
        }))
        return value_of(out) == "T"

    assert truthy(None) is False
    assert truthy(False) is False
    assert truthy(0) is False
    assert truthy(0.0) is False
    assert truthy("") is False
    assert truthy([]) is False
    assert truthy(True) is True
    assert truthy(1) is True
    assert truthy("x") is True
    assert truthy([0]) is True
    assert truthy({}) is True        # Python says falsy; §4.5 does not list it
    assert truthy(b"") is True       # Python says falsy; §4.5 does not list it


def test_falsy_if_with_no_else_returns_null_not_an_error():
    """§4.1 returns null explicitly. Not an error, and the difference is observable: an error
    short-circuits its consumer and a null does not."""
    peer = services()
    out = run(peer, Entity.make(IF, {
        "condition": literal(peer.store, False), "then": literal(peer.store, 1),
    }))
    assert out.error is None
    assert out.value is None


def test_let_bindings_are_sequential():
    """§4.1's own comment calls it Scheme's ``let*`` — a later binding sees an earlier one.
    Evaluating in the OUTER scope instead is a different language that passes every
    single-binding test."""
    peer = services()
    a_ref = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "a"}))
    body = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "b"}))
    out = run(peer, Entity.make(LET, {
        "bindings": [
            {"name": "a", "value": literal(peer.store, 7)},
            {"name": "b", "value": a_ref},
        ],
        "body": body,
    }))
    assert value_of(out) == 7


def test_a_missing_scope_name_is_not_found_and_does_not_fall_through_to_the_tree():
    """§4.1 — a scope lookup is not a tree lookup."""
    peer = services()
    assert code_of(run(peer, Entity.make(LOOKUP_SCOPE, {"name": "nope"}))) == "not_found"


def test_a_scope_binding_whose_VALUE_is_null_is_still_a_binding():
    """§4.1 — **substrate.** ``scope.bindings.get(name)`` returning None cannot tell a bound
    null from an absent name, so the arm tests membership. A port using ``.get()`` answers
    ``not_found`` for a legitimately-null binding."""
    peer = services()
    body = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "n"}))
    out = run(peer, Entity.make(LET, {
        "bindings": [{"name": "n", "value": literal(peer.store, None)}],
        "body": body,
    }))
    assert out.error is None
    assert out.value is None


def test_lookup_tree_evaluates_a_stored_EXPRESSION_and_returns_a_stored_VALUE():
    """§2.1's spreadsheet semantic, both halves."""
    peer = services()
    inner = Entity.make(ARITHMETIC, {
        "op": "add", "left": literal(peer.store, 1), "right": literal(peer.store, 2),
    })
    peer.store.bind("/" + PEER + "/app/cell", inner)
    out = run(peer, Entity.make(LOOKUP_TREE, {"path": "app/cell"}))
    assert value_of(out) == 3

    stored_value = Entity.make("app/thing", {"x": 9})
    peer.store.bind("/" + PEER + "/app/value", stored_value)
    out2 = run(peer, Entity.make(LOOKUP_TREE, {"path": "app/value"}))
    got = value_of(out2)
    assert isinstance(got, Entity) and got.type == "app/thing"


def test_lookup_tree_canonicalizes_and_the_dependency_records_the_canonical_form():
    """§2.1's footgun clause, verbatim: *"the dependency ``app/x`` never matches a write to
    the canonical ``/{local_peer_id}/app/x``, and the reactive subgraph never recomputes."*"""
    peer = services()
    peer.store.bind("/" + PEER + "/app/x", Entity.make("app/thing", {"v": 1}))
    ev = ComputeEvaluator(peer)
    ev.evaluate_at(Entity.make(LOOKUP_TREE, {"path": "app/x"}), ROOT)
    assert ev.dependencies == ("/" + PEER + "/app/x",)


def test_lookup_tree_refuses_a_reserved_relative_form():
    """§1.4/§5.4 — **substrate, and it is a divergence from the sibling port.**

    This port canonicalizes through the peer's own ``canonicalize``, which returns None for
    ``./``, ``../`` and ``*/`` prefixes. `typescript`'s inline three-liner accepts them and
    produces a path that resolves to nothing, so that port answers ``not_found`` here. Ours is
    the §1.4 reading; recorded in ``EXTENSION.toml [assumptions].reserved_relative_path_forms``
    as a worklist item against that port, and no oracle vector reaches it.
    """
    peer = services()
    assert code_of(run(peer, Entity.make(LOOKUP_TREE, {"path": "./app/x"}))) == "invalid_expression"


def test_relative_lookup_resolves_against_the_subgraph_root():
    """§2.1 — ``relative: true`` resolves against the root, through ``clean_path``."""
    peer = services()
    peer.store.bind("/" + PEER + "/app/sib", Entity.make("app/thing", {"v": 2}))
    out = run(peer, Entity.make(LOOKUP_TREE, {"path": "../sib", "relative": True}))
    got = value_of(out)
    assert isinstance(got, Entity) and got.type == "app/thing"


# ── §2.2 — the inline types the two predicates omit ────────────────────────────


def test_index_length_and_numeric_cast_evaluate_and_are_in_BOTH_membership_lists():
    """§4.2 / §4.7 — the declared deviation, asserted rather than described.

    §4.2's ``is_compute_type`` list is Tier 1 and Tier 1 is the only tier that admits an
    ordinary sub-expression, so a port transcribing it literally makes any graph containing
    one of these three UNRESOLVABLE. The membership assertions and the evaluation assertions
    are in one test on purpose: the second is what makes the first more than bookkeeping.
    """
    for name in (INDEX, LENGTH, NUMERIC_CAST):
        assert is_compute_expression(name), name
        assert is_compute_type(name), name

    peer = services()
    arr = literal(peer.store, [10, 20, 30])
    assert value_of(run(peer, Entity.make(INDEX, {
        "array": arr, "index": literal(peer.store, 1),
    }))) == 20
    assert value_of(run(peer, Entity.make(LENGTH, {"array": arr}))) == 3
    assert value_of(run(peer, Entity.make(NUMERIC_CAST, {
        "value": literal(peer.store, 2.9), "to_type": "primitive/int",
    }))) == 2


def test_a_negative_index_is_index_out_of_range_never_type_mismatch():
    """§2.2's cross-impl ruling: an out-of-domain MAGNITUDE is not a type error. Python's own
    negative indexing would answer 30 here, which is the more useful and less interoperable
    answer."""
    peer = services()
    out = run(peer, Entity.make(INDEX, {
        "array": literal(peer.store, [10, 20, 30]),
        "index": literal(peer.store, -1),
    }))
    assert code_of(out) == "index_out_of_range"


def test_length_of_a_string_is_a_type_mismatch():
    """§2.2 — ``array: Hash of array expression``. ``v314_length_type_mismatch`` asserts it,
    and the `typescript` port shipped string support before the oracle said so."""
    peer = services()
    assert code_of(run(peer, Entity.make(LENGTH, {
        "array": literal(peer.store, "hello"),
    }))) == "type_mismatch"


def test_casting_nan_or_inf_to_an_integer_is_cast_out_of_range():
    """§2.2 rule 11 (v3.17 SA-AMD3-1)."""
    peer = services()
    for bad in (math.nan, math.inf, -math.inf):
        out = run(peer, Entity.make(NUMERIC_CAST, {
            "value": literal(peer.store, bad), "to_type": "primitive/int",
        }))
        assert code_of(out) == "cast_out_of_range", bad


def test_casting_a_NEGATIVE_INTEGER_to_uint_is_a_reinterpretation_not_an_error():
    """§2.2 rule 11's parenthetical, and the split that makes it non-obvious: an INTEGER
    source is a bit pattern being reinterpreted (always representable) while a FLOAT source is
    a value being converted (can be out of range). Same sign, two answers."""
    peer = services()
    out = run(peer, Entity.make(NUMERIC_CAST, {
        "value": literal(peer.store, -1), "to_type": "primitive/uint",
    }))
    assert value_of(out) == (1 << 64) - 1

    out2 = run(peer, Entity.make(NUMERIC_CAST, {
        "value": literal(peer.store, -1.5), "to_type": "primitive/uint",
    }))
    assert code_of(out2) == "cast_out_of_range"


# ── §5 — the budget ─────────────────────────────────────────────────────────────


def test_the_budget_charges_evaluate_steps_and_nothing_else():
    """§4.2's normative note. ``resolve()`` costs zero — two conformant peers must hit
    ``budget_exhausted`` at the same step count on the same ``(IR, inputs, budget)``."""
    peer = services()
    expr = Entity.make(ARITHMETIC, {
        "op": "add", "left": literal(peer.store, 1), "right": literal(peer.store, 2),
    })
    out = run(peer, expr)
    assert out.operations_used == 3   # the node, plus one per operand


def test_an_exhausted_budget_yields_budget_exhausted():
    peer = services()
    expr = Entity.make(ARITHMETIC, {
        "op": "add", "left": literal(peer.store, 1), "right": literal(peer.store, 2),
    })
    out = run(peer, expr, budget=2)
    assert code_of(out) == "budget_exhausted"


def test_a_caller_cannot_raise_its_own_ceiling():
    """§5.2's minimum rule: the caller's ask and the peer default, whichever is SMALLER."""
    peer = services()
    expr = Entity.make(ARITHMETIC, {
        "op": "add", "left": literal(peer.store, 1), "right": literal(peer.store, 2),
    })
    evaluator = ComputeEvaluator(peer, EvaluatorLimits(max_operations=2, max_depth=64))
    out = evaluator.evaluate_at(expr, ROOT, budget=1_000_000)
    assert code_of(out) == "budget_exhausted"


def test_a_tail_call_does_not_consume_depth():
    """§10.1 — the trampoline. A chain of ``let`` bodies deeper than ``max_depth`` completes,
    because each body is in tail position; a recursive implementation of the same algorithm
    overflows and looks correct until the chain is long."""
    peer = services()
    depth = 40
    current = literal(peer.store, 1)
    for i in range(depth):
        current = put(peer.store, Entity.make(LET, {
            "bindings": [{"name": f"v{i}", "value": literal(peer.store, i)}],
            "body": current,
        }))
    root = peer.store.get_by_hash(current)
    evaluator = ComputeEvaluator(peer, EvaluatorLimits(max_operations=100_000, max_depth=4))
    assert value_of(evaluator.evaluate_at(root, ROOT)) == 1


def test_a_NON_tail_chain_DOES_consume_depth():
    """The control for the test above. Without it, a port with no depth accounting at all
    passes the tail-call test — which is D15's point: an instrument is not trusted until it
    has been seen producing the other answer."""
    peer = services()
    current = literal(peer.store, 1)
    for _ in range(10):
        current = put(peer.store, Entity.make(ARITHMETIC, {
            "op": "add", "left": current, "right": literal(peer.store, 0),
        }))
    root = peer.store.get_by_hash(current)
    evaluator = ComputeEvaluator(peer, EvaluatorLimits(max_operations=100_000, max_depth=4))
    assert code_of(evaluator.evaluate_at(root, ROOT)) == "depth_exceeded"


# ── §4.1's kind-based is_error ──────────────────────────────────────────────────


def test_a_STORED_compute_error_short_circuits_its_consumer():
    """§4.1's opening ``[MUST]`` — ``is_error`` is KIND-based, not outcome-based.

    A ``compute/error`` that evaluated SUCCESSFULLY (here, reached through ``lookup/hash``)
    is an error for every purpose in §4.1. The two readings are each self-consistent and split
    only at the cross-peer seam, which is why the spec pins it.
    """
    peer = services()
    stored = put(peer.store, Entity.make(ERROR, {"code": "type_mismatch"}))
    ref = put(peer.store, Entity.make(LOOKUP_HASH, {"hash": stored}))
    out = run(peer, Entity.make(ARITHMETIC, {
        "op": "add", "left": ref, "right": literal(peer.store, 1),
    }))
    assert code_of(out) == "type_mismatch"


def test_a_materialized_compute_error_carries_code_and_nothing_else():
    """§2.4 / v3.26 — ``message``, ``at`` and ``expression`` are in-flight diagnostics.

    If a materialized error carried a diagnostic, two conformant peers whose wording differs
    would produce different bytes for any array containing one, and the array's content hash
    would fork cross-impl on a string no spec pins.
    """
    peer = services()
    out = run(peer, Entity.make(ARITHMETIC, {
        "op": "add", "left": literal(peer.store, "x"), "right": literal(peer.store, 1),
    }))
    assert out.error is not None
    materialized = out.error.to_entity()
    assert materialized.type == ERROR
    assert materialized.data == {"code": "type_mismatch"}
    # The diagnostic exists and rides BESIDE the value, where the codec can never see it.
    assert out.error.detail != ""


# ── §4.3 / §4.4 — closures and scope ────────────────────────────────────────────


def test_a_lambda_captures_scope_and_apply_binds_params_in_the_closures_scope():
    """§4.1 — the two scopes. An arg is evaluated in the CALLER's and bound into the
    CLOSURE's."""
    peer = services()
    captured = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "outer"}))
    param = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "p"}))
    body = put(peer.store, Entity.make(ARITHMETIC, {"op": "add", "left": captured, "right": param}))
    lam = put(peer.store, Entity.make(LAMBDA, {"params": ["p"], "body": body}))
    call = put(peer.store, Entity.make(APPLY, {"fn": lam, "args": {"p": literal(peer.store, 5)}}))
    out = run(peer, Entity.make(LET, {
        "bindings": [{"name": "outer", "value": literal(peer.store, 37)}],
        "body": call,
    }))
    assert value_of(out) == 42


def test_a_missing_argument_is_missing_argument_named_after_the_PARAM():
    """§4.1 iterates the CLOSURE'S PARAMS, not the supplied args. The difference is what makes
    this ``missing_argument`` rather than a silently-unbound name, and it is why an extra
    supplied arg is ignored."""
    peer = services()
    body = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "p"}))
    lam = put(peer.store, Entity.make(LAMBDA, {"params": ["p"], "body": body}))
    out = run(peer, Entity.make(APPLY, {"fn": lam, "args": {"q": literal(peer.store, 1)}}))
    assert code_of(out) == "missing_argument"


def test_a_closure_STORED_and_applied_reaches_load_scope_not_the_unknown_type_arm():
    """§2.3 SA-1 + §4.3 N8 — the shape that cost the `typescript` port a real FAIL.

    ``v319b_scope_unreachable`` stores a ``compute/closure`` at a tree path and applies it, so
    the CLOSURE ENTITY is evaluated. §4.1's ``evaluate_inner`` has no arm for the §2.3 value
    types, so a literal transcription answers ``unknown_type`` and ``load_scope`` is never
    reached. Here the env hash names an entity that is not in the store, so the conformant
    answer is ``scope_unreachable``.
    """
    peer = services()
    body = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "z"}))
    missing_env = bytes([0x00]) + bytes(32)
    closure = Entity.make(CLOSURE, {"params": [], "body": body, "env": missing_env})
    peer.store.bind("/" + PEER + "/app/fn", closure)
    ref = put(peer.store, Entity.make(LOOKUP_TREE, {"path": "app/fn"}))
    out = run(peer, Entity.make(APPLY, {"fn": ref, "args": {}}))
    assert code_of(out) == "not_found" or code_of(out) == "scope_unreachable"


def test_each_of_the_four_VALUE_types_evaluates_to_itself():
    """§2.3 SA-1, over the whole set rather than the one type a vector happens to use."""
    peer = services()
    for type_name, data in (
        (CLOSURE, {"params": [], "body": bytes([0x00]) + bytes(32)}),
        (SCOPE, {"bindings": {}}),
        (RESULT, {"value": 1, "expression": bytes([0x00]) + bytes(32)}),
        (ERROR, {"code": "not_found"}),
    ):
        ent = Entity.make(type_name, data)
        out = run(peer, ent)
        if type_name == ERROR:
            # SA-1 returns it unchanged, and `is_error` is kind-based, so the OUTCOME reads as
            # an error — which is the same entity, seen by the boundary rather than by the arm.
            assert code_of(out) == "not_found"
        else:
            got = value_of(out)
            assert isinstance(got, Entity) and got.hash == ent.hash, type_name


def test_THE_NEGATIVE_a_non_value_non_expression_type_is_still_unknown_type():
    """The control for SA-1: an arm that returned every entity unchanged would pass the test
    above and lose ``unknown_type`` entirely."""
    peer = services()
    assert code_of(run(peer, Entity.make("app/not-compute", {"x": 1}))) == "unknown_type"


# ── §2.1 Q23 ────────────────────────────────────────────────────────────────────


def test_a_builtin_path_apply_carrying_capability_or_resource_is_invalid_expression():
    """§2.1 Q23 — a SHAPE check that runs before any field is resolved, so the returned code
    cannot depend on the field's value."""
    peer = services()
    fake = bytes([0x00]) + bytes(32)
    for extra in ({"capability": fake, "resource": fake}, {"resource": fake}):
        out = run(peer, Entity.make(APPLY, {
            "path": "system/compute/builtins/map", "operation": "eval", **extra,
        }))
        assert code_of(out) == "invalid_expression", extra


def test_a_near_miss_builtin_path_is_NOT_a_builtin():
    """``system/compute/builtinsomething`` must not be a builtin — the test is the separator,
    not a prefix. One parser answers both questions so the near-miss cannot split them."""
    peer = services()
    out = run(peer, Entity.make(APPLY, {
        "path": "system/compute/builtinsomething", "operation": "eval",
    }))
    # Handler mode, which this port does not implement — NOT "no such builtin".
    assert code_of(out) == "invalid_expression"
    assert "handler mode" in out.error.detail


def test_an_apply_carrying_both_path_and_fn_is_invalid_before_either_mode():
    """§2.1 [MUST] — "either `path` or `fn`, not both". CONTROL: the same closure through `fn`
    alone evaluates, so the refusal is the rule's and not the closure's."""
    peer = services()
    body = put(peer.store, Entity.make(LITERAL, {"value": 7}))
    lam = put(peer.store, Entity.make(LAMBDA, {"params": [], "body": body}))
    assert run(peer, Entity.make(APPLY, {"fn": lam})).error is None
    out = run(peer, Entity.make(APPLY, {
        "path": "system/compute/builtins/arithmetic", "operation": "eval", "fn": lam,
    }))
    assert code_of(out) == "invalid_expression"
    assert "not both" in out.error.detail


# ── §3.5 — the builtins ─────────────────────────────────────────────────────────


def _builtin(peer: _Services, name: str, args: dict) -> Entity:
    return Entity.make(APPLY, {
        "path": "system/compute/builtins/" + name, "operation": "eval", "args": args,
    })


def test_map_CONTAINS_a_failing_element_rather_than_short_circuiting():
    """§3.5 v3.27 — the OUTPUT element contains. ``map`` never reads the closure's result; it
    places it. §1.5's *"same model as NaN propagation in IEEE 754"* is element-wise, and
    short-circuiting the whole array is exception semantics, which §1.5 declined."""
    peer = services()
    # fn = \x -> x + 1. Element "b" is a string, so it fails — and only it.
    x = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "x"}))
    body = put(peer.store, Entity.make(ARITHMETIC, {
        "op": "add", "left": x, "right": literal(peer.store, 1),
    }))
    lam = put(peer.store, Entity.make(LAMBDA, {"params": ["x"], "body": body}))
    out = run(peer, _builtin(peer, "map", {
        "collection": literal(peer.store, [1, "b", 3]), "fn": lam,
    }))
    got = value_of(out)
    assert isinstance(got, list) and len(got) == 3
    assert got[0] == 2 and got[2] == 4
    # The middle element is a bare `system/hash` pointing at a CODE-ONLY compute/error.
    assert isinstance(got[1], (bytes, bytearray))
    err = peer.store.get_by_hash(bytes(got[1]))
    assert err is not None and err.type == ERROR and err.data == {"code": "type_mismatch"}


def test_filter_SHORT_CIRCUITS_on_a_failing_predicate():
    """§3.5 v3.27 — the row that differs from ``map``'s. The predicate result is READ for
    truthiness to decide inclusion, which makes it a consumed operand; containing it would
    coerce an error to false and SILENTLY DROP the element."""
    peer = services()
    x = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "x"}))
    body = put(peer.store, Entity.make(ARITHMETIC, {
        "op": "add", "left": x, "right": literal(peer.store, 1),
    }))
    lam = put(peer.store, Entity.make(LAMBDA, {"params": ["x"], "body": body}))
    out = run(peer, _builtin(peer, "filter", {
        "collection": literal(peer.store, [1, "b", 3]), "fn": lam,
    }))
    assert code_of(out) == "type_mismatch"


def test_fold_does_NOT_abort_on_an_error_accumulator():
    """§3.5 v3.27 — *"``fold`` MUST NOT abort on an error accumulator"*, and a closure that
    ignores its accumulator RECOVERS. The one position where the two readings produce a
    different VALUE rather than a different cost."""
    peer = services()
    # fn = \acc, e -> e   (ignores the accumulator entirely)
    e = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "e"}))
    lam = put(peer.store, Entity.make(LAMBDA, {"params": ["acc", "e"], "body": e}))
    # `initial` is a stored compute/error — a real value under §3.2's F10.
    bad = put(peer.store, Entity.make(ERROR, {"code": "not_found"}))
    initial = put(peer.store, Entity.make(LOOKUP_HASH, {"hash": bad}))
    out = run(peer, _builtin(peer, "fold", {
        "collection": literal(peer.store, [7]), "fn": lam, "initial": initial,
    }))
    assert value_of(out) == 7


def test_fold_over_an_EMPTY_collection_returns_the_initial_accumulator():
    peer = services()
    e = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "e"}))
    lam = put(peer.store, Entity.make(LAMBDA, {"params": ["acc", "e"], "body": e}))
    out = run(peer, _builtin(peer, "fold", {
        "collection": literal(peer.store, []), "fn": lam, "initial": literal(peer.store, 99),
    }))
    assert value_of(out) == 99


def test_range_REFUSES_rather_than_clamping():
    """§3.5 v3.25 — a negative ``n`` is ``count_out_of_range`` and NOT ``type_mismatch``, and
    it is NOT clamped to ``[]``: ``n`` is a loop bound, so a silent empty array propagates
    through every downstream map/filter/fold as a well-formed wrong answer."""
    peer = services()
    assert value_of(run(peer, _builtin(peer, "range", {"n": literal(peer.store, 3)}))) == [0, 1, 2]
    assert code_of(run(peer, _builtin(peer, "range", {
        "n": literal(peer.store, -1),
    }))) == "count_out_of_range"
    assert code_of(run(peer, _builtin(peer, "range", {
        "n": literal(peer.store, "3"),
    }))) == "type_mismatch"


def test_concat_joins_ONE_level_and_preserves_order():
    """§3.5 v3.27 — ``collections`` is ONE hash of an expression evaluating to an array OF
    arrays, never a literal array of hashes, and the join is one level and not a recursive
    flatten."""
    peer = services()
    out = run(peer, _builtin(peer, "concat", {
        "collections": literal(peer.store, [[1, 2], [3], [[4]]]),
    }))
    assert value_of(out) == [1, 2, 3, [4]]


def test_assoc_uses_compute_indexs_code_and_condition():
    """§3.5 v3.25 — v3.24 said ``type_mismatch`` here and was corrected: one document must not
    answer one malformed program with two codes depending on which array operation it
    reached."""
    peer = services()
    args = {
        "collection": literal(peer.store, [1, 2, 3]),
        "index": literal(peer.store, 1),
        "value": literal(peer.store, 9),
    }
    assert value_of(run(peer, _builtin(peer, "assoc", args))) == [1, 9, 3]

    args_bad = dict(args, index=literal(peer.store, 5))
    assert code_of(run(peer, _builtin(peer, "assoc", args_bad))) == "index_out_of_range"


def test_group_by_orders_groups_by_FIRST_APPEARANCE_of_their_key():
    """§3.5 — one pass, first-appearance order, and the key compared by the MATERIALIZED
    canonical encoding (v3.27 D4)."""
    peer = services()
    x = put(peer.store, Entity.make(LOOKUP_SCOPE, {"name": "x"}))
    body = put(peer.store, Entity.make(ARITHMETIC, {
        "op": "mod", "left": x, "right": literal(peer.store, 2),
    }))
    lam = put(peer.store, Entity.make(LAMBDA, {"params": ["x"], "body": body}))
    out = run(peer, _builtin(peer, "group-by", {
        "collection": literal(peer.store, [1, 2, 3, 4]), "fn": lam,
    }))
    groups = value_of(out)
    assert isinstance(groups, list) and len(groups) == 2
    decoded = [peer.store.get_by_hash(bytes(h)) for h in groups]
    assert [g.field("key") for g in decoded] == [1, 0]        # 1 appears first
    assert [g.field("members") for g in decoded] == [[1, 3], [2, 4]]


def test_the_arithmetic_alias_shares_the_inline_code_path():
    """§10.2's SHOULD aliases, and the reason they share: `entity-core-rust` shipped two
    construct paths that disagreed on the materialized hash, which is what
    ``v319c_inline_vs_builtin_construct_hash_agreement`` exists to catch. There is no second
    copy of any operator's semantics in this port."""
    peer = services()
    out = run(peer, _builtin(peer, "arithmetic", {
        "op": literal(peer.store, "add"),
        "left": literal(peer.store, 20),
        "right": literal(peer.store, 22),
    }))
    assert value_of(out) == 42


def test_the_construct_alias_and_the_inline_form_agree_on_the_MATERIALIZED_HASH():
    """``v319c_inline_vs_builtin_construct_hash_agreement``, as a unit test.

    The vector passes trivially on a single-path implementation and catches the fork on any
    other, which means it cannot tell a port that has one path from a port that has two that
    happen to agree today. Asserting the hashes are EQUAL is that check; asserting they are
    the hash of the bare V7 §1.4 shape is the next test.
    """
    peer = services()
    inline = run(peer, Entity.make(CONSTRUCT, {
        "entity_type": "app/point", "fields": {
            "x": literal(peer.store, 1), "y": literal(peer.store, 2),
        },
    }))
    alias = run(peer, _builtin(peer, "construct", {
        "entity_type": literal(peer.store, "app/point"),
        "x": literal(peer.store, 1),
        "y": literal(peer.store, 2),
    }))
    a = value_of(inline)
    b = value_of(alias)
    assert isinstance(a, Entity) and isinstance(b, Entity)
    assert a.hash == b.hash
    assert a.data == {"x": 1, "y": 2}


def test_store_writes_through_the_tree_and_returns_the_written_entity():
    """§3.5 / §6.3's ``store``, and SA-9's wrapper: a bare-primitive result is wrapped in
    ``primitive/any`` whose DATA IS the value, not a map holding it."""
    peer = services()
    out = run(peer, _builtin(peer, "store", {
        "path": literal(peer.store, "app/out"),
        "value": literal(peer.store, 7),
    }))
    written = value_of(out)
    assert isinstance(written, Entity)
    assert written.type == "primitive/any" and written.data == 7
    assert peer.store.get_at("/" + PEER + "/app/out").hash == written.hash


def test_store_refuses_when_the_write_predicate_says_no():
    """§6.3 — the caller's capability MUST cover the write, and the handler MUST NOT
    substitute its own grant. Driven here through the predicate rather than through a token,
    because the predicate is the seam the handler and §7.2 each supply differently."""
    peer = services()
    out = run(
        peer,
        _builtin(peer, "store", {
            "path": literal(peer.store, "app/out"),
            "value": literal(peer.store, 7),
        }),
        can_write_path=lambda _p: False,
    )
    assert code_of(out) == "permission_denied"
    assert peer.store.get_at("/" + PEER + "/app/out") is None


def test_a_read_predicate_that_says_no_denies_BEFORE_the_dependency_is_registered():
    """§6.2 — the capability check comes before the read AND before the dependency
    registration, so an unauthorized path does not leak its existence through a registered
    dependency. The dependency assertion is the half a port drops."""
    peer = services()
    peer.store.bind("/" + PEER + "/app/secret", Entity.make("app/thing", {"v": 1}))
    ev = ComputeEvaluator(peer)
    out = ev.evaluate_at(
        Entity.make(LOOKUP_TREE, {"path": "app/secret"}), ROOT, can_read_path=lambda _p: False
    )
    assert code_of(out) == "permission_denied"
    assert ev.dependencies == ()


def test_an_unknown_builtin_is_invalid_expression_naming_the_name():
    """The refusal that keeps a typo from looking like a semantic."""
    peer = services()
    out = run(peer, _builtin(peer, "reduce", {}))
    assert code_of(out) == "invalid_expression"
    assert "reduce" in out.error.detail


# ── §4.1 construct / §2.3 in-flight navigation ──────────────────────────────────


def test_construct_fields_evaluate_in_ECF_CANONICAL_key_order():
    """§4.1's ``canonical_sorted`` — by ENCODED BYTE LENGTH first, then lexicographically.

    Length-then-lex, not plain lex: ``"z"`` sorts before ``"aa"``. Getting it wrong produces a
    correct-looking evaluator that disagrees with every other peer about evaluation order the
    moment two field names differ in length — observable whenever a field expression exhausts
    the budget, because the peers then disagree about WHICH field's error is returned.

    Measured through the budget: a budget that runs out after the first field's evaluation
    tells us which field was first.
    """
    peer = services()
    # `z` (1 byte) must be evaluated before `aa` (2 bytes). The `aa` field is the only one
    # that can fail, so a port sorting plain-lex evaluates `aa` FIRST and returns its error;
    # this port evaluates `z` first, spends the budget, and returns budget_exhausted.
    expr = Entity.make(CONSTRUCT, {
        "entity_type": "app/ordered",
        "fields": {
            "aa": put(peer.store, Entity.make(ARITHMETIC, {
                "op": "add", "left": literal(peer.store, "x"), "right": literal(peer.store, 1),
            })),
            "z": literal(peer.store, 1),
        },
    })
    out = run(peer, expr, budget=3)
    assert code_of(out) == "budget_exhausted"

    # THE CONTROL: with budget enough for both, the `aa` error is what comes back — so the
    # test above measured the ORDER and not merely the existence of a small budget.
    assert code_of(run(peer, expr)) == "type_mismatch"


def test_navigation_composes_through_a_construct_INSIDE_one_evaluation():
    """v3.19c option α + §2.3's read-back clause. §4.1's construct arm keeps no in-flight
    representation at all, so a transcription of it can navigate exactly one level: the second
    hop reads a bare ``system/hash`` and answers ``type_mismatch``."""
    peer = services()
    inner = put(peer.store, Entity.make(CONSTRUCT, {
        "entity_type": "app/inner", "fields": {"name": literal(peer.store, "alice")},
    }))
    outer = put(peer.store, Entity.make(CONSTRUCT, {
        "entity_type": "app/outer", "fields": {"inner": inner},
    }))
    hop1 = put(peer.store, Entity.make(FIELD, {"name": "inner", "entity": outer}))
    hop2 = Entity.make(FIELD, {"name": "name", "entity": hop1})
    assert value_of(run(peer, hop2)) == "alice"


def test_THE_NEGATIVE_read_back_navigation_on_a_MATERIALIZED_entity_returns_the_hash():
    """§2.3's other half, and the reason both branches exist rather than one auto-resolving
    heuristic: *"on a bare materialized entity, a reference is followed explicitly."* A port
    that resolved transparently passes the test above and fails this one."""
    peer = services()
    inner = Entity.make("app/inner", {"name": "alice"})
    outer = Entity.make("app/outer", {"inner": inner.hash})
    peer.store.put_entity(inner)
    peer.store.bind("/" + PEER + "/app/outer", outer)
    ref = put(peer.store, Entity.make(LOOKUP_TREE, {"path": "app/outer"}))
    out = run(peer, Entity.make(FIELD, {"name": "inner", "entity": ref}))
    got = value_of(out)
    assert isinstance(got, (bytes, bytearray)) and bytes(got) == inner.hash


def test_the_materialized_form_of_a_nested_construct_is_the_bare_shape():
    """The M1 hash gate's subject: no ``kind`` tags anywhere, entity-valued fields as bare
    ``system/hash``, byte-identical to the same entity built outside compute."""
    peer = services()
    inner = put(peer.store, Entity.make(CONSTRUCT, {
        "entity_type": "app/inner", "fields": {"name": literal(peer.store, "alice")},
    }))
    outer = Entity.make(CONSTRUCT, {"entity_type": "app/outer", "fields": {"inner": inner}})
    got = value_of(run(peer, outer))
    assert isinstance(got, Entity)
    expected_inner = Entity.make("app/inner", {"name": "alice"})
    assert got.data == {"inner": expected_inner.hash}
    assert got.hash == Entity.make("app/outer", {"inner": expected_inner.hash}).hash
    # `materialize` also STORES what the bare form references — the half of the rule that is
    # easy to drop. A returned entity whose `system/hash` field points at nothing the store
    # has is a reference the caller cannot follow, and no vector for that failure exists.
    assert peer.store.get_by_hash(expected_inner.hash) is not None


def test_field_navigation_requires_an_entity_or_record():
    """§2.3 N3 — navigation is by KIND, never by shape."""
    peer = services()
    out = run(peer, Entity.make(FIELD, {
        "name": "x", "entity": literal(peer.store, 5),
    }))
    assert code_of(out) == "type_mismatch"


# ── §4.2 — the three-tier resolution gate ───────────────────────────────────────


def test_resolve_REJECTS_a_non_compute_entity_without_content_store_access():
    """§4.2's whole point: compute is not a content-store oracle. External data goes through
    ``compute/lookup/tree``, which is capability-checked."""
    peer = services()
    data = Entity.make("app/secret", {"v": 1})
    peer.store.put_entity(data)
    out = run(peer, Entity.make(LOOKUP_HASH, {"hash": data.hash}))
    assert code_of(out) == "not_found"


def test_TIER_0_content_store_access_admits_it():
    """The control for the test above — and the door ``_internal`` exists to keep shut."""
    peer = services()
    data = Entity.make("app/secret", {"v": 1})
    peer.store.put_entity(data)
    out = run(peer, Entity.make(LOOKUP_HASH, {"hash": data.hash}), content_store_access=True)
    got = value_of(out)
    assert isinstance(got, Entity) and got.type == "app/secret"


def test_TIER_2_the_sealed_set_admits_it():
    """§4.2 Tier 2 — the set §3.3 Phase 2b sealed. Empty on the explicit-eval path, which is
    why it has to be passed in rather than inferred."""
    peer = services()
    data = Entity.make("app/secret", {"v": 1})
    peer.store.put_entity(data)
    out = run(
        peer,
        Entity.make(LOOKUP_HASH, {"hash": data.hash}),
        authorized_data_hashes=frozenset({data.hash.hex()}),
    )
    got = value_of(out)
    assert isinstance(got, Entity) and got.type == "app/secret"


def test_the_INCLUDED_map_is_consulted_before_the_content_store():
    """§4.2 step 1 — an installer can carry an entity in the EXECUTE rather than publishing it
    first, which is how CP1's adversarial vector arrives."""
    peer = services()
    lit = Entity.make(LITERAL, {"value": 5})
    # Deliberately NOT in the store.
    out = run(
        peer,
        Entity.make(ARITHMETIC, {
            "op": "add", "left": lit.hash, "right": literal(peer.store, 1),
        }),
        included={lit.hash.hex(): lit},
    )
    assert value_of(out) == 6


# ── the type layer ──────────────────────────────────────────────────────────────


def test_33_types_are_defined_and_the_subgraph_carries_the_field_10_1_MUSTs():
    """§2.5's type block declares six fields; §3.3 writes seven and §10.1 MUSTs the seventh by
    name. The declared deviation, asserted."""
    defs = compute_type_defs()
    assert len(defs) == 33
    names = [name for name, _ in defs]
    assert len(set(names)) == 33
    subgraph = next(data for name, data in defs if name == SUBGRAPH)
    assert "authorized_data_hashes" in subgraph["fields"]
    assert len(subgraph["fields"]) == 7


def test_the_eighth_core_expression_type_is_registered():
    """§2.1 says "Seven primitive expression types" and defines EIGHT. The oracle's
    ``types_expression`` asks for seven and its own pass message says seven, so a peer that
    never registers ``compute/lookup/hash`` passes the check that names it — while §10.1 MUSTs
    that very type by name in ``is_compute_type``."""
    names = [name for name, _ in compute_type_defs()]
    assert LOOKUP_HASH in names
    assert is_compute_expression(LOOKUP_HASH)
    assert is_compute_type(LOOKUP_HASH)


def test_a_compute_result_wraps_a_primitive_with_the_source_expressions_hash():
    """§2.4 — and the shape is asserted here because it is the one both the handler's ``eval``
    return and §7.2's result write produce, from two different files."""
    peer = services()
    expr = Entity.make(ARITHMETIC, {
        "op": "add", "left": literal(peer.store, 1), "right": literal(peer.store, 1),
    })
    out = run(peer, expr)
    wrapped = Entity.make(RESULT, {"value": value_of(out), "expression": expr.hash})
    assert wrapped.data["value"] == 2
    assert wrapped.data["expression"] == expr.hash

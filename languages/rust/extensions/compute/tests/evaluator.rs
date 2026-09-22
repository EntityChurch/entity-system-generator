//! §4 — the evaluation algorithm, exercised through the PUBLIC surface only.
//!
//! **What these are for.** Not a conformance claim: on this peer no wire request can reach the
//! evaluator, so the oracle's `compute` category cannot score it at all. These tests cover the
//! clauses where §4.1 says something a reasonable implementation gets wrong, and the ones marked
//! *substrate* are the places Rust's own semantics have an opinion §4.1 does not share.
//!
//! Each substrate test was written BEFORE the composed run, as `python`'s seven were.

mod common;

use std::collections::{BTreeMap, HashSet};

use common::*;
use entity_compute::*;
use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::Value;

fn arith(store: &Store, op: &str, l: Value, r: Value) -> Entity {
    let left = literal(store, l);
    let right = literal(store, r);
    entity(ARITHMETIC, vec![("op", text(op)), ("left", bytes(&left)), ("right", bytes(&right))])
}

fn compare(store: &Store, op: &str, l: Value, r: Value) -> Entity {
    let left = literal(store, l);
    let right = literal(store, r);
    entity(COMPARE, vec![("op", text(op)), ("left", bytes(&left)), ("right", bytes(&right))])
}

fn cast(store: &Store, value: Value, to: &str) -> Vec<u8> {
    let v = literal(store, value);
    put(store, entity(NUMERIC_CAST, vec![("value", bytes(&v)), ("to_type", text(to))]))
}

fn float_of(v: Value) -> f64 {
    match v {
        Value::Float(f) => f,
        other => panic!("expected a float, got {other:?}"),
    }
}

// ── §2.1 / §4.1 — the core forms ────────────────────────────────────────────────────

#[test]
fn literal_evaluates_to_its_value() {
    let s = Store::new();
    assert_eq!(value_of(&run(&s, &entity(LITERAL, vec![("value", int(7))]))), int(7));
}

#[test]
fn a_literal_holding_a_stored_null_round_trips() {
    // null is a VALUE (§4.5 makes it falsy), distinct from an absent key.
    let s = Store::new();
    assert_eq!(value_of(&run(&s, &entity(LITERAL, vec![("value", Value::Null)]))), Value::Null);
}

#[test]
fn a_literal_with_no_value_key_is_invalid_expression() {
    let s = Store::new();
    assert_eq!(code_of(&run(&s, &entity(LITERAL, vec![]))), CODE_INVALID_EXPRESSION);
}

// ── §4.1 arithmetic ─────────────────────────────────────────────────────────────────

#[test]
fn arithmetic_reads_operands_through_hash_references() {
    let s = Store::new();
    assert_eq!(value_of(&run(&s, &arith(&s, "add", int(2), int(3)))), int(5));
    // The NEGATIVE: an operand hash nothing stores is not_found, not a default of zero.
    let dangling = entity(ARITHMETIC, vec![("op", text("add")), ("left", bytes(&[0; 33])), ("right", bytes(&[0; 33]))]);
    assert_eq!(code_of(&run(&s, &dangling)), CODE_NOT_FOUND);
}

#[test]
fn div_exact_stays_integer_inexact_promotes_to_float() {
    let s = Store::new();
    assert_eq!(value_of(&run(&s, &arith(&s, "div", int(10), int(2)))), int(5));
    assert_eq!(float_of(value_of(&run(&s, &arith(&s, "div", int(7), int(2))))), 3.5);
}

/// **substrate, and a finding about our own `python` port.** §4.1: an inexact integer division is
/// `to_float(left) / to_float(right)` — each operand converted, THEN divided. `typescript` and
/// `entity-core-go` do exactly that. Python's `int / int` is CORRECTLY ROUNDED over the exact
/// rational instead, and the two disagree once an operand exceeds 2^53: for `(2^60 + 127) / 3`
/// python yields 384307168202282368.0 and §4.1 yields 384307168202282304.0. This pins the spec's.
#[test]
fn inexact_div_converts_each_operand_before_dividing() {
    let s = Store::new();
    let l: i128 = (1 << 60) + 127;
    let got = float_of(value_of(&run(&s, &arith(&s, "div", int(l), int(3)))));
    assert_eq!(got, 384_307_168_202_282_304.0);
    assert_ne!(got, 384_307_168_202_282_368.0, "that is the correctly-rounded quotient §4.1 does not use");
}

#[test]
fn integer_div_by_zero_errors_float_div_by_zero_is_ieee() {
    let s = Store::new();
    assert_eq!(code_of(&run(&s, &arith(&s, "div", int(1), int(0)))), CODE_DIVISION_BY_ZERO);
    assert_eq!(code_of(&run(&s, &arith(&s, "mod", int(1), int(0)))), CODE_DIVISION_BY_ZERO);
    assert_eq!(float_of(value_of(&run(&s, &arith(&s, "div", Value::Float(1.0), int(0))))), f64::INFINITY);
    let neg = float_of(value_of(&run(&s, &arith(&s, "div", Value::Float(1.0), Value::Float(-0.0)))));
    assert_eq!(neg, f64::NEG_INFINITY, "IEEE distinguishes -0.0");
    assert!(float_of(value_of(&run(&s, &arith(&s, "div", Value::Float(0.0), int(0))))).is_nan());
    // Float MOD by zero IS division_by_zero — §4.1's `mod` arm checks before the float split.
    assert_eq!(code_of(&run(&s, &arith(&s, "mod", Value::Float(1.0), Value::Float(0.0)))), CODE_DIVISION_BY_ZERO);
}

#[test]
fn mod_is_truncated_not_floored() {
    // The three `v36_mod_*` vectors' shapes. Rust's `%` truncates, which is §4.1's rule; the test is
    // here so a port change to `rem_euclid` — the natural "fix" for a negative result — goes red.
    let s = Store::new();
    assert_eq!(value_of(&run(&s, &arith(&s, "mod", int(-7), int(2)))), int(-1));
    assert_eq!(value_of(&run(&s, &arith(&s, "mod", int(7), int(-2)))), int(1));
    assert_eq!(value_of(&run(&s, &arith(&s, "mod", int(-7), int(-2)))), int(-1));
    assert_eq!(float_of(value_of(&run(&s, &arith(&s, "mod", Value::Float(-7.5), int(2))))), -1.5);
}

#[test]
fn add_sub_mul_are_sign_agnostic_and_wrap_at_2_64() {
    let s = Store::new();
    let max_u = u64::MAX as i128;
    assert_eq!(value_of(&run(&s, &arith(&s, "add", int(max_u), int(1)))), int(0));
    assert_eq!(value_of(&run(&s, &arith(&s, "sub", int(i64::MIN as i128), int(1)))), int(i64::MAX as i128));
}

/// **substrate.** `u64 * u64` is up to 2^128 and overflows `i128`, so `mul` cannot be computed
/// exactly the way `add` is. The bit pattern comes from `wrapping_mul` and the TRUE product's sign
/// decides the reading. Each case below would be wrong under a different shortcut.
#[test]
fn mul_wraps_past_i128_and_keeps_the_sign_of_the_true_product() {
    let s = Store::new();
    let max_u = u64::MAX as i128;
    assert_eq!(value_of(&run(&s, &arith(&s, "mul", int(max_u), int(max_u)))), int(1), "(2^64-1)^2 mod 2^64");
    assert_eq!(value_of(&run(&s, &arith(&s, "mul", int(1 << 63), int(2)))), int(0));
    assert_eq!(value_of(&run(&s, &arith(&s, "mul", int(-1), int(3)))), int(-3));
    assert_eq!(value_of(&run(&s, &arith(&s, "mul", int(-2), int(-3)))), int(6));
    assert_eq!(value_of(&run(&s, &arith(&s, "mul", int(0), int(-3)))), int(0), "zero is not negative");
}

#[test]
fn div_is_signed_default_unless_a_direct_uint_cast_is_the_operand() {
    let s = Store::new();
    let big = (u64::MAX - 1) as i128; // reads as -2 signed
    assert_eq!(value_of(&run(&s, &arith(&s, "div", int(big), int(2)))), int(-1));

    let casted = cast(&s, int(big), "primitive/uint");
    let two = literal(&s, int(2));
    let direct = entity(ARITHMETIC, vec![("op", text("div")), ("left", bytes(&casted)), ("right", bytes(&two))]);
    assert_eq!(value_of(&run(&s, &direct)), int(((u64::MAX - 1) / 2) as i128));

    // THE NEGATIVE: through a `let`, the cast is no longer the direct operand, so the intent drops.
    let lookup = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("y"))]));
    let body = put(&s, entity(ARITHMETIC, vec![("op", text("div")), ("left", bytes(&lookup)), ("right", bytes(&two))]));
    let indirect = entity(LET, vec![("bindings", Value::Array(vec![map(vec![("name", text("y")), ("value", bytes(&casted))])])), ("body", bytes(&body))]);
    assert_eq!(value_of(&run(&s, &indirect)), int(-1));
}

// ── §4.1 comparison ─────────────────────────────────────────────────────────────────

#[test]
fn eq_across_type_classes_is_false_not_a_type_mismatch() {
    let s = Store::new();
    assert_eq!(value_of(&run(&s, &compare(&s, "eq", int(1), text("1")))), Value::Bool(false));
    assert_eq!(value_of(&run(&s, &compare(&s, "neq", int(1), text("1")))), Value::Bool(true));
    // The tagged model keeps bool and int apart by construction; asserted anyway, because it is
    // the rule `python` needed a special case for.
    assert_eq!(value_of(&run(&s, &compare(&s, "eq", Value::Bool(true), int(1)))), Value::Bool(false));
}

#[test]
fn eq_over_ints_and_floats_is_one_type_class() {
    let s = Store::new();
    assert_eq!(value_of(&run(&s, &compare(&s, "eq", int(1), Value::Float(1.0)))), Value::Bool(true));
    // ...but inside an ARRAY, identity is the canonical encoding, where 1 and 1.0 differ.
    let a = Value::Array(vec![int(1)]);
    let b = Value::Array(vec![Value::Float(1.0)]);
    assert_eq!(value_of(&run(&s, &compare(&s, "eq", a.clone(), b))), Value::Bool(false));
    assert_eq!(value_of(&run(&s, &compare(&s, "eq", a.clone(), a))), Value::Bool(true));
}

#[test]
fn ordering_across_type_classes_is_a_type_mismatch_and_strings_order_by_utf8_bytes() {
    let s = Store::new();
    assert_eq!(code_of(&run(&s, &compare(&s, "lt", int(1), text("a")))), CODE_TYPE_MISMATCH);
    // "Z" (0x5A) < "a" (0x61) by bytes; "é" (0xC3 0xA9) > "z" by bytes.
    assert_eq!(value_of(&run(&s, &compare(&s, "lt", text("Z"), text("a")))), Value::Bool(true));
    assert_eq!(value_of(&run(&s, &compare(&s, "gt", text("é"), text("z")))), Value::Bool(true));
    // NaN is unordered: every ordering comparison is false, including lte and gte.
    assert_eq!(value_of(&run(&s, &compare(&s, "lte", Value::Float(f64::NAN), int(1)))), Value::Bool(false));
    assert_eq!(value_of(&run(&s, &compare(&s, "gte", Value::Float(f64::NAN), int(1)))), Value::Bool(false));
}

// ── §4.1 logic, truthiness, if, let ─────────────────────────────────────────────────

#[test]
fn logic_not_returns_before_right_is_resolved_and_and_or_do_not_short_circuit() {
    let s = Store::new();
    let t = literal(&s, Value::Bool(true));
    let not = entity(LOGIC, vec![("op", text("not")), ("left", bytes(&t)), ("right", bytes(&[0; 33]))]);
    assert_eq!(value_of(&run(&s, &not)), Value::Bool(false));

    let f = literal(&s, Value::Bool(false));
    let and = entity(LOGIC, vec![("op", text("and")), ("left", bytes(&f)), ("right", bytes(&t))]);
    let used = run(&s, &and).operations_used;
    // Three evaluate() steps: the logic node, left, AND right — the right operand is charged even
    // though `false and _` is decided by the left.
    assert_eq!(used, 3);
}

#[test]
fn truthiness_ladder() {
    let s = Store::new();
    let falsy = [Value::Null, Value::Bool(false), int(0), Value::Float(0.0), text(""), Value::Array(vec![])];
    let truthy = [int(-1), Value::Float(f64::NAN), text("0"), Value::Array(vec![Value::Null]), map(vec![]), Value::Bytes(vec![])];
    for (v, expected) in falsy.iter().map(|v| (v, false)).chain(truthy.iter().map(|v| (v, true))) {
        let c = literal(&s, v.clone());
        let one = literal(&s, int(1));
        let zero = literal(&s, int(0));
        let e = entity(IF, vec![("condition", bytes(&c)), ("then", bytes(&one)), ("else", bytes(&zero))]);
        assert_eq!(value_of(&run(&s, &e)), int(expected as i128), "truthy({v:?})");
    }
}

#[test]
fn a_falsy_if_with_no_else_returns_null_not_an_error() {
    let s = Store::new();
    let c = literal(&s, Value::Bool(false));
    let one = literal(&s, int(1));
    assert_eq!(value_of(&run(&s, &entity(IF, vec![("condition", bytes(&c)), ("then", bytes(&one))]))), Value::Null);
}

#[test]
fn let_bindings_are_sequential() {
    let s = Store::new();
    let one = literal(&s, int(1));
    let x = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("x"))]));
    let x_plus_one = put(&s, entity(ARITHMETIC, vec![("op", text("add")), ("left", bytes(&x)), ("right", bytes(&one))]));
    let y = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("y"))]));
    let e = entity(
        LET,
        vec![
            ("bindings", Value::Array(vec![
                map(vec![("name", text("x")), ("value", bytes(&one))]),
                map(vec![("name", text("y")), ("value", bytes(&x_plus_one))]),
            ])),
            ("body", bytes(&y)),
        ],
    );
    assert_eq!(value_of(&run(&s, &e)), int(2));
}

#[test]
fn a_missing_scope_name_is_not_found_and_a_null_binding_is_still_a_binding() {
    let s = Store::new();
    assert_eq!(code_of(&run(&s, &entity(LOOKUP_SCOPE, vec![("name", text("nope"))]))), CODE_NOT_FOUND);
    let null = literal(&s, Value::Null);
    let n = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("n"))]));
    let e = entity(LET, vec![("bindings", Value::Array(vec![map(vec![("name", text("n")), ("value", bytes(&null))])])), ("body", bytes(&n))]);
    assert_eq!(value_of(&run(&s, &e)), Value::Null);
}

// ── §2.1 lookups ────────────────────────────────────────────────────────────────────

#[test]
fn lookup_tree_evaluates_a_stored_expression_and_returns_a_stored_value() {
    let s = Store::new();
    let expr = arith(&s, "add", int(1), int(1));
    s.bind(&format!("/{PEER}/app/sum"), &expr);
    let value = entity("app/thing", vec![("x", int(9))]);
    s.bind(&format!("/{PEER}/app/thing"), &value);

    assert_eq!(value_of(&run(&s, &entity(LOOKUP_TREE, vec![("path", text("app/sum"))]))), int(2));
    assert_eq!(entity_of(&run(&s, &entity(LOOKUP_TREE, vec![("path", text("app/thing"))]))).hash, value.hash);
}

#[test]
fn lookup_tree_canonicalizes_and_the_dependency_records_the_canonical_form() {
    let s = Store::new();
    s.bind(&format!("/{PEER}/app/v"), &entity("app/v", vec![]));
    let mut ev = ComputeEvaluator::new(&s, PEER, DEFAULT_LIMITS);
    let out = ev.evaluate_at(&entity(LOOKUP_TREE, vec![("path", text("app/v"))]), &root(), EvaluateOptions::default());
    assert!(out.error.is_none());
    assert_eq!(ev.dependencies(), [format!("/{PEER}/app/v")]);
}

/// **substrate, and the FOURTH data point for `[assumptions].reserved_relative_path_forms` — this
/// test went red on the peer moving under us, which is what it was written to do.**
///
/// It used to assert that this peer's `capability::canonicalize` PREFIXES `./x` like any relative
/// path (`/{PEER}/./x`), and its own docstring ended *"if keystone makes this peer refuse, this
/// test goes red and says so."* Keystone's 0.8.2.20 work did neither: `canonicalize` went TOTAL and
/// now returns the `NEVER_MATCH` sentinel for the three §1.4 reserved forms. Landed in
/// `c255fdfe`/`2f6547ae` — the 45-language sweep, which is not addressed to us and changed our
/// substrate anyway.
///
/// **The observable verdict is UNCHANGED and the two things under it both moved**, which is why
/// this is three assertions now rather than one:
///   1. still `not_found` under a permissive read predicate — nothing is bound at the sentinel;
///   2. NO dependency is registered, where the old path registered `/{PEER}/./x`;
///   3. under a REAL grant it is `permission_denied`, not `not_found`, because `matches_pattern`
///      refuses `NEVER_MATCH` in either operand. That third one is a genuine change of answer and
///      it was invisible before: every existing assertion here ran on the default permissive
///      predicate, so the capability arm was never reached.
#[test]
fn a_reserved_relative_form_canonicalizes_to_the_sentinel_and_is_not_a_dependency() {
    let s = Store::new();
    let mut ev = ComputeEvaluator::new(&s, PEER, DEFAULT_LIMITS);
    let out = ev.evaluate_at(&entity(LOOKUP_TREE, vec![("path", text("./x"))]), &root(), EvaluateOptions::default());
    assert_eq!(code_of(&out), CODE_NOT_FOUND);
    assert!(ev.dependencies().is_empty(), "the sentinel is not a path: {:?}", ev.dependencies());

    // CONTROL — the same lookup at an ORDINARY relative path still registers its dependency. Without
    // this, a `register_dependency` that had simply stopped working would pass the assertion above.
    let mut ev2 = ComputeEvaluator::new(&s, PEER, DEFAULT_LIMITS);
    let _ = ev2.evaluate_at(&entity(LOOKUP_TREE, vec![("path", text("app/x"))]), &root(), EvaluateOptions::default());
    assert_eq!(ev2.dependencies(), [format!("/{PEER}/app/x")]);
}

/// The third assertion above, given its own test because it is a CHANGE OF ANSWER rather than a
/// change of internal bookkeeping: on this peer a §1.4 reserved form under a real grant now fails
/// CLOSED. `python` answers `invalid_expression` and `typescript` answers `not_found`, so the three
/// ports now give three different codes for one input — recorded in the contract's assumption row,
/// not routed, because core `CORE-TREE-PATH-FLEX-1` makes all three conformant.
#[test]
fn a_reserved_relative_form_fails_closed_under_a_real_grant() {
    let s = Store::new();
    let deny_sentinel = |p: &str| p != "/never-match";
    let mut ev = ComputeEvaluator::new(&s, PEER, DEFAULT_LIMITS);
    let out = ev.evaluate_at(
        &entity(LOOKUP_TREE, vec![("path", text("./x"))]),
        &root(),
        EvaluateOptions { can_read_path: Some(&deny_sentinel), ..Default::default() },
    );
    assert_eq!(code_of(&out), CODE_PERMISSION_DENIED);
}

#[test]
fn relative_lookup_resolves_against_the_subgraph_root() {
    let s = Store::new();
    s.bind(&format!("/{PEER}/app/sibling"), &entity("app/v", vec![("n", int(3))]));
    let e = entity(LOOKUP_TREE, vec![("path", text("../sibling")), ("relative", Value::Bool(true))]);
    assert_eq!(entity_of(&run(&s, &e)).typ, "app/v");
}

#[test]
fn a_read_predicate_that_says_no_denies_before_the_dependency_is_registered() {
    let s = Store::new();
    s.bind(&format!("/{PEER}/app/secret"), &entity("app/v", vec![]));
    let deny = |_: &str| false;
    let mut ev = ComputeEvaluator::new(&s, PEER, DEFAULT_LIMITS);
    let out = ev.evaluate_at(
        &entity(LOOKUP_TREE, vec![("path", text("app/secret"))]),
        &root(),
        EvaluateOptions { can_read_path: Some(&deny), ..Default::default() },
    );
    assert_eq!(code_of(&out), CODE_PERMISSION_DENIED);
    assert!(ev.dependencies().is_empty(), "an unauthorized path must not leak through a registered dependency");
}

// ── §2.2 N.1 / N.4 ──────────────────────────────────────────────────────────────────

#[test]
fn index_length_and_numeric_cast_evaluate_and_are_in_both_membership_lists() {
    for t in [INDEX, LENGTH, NUMERIC_CAST] {
        assert!(is_compute_expression(t) && is_compute_type(t), "{t}");
    }
    let s = Store::new();
    let arr = literal(&s, Value::Array(vec![int(10), int(20)]));
    let one = literal(&s, int(1));
    assert_eq!(value_of(&run(&s, &entity(INDEX, vec![("array", bytes(&arr)), ("index", bytes(&one))]))), int(20));
    assert_eq!(value_of(&run(&s, &entity(LENGTH, vec![("array", bytes(&arr))]))), int(2));
    let neg = literal(&s, int(-1));
    assert_eq!(code_of(&run(&s, &entity(INDEX, vec![("array", bytes(&arr)), ("index", bytes(&neg))]))), CODE_INDEX_OUT_OF_RANGE);
    let hello = literal(&s, text("hello"));
    assert_eq!(code_of(&run(&s, &entity(LENGTH, vec![("array", bytes(&hello))]))), CODE_TYPE_MISMATCH);
}

#[test]
fn casting_nan_or_inf_to_an_integer_is_cast_out_of_range_and_negative_int_to_uint_reinterprets() {
    let s = Store::new();
    for v in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        let c = cast(&s, Value::Float(v), "primitive/int");
        assert_eq!(code_of(&run(&s, &s.get_by_hash(&c).unwrap())), CODE_CAST_OUT_OF_RANGE);
    }
    let c = cast(&s, int(-1), "primitive/uint");
    assert_eq!(value_of(&run(&s, &s.get_by_hash(&c).unwrap())), int(u64::MAX as i128));
    let c = cast(&s, Value::Float(-1.5), "primitive/uint");
    assert_eq!(code_of(&run(&s, &s.get_by_hash(&c).unwrap())), CODE_CAST_OUT_OF_RANGE);
}

/// **substrate.** `f64 as i64` SATURATES in Rust and maps NaN to 0 — a cast that never fails, which
/// is the opposite of §2.2 rule 11. Every boundary below is one a saturating cast gets silently
/// wrong: 2^63 as int would come back as `i64::MAX`, 2^64 as uint as `u64::MAX`.
#[test]
fn float_casts_range_check_before_any_native_cast() {
    let s = Store::new();
    let two63 = 9_223_372_036_854_775_808.0_f64;
    let two64 = 18_446_744_073_709_551_616.0_f64;
    let run_cast = |v: f64, to: &str| {
        let c = cast(&s, Value::Float(v), to);
        run(&s, &s.get_by_hash(&c).unwrap())
    };
    assert_eq!(code_of(&run_cast(two63, "primitive/int")), CODE_CAST_OUT_OF_RANGE);
    assert_eq!(value_of(&run_cast(-two63, "primitive/int")), int(i64::MIN as i128));
    assert_eq!(code_of(&run_cast(two64, "primitive/uint")), CODE_CAST_OUT_OF_RANGE);
    assert_eq!(value_of(&run_cast(1e19, "primitive/uint")), int(10_000_000_000_000_000_000));
    assert_eq!(value_of(&run_cast(-0.5, "primitive/uint")), int(0), "trunc(-0.5) is -0.0, which is not < 0");
    assert_eq!(value_of(&run_cast(-7.9, "primitive/int")), int(-7));
}

// ── §4.2 / §5 — the budget and the depth ────────────────────────────────────────────

#[test]
fn the_budget_charges_evaluate_steps_and_nothing_else() {
    let s = Store::new();
    // arithmetic node + two literals = 3 steps; resolve() is free.
    assert_eq!(run(&s, &arith(&s, "add", int(1), int(2))).operations_used, 3);
}

#[test]
fn an_exhausted_budget_yields_budget_exhausted_and_a_caller_cannot_raise_its_ceiling() {
    let s = Store::new();
    let e = arith(&s, "add", int(1), int(2));
    let tight = EvaluatorLimits { max_operations: 2, max_depth: 64 };
    assert_eq!(code_of(&run_with(&s, &e, tight, EvaluateOptions::default())), CODE_BUDGET_EXHAUSTED);
    let asked = EvaluateOptions { budget: Some(1_000_000), ..Default::default() };
    assert_eq!(code_of(&run_with(&s, &e, tight, asked)), CODE_BUDGET_EXHAUSTED, "§5.2's minimum rule");
}

/// Build `let f = lambda(n) -> if n then f(n-1) else 0` style recursion without a real `f` in scope:
/// a chain of `depth` nested `if`s (tail) or `add`s (non-tail) over a literal.
fn chain(s: &Store, depth: usize, tail: bool) -> Entity {
    let mut h = literal(s, int(0));
    let t = literal(s, Value::Bool(true));
    let one = literal(s, int(1));
    for _ in 0..depth {
        let e = if tail {
            entity(IF, vec![("condition", bytes(&t)), ("then", bytes(&h))])
        } else {
            entity(ARITHMETIC, vec![("op", text("add")), ("left", bytes(&h)), ("right", bytes(&one))])
        };
        h = put(s, e);
    }
    s.get_by_hash(&h).unwrap()
}

#[test]
fn a_tail_chain_does_not_consume_depth_and_a_non_tail_chain_does() {
    let s = Store::new();
    let limits = EvaluatorLimits { max_operations: 1_000_000, max_depth: 16 };
    assert_eq!(value_of(&run_with(&s, &chain(&s, 200, true), limits, EvaluateOptions::default())), int(0));
    assert_eq!(code_of(&run_with(&s, &chain(&s, 200, false), limits, EvaluateOptions::default())), CODE_DEPTH_EXCEEDED);
}

/// **substrate, and the liveness control for `sdk::EVAL_STACK_BYTES`.** A Rust thread that
/// overflows its stack ABORTS the process — no `RecursionError`, no `RangeError`, no unwinding.
/// §9.3's `max_depth` is 1024, and a non-tail chain deeper than that must come back as a
/// `depth_exceeded` VALUE from a debug build. If the evaluation stack is ever sized too small this
/// test does not fail: the test binary dies, which `cargo test` reports as a signal.
#[test]
fn depth_limit_is_reached_without_overflowing_the_stack() {
    let s = Store::new();
    let deep = chain(&s, 1100, false);
    assert_eq!(code_of(&run(&s, &deep)), CODE_DEPTH_EXCEEDED);
    let at_limit = chain(&s, 1000, false);
    assert_eq!(value_of(&run(&s, &at_limit)), int(1000));
}

// ── §2.4 / §4.1 — errors are kind-based ─────────────────────────────────────────────

#[test]
fn a_stored_compute_error_short_circuits_its_consumer_and_materializes_code_only() {
    let s = Store::new();
    let stored = put(&s, entity(ERROR, vec![("code", text("custom_code")), ("message", text("diagnostic"))]));
    let one = literal(&s, int(1));
    let e = entity(IF, vec![("condition", bytes(&stored)), ("then", bytes(&one))]);
    let out = run(&s, &e);
    assert_eq!(code_of(&out), "custom_code");
    let materialized = out.error.unwrap().to_entity();
    assert_eq!(materialized, entity(ERROR, vec![("code", text("custom_code"))]), "message is never materialized");
}

// ── §2.3 closures and value types ───────────────────────────────────────────────────

fn identity_closure_apply(s: &Store, arg: Value) -> Entity {
    let x = put(s, entity(LOOKUP_SCOPE, vec![("name", text("x"))]));
    let lam = put(s, entity(LAMBDA, vec![("params", Value::Array(vec![text("x")])), ("body", bytes(&x))]));
    let a = literal(s, arg);
    entity(APPLY, vec![("fn", bytes(&lam)), ("args", map(vec![("x", bytes(&a))]))])
}

#[test]
fn a_lambda_applies_and_a_missing_argument_is_named_after_the_param() {
    let s = Store::new();
    assert_eq!(value_of(&run(&s, &identity_closure_apply(&s, int(5)))), int(5));
    let x = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("x"))]));
    let lam = put(&s, entity(LAMBDA, vec![("params", Value::Array(vec![text("x")])), ("body", bytes(&x))]));
    let out = run(&s, &entity(APPLY, vec![("fn", bytes(&lam))]));
    assert_eq!(code_of(&out), CODE_MISSING_ARGUMENT);
    assert!(out.error.unwrap().detail.contains('x'));
}

#[test]
fn a_closure_captures_its_scope() {
    let s = Store::new();
    let seven = literal(&s, int(7));
    let y = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("y"))]));
    let lam = put(&s, entity(LAMBDA, vec![("params", Value::Array(vec![])), ("body", bytes(&y))]));
    let apply = put(&s, entity(APPLY, vec![("fn", bytes(&lam))]));
    let e = entity(LET, vec![("bindings", Value::Array(vec![map(vec![("name", text("y")), ("value", bytes(&seven))])])), ("body", bytes(&apply))]);
    assert_eq!(value_of(&run(&s, &e)), int(7));
}

/// SA-1: a stored `compute/closure` applied must reach `load_scope` — `v319b_scope_unreachable`'s
/// shape — rather than falling into §4.1's `unknown_type`.
#[test]
fn a_stored_closure_applied_reaches_load_scope() {
    let s = Store::new();
    let body = literal(&s, int(1));
    let dangling_binding = map(vec![("kind", text("entity")), ("entity_hash", bytes(&[9; 33]))]);
    let env = put(&s, entity(SCOPE, vec![("bindings", map(vec![("gone", dangling_binding)]))]));
    let closure = put(&s, entity(CLOSURE, vec![("params", Value::Array(vec![])), ("body", bytes(&body)), ("env", bytes(&env))]));
    assert_eq!(code_of(&run(&s, &entity(APPLY, vec![("fn", bytes(&closure))]))), CODE_SCOPE_UNREACHABLE);
}

#[test]
fn each_value_type_evaluates_to_itself_and_an_unknown_type_is_still_unknown_type() {
    let s = Store::new();
    let body = literal(&s, int(1));
    for e in [
        entity(CLOSURE, vec![("params", Value::Array(vec![])), ("body", bytes(&body))]),
        entity(SCOPE, vec![("bindings", map(vec![]))]),
        entity(RESULT, vec![("value", int(1)), ("expression", bytes(&body))]),
    ] {
        assert_eq!(entity_of(&run(&s, &e)).hash, e.hash, "{}", e.typ);
    }
    // THE NEGATIVE: widening the fallthrough to "anything not an expression" would pass the loop
    // above and turn `eval_error_non_expression`'s code into dead code.
    assert_eq!(code_of(&run(&s, &entity("compute/nonsense", vec![]))), CODE_UNKNOWN_TYPE);
    assert_eq!(code_of(&run(&s, &entity("app/thing", vec![]))), CODE_UNKNOWN_TYPE);
}

// ── §3.5 builtins ───────────────────────────────────────────────────────────────────

fn builtin(_s: &Store, name: &str, args: Vec<(&str, Vec<u8>)>) -> Entity {
    entity(
        APPLY,
        vec![
            ("path", text(&format!("{BUILTINS_PREFIX}/{name}"))),
            ("operation", text("eval")),
            ("args", map(args.into_iter().map(|(k, v)| (k, bytes(&v))).collect())),
        ],
    )
}

fn lambda(s: &Store, params: &[&str], body: Vec<u8>) -> Vec<u8> {
    put(s, entity(LAMBDA, vec![("params", Value::Array(params.iter().map(|p| text(p)).collect())), ("body", bytes(&body))]))
}

#[test]
fn a_builtin_path_apply_carrying_capability_or_resource_is_invalid_and_a_near_miss_is_not_a_builtin() {
    let s = Store::new();
    let h = literal(&s, int(1));
    let bad = entity(APPLY, vec![("path", text(&format!("{BUILTINS_PREFIX}/map"))), ("operation", text("eval")), ("resource", bytes(&h))]);
    assert_eq!(code_of(&run(&s, &bad)), CODE_INVALID_EXPRESSION);
    let near = entity(APPLY, vec![("path", text("system/compute/builtinsmap")), ("operation", text("eval"))]);
    let out = run(&s, &near);
    assert_eq!(code_of(&out), CODE_INVALID_EXPRESSION);
    // With no dispatcher (an in-process evaluation), handler mode names that; a builtin would have run.
    assert!(out.error.unwrap().detail.contains("handler dispatch not available"), "a near miss is handler mode, not a builtin");
}

#[test]
fn map_contains_a_failing_element_and_filter_short_circuits() {
    let s = Store::new();
    let coll = literal(&s, Value::Array(vec![int(2), int(0), int(4)]));
    let x = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("x"))]));
    let ten = literal(&s, int(10));
    let div = put(&s, entity(ARITHMETIC, vec![("op", text("div")), ("left", bytes(&ten)), ("right", bytes(&x))]));
    let f = lambda(&s, &["x"], div);

    let mapped = value_of(&run(&s, &builtin(&s, "map", vec![("collection", coll.clone()), ("fn", f.clone())])));
    let Value::Array(items) = mapped else { panic!() };
    assert_eq!(items[0], int(5));
    assert_eq!(items[2], Value::Float(2.5));
    let err_hash = entity(ERROR, vec![("code", text(CODE_DIVISION_BY_ZERO))]).hash;
    assert_eq!(items[1], Value::Bytes(err_hash), "a contained error is a code-only entity, by hash");

    assert_eq!(code_of(&run(&s, &builtin(&s, "filter", vec![("collection", coll), ("fn", f)]))), CODE_DIVISION_BY_ZERO);
}

#[test]
fn fold_does_not_abort_on_an_error_accumulator_and_an_empty_fold_is_the_initial() {
    let s = Store::new();
    // fn(acc, x) -> x : ignores its accumulator, so an error initial is recovered from.
    let x = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("x"))]));
    let f = lambda(&s, &["acc", "x"], x);
    let one = literal(&s, int(1));
    let zero = literal(&s, int(0));
    let bad_initial = put(&s, entity(ARITHMETIC, vec![("op", text("div")), ("left", bytes(&one)), ("right", bytes(&zero))]));
    let coll = literal(&s, Value::Array(vec![int(7)]));
    assert_eq!(value_of(&run(&s, &builtin(&s, "fold", vec![("collection", coll), ("fn", f.clone()), ("initial", bad_initial)]))), int(7));

    let empty = literal(&s, Value::Array(vec![]));
    let init = literal(&s, text("start"));
    assert_eq!(value_of(&run(&s, &builtin(&s, "fold", vec![("collection", empty), ("fn", f), ("initial", init)]))), text("start"));
}

#[test]
fn range_refuses_rather_than_clamping() {
    let s = Store::new();
    let three = literal(&s, int(3));
    assert_eq!(value_of(&run(&s, &builtin(&s, "range", vec![("n", three)]))), Value::Array(vec![int(0), int(1), int(2)]));
    let neg = literal(&s, int(-1));
    assert_eq!(code_of(&run(&s, &builtin(&s, "range", vec![("n", neg)]))), CODE_COUNT_OUT_OF_RANGE);
    // Past this runtime's maximum Vec<Value> length — refused WITHOUT attempting the allocation.
    let huge = literal(&s, int(i64::MAX as i128));
    assert_eq!(code_of(&run(&s, &builtin(&s, "range", vec![("n", huge)]))), CODE_COUNT_OUT_OF_RANGE);
}

#[test]
fn concat_joins_one_level_and_assoc_uses_index_codes() {
    let s = Store::new();
    let nested = literal(&s, Value::Array(vec![Value::Array(vec![int(1)]), Value::Array(vec![Value::Array(vec![int(2)])])]));
    assert_eq!(
        value_of(&run(&s, &builtin(&s, "concat", vec![("collections", nested)]))),
        Value::Array(vec![int(1), Value::Array(vec![int(2)])])
    );
    let coll = literal(&s, Value::Array(vec![int(1), int(2)]));
    let idx = literal(&s, int(2));
    let v = literal(&s, int(9));
    assert_eq!(code_of(&run(&s, &builtin(&s, "assoc", vec![("collection", coll.clone()), ("index", idx), ("value", v.clone())]))), CODE_INDEX_OUT_OF_RANGE);
    let idx0 = literal(&s, int(0));
    assert_eq!(value_of(&run(&s, &builtin(&s, "assoc", vec![("collection", coll), ("index", idx0), ("value", v)]))), Value::Array(vec![int(9), int(2)]));
}

#[test]
fn group_by_orders_groups_by_first_appearance_of_their_key() {
    let s = Store::new();
    let coll = literal(&s, Value::Array(vec![int(3), int(1), int(4), int(1), int(5)]));
    let x = put(&s, entity(LOOKUP_SCOPE, vec![("name", text("x"))]));
    let two = literal(&s, int(2));
    let parity = put(&s, entity(ARITHMETIC, vec![("op", text("mod")), ("left", bytes(&x)), ("right", bytes(&two))]));
    let f = lambda(&s, &["x"], parity);
    let Value::Array(groups) = value_of(&run(&s, &builtin(&s, "group-by", vec![("collection", coll), ("fn", f)]))) else { panic!() };
    assert_eq!(groups.len(), 2);
    let first = match &groups[0] {
        Value::Bytes(h) => s.get_by_hash(h).expect("group entity stored"),
        other => panic!("{other:?}"),
    };
    assert_eq!(first.typ, GROUP);
    assert_eq!(first.field("key"), Some(&int(1)), "3 appears first, and 3 mod 2 is 1");
    assert_eq!(first.field("members"), Some(&Value::Array(vec![int(3), int(1), int(1), int(5)])));
}

#[test]
fn the_construct_alias_and_the_inline_form_agree_on_the_materialized_hash() {
    let s = Store::new();
    let a = literal(&s, int(1));
    let b = literal(&s, text("two"));
    let inline = entity(CONSTRUCT, vec![("entity_type", text("app/pair")), ("fields", map(vec![("a", bytes(&a)), ("b", bytes(&b))]))]);
    let ty = literal(&s, text("app/pair"));
    let alias = builtin(&s, "construct", vec![("entity_type", ty), ("a", a), ("b", b)]);
    let one = entity_of(&run(&s, &inline));
    assert_eq!(one.hash, entity_of(&run(&s, &alias)).hash);
    assert_eq!(one, entity("app/pair", vec![("a", int(1)), ("b", text("two"))]), "the bare shape");
}

#[test]
fn the_arithmetic_alias_shares_the_inline_path_and_an_unknown_builtin_is_named() {
    let s = Store::new();
    let op = literal(&s, text("sub"));
    let l = literal(&s, int(5));
    let r = literal(&s, int(8));
    assert_eq!(value_of(&run(&s, &builtin(&s, "arithmetic", vec![("op", op), ("left", l), ("right", r)]))), int(-3));
    let out = run(&s, &builtin(&s, "teleport", vec![]));
    assert_eq!(code_of(&out), CODE_INVALID_EXPRESSION);
    assert!(out.error.unwrap().detail.contains("teleport"));
}

#[test]
fn store_writes_through_the_tree_and_is_refused_when_the_write_predicate_says_no() {
    let s = Store::new();
    let path = literal(&s, text("app/out"));
    let v = literal(&s, int(42));
    let e = builtin(&s, "store", vec![("path", path), ("value", v)]);
    let written = entity_of(&run(&s, &e));
    assert_eq!(written, Entity::make("primitive/any", int(42)));
    assert_eq!(s.get_at(&format!("/{PEER}/app/out")), Some(written));

    let deny = |_: &str| false;
    let out = run_with(&s, &e, DEFAULT_LIMITS, EvaluateOptions { can_write_path: Some(&deny), ..Default::default() });
    assert_eq!(code_of(&out), CODE_PERMISSION_DENIED);
}

// ── option α — construct and navigation ─────────────────────────────────────────────

/// Fields evaluate in ECF canonical map key order — length first, so `z` before `aa`. Both fields
/// fail with `division_by_zero`, and the detail says which operator ran first.
#[test]
fn construct_fields_evaluate_in_ecf_canonical_key_order() {
    let s = Store::new();
    let one = literal(&s, int(1));
    let two = literal(&s, int(2));
    let zero = literal(&s, int(0));
    let aa_div = put(&s, entity(ARITHMETIC, vec![("op", text("div")), ("left", bytes(&one)), ("right", bytes(&zero))]));
    let z_mod = put(&s, entity(ARITHMETIC, vec![("op", text("mod")), ("left", bytes(&two)), ("right", bytes(&zero))]));
    let e = entity(CONSTRUCT, vec![("entity_type", text("app/t")), ("fields", map(vec![("aa", bytes(&aa_div)), ("z", bytes(&z_mod))]))]);
    let out = run(&s, &e);
    assert_eq!(code_of(&out), CODE_DIVISION_BY_ZERO);
    assert!(out.error.unwrap().detail.contains("Modulo"), "`z` (mod) is evaluated before `aa` (div)");
}

#[test]
fn navigation_composes_through_a_construct_inside_one_evaluation_and_a_readback_returns_the_hash() {
    let s = Store::new();
    let n = literal(&s, text("deep"));
    let inner = put(&s, entity(CONSTRUCT, vec![("entity_type", text("app/inner")), ("fields", map(vec![("name", bytes(&n))]))]));
    let outer = put(&s, entity(CONSTRUCT, vec![("entity_type", text("app/outer")), ("fields", map(vec![("inner", bytes(&inner))]))]));
    let f1 = put(&s, entity(FIELD, vec![("name", text("inner")), ("entity", bytes(&outer))]));
    let f2 = entity(FIELD, vec![("name", text("name")), ("entity", bytes(&f1))]);
    assert_eq!(value_of(&run(&s, &f2)), text("deep"));

    // THE NEGATIVE: on the MATERIALIZED outer (read back from the tree), `inner` is a bare hash.
    let materialized = entity_of(&run(&s, &s.get_by_hash(&outer).unwrap()));
    s.bind(&format!("/{PEER}/app/o"), &materialized);
    let look = put(&s, entity(LOOKUP_TREE, vec![("path", text("app/o"))]));
    let readback = entity(FIELD, vec![("name", text("inner")), ("entity", bytes(&look))]);
    assert!(matches!(value_of(&run(&s, &readback)), Value::Bytes(h) if h.len() == 33));
}

#[test]
fn field_navigation_requires_an_entity_or_record() {
    let s = Store::new();
    let five = literal(&s, int(5));
    assert_eq!(code_of(&run(&s, &entity(FIELD, vec![("name", text("x")), ("entity", bytes(&five))]))), CODE_TYPE_MISMATCH);
}

// ── §4.2 resolution tiers ───────────────────────────────────────────────────────────

#[test]
fn resolve_rejects_a_non_compute_entity_and_tiers_0_and_2_and_included_admit_it() {
    let s = Store::new();
    let data = entity("app/secret", vec![("v", int(1))]);
    s.put_entity(&data);
    let e = entity(LOOKUP_HASH, vec![("hash", bytes(&data.hash))]);

    assert_eq!(code_of(&run(&s, &e)), CODE_NOT_FOUND, "compute is not a content-store oracle");

    let tier0 = run_with(&s, &e, DEFAULT_LIMITS, EvaluateOptions { content_store_access: true, ..Default::default() });
    assert_eq!(entity_of(&tier0).hash, data.hash);

    let sealed: HashSet<Vec<u8>> = [data.hash.clone()].into();
    let tier2 = run_with(&s, &e, DEFAULT_LIMITS, EvaluateOptions { authorized_data_hashes: Some(&sealed), ..Default::default() });
    assert_eq!(entity_of(&tier2).hash, data.hash);

    // The included map is consulted before the content store — an entity the store never saw.
    let s2 = Store::new();
    let only_included = entity(LITERAL, vec![("value", int(11))]);
    let included: BTreeMap<Vec<u8>, Entity> = [(only_included.hash.clone(), only_included.clone())].into();
    let lookup = entity(LOOKUP_HASH, vec![("hash", bytes(&only_included.hash))]);
    assert_eq!(code_of(&run(&s2, &lookup)), CODE_NOT_FOUND);
    let out = run_with(&s2, &lookup, DEFAULT_LIMITS, EvaluateOptions { included: Some(&included), ..Default::default() });
    assert_eq!(value_of(&out), int(11));
}

// ── the predicates are called, not assumed ──────────────────────────────────────────

/// A control for the two path predicates: the evaluator must CONSULT the one it was given. A
/// predicate that is accepted and never called would pass every deny test above only by accident of
/// the default.
#[test]
fn the_read_predicate_is_consulted_once_per_tree_read() {
    let s = Store::new();
    s.bind(&format!("/{PEER}/app/a"), &entity("app/v", vec![]));
    let calls = std::sync::atomic::AtomicUsize::new(0);
    let counting = |_: &str| {
        calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        true
    };
    let out = run_with(
        &s,
        &entity(LOOKUP_TREE, vec![("path", text("app/a"))]),
        DEFAULT_LIMITS,
        EvaluateOptions { can_read_path: Some(&counting), ..Default::default() },
    );
    assert!(out.error.is_none());
    assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
}

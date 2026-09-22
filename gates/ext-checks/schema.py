#!/usr/bin/env python3
"""gates/ext-checks/schema.py — the check-definition format, in one place.

**The neutral half of the authored-check axis.** It loads and VALIDATES every
`extension-contracts/<ext>/checks/*.toml`, and it is imported by two consumers that must not
disagree about what a check is:

    the ARM        languages/<target>/gates/ext-checks/run   — executes the steps
    the COMPARER   gates/ext-checks/compare.py               — applies the arm rule

Keeping the vocabulary here rather than in each arm is the rule this tree already runs on
(`DESIGN-THE-SYSTEM-STRUCTURE` §1.2b): the shared protocol lives in one copy, the ecosystem
polish lives per target. `chunking-parity` is the measured precedent — neutral half, 141
lines of arms across three targets; `host-seam` has no neutral half and 1,478.

**Why the arms import a Python module.** They do not, and that is deliberate. Each arm reads
these definitions itself, in its own language, from the same TOML. This module is the
REFERENCE reading of the format plus the validator the gate runs before any arm executes —
an arm that disagrees with it disagrees visibly, at the schema, rather than by silently
skipping a verb it did not implement. `VERBS` and `ASSERTIONS` below are the contract; an
arm declares which it implements and the comparer refuses a verdict from an arm that does
not implement every verb the definitions use.

WHAT A CHECK IS ALLOWED TO BE
-----------------------------
Kind C in `entity-core-keystone`'s `docs/VERIFICATION-ARCHITECTURE.md`: authored from the
SPEC at the same normative target as the oracle, never from the oracle's source, and NEVER a
conformance verdict. The operator's standing condition, ruled 2026-09-07 for keystone and
adopted here unchanged:

    an official green requires the suite we do not author.

So these run on their own axis, write only under `output/ext-checks/`, and nothing here may
produce or contribute to a number reported as conformance. Divergence from the oracle is a
finding to be ROUTED, never carried privately — a silently divergent test set manufactures a
second de-facto standard, which is the one thing this position must not do.

THE ARM RULE, WHICH IS THIS FORMAT'S REASON FOR EXISTING
--------------------------------------------------------
Every authored check declares a verdict for BOTH arms and the two MUST differ. A check that
reports the same thing against a peer with the extension not installed is measuring something
other than the extension.

That is not a hypothetical worry: four of the thirteen checks in the oracle's own `content`
category PASS in the bare arm — measuring core-go's in-process library rather than the peer —
while the report's `summary.self_checks` reads `0` (AP-19). The rule makes that shape
**unauthorable here** rather than merely discouraged, and it is enforced by the comparer
rather than by review.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# ── the vocabulary ──────────────────────────────────────────────────────────────────────
#
# Seven verbs and seven assertion kinds, and the smallness is a design constraint rather
# than a stage of growth. A check language rich enough to need control flow is a second
# implementation of the thing under test, and it acquires its own defect rate: this repo has
# written twelve instruments and found a defect in every one by RUNNING it. The way to keep
# that number bounded is to keep the executable surface small enough to read.
#
# A step or assertion kind that is not here is a FAILURE, never a skip. A silently ignored
# assertion is a check that reports PASS having measured less than it claims.

VERBS = {
    "connect": "dial the addr and complete the §4.1 handshake",
    "execute": "one authenticated EXECUTE; `capture` names the response for assertions",
}

ASSERTIONS = {
    "status":                 "the response envelope's status equals `equals`",
    "result_field_present":   "the result entity has `field`",
    "result_field_absent":    "the result entity does NOT have `field` — the half a presence check cannot make",
    "result_array_contains":  "the result's `field` array contains `value`",
    "result_array_empty":     "the result's `field` array is empty (or absent)",
    "result_array_nonempty":  "the result's `field` array has at least one entry — the positive half, without which an emptiness assertion passes on a peer that records nothing at all",
    "included_has":           "the response envelope's `included` map holds an entity whose hash is `value`",
    "error_code":             "the result's `code` equals `equals` — for a check whose subject is a refusal",
}

# A `$capture.result.field` reference, resolved by the arm against an earlier response. The
# only indirection in the format: without it a check cannot use a hash the peer chose, and
# every scenario collapses to one request.
REF_PREFIX = "$"

# Reserved param wrappers the arm materialises into the peer's own types. They exist because
# an `entity` and an `envelope` are protocol structures, not TOML tables, and spelling them
# out per arm is how a per-target file starts holding protocol.
PARAM_WRAPPERS = ("$entity", "$envelope")

REQUIRED_CHECK_FIELDS = ("id", "requirement", "spec", "snapshot", "level", "kind", "face")

# D13's face amendment, arriving on this axis. `<peer> is a host` is not a proposition;
# `<peer> hosts <face>` is. A check drives ONE of an extension's four faces, and a target
# that cannot host that face is not a target the check FAILS on — it is a target the check
# does not range over. On `entity-core-protocol-rust` the handler body is not installable at
# any visibility, so the three checks authored so far would each read `composed=fail
# bare=fail` there, which `decide()` calls `failed`. That is a category error of exactly the
# kind the amendment was earned on, one axis over.
#
# The four names are `docs/DESIGN-THE-SDK-LAYER.md` §1's and are the same vocabulary
# `tools/compose.py` enforces for `[system.faces]`, so the check's `face` and the
# composition's declaration meet in one word set rather than two (the `usable` /
# `library-only` drift recorded in the compositions is what two word sets look like).
FACES = ("types", "emit_consumer", "sdk", "handler")

# A floor on the corpus, not a style rule. The fragile part of this gate is a glob; its
# failure mode is a clean run over nothing, which reads as "every authored check passed".
MIN_CHECKS = 3


class SchemaError(Exception):
    pass


def load_checks(root: Path | None = None) -> list[dict]:
    """Every check definition in the tree, validated. Raises rather than skipping."""
    root = root or ROOT
    out: list[dict] = []
    for path in sorted(root.glob("extension-contracts/*/checks/*.toml")):
        doc = tomllib.loads(path.read_text())
        chk = doc.get("check")
        if not isinstance(chk, dict):
            raise SchemaError(f"{path}: no [check] table")
        chk["_path"] = str(path.relative_to(root))
        chk["_extension"] = path.parent.parent.name
        validate(chk)
        out.append(chk)
    return out


def validate(chk: dict) -> None:
    where = chk.get("_path", chk.get("id", "?"))
    for f in REQUIRED_CHECK_FIELDS:
        if not chk.get(f):
            raise SchemaError(f"{where}: [check].{f} is required")
    if chk["face"] not in FACES:
        raise SchemaError(
            f"{where}: [check].face={chk['face']!r} is not one of {', '.join(FACES)}. "
            f"A check names the FACE it drives or it names nothing (D13, amended): a target "
            f"that cannot host that face is not a target the check fails on."
        )
    if chk["kind"] != "independent":
        raise SchemaError(
            f"{where}: kind={chk['kind']!r}. Only `independent` (keystone Kind C) is "
            f"authorable here; a probe belongs under a gate that may not gate, and a "
            f"transcription belongs beside the rule it pins."
        )
    if not chk.get("reading"):
        raise SchemaError(
            f"{where}: [check].reading is required. A check authored from the spec states "
            f"the reading it pins, so a reviewer checks the CHECK against the SPEC rather "
            f"than against what the implementation happens to do."
        )

    steps = chk.get("step") or []
    if not steps:
        raise SchemaError(f"{where}: no [[check.step]] — a check that drives nothing measures nothing")
    for i, s in enumerate(steps):
        if s.get("op") not in VERBS:
            raise SchemaError(
                f"{where}: step {i} op={s.get('op')!r} is not in the vocabulary "
                f"({', '.join(sorted(VERBS))}). An unknown verb is a failure, never a skip."
            )
    if steps[0].get("op") != "connect":
        raise SchemaError(f"{where}: the first step must be `connect`")

    asserts = chk.get("assert") or []
    if not asserts:
        raise SchemaError(f"{where}: no [[check.assert]] — see above")
    for i, a in enumerate(asserts):
        if a.get("kind") not in ASSERTIONS:
            raise SchemaError(
                f"{where}: assert {i} kind={a.get('kind')!r} is not in the vocabulary "
                f"({', '.join(sorted(ASSERTIONS))})"
            )
        if not a.get("capture"):
            raise SchemaError(f"{where}: assert {i} names no `capture`")

    captures = {s["capture"] for s in steps if s.get("capture")}
    for i, a in enumerate(asserts):
        if a["capture"] not in captures:
            raise SchemaError(
                f"{where}: assert {i} reads capture {a['capture']!r}, which no step produces. "
                f"That is D18's rule with a capture name as the referent: a citation resolves "
                f"or it is not a citation."
            )

    arms = chk.get("arms") or {}
    if arms.get("composed") != "pass" or arms.get("bare") != "fail":
        raise SchemaError(
            f"{where}: [check.arms] must declare composed=\"pass\" and bare=\"fail\". "
            f"THE ARM RULE: an authored check is not admitted until it has been seen "
            f"producing a different answer against a peer with the extension absent. Four "
            f"of the oracle's thirteen `content` checks pass in the bare arm (AP-19); this "
            f"format exists so that shape cannot be written here."
        )
    if not arms.get("bare_why"):
        raise SchemaError(f"{where}: [check.arms].bare_why must say WHY the bare arm fails")


def verbs_used(checks: list[dict]) -> set[str]:
    return {s["op"] for c in checks for s in c.get("step", [])}


def assertions_used(checks: list[dict]) -> set[str]:
    return {a["kind"] for c in checks for a in c.get("assert", [])}


if __name__ == "__main__":
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--emit", metavar="PATH",
                    help="write the validated definitions as JSON for the arms to consume")
    opts = ap.parse_args()

    try:
        checks = load_checks()
    except SchemaError as e:
        print(f"REFUSING: {e}", file=sys.stderr)
        sys.exit(3)
    if len(checks) < MIN_CHECKS:
        print(f"REFUSING: {len(checks)} check definitions, below MIN_CHECKS={MIN_CHECKS}. "
              f"A glob that has stopped matching reports a clean run over nothing.",
              file=sys.stderr)
        sys.exit(3)

    # TOML TO AUTHOR, JSON TO CONSUME — and the second arm is what forced it.
    #
    # The `python` arm globbed the TOML directly, which worked and was wrong: `node` has no
    # TOML parser in its standard library and none of these images may fetch one
    # (`--network=none`). An arm-side parser per language would put the DEFINITION FORMAT in
    # the per-target half — the exact inversion this axis exists to avoid, and one that gets
    # worse per target rather than better.
    #
    # So the neutral half validates once and emits JSON, which every target reads. The arms
    # now consume ONE artifact rather than each re-deriving the corpus, which also closes a
    # gap nobody had noticed: two arms globbing independently could disagree about which
    # checks exist, and `compare.py` would have refused on the set mismatch with no way to
    # say why.
    if opts.emit:
        Path(opts.emit).parent.mkdir(parents=True, exist_ok=True)
        Path(opts.emit).write_text(json.dumps({"checks": checks}, indent=1))
        print(f"ext-checks: emitted {len(checks)} validated definitions -> {opts.emit}")

    print(f"ext-checks: {len(checks)} definitions, all valid")
    for c in checks:
        print(f"  {c['id']:42s} {c['level']:6s} {c['requirement']:6s} {c['spec']}")
    print(f"  verbs used      : {', '.join(sorted(verbs_used(checks)))}")
    print(f"  assertions used : {', '.join(sorted(assertions_used(checks)))}")

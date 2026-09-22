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

import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


# ── the corpus travels as canonical ECF, and the codec is a peer's ──────────────────────
#
# NOT JSON. The ecosystem's data language is CBOR in Entity Canonical Form, and a build that
# emitted JSON so a third arm could read a corpus would be introducing a second data model
# with no canonical form, no byte strings and no map-ordering rule — the three things
# `content_hash` is computed from. `docs/DESIGN-THE-CBOR-INTERCHANGE-LAYER.md` is the whole
# argument; this is the first consumer.
#
# NOT A HAND-ROLLED ENCODER EITHER. Every peer ships a conformant one, byte-verified against
# the locked ECF corpus in a cross-impl round. Using one as a library is what a library is
# for. WHICH one is a value, declared in `tools/tooling.toml` rather than written here: a
# neutral file that names an implementation is one edit from being a dispatch over all of
# them, and `tools/check-glue.py` fails it on sight.
def ecf_decoder():
    """The declared decoder alone, for consumers that only read (the comparer)."""
    return _ecf_codec()[1]


def _ecf_codec():
    decl = tomllib.loads((ROOT / "tools" / "tooling.toml").read_text())["ecf_codec"]
    src = (ROOT / decl["peer"]).resolve()
    if not src.is_dir():
        raise SchemaError(
            f"REFUSING: no ECF codec at {src} (tools/tooling.toml [ecf_codec].peer). "
            f"The corpus is canonical ECF and this repo does not hand-roll a codec."
        )
    sys.path.insert(0, str(src))
    mod = __import__(decl["package"])
    return mod.encode, mod.decode

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

# ── the SECOND indirection, and it is a different kind from the first ────────────────────
#
# `$capture.result.field` names a value the PEER RETURNED. `{local_peer_id}` names a value
# the peer IS, and no response has to carry it: every arm already learns it in the §4.1
# handshake, because it is what the peer identifies itself as.
#
# It exists because HISTORY §3.1 puts the head pointer at `system/history/head/{path}` where
# `{path}` is the FULL peer-namespaced path — so the address of the recorder's own output
# embeds the peer's id twice over, and a check that cannot spell the peer's id cannot read
# what the recorder wrote. The alternative was to observe recording through
# `system/history:query`, which is the HANDLER face — and the whole reason to author a check
# for §6.2 is that it is the first one whose subject is the RECORDER, on a face
# `entity-core-protocol-rust` actually hosts.
#
# The spelling is the spec's own (§3.1: `system/history/head/{local_peer_id}/docs/report`),
# so a resource line in a check is character-for-character the path the spec names.
#
# AN UNKNOWN `{...}` TOKEN IS A REFUSAL, never a literal. A path substituted with nothing
# resolves to a real, wrong, absent path, and the assertion then fails — or worse, PASSES,
# when the assertion is that nothing is there. That is the failure mode of the whole check
# below: two of its three head reads assert a 404, and a mis-substituted path 404s for free.
PLACEHOLDERS = ("{local_peer_id}",)

REQUIRED_CHECK_FIELDS = ("id", "requirement", "spec", "snapshot", "level", "kind", "face")

# ── every type a check names is DECLARED with the authority that defines it ──────────────
#
# D16's remedy, third time in this tree, on an axis nobody had looked at: the type names a
# check puts on the wire. Found 2026-09-08 while authoring the §6.2 checks —
# `local-namespace-excluded` had been sending `system/tree/put-params` since it was written,
# and the core registry defines `system/tree/put-request`. It also carried a `path` field
# `put-request` does not have.
#
# NOTHING COULD HAVE SAID SO, and that is the finding rather than the typo. No peer validates
# a params entity's `type` against the §9.5 registry — `data` is never checked against the
# type it names (§6.3 structural admission) — so a check with an invented request type
# behaves identically to one with the right name, passes both arms, and reads as evidence.
# The check that was wrong is the one measuring a MUST nothing upstream measures.
#
# The remedy is `[error_surface]`'s, which is the one this repo has already paid for: an
# undeclared name is a FAILURE, and the declaration must name an AUTHORITY. It does not prove
# the name is right. It forces someone to go and look for the document that defines it, which
# is exactly the step that was skipped — the same mechanism that surfaced `path_required`,
# MUST-ed twice and defined in no code set.
CHECK_TYPE_AUTHORITIES = ("core", "spec", "ours", "unresolved")

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


def _type_names(value) -> set[str]:
    """Every entity type a step puts on the wire — params types and `$entity`/`$envelope` roots."""
    out: set[str] = set()
    if isinstance(value, dict):
        t = value.get("type")
        if isinstance(t, str) and t:
            out.add(t)
        for v in value.values():
            out |= _type_names(v)
    elif isinstance(value, list):
        for v in value:
            out |= _type_names(v)
    return out


def _tokens(value) -> set[str]:
    """Every `{...}` substitution appearing in a step's addressable parts, at any depth."""
    if isinstance(value, str):
        return set(re.findall(r"\{[^{}]*\}", value))
    if isinstance(value, dict):
        out: set[str] = set()
        for k, v in value.items():
            out |= _tokens(k) | _tokens(v)
        return out
    if isinstance(value, list):
        out = set()
        for v in value:
            out |= _tokens(v)
        return out
    return set()


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
        for tok in _tokens(s.get("resource")) | _tokens(s.get("params")):
            if tok not in PLACEHOLDERS:
                raise SchemaError(
                    f"{where}: step {i} uses the substitution {tok} , which no arm resolves "
                    f"(known: {', '.join(PLACEHOLDERS)}). An unresolved token is substituted "
                    f"with nothing and the request goes to a real, wrong path — which a "
                    f"404-asserting check reports as a PASS."
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

    # ── the types, declared with an authority (see CHECK_TYPE_AUTHORITIES) ───────────────
    used = set()
    for s in steps:
        used |= _type_names(s.get("params"))
    declared = chk.get("types") or {}
    if not isinstance(declared, dict):
        raise SchemaError(f"{where}: [check.types] must be a table of type -> authority")
    for name in sorted(used - set(declared)):
        raise SchemaError(
            f"{where}: the step wire type {name!r} is declared nowhere in [check.types]. "
            f"No peer validates a params entity's type against the §9.5 registry, so an "
            f"invented request type passes both arms and reads as evidence — which is how "
            f"`system/tree/put-params` survived in this corpus. Name the authority."
        )
    for name in sorted(set(declared) - used):
        raise SchemaError(
            f"{where}: [check.types] declares {name!r}, which no step sends. A declaration "
            f"that outlived its call site is the citation-rot D18 is about, one file over."
        )
    for name, auth in sorted(declared.items()):
        head = str(auth).split(None, 1)[0].rstrip(":")
        if head not in CHECK_TYPE_AUTHORITIES:
            raise SchemaError(
                f"{where}: [check.types].{name!r} begins {head!r}; it must begin with one of "
                f"{', '.join(CHECK_TYPE_AUTHORITIES)} and then cite the document."
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


def self_test() -> int:
    """D15's executed control for the ONE rule in this file that can go red on real input.

    The vocabulary rules (verb, assertion kind, face) have been red in anger — every one of
    them was written after an arm or an author got it wrong. The placeholder rule has not,
    so it ships with the planted defect instead: a token no arm resolves, which is the
    failure that would otherwise present as a PASSING check, because an unsubstituted path
    is a real path with nothing at it and two of the head reads below assert exactly that.
    """
    base = {
        "_path": "<self-test>", "id": "x/y", "requirement": "R", "spec": "S", "snapshot": "s",
        "level": "MUST", "kind": "independent", "face": "handler", "reading": "r",
        "step": [{"op": "connect"},
                 {"op": "execute", "uri": "system/tree", "operation": "get", "capture": "c",
                  "resource": ["system/history/head/{local_peer_id}/p"],
                  "params": {"type": "t", "data": {}}}],
        "assert": [{"kind": "status", "capture": "c", "equals": 200}],
        "arms": {"composed": "pass", "bare": "fail", "bare_why": "w"},
        "types": {"t": "core — a citation"},
    }
    try:
        validate(base)
    except SchemaError as e:
        print(f"SELF-TEST FAILED: the clean definition was rejected: {e}", file=sys.stderr)
        return 1

    # Each planted defect is one an author actually made, or one whose failure mode is a
    # PASSING check. A control that plants something nobody would write proves nothing.
    planted = [
        ("an unresolvable substitution `{peer}`",
         lambda c: c["step"][1].__setitem__("resource", ["system/history/head/{peer}/p"])),
        ("an undeclared wire type",
         lambda c: c["step"][1]["params"].__setitem__("type", "system/tree/put-params")),
        ("a [check.types] entry no step sends",
         lambda c: c["types"].__setitem__("system/tree/put-params", "core — nothing")),
        ("an authority outside the vocabulary",
         lambda c: c["types"].__setitem__("t", "probably core")),
    ]
    for label, mutate in planted:
        c = json.loads(json.dumps(base))
        mutate(c)
        try:
            validate(c)
        except SchemaError:
            continue
        print(f"SELF-TEST FAILED: {label} validated clean. Its failure mode is a check that "
              f"PASSES having measured something other than what it names.", file=sys.stderr)
        return 1

    print(f"ext-checks schema self-test: OK — clean definition accepted, "
          f"{len(planted)} planted defects refused")
    return 0


def verbs_used(checks: list[dict]) -> set[str]:
    return {s["op"] for c in checks for s in c.get("step", [])}


def assertions_used(checks: list[dict]) -> set[str]:
    return {a["kind"] for c in checks for a in c.get("assert", [])}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--emit", metavar="PATH",
                    help="write the validated definitions as JSON for the arms to consume")
    ap.add_argument("--self-test", action="store_true",
                    help="plant an unresolvable substitution and require it to be refused")
    opts = ap.parse_args()

    if opts.self_test:
        sys.exit(self_test())

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

    # TOML TO AUTHOR, CANONICAL ECF TO CONSUME.
    #
    # The `python` arm globbed the TOML directly, which worked and was wrong: an arm-side
    # parser per language puts the DEFINITION FORMAT in the per-target half — the inversion
    # this axis exists to avoid, and one that gets worse per target rather than better. So
    # the neutral half validates once and emits, and every arm reads one artifact.
    #
    # THAT ARTIFACT WAS JSON FOR ONE DAY AND SHOULD NEVER HAVE BEEN. It was chosen because
    # `node` has no TOML parser, which is true and beside the point: this ecosystem's data
    # language is CBOR in Entity Canonical Form, every arm links a conformant ECF codec BY
    # CONSTRUCTION — an arm is a wire client — and JSON is a second data model with no
    # canonical form, no byte strings and no map-ordering rule. The corpus now travels in
    # the form everything else here travels in, and a new target's arm needs a client and
    # nothing else. `docs/DESIGN-THE-CBOR-INTERCHANGE-LAYER.md`.
    if opts.emit:
        encode, decode = _ecf_codec()
        payload = {"checks": checks}
        blob = encode(payload)

        # D15's refusal, and it is not ceremony: this is the first artifact in this tree
        # whose PRODUCER and one CONSUMER are the same codec (`python` is both our tooling
        # and a peer under test). A round trip here catches the encoder losing something
        # before two arms are asked to agree about it — and the arms that do NOT share this
        # codec are the control that catches what a round trip cannot.
        if decode(blob) != payload:
            print("REFUSING: the corpus does not survive its own encode/decode round trip. "
                  "An arm would execute a corpus that is not the one that was validated.",
                  file=sys.stderr)
            sys.exit(3)

        Path(opts.emit).parent.mkdir(parents=True, exist_ok=True)
        Path(opts.emit).write_bytes(blob)
        # D14: the number cites the artifact. Canonical encoding makes these bytes a
        # function of the corpus alone, so this digest identifies exactly what ran.
        print(f"ext-checks: emitted {len(checks)} validated definitions -> {opts.emit}\n"
              f"  {len(blob)} bytes canonical ECF, sha256 {hashlib.sha256(blob).hexdigest()}")

    print(f"ext-checks: {len(checks)} definitions, all valid")
    for c in checks:
        print(f"  {c['id']:42s} {c['level']:6s} {c['requirement']:6s} {c['spec']}")
    print(f"  verbs used      : {', '.join(sorted(verbs_used(checks)))}")
    print(f"  assertions used : {', '.join(sorted(assertions_used(checks)))}")

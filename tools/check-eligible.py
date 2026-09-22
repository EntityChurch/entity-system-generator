#!/usr/bin/env python3
"""check-eligible.py — `make eligible`: is this composition's peer certified for what it needs?

**The consumer half of the keystone peer contract** (W-17). Keystone certifies each peer and
publishes `protocol-generator/<peer>/status/KEYSTONE-PEER-REPORT.json`; we never re-measure what
that report certifies. This gate reads it and refuses a composition whose declared needs meet a
row that is not `pass`.

  ./tools/check-eligible.py languages/rust/compositions/compute
  ./tools/check-eligible.py languages/rust/compositions/compute --report /tmp/planted.json
  ./tools/check-eligible.py --self-test

## The needs are DECLARED, the vocabulary is READ

What an extension needs is `extension-contracts/<ext>/EXTENSION.toml [requires]`; what the launch
path needs is `gates/eligible/LAUNCH.toml`. The requirement NAMES are keystone's and are read out
of keystone's tree every run — `requirements.toml` for REQUIRED/MODULE, `CONTRACT-DRAFT.md` §5 for
pending — because a copy of that vocabulary here is exactly the kind of fact AGENTS.md says we
never keep. A declared name keystone does not define FAILS; a pending name keystone has since
promoted to a requirement FAILS, so the declaration cannot silently lag the contract.

## What makes a report about THIS build (the part a verdict alone does not say)

A `certified` verdict is a statement about some commit of some contract text. Two checks join it to
what we are about to compile:

- `contract_digest` is recomputed from keystone's three contract files (their `report.py`'s rule:
  sha256 over `requirements.toml`, `CONTRACT-DRAFT.md`, `FIXTURE-HOST.md`, in that order).
- the peer source is unchanged since `delivery.commit`: `git diff` from that commit to the working
  tree over the peer directory, excluding `status/` (where the report itself is committed).

`delivery.commit` being reachable from a remote-tracking ref is printed as a census line and failed
only under `--release`: keystone's reply says the consume step runs on path dependencies and the
pushed-tag rule belongs to the release boundary.

## D15

Every rule has a planted defect in `--self-test` that must turn it red, plus a clean arm that must
stay green and a control that a row we do NOT require is not read. Refusals: no extensions, an
empty vocabulary, an empty pending list, a report with no rows, a report whose `certified` verdict
contradicts its own REQUIRED rows.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import compose  # noqa: E402  — one resolver for the plan, never a second copy

LAUNCH = ROOT / "gates" / "eligible" / "LAUNCH.toml"
CONTRACT_NAME = "keystone-peer-contract"
#: keystone's `tools/peer-contract/report.py` `CONTRACT_FILES`, in its order. Cited, not owned:
#: if keystone changes the rule, R2 goes red on every report at once, which is the loud direction.
CONTRACT_FILES = ("requirements.toml", "CONTRACT-DRAFT.md", "FIXTURE-HOST.md")
REPORT_NAME = "status/KEYSTONE-PEER-REPORT.json"


class Refusing(Exception):
    """The gate cannot answer. Never reported as a verdict."""


# ── inputs ─────────────────────────────────────────────────────────────────────────────────────

def load_vocabulary(contract_dir: Path) -> tuple[dict[str, str], set[str], str]:
    """({name: level}, {pending names}, contract_digest) from keystone's contract directory."""
    reg = tomllib.loads((contract_dir / "requirements.toml").read_text(encoding="utf-8"))
    if reg.get("contract") != CONTRACT_NAME:
        raise Refusing(f"{contract_dir}/requirements.toml names contract {reg.get('contract')!r}, "
                       f"not {CONTRACT_NAME!r}")
    levels = {r["name"]: r["level"] for r in reg.get("requirement", [])}
    if not levels:
        raise Refusing(f"{contract_dir}/requirements.toml parsed to ZERO requirements")
    pending = parse_pending((contract_dir / "CONTRACT-DRAFT.md").read_text(encoding="utf-8"))
    h = hashlib.sha256()
    for f in CONTRACT_FILES:
        h.update((contract_dir / f).read_bytes())
    return levels, pending, h.hexdigest()


def parse_pending(draft: str) -> set[str]:
    """The first backticked cell of every table row in the `## 5.` section."""
    m = re.search(r"^## 5\..*?$(.*?)(?=^## )", draft, re.M | re.S)
    if not m:
        raise Refusing("CONTRACT-DRAFT.md has no `## 5.` section — the pending list moved")
    names = set(re.findall(r"^\|\s*`([a-z_]+\.[a-z_*]+)`\s*\|", m.group(1), re.M))
    if not names:
        raise Refusing("CONTRACT-DRAFT.md §5 parsed to ZERO pending names — the table shape moved")
    return names


def load_requires(path: Path, owner: str) -> dict:
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    req = doc.get("requires")
    return {"owner": owner, "path": str(path.relative_to(ROOT)), "block": req}


def freshness(peer_dir: Path, delivery: dict) -> dict:
    """Is the peer source we build the source that was certified? Reads keystone's git, writes nothing."""
    out = {"commit": delivery.get("commit"), "tree_dirty": delivery.get("tree_dirty"),
           "moved": None, "dirty_now": None, "remote": None, "error": None}
    commit = delivery.get("commit")
    if not commit:
        out["error"] = "report carries no delivery.commit"
        return out
    git = ["git", "-C", str(peer_dir)]
    spec = [".", ":(exclude)status"]
    try:
        top = subprocess.run(git + ["rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        del top
        d = subprocess.run(git + ["diff", "--name-only", commit, "--"] + spec,
                           capture_output=True, text=True)
        if d.returncode != 0:
            out["error"] = f"git diff {commit[:12]}: {d.stderr.strip()}"
            return out
        out["moved"] = [l for l in d.stdout.splitlines() if l]
        s = subprocess.run(git + ["status", "--porcelain", "--"] + spec, capture_output=True, text=True, check=True)
        out["dirty_now"] = [l for l in s.stdout.splitlines() if l]
        r = subprocess.run(git + ["branch", "-r", "--contains", commit], capture_output=True, text=True)
        out["remote"] = [l.strip() for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []
    except (OSError, subprocess.CalledProcessError) as e:
        out["error"] = f"git: {e}"
    return out


# ── the gate function ──────────────────────────────────────────────────────────────────────────

def drift_applies(peer_drift: dict | None, certified_commit: str) -> bool:
    """Does a `[peer_drift]` declaration cover THIS certified commit?

    **The declaration names the commit it is ABOUT, so it expires on the condition rather than
    on a date** — the shape `[peer_contract]` used, which is the only exemption in this tree that
    has ever removed itself. When keystone re-certifies, `delivery.commit` changes, this returns
    False, and F1 fires again with nobody having to remember.

    REFUSES an incomplete declaration. `routed` is not paperwork: a declaration with no
    destination is a suppression (D21), and the one thing separating "we decided to absorb this"
    from "somebody silenced a gate" is a document that says which.
    """
    if peer_drift is None:
        return False
    for field in ("certified", "since", "routed", "reason"):
        if not peer_drift.get(field):
            raise Refusing(f"[peer_drift] is missing {field!r} — a declaration with no "
                           f"{'destination' if field == 'routed' else field} is a suppression")
    declared = str(peer_drift["certified"])
    # Prefix match in ONE direction: the declaration may abbreviate the commit, the report may not
    # abbreviate the declaration. `startswith` the other way round would let a 2-character
    # declaration cover every future commit that happens to share a prefix.
    return bool(declared) and str(certified_commit).startswith(declared)


def evaluate(*, report: dict | None, levels: dict[str, str], pending_vocab: set[str], digest: str,
             declarations: list[dict], fresh: dict | None, pre_contract: dict | None,
             peer_drift: dict | None = None,
             strict: bool = False, strict_pending: bool = False, release: bool = False,
             strict_drift: bool = False) -> list[tuple[str, str, str]]:
    """Return (severity, rule, message). Severities: FAIL, PENDING, PRE, INFO, OK."""
    out: list[tuple[str, str, str]] = []
    wanted: dict[str, list[str]] = {}          # name -> owners, for REQUIRED/MODULE rows
    for d in declarations:
        blk, who = d["block"], d["owner"]
        if blk is None:
            out.append(("FAIL", "V1", f"{who}: no [requires] in {d['path']} — an undeclared need is not no need"))
            continue
        if blk.get("contract") != CONTRACT_NAME:
            out.append(("FAIL", "V1", f"{who}: [requires].contract = {blk.get('contract')!r}, expected {CONTRACT_NAME!r}"))
        names: list[str] = []
        for key, level in (("required", "REQUIRED"), ("modules", "MODULE")):
            for n in blk.get(key, []):
                names.append(n)
                if n not in levels:
                    hint = " (keystone lists it as PENDING — move it to `pending`)" if n in pending_vocab else ""
                    out.append(("FAIL", "V2", f"{who}: `{n}` in `{key}` is not a contract requirement{hint}"))
                elif levels[n] != level:
                    out.append(("FAIL", "V2", f"{who}: `{n}` is {levels[n]} in the contract, declared under `{key}`"))
                else:
                    wanted.setdefault(n, []).append(who)
        for n in blk.get("pending", []):
            names.append(n)
            if n in levels:
                out.append(("FAIL", "V3", f"{who}: `{n}` is declared pending but keystone now measures it as "
                                          f"{levels[n]} — move it, so the report row is read"))
            elif n not in pending_vocab:
                out.append(("FAIL", "V2", f"{who}: pending `{n}` is not in CONTRACT-DRAFT §5"))
            else:
                out.append(("FAIL" if strict_pending else "PENDING", "P1",
                            f"{who}: builds on `{n}`, which no report certifies"))
        why = set(blk.get("why", {}))
        if why != set(names):
            out.append(("FAIL", "V4", f"{who}: [requires.why] keys differ from the declared names: "
                                      f"missing {sorted(set(names) - why)}, extra {sorted(why - set(names))}"))
    if not wanted and not any(s == "FAIL" for s, _, _ in out):
        raise Refusing("the composition declares ZERO contract requirements — nothing to check")

    if report is None:
        if pre_contract is not None:
            out.append(("FAIL" if strict else "PRE", "R0",
                        f"peer is declared pre-contract since {pre_contract.get('since')} ({pre_contract.get('ask')}); "
                        f"{len(wanted)} requirement(s) unchecked"))
        else:
            out.append(("FAIL", "R1", "no KEYSTONE-PEER-REPORT.json for this peer — every requirement is `unknown`"))
        return out
    if pre_contract is not None:
        out.append(("FAIL", "R0", "the profile declares this peer pre-contract, but keystone has published a "
                                  "report for it — delete [peer_contract] from the profile"))

    rows = {r.get("name"): r for r in report.get("requirements", [])}
    if not rows:
        raise Refusing("the report has ZERO requirement rows")
    if report.get("verdict") == "certified":
        bad = [n for n, r in rows.items() if r.get("level") == "REQUIRED" and r.get("verdict") != "pass"]
        if bad:
            raise Refusing(f"the report says certified and its own REQUIRED rows {bad} are not pass")

    if report.get("contract") != CONTRACT_NAME:
        out.append(("FAIL", "R2", f"report.contract = {report.get('contract')!r}"))
    if report.get("contract_digest") != digest:
        out.append(("FAIL", "R2", f"report cites contract {str(report.get('contract_digest'))[:16]}…, keystone's "
                                  f"contract files hash to {digest[:16]}… — the report certifies a different text"))
    if report.get("verdict") != "certified":
        out.append(("FAIL", "R3", f"report verdict is {report.get('verdict')!r}"))

    for n, owners in sorted(wanted.items()):
        row = rows.get(n)
        v = row.get("verdict") if row else None
        who = ", ".join(owners)
        if row is None:
            out.append(("FAIL", "R4", f"`{n}` ({who}): no row in the report — unknown, not pass"))
        elif v != "pass":
            out.append(("FAIL", "R4", f"`{n}` ({who}): report row verdict {v!r}"))
        else:
            out.append(("OK", "R4", f"`{n}` pass — {row.get('binding', '(no binding)')}"))

    if fresh is None or fresh.get("error"):
        out.append(("FAIL", "F1", f"cannot tie the report to the peer source: {(fresh or {}).get('error', 'not checked')}"))
    else:
        c = str(fresh["commit"])[:12]
        if fresh.get("tree_dirty") is not False:
            out.append(("FAIL", "F1", f"the report was measured on a dirty tree (tree_dirty={fresh.get('tree_dirty')!r})"))
        if fresh["moved"]:
            # A DECLARED drift is reported and not failed. It covers ONLY `moved` — a report
            # measured on a dirty tree and a peer dirty right now are different failures and are
            # never in scope, because those say the measurement was untrustworthy where this says
            # the measurement was trustworthy and is now old.
            covered = drift_applies(peer_drift, fresh["commit"]) and not strict_drift
            out.append(("DRIFT" if covered else "FAIL", "F1",
                        f"the peer source moved since the certified commit {c}: "
                        f"{len(fresh['moved'])} file(s), e.g. {fresh['moved'][:3]}"
                        + (f" — DECLARED {peer_drift.get('since')}, {peer_drift.get('routed')}"
                           if covered else "")))
        if fresh["dirty_now"]:
            out.append(("FAIL", "F1", f"the peer's working tree has uncommitted changes: {fresh['dirty_now'][:3]}"))
        if not fresh["moved"] and not fresh["dirty_now"]:
            out.append(("OK", "F1", f"peer source is the certified commit {c} (status/ excluded)"))
        if fresh["remote"]:
            out.append(("INFO", "F2", f"{c} is on {', '.join(fresh['remote'])}"))
        else:
            out.append(("FAIL" if release else "INFO", "F2",
                        f"{c} is on no remote-tracking ref — fine for a path-dependency consume, not for a release"))
    return out


# ── CLI ────────────────────────────────────────────────────────────────────────────────────────

def run_composition(comp: Path, args) -> int:
    try:
        plan = compose.build_plan(comp.resolve())
    except compose.Refusal as e:
        print(f"eligible: REFUSING — the composition does not resolve: {e}", file=sys.stderr)
        return 2
    target, name = plan["target"], plan["composition"]
    peer_dir = (ROOT / plan["peer"]["path"]).resolve()
    contract_dir = peer_dir.parent / "shared" / "peer-contract"
    report_path = Path(args.report) if args.report else peer_dir / REPORT_NAME
    profile = tomllib.loads((ROOT / "languages" / target / "profile.toml").read_text(encoding="utf-8"))
    pre = profile.get("peer_contract")
    drift = profile.get("peer_drift")

    try:
        if not plan["installs"]:
            raise Refusing("the plan installs ZERO extensions")
        levels, pending, digest = load_vocabulary(contract_dir)
        decls = [load_requires(compose.contract_dir(i["extension"]) / "EXTENSION.toml", i["extension"])
                 for i in plan["installs"]]
        decls.append(load_requires(LAUNCH, "launch"))
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
        fresh = freshness(peer_dir, report.get("delivery", {})) if report else None
        rows = evaluate(report=report, levels=levels, pending_vocab=pending, digest=digest,
                        declarations=decls, fresh=fresh, pre_contract=pre, peer_drift=drift,
                        strict=args.strict, strict_pending=args.strict_pending,
                        release=args.release, strict_drift=args.strict_drift)
    except (Refusing, OSError, tomllib.TOMLDecodeError, json.JSONDecodeError) as e:
        print(f"eligible: {target}/{name} — REFUSING: {e}", file=sys.stderr)
        return 2

    print(f"eligible: {target}/{name}  peer={plan['peer']['path']}")
    print(f"  vocabulary: {len(levels)} requirements, {len(pending)} pending, contract {digest[:16]}…")
    print(f"  report:     {report_path if report else '(none)'}")
    for sev, rule, msg in rows:
        if sev != "OK" or args.verbose:
            print(f"  {sev:<8}{rule:<4}{msg}")
    fails = [r for r in rows if r[0] == "FAIL"]
    oks = [r for r in rows if r[0] == "OK" and r[1] == "R4"]
    pend = [r for r in rows if r[0] == "PENDING"]
    pre_rows = [r for r in rows if r[0] == "PRE"]
    if fails:
        print(f"eligible: {target}/{name} — NOT ELIGIBLE ({len(fails)} failure(s))")
        return 1
    if pre_rows:
        print(f"eligible: {target}/{name} — PRE-CONTRACT (declared; --strict fails it)")
        return 0
    print(f"eligible: {target}/{name} — ELIGIBLE ({len(oks)} requirement(s) pass; "
          f"{len(pend)} pending declaration(s) build on uncertified surfaces)")
    return 0


def self_test() -> int:
    levels = {"a": "REQUIRED", "b": "REQUIRED", "m": "MODULE", "n": "MODULE"}
    pend = {"p"}
    decl = [{"owner": "EXT", "path": "x", "block": {
        "contract": CONTRACT_NAME, "required": ["a"], "modules": ["m"], "pending": ["p"],
        "why": {"a": ".", "m": ".", "p": "."}}}]
    report = {"contract": CONTRACT_NAME, "contract_digest": "D", "verdict": "certified", "requirements": [
        {"name": "a", "level": "REQUIRED", "verdict": "pass"},
        {"name": "b", "level": "REQUIRED", "verdict": "pass"},
        {"name": "m", "level": "MODULE", "verdict": "pass"},
        {"name": "n", "level": "MODULE", "verdict": "declined"}]}
    fresh = {"commit": "c0ffee", "tree_dirty": False, "moved": [], "dirty_now": [], "remote": ["origin/dev"], "error": None}
    base = dict(report=report, levels=levels, pending_vocab=pend, digest="D", declarations=decl,
                fresh=fresh, pre_contract=None)

    def fails(**over) -> set[str]:
        kw = copy.deepcopy(base)
        kw.update(over)
        return {rule for sev, rule, _ in evaluate(**kw) if sev == "FAIL"}

    def row(name, row_verdict=None, drop=False, **extra):
        r = copy.deepcopy(report)
        r["requirements"] = [x for x in r["requirements"] if not (drop and x["name"] == name)]
        for x in r["requirements"]:
            if x["name"] == name and row_verdict:
                x["verdict"] = row_verdict
        r.update(extra)
        return r

    def decl_with(**blk):
        d = copy.deepcopy(decl)
        d[0]["block"].update(blk)
        return d

    cases = [
        ("clean arm",                                   fails(),                                                     set()),
        ("control: a row we do not require is not read", fails(report=row("n", "fail", verdict="certified")),       set()),
        ("planted: required row -> fail",               fails(report=row("a", "fail", verdict="not-certified")),     {"R3", "R4"}),
        ("planted: required row missing -> unknown",    fails(report=row("a", drop=True)),                           {"R4"}),
        ("planted: MODULE declined counts only as pass", fails(report=row("m", "declined")),                          {"R4"}),
        ("planted: verdict not-certified",              fails(report=row("zz", verdict="not-certified")),            {"R3"}),
        ("planted: contract digest mismatch",           fails(digest="E"),                                           {"R2"}),
        ("planted: peer source moved",                  fails(fresh={**fresh, "moved": ["src/lib.rs"]}),             {"F1"}),
        ("planted: report measured dirty",              fails(fresh={**fresh, "tree_dirty": True}),                  {"F1"}),
        ("planted: no report",                          fails(report=None),                                          {"R1"}),
        ("planted: pre-contract while a report exists", fails(pre_contract={"since": "x"}),                          {"R0"}),
        ("planted: name keystone does not define",      fails(declarations=decl_with(required=["a", "zz"], why={"a": 1, "zz": 1, "m": 1, "p": 1})), {"V2"}),
        ("planted: pending name now measured",          fails(declarations=decl_with(pending=["b"], why={"a": 1, "m": 1, "b": 1})), {"V3"}),
        ("planted: why does not match the names",       fails(declarations=decl_with(why={"a": 1})),                 {"V4"}),
        ("planted: undeclared [requires]",              fails(declarations=[{"owner": "EXT", "path": "x", "block": None}]), {"V1"}),
        ("flag: --strict-pending",                      fails(strict_pending=True),                                  {"P1"}),
        ("flag: --release, commit on no remote",        fails(release=True, fresh={**fresh, "remote": []}),          {"F2"}),
    ]
    # Pre-contract with no report is NOT a failure unless --strict: both directions.
    cases.append(("pre-contract, no report",             fails(report=None, pre_contract={"since": "x"}),             set()))
    cases.append(("flag: --strict on pre-contract",      fails(report=None, pre_contract={"since": "x"}, strict=True), {"R0"}))

    # ── [peer_drift]: five cases, and the THIRD is the one that matters ────────────────────────
    #
    # A declared drift not failing is easy to get right and worth little on its own; what makes the
    # declaration safe rather than a suppression is that it EXPIRES BY ITSELF. Case 3 is the whole
    # mechanism: the same declaration against a peer certified at a DIFFERENT commit must go red
    # again, with nobody editing anything. Without it this block would prove only that a gate can
    # be switched off.
    moved = {**fresh, "moved": ["src/lib.rs"]}
    ok_drift = {"certified": "c0ffee", "since": "2026-09-14", "routed": "docs/status/R.md", "reason": "r"}
    cases.append(("drift: undeclared moved source still FAILS",
                  fails(fresh=moved),                                                             {"F1"}))
    cases.append(("drift: declared for THIS commit is not a failure",
                  fails(fresh=moved, peer_drift=ok_drift),                                        set()))
    cases.append(("drift: declaration EXPIRES when the peer is re-certified",
                  fails(fresh={**moved, "commit": "deadbee"}, peer_drift=ok_drift),               {"F1"}))
    cases.append(("drift: --strict-drift promotes it back",
                  fails(fresh=moved, peer_drift=ok_drift, strict_drift=True),                     {"F1"}))
    # Scope: a drift declaration is about a measurement that was trustworthy and is now old. It
    # never covers a measurement that was untrustworthy when taken.
    cases.append(("drift: a declaration does NOT cover a dirty-tree measurement",
                  fails(fresh={**moved, "tree_dirty": True}, peer_drift=ok_drift),                {"F1"}))

    bad = 0
    for label, got, want in cases:
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'}  {label}: failed rules {sorted(got)}" + ("" if ok else f", expected {sorted(want)}"))

    refusals = 0
    for label, kw in [("zero declared requirements", dict(declarations=decl_with(required=[], modules=[], pending=[], why={}))),
                      ("zero report rows", dict(report=row("zz", requirements=[]))),
                      ("certified contradicts its rows", dict(report=row("b", "fail"))),
                      # A declaration with no destination is a suppression (D21). The gate refuses
                      # rather than quietly treating it as absent: "absent" would FAIL, which looks
                      # like the safe direction and hides that somebody wrote a half-declaration.
                      ("a [peer_drift] with no `routed` destination",
                       dict(fresh={**fresh, "moved": ["src/lib.rs"]},
                            peer_drift={"certified": "c0ffee", "since": "2026-09-14", "reason": "r"})),
                      ("a [peer_drift] with no `certified` commit to expire against",
                       dict(fresh={**fresh, "moved": ["src/lib.rs"]},
                            peer_drift={"since": "2026-09-14", "routed": "docs/status/R.md", "reason": "r"}))]:
        k = copy.deepcopy(base)
        k.update(kw)
        try:
            evaluate(**k)
            print(f"  BAD  refusal did not fire: {label}")
            bad += 1
        except Refusing:
            refusals += 1
            print(f"  ok   REFUSING on {label}")
    try:
        parse_pending("## 5. Pending\n\nno table\n\n## 6. x\n")
        print("  BAD  refusal did not fire: empty pending table")
        bad += 1
    except Refusing:
        print("  ok   REFUSING on an empty pending table")

    print(f"eligible --self-test: {len(cases)} cases, {refusals + 1} refusals, {bad} wrong")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("composition", nargs="?", help="languages/<target>/compositions/<name>")
    ap.add_argument("--report", help="read this report instead of the peer's (a planted copy)")
    ap.add_argument("--strict", action="store_true", help="fail a pre-contract peer")
    ap.add_argument("--strict-pending", action="store_true", help="fail a need no report certifies")
    ap.add_argument("--release", action="store_true", help="fail a certified commit on no remote ref")
    ap.add_argument("--strict-drift", action="store_true",
                    help="fail a DECLARED [peer_drift] — the switch that gets flipped once the "
                         "peer is re-certified, so the class cannot quietly refill")
    ap.add_argument("--verbose", "-v", action="store_true", help="print passing rows too")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.composition:
        ap.error("a composition directory is required")
    return run_composition(Path(args.composition), args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""languages/python/gates/ext-checks/exec.py — the `python` arm of the authored-check axis.

**A TRANSPORT BINDING AND NOTHING ELSE.** Every check this executes lives in
`extension-contracts/<ext>/checks/*.toml`, language-neutral, and this file knows none of
them by name — no extension slug, no operation name, no assertion written in Python. It
implements the seven verbs and seven assertion kinds `gates/ext-checks/schema.py` declares,
and stops.

That split is the whole cost argument. Check logic in an arm would be per-(extension ×
target) — the quadrant `make scale` measures at 96% of the projection at 26 × 46. Check
logic in DATA is per-extension, ×1, and adding a target adds one of these files rather than
E of them. `chunking-parity` is the measured precedent for the shape; `host-seam`, at 1,478
lines of arms with no neutral half, is the measured cost of not doing it.

**Why an arm per target at all, when the wire is language-neutral.** Because a wire client
is not. `entity_core.peer` needs `cryptography` for Ed25519, which is absent from the
`node24` and `rust-toolchain` images — measured, not assumed — so one neutral client cannot
run everywhere the way the oracle's static ELF can. Each peer ships a client in its own
language and each arm binds to its own; the neutral half stays neutral.

**Read-only against keystone.** This imports the peer package from the read-only sibling
mount and writes nothing into it.

INVOKED BY `tools/host-launch` as `$CLIENT`, with the host already booted and asserted:

    ADDR=127.0.0.1:7777  ARM=composed|bare  TARGET=python  COMP=<composition>
    EXT_CHECKS_OUT=<path to write the JSON verdict>

It writes JSON and exits 0 even when checks fail — the VERDICT is the output, and a
non-zero exit here would be read by `host-launch` as a launcher failure. The comparer
decides; this arm only reports.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(os.environ.get("GENERATOR_ROOT", Path(__file__).resolve().parents[4]))
PEER_SRC = ROOT.parent / "entity-core-keystone/protocol-generator/python/src"

if not PEER_SRC.is_dir():
    print(json.dumps({"arm_error": f"no peer client at {PEER_SRC}"}))
    sys.exit(0)
sys.path.insert(0, str(PEER_SRC))

from entity_core.peer import (  # noqa: E402
    Entity,
    Identity,
    dial,
    resource_target,
    response_result,
    response_status,
)

SEED = bytes([0x22] * 32)  # a caller distinct from the host's 0x11 identity


# ── the reference indirection ───────────────────────────────────────────────────────────

def _resolve(value, captures):
    """`$capture.result.field` -> the value from an earlier response.

    The only indirection in the format. Without it a scenario cannot use a hash the PEER
    chose, and every check collapses to a single request against values we picked — which
    would make the peer's own content addressing untestable from here.

    An unresolvable reference RAISES. It never falls through as a literal string: a
    `$ingest.result.root_hash` silently compared as text would make an `included_has`
    assertion fail for the wrong reason, and a check that fails for the wrong reason is
    worse than one that does not exist.
    """
    if isinstance(value, str) and value.startswith("$"):
        parts = value[1:].split(".")
        if len(parts) != 3 or parts[1] != "result":
            raise ValueError(f"malformed reference {value!r}; expected $capture.result.field")
        cap, _, field = parts
        if cap not in captures:
            raise ValueError(f"reference {value!r} names no capture")
        res = captures[cap]["result"]
        if res is None:
            raise ValueError(f"reference {value!r}: {cap} produced no result entity")
        got = res.field(field)
        if got is None:
            raise ValueError(f"reference {value!r}: result has no field {field!r}")
        return got
    if isinstance(value, list):
        return [_resolve(v, captures) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v, captures) for k, v in value.items()}
    return value


def _materialise(value, captures):
    """TOML -> the peer's own types, for the two reserved wrappers.

    `$entity` and `$envelope` exist because an entity and an envelope are protocol
    structures rather than TOML tables. Spelling them out inline per arm is how a per-target
    file starts holding protocol (D17's distinction: a PROCEDURE may differ per target, a
    VALUE that differs is a fact that escaped the schema).
    """
    if isinstance(value, dict):
        if "$entity" in value:
            spec = _resolve(value["$entity"], captures)
            # `.to_cbor()`, not the Entity: an entity nested inside another entity's data
            # travels in its WIRE form `{type, data, content_hash}` (§1.8), which is what
            # `core/entity` means as a field type. Passing the object encodes nothing —
            # measured, on the first run: `cannot ECF-encode value of type Entity`.
            return Entity.make(spec["type"], _bytes_fields(spec.get("data", {}))).to_cbor()
        if "$envelope" in value:
            spec = _resolve(value["$envelope"], captures)
            root = spec.get("root")
            root_e = Entity.make(root["type"], _bytes_fields(root.get("data", {}))) if root else None
            inc = [Entity.make(e["type"], _bytes_fields(e.get("data", {})))
                   for e in spec.get("included", [])]
            from entity_core.peer import Envelope
            return Envelope.of(root_e, *inc).to_cbor() if root_e else None
        return {k: _materialise(v, captures) for k, v in value.items()}
    if isinstance(value, list):
        return [_materialise(v, captures) for v in value]
    return _resolve(value, captures)


def _bytes_fields(data: dict) -> dict:
    """`{ bytes = "<hex>" }` -> real bytes. TOML has no byte-string literal and a check that
    needs one is not exotic — content is bytes."""
    out = {}
    for k, v in data.items():
        if isinstance(v, dict) and set(v) == {"bytes"}:
            out[k] = bytes.fromhex(v["bytes"])
        else:
            out[k] = v
    return out


# ── the verbs ───────────────────────────────────────────────────────────────────────────

def run_check(chk: dict, host: str, port: int) -> dict:
    """Run the steps, then the assertions.

    A STEP FAILURE DOES NOT ABORT THE ASSERTIONS, and that is not tidiness. On the bare arm
    the peer answers `404 handler_not_found`, so a later step's `$ingest.result.root_hash`
    cannot resolve — and aborting there reports the whole check as `error`, which says "the
    instrument broke" when what happened is "the extension is absent and the check noticed."
    Those are different facts and the arm rule turns on telling them apart: a bare arm full
    of `error` is indistinguishable from an arm that never ran.

    So the step error is recorded and the assertions are evaluated over whatever was
    captured. An assertion whose capture is missing fails with that named as its reason,
    which is the honest verdict and the readable one.
    """
    captures: dict[str, dict] = {}
    identity = Identity.of_seed(SEED)
    conn = None
    step_error = None
    try:
        for i, step in enumerate(chk.get("step", [])):
            op = step["op"]
            if op == "connect":
                conn = dial(host, port)
                conn.handshake(identity)
            elif op == "execute":
                if conn is None:
                    raise RuntimeError("execute before connect")
                params_spec = _materialise(step["params"], captures)
                params = Entity.make(params_spec["type"], params_spec.get("data", {}))
                resource = resource_target(*step["resource"]) if step.get("resource") else None
                env = conn.execute(identity, step["uri"], step["operation"], params, resource)
                if env is None:
                    raise RuntimeError(f"step {i}: no response envelope (connection broken)")
                captures[step["capture"]] = {
                    "status": response_status(env),
                    "result": response_result(env),
                    "included": {h: e for h, e in env.included.items()},
                }
            else:
                # Never a skip. schema.py validates the vocabulary before any arm runs, so
                # reaching here means this arm is behind the schema — which must be loud.
                raise RuntimeError(f"step {i}: this arm does not implement verb {op!r}")
    except Exception as exc:  # noqa: BLE001 — the arm reports, it does not decide
        step_error = f"{type(exc).__name__}: {exc}"
        if conn is None:
            # A connect that never landed is the one fatal case: there is no peer to have
            # measured, so every assertion below would be about our own socket.
            return {"id": chk["id"], "requirement": chk["requirement"], "spec": chk["spec"],
                    "level": chk["level"], "verdict": "error", "error": step_error,
                    "trace": traceback.format_exc(limit=3).splitlines()[-3:]}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    results = [_assert(a, captures) for a in chk.get("assert", [])]
    failed = [r for r in results if not r["ok"]]
    out = {"id": chk["id"], "requirement": chk["requirement"], "spec": chk["spec"],
           "level": chk["level"],
           "verdict": "fail" if failed else "pass",
           "assertions": results}
    if step_error:
        out["step_error"] = step_error
        # A step that failed and assertions that all passed is not a pass. It means the
        # assertions did not range over the part that broke, which is a defect in the CHECK
        # rather than in the peer, and it must not read as green.
        if not failed:
            out["verdict"] = "error"
            out["error"] = ("a step failed and every assertion still passed — the assertions "
                            "do not cover the scenario: " + step_error)
    return out


def _assert(a: dict, captures: dict) -> dict:
    kind, cap = a["kind"], a["capture"]
    got = captures.get(cap)
    base = {"kind": kind, "capture": cap, "why": a.get("why", "")}
    if got is None:
        return {**base, "ok": False, "detail": f"no capture {cap!r}"}
    res = got["result"]

    try:
        if kind == "status":
            # The CODE, not only the number. A status assertion that hides the error code
            # makes every failure opaque: the `typescript` arm's first run produced three
            # `status=400` lines with no way to see which of §6.3's two 400s it was.
            code = res.text("code") if res is not None else None
            msg = res.text("message") if res is not None else None
            extra = (f" code={code}" if code else "") + (f" msg={msg[:80]}" if msg else "")
            return {**base, "ok": got["status"] == a["equals"],
                    "detail": f"status={got['status']} expected={a['equals']}{extra}"}

        if kind == "error_code":
            code = res.text("code") if res is not None else None
            return {**base, "ok": code == a["equals"], "detail": f"code={code!r} expected={a['equals']!r}"}

        if res is None:
            return {**base, "ok": False, "detail": "no result entity in the response"}

        if kind == "result_field_present":
            return {**base, "ok": res.field(a["field"]) is not None,
                    "detail": f"field {a['field']!r} " +
                              ("present" if res.field(a["field"]) is not None else "ABSENT")}

        if kind == "result_field_absent":
            return {**base, "ok": res.field(a["field"]) is None,
                    "detail": f"field {a['field']!r} " +
                              ("absent" if res.field(a["field"]) is None else "PRESENT")}

        if kind == "result_array_contains":
            want = _resolve(a["value"], captures)
            arr = res.field(a["field"]) or []
            hit = any(_eq(x, want) for x in arr)
            return {**base, "ok": hit,
                    "detail": f"{a['field']}[{len(arr)}] " +
                              ("contains" if hit else "DOES NOT contain") + " the value"}

        if kind == "result_array_empty":
            arr = res.field(a["field"])
            n = 0 if arr is None else len(arr)
            return {**base, "ok": n == 0, "detail": f"{a['field']} has {n} entries"}

        if kind == "result_array_nonempty":
            arr = res.field(a["field"])
            n = 0 if arr is None else len(arr)
            return {**base, "ok": n > 0, "detail": f"{a['field']} has {n} entries"}

        if kind == "included_has":
            want = _resolve(a["value"], captures)
            key = bytes(want).hex() if isinstance(want, (bytes, bytearray)) else str(want)
            return {**base, "ok": key in got["included"],
                    "detail": f"included[{len(got['included'])}] " +
                              ("holds" if key in got["included"] else "DOES NOT hold") +
                              f" {key[:16]}…"}

        return {**base, "ok": False, "detail": f"this arm does not implement assertion {kind!r}"}
    except Exception as exc:  # noqa: BLE001
        return {**base, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def _eq(a, b) -> bool:
    if isinstance(a, (bytes, bytearray)) and isinstance(b, (bytes, bytearray)):
        return bytes(a) == bytes(b)
    return a == b


# ── main ────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    addr = os.environ.get("ADDR", "127.0.0.1:7777")
    host, _, port = addr.partition(":")
    arm = os.environ.get("ARM", "?")
    out_path = os.environ.get("EXT_CHECKS_OUT")

    # The VALIDATED definitions, emitted once by the neutral half. Not a glob over the TOML:
    # an arm that re-derives the corpus can disagree with the other arms about which checks
    # exist, and `node` cannot parse TOML at all without a dependency these offline images
    # may not fetch. One artifact, every arm.
    defs_path = os.environ.get("EXT_CHECKS_DEFS")
    if not defs_path or not Path(defs_path).is_file():
        print(json.dumps({"arm_error": f"no emitted definitions at {defs_path!r}; "
                                       f"run gates/ext-checks/schema.py --emit first"}))
        return 0
    checks = json.loads(Path(defs_path).read_text())["checks"]

    report = {
        "target": os.environ.get("TARGET", "?"),
        "composition": os.environ.get("COMP", "?"),
        "arm": arm,
        "addr": addr,
        "definitions": len(checks),
        "checks": [run_check(c, host, int(port)) for c in checks],
    }
    blob = json.dumps(report, indent=1)
    if out_path:
        Path(out_path).write_text(blob)
    print(f"ext-checks[{arm}]: {len(checks)} checks -> "
          + " ".join(f"{c['id'].split('/')[-1]}={c['verdict']}" for c in report["checks"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

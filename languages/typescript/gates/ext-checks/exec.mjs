/**
 * languages/typescript/gates/ext-checks/exec.mjs — the `typescript` arm of the authored-check
 * axis.
 *
 * A TRANSPORT BINDING AND NOTHING ELSE. It names no extension, no operation and no assertion
 * subject; every one of those lives in `extension-contracts/<ext>/checks/*.toml`, validated
 * and emitted as JSON by `gates/ext-checks/schema.py`. This file implements the verbs and the
 * assertion kinds and stops. The `python` arm is its twin and the two are worth diffing: what
 * differs is the client library and the two places §1 of this comment names, and nothing else.
 *
 * WHAT THE SECOND ARM CHANGED, because a design at n=1 has not been tested:
 *
 *   1. THE DEFINITIONS ARE NOW JSON. The `python` arm globbed the TOML directly. `node` has
 *      no TOML parser in its standard library and these images run `--network=none`, so an
 *      arm-side parser would have put the DEFINITION FORMAT in the per-target half — the
 *      exact inversion this axis exists to avoid. The neutral half validates once and emits;
 *      every arm reads one artifact.
 *
 *   2. THE URI IS RENDERED PER TARGET. A definition says `uri = "system/content"` — the
 *      handler PATTERN, which is what the spec names. This peer's client wants a full
 *      `entity://<peer-id>/<pattern>`; the python peer's takes the bare pattern. That is a
 *      procedure difference and it belongs in the arm (D17: a procedure may differ per target,
 *      a VALUE that differs is a fact that escaped the schema). Putting the URI form in the
 *      data would have made every check carry a peer id it cannot know.
 *
 * Invoked by `tools/host-launch` as $CLIENT with the host booted and its COMPOSED line
 * asserted:  ADDR, ARM, TARGET, COMP, EXT_CHECKS_DEFS, EXT_CHECKS_OUT.
 *
 * Exits 0 even when checks fail: the VERDICT is the output and `gates/ext-checks/compare.py`
 * is the only thing that decides. A non-zero exit here reads to `host-launch` as a launcher
 * failure, which is a different fact.
 */

import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = process.env.GENERATOR_ROOT ?? path.resolve(import.meta.dirname, "../../../..");
const STAGE = `${ROOT}/languages/typescript/output/${process.env.COMP}/build`;

// Resolve the peer THROUGH THE PACKAGING BOUNDARY, the way a consumer does, rather than by
// guessing a path into someone's build output. `gates/README.md`: a path guess reaches around
// the boundary D13 is about, and turns an export-map failure into a passing probe.
//
// The peer package is ESM-only — its `exports` map has `import` and no `require` — so
// `createRequire().resolve()` fails with ERR_PACKAGE_PATH_NOT_EXPORTED (measured, on the first
// run). ESM resolves a bare specifier relative to the IMPORTING FILE, so the import has to
// happen from inside the stage. That is the same constraint `gates/type-parity`'s arm has, and
// the reason its resolution is the `gate-probe-*` reserved prefix:
//
//   D19 — an instrument does not read a quantity its own execution writes.
//
// `tools/gate-stage` excludes `gate-probe-*` from its staleness scan and
// `tools/check-structure.py` FAILS any gate arm writing another name into a stage, precisely
// so this legitimate write cannot silently pass a staleness check over a stale stage.
const LOADER = `${STAGE}/gate-probe-ext-checks-loader.mjs`;
writeFileSync(LOADER, 'export * from "entity-core-protocol-typescript";\n');
const { Peer, Entity, Ecf, ResourceTarget } = await import(pathToFileURL(LOADER).href);

const ADDR = process.env.ADDR ?? "127.0.0.1:7777";
const [HOST, PORT] = ADDR.split(":");

const defsPath = process.env.EXT_CHECKS_DEFS;
if (!defsPath) {
  console.log(JSON.stringify({ arm_error: "EXT_CHECKS_DEFS unset" }));
  process.exit(0);
}

// The corpus is CANONICAL ECF, decoded with THIS PEER'S OWN CODEC — not JSON, which is a
// second data model with no canonical form, no byte strings and no map-ordering rule
// (`docs/DESIGN-THE-CBOR-INTERCHANGE-LAYER.md`). An arm needs no parser for this: it links a
// conformant ECF codec by construction, because an arm is a wire client.
//
// `plain()` lowers the decoded value tree into this language's ordinary values so everything
// below is unchanged. That is a codec doing its job, not a translation layer: the thing that
// was removed is a second SERIALIZATION, and nothing here re-encodes.
function plain(v) {
  switch (v.kind) {
    case "map": return Object.fromEntries(Ecf.entries(v).map(([k, x]) => [k, plain(x)]));
    case "array": return Ecf.asArray(v).map(plain);
    case "text": return Ecf.asText(v);
    case "bytes": return Ecf.asBytes(v);
    case "bool": return Ecf.asBool(v);
    // `int` carries both signs in this peer's value model (`{kind:"int", negative, argument}`);
    // `asUint` is the unsigned reader and the corpus has no negative integers, so a negative
    // one must raise rather than be coerced.
    case "int": return Number(Ecf.asUint(v));
    case "null": return null;
    // Never a silent fallthrough. A major type this arm does not lower would arrive as
    // `undefined` and read downstream as an absent field — a check quietly measuring less
    // than it names, which is the failure this whole gate exists to make unauthorable.
    default: throw new Error(`ext-checks: corpus carries an ECF value this arm does not lower: ${v.kind}`);
  }
}
const CHECKS = plain(Ecf.decodeEcf(new Uint8Array(readFileSync(defsPath)))).checks;

// ── the reference indirection ─────────────────────────────────────────────────────────────
//
// `$capture.result.field`. Unresolvable RAISES rather than falling through as a literal: a
// reference silently compared as text fails the assertion for the wrong reason, and a check
// that fails for the wrong reason is worse than one that does not exist.
// `{local_peer_id}` — the second indirection, and it points the other way from the first.
// `$capture.result.field` names what the peer RETURNED; this names what the peer IS, learned
// in the §4.1 handshake. HISTORY §3.1 addresses the recorder's own output at
// `system/history/head/{local_peer_id}/...`, so without it a check can only observe recording
// through the handler face — the one face `entity-core-protocol-rust` cannot host.
//
// An EMPTY id would substitute into a real, wrong path, and a check asserting `404` there
// would pass for free. So it throws. `schema.py` refuses an unknown token before any arm
// runs; this refuses a known token with nothing to put in it.
function substitute(text, peerId) {
  if (!text.includes("{local_peer_id}")) return text;
  if (!peerId) throw new Error("{local_peer_id} used before the handshake yielded a peer id");
  return text.replaceAll("{local_peer_id}", peerId);
}

function resolve(value, captures, peerId = "") {
  if (typeof value === "string" && value.startsWith("$")) {
    const parts = value.slice(1).split(".");
    if (parts.length !== 3 || parts[1] !== "result") {
      throw new Error(`malformed reference ${value}; expected $capture.result.field`);
    }
    const [cap, , field] = parts;
    if (!(cap in captures)) throw new Error(`reference ${value} names no capture`);
    const res = captures[cap].result;
    if (!res) throw new Error(`reference ${value}: ${cap} produced no result entity`);
    const got = rawField(res, field);
    if (got === undefined || got === null) {
      throw new Error(`reference ${value}: result has no field ${field}`);
    }
    return got;
  }
  if (typeof value === "string") return substitute(value, peerId);
  if (Array.isArray(value)) return value.map((v) => resolve(v, captures, peerId));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, resolve(v, captures, peerId)]),
    );
  }
  return value;
}

function rawField(entity, field) {
  for (const [k, v] of Ecf.entries(entity.data)) if (k === field) return v;
  return undefined;
}

// TOML/JSON -> this peer's ECF values. The two reserved wrappers exist because an entity and
// an envelope are protocol structures rather than data tables.
function ecfOf(value) {
  if (value === null || value === undefined) return Ecf.nullValue?.() ?? Ecf.text("");
  if (typeof value === "string") return Ecf.text(value);
  if (typeof value === "boolean") return Ecf.bool(value);
  if (typeof value === "number") return Ecf.uint(BigInt(value));
  if (typeof value === "bigint") return Ecf.uint(value);
  if (value instanceof Uint8Array) return Ecf.bytes(value);
  if (Array.isArray(value)) return Ecf.array(value.map(ecfOf));
  if (typeof value === "object") {
    if (value.kind) return value; // already an Ecf value (a resolved reference, or $entity)
    if ("bytes" in value && Object.keys(value).length === 1) {
      return Ecf.bytes(Uint8Array.from(Buffer.from(value.bytes, "hex")));
    }
    return Ecf.map(...Object.entries(value).map(([k, v]) => [k, ecfOf(v)]));
  }
  throw new Error(`cannot encode ${typeof value}`);
}

// The WIRE form, not the object. An entity nested in another entity's data travels as
// `{type, data, content_hash}` (§1.8) — that is what `core/entity` means as a field type. The
// `python` arm needed the identical fix on its first run (`.to_cbor()`), and that it recurred
// in a second language is what makes it a property of the FORMAT rather than one arm's slip.
function entityWire(e) {
  return Ecf.map(
    ["type", Ecf.text(e.type)],
    ["data", e.data],
    ["content_hash", Ecf.bytes(e.contentHash)],
  );
}

function materialise(value, captures, peerId = "") {
  if (Array.isArray(value)) return value.map((v) => materialise(v, captures, peerId));
  if (value && typeof value === "object") {
    if ("$entity" in value) {
      const spec = resolve(value.$entity, captures, peerId);
      return entityWire(Entity.create(spec.type, ecfOf(spec.data ?? {})));
    }
    if ("$envelope" in value) {
      // `system/envelope` on the wire is `{root, included}` (§3.1). The check's envelopes
      // carry no `included` today; an empty map is the honest encoding of that rather than
      // an omitted field, because §6.3's algorithm iterates it.
      const spec = resolve(value.$envelope, captures, peerId);
      const root = spec.root
        ? entityWire(Entity.create(spec.root.type, ecfOf(spec.root.data ?? {})))
        : null;
      return Ecf.map(["root", root], ["included", Ecf.emptyMap()]);
    }
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, materialise(v, captures, peerId)]),
    );
  }
  return resolve(value, captures, peerId);
}

// ── the verbs ─────────────────────────────────────────────────────────────────────────────

async function runCheck(chk, hostPeerIdRef) {
  const captures = {};
  let client = null;
  let session = null;
  let stepError = null;

  try {
    for (const [i, step] of (chk.step ?? []).entries()) {
      if (step.op === "connect") {
        client = new Peer();
        session = await client.connect(HOST, Number(PORT));
        hostPeerIdRef.value ??= session.remotePeerId ?? null;
      } else if (step.op === "execute") {
        if (!session) throw new Error("execute before connect");
        const spec = materialise(step.params, captures, hostPeerIdRef.value ?? "");
        const params = Entity.create(spec.type, ecfOf(spec.data ?? {}));
        // §2 of the header: the definition names the PATTERN; this peer's client wants the
        // full URI. Rendered here, where it is one target's business.
        const uri = step.uri.includes("://")
          ? step.uri
          : `entity://${hostPeerIdRef.value}/${step.uri}`;
        const resource = step.resource
          ? new ResourceTarget(
              step.resource.map((r) => substitute(r, hostPeerIdRef.value ?? "")), null)
          : undefined;
        const response = await session.execute(uri, step.operation, params, resource);
        captures[step.capture] = {
          status: response.statusCode,
          result: response.result ?? null,
          included: response.included ?? null,
        };
      } else {
        // Never a skip. schema.py validates the vocabulary before any arm runs, so reaching
        // here means this arm is behind the schema, and that must be loud.
        throw new Error(`step ${i}: this arm does not implement verb ${step.op}`);
      }
    }
  } catch (e) {
    stepError = `${e.name}: ${e.message}`;
    if (!session) {
      return { id: chk.id, requirement: chk.requirement, spec: chk.spec, level: chk.level,
               verdict: "error", error: stepError };
    }
  } finally {
    try { await client?.close?.(); } catch { /* teardown is not a verdict */ }
  }

  const assertions = (chk.assert ?? []).map((a) => runAssert(a, captures));
  const failed = assertions.filter((r) => !r.ok);
  const out = { id: chk.id, requirement: chk.requirement, spec: chk.spec, level: chk.level,
                verdict: failed.length ? "fail" : "pass", assertions };
  if (stepError) {
    out.step_error = stepError;
    if (!failed.length) {
      out.verdict = "error";
      out.error = "a step failed and every assertion still passed — the assertions do not "
                + "cover the scenario: " + stepError;
    }
  }
  return out;
}

function runAssert(a, captures) {
  const base = { kind: a.kind, capture: a.capture, why: a.why ?? "" };
  const got = captures[a.capture];
  if (!got) return { ...base, ok: false, detail: `no capture ${a.capture}` };
  const res = got.result;

  try {
    if (a.kind === "status") {
      const code = res ? (Ecf.optText(res.data, "code") ?? "") : "";
      const msg = res ? (Ecf.optText(res.data, "message") ?? "") : "";
      return { ...base, ok: got.status === a.equals,
               detail: `status=${got.status} expected=${a.equals}`
                     + (code ? ` code=${code}` : "") + (msg ? ` msg=${msg.slice(0, 80)}` : "") };
    }
    if (a.kind === "error_code") {
      const code = res ? Ecf.optText(res.data, "code") : null;
      return { ...base, ok: code === a.equals, detail: `code=${code} expected=${a.equals}` };
    }
    if (!res) return { ...base, ok: false, detail: "no result entity in the response" };

    if (a.kind === "result_field_present" || a.kind === "result_field_absent") {
      const present = rawField(res, a.field) !== undefined;
      const want = a.kind === "result_field_present";
      return { ...base, ok: present === want,
               detail: `field ${a.field} ${present ? "present" : "ABSENT"}` };
    }
    if (a.kind === "result_array_contains") {
      const want = resolve(a.value, captures);
      const arr = arrayField(res, a.field);
      const hit = arr.some((x) => eq(x, want));
      return { ...base, ok: hit,
               detail: `${a.field}[${arr.length}] ${hit ? "contains" : "DOES NOT contain"} the value` };
    }
    if (a.kind === "result_array_empty" || a.kind === "result_array_nonempty") {
      const n = arrayField(res, a.field).length;
      const want = a.kind === "result_array_nonempty";
      return { ...base, ok: (n > 0) === want, detail: `${a.field} has ${n} entries` };
    }
    if (a.kind === "included_has") {
      const want = resolve(a.value, captures);
      const key = hexOf(want);
      const has = includedHas(got.included, key);
      return { ...base, ok: has,
               detail: `included ${has ? "holds" : "DOES NOT hold"} ${key.slice(0, 16)}…` };
    }
    return { ...base, ok: false, detail: `this arm does not implement assertion ${a.kind}` };
  } catch (e) {
    return { ...base, ok: false, detail: `${e.name}: ${e.message}` };
  }
}

function arrayField(res, field) {
  const v = rawField(res, field);
  if (v === undefined || v === null) return [];
  try { return Ecf.asArray(v); } catch { return []; }
}

function hexOf(v) {
  if (v instanceof Uint8Array) return Buffer.from(v).toString("hex");
  if (v && v.kind === "bytes") return Buffer.from(Ecf.asBytes(v)).toString("hex");
  return String(v);
}

function includedHas(included, hex) {
  // `Envelope.included` is a ReadonlyMap keyed by `contentHashHex` (§3.1). Compared by key
  // rather than by iterating entities: the map's key IS the peer's own hash of the entity,
  // so a mismatch between key and body is the peer's bug to report, not ours to paper over.
  if (!included) return false;
  if (typeof included.has === "function") return included.has(hex);
  return Object.prototype.hasOwnProperty.call(included, hex);
}

function eq(a, b) {
  return hexOf(a) === hexOf(b) || String(a) === String(b);
}

// ── main ──────────────────────────────────────────────────────────────────────────────────

const hostPeerIdRef = { value: null };
const checks = [];
for (const chk of CHECKS) checks.push(await runCheck(chk, hostPeerIdRef));

const report = {
  target: process.env.TARGET ?? "typescript",
  composition: process.env.COMP ?? "?",
  arm: process.env.ARM ?? "?",
  addr: ADDR,
  definitions: CHECKS.length,
  checks,
};
// The verdict leaves as canonical ECF, like the corpus arrived. A JSON report would need a
// JSON WRITER in every arm, and the arm being written next has none in its offline closure —
// the same per-target burden the corpus side just shed, in the other direction.
//
// `toEcf` lifts ordinary values back into the peer's value model. It is the exact inverse of
// `plain()` above and refuses the same way: an unrepresentable value raises rather than
// encoding as something else, because a verdict that quietly changed shape in transit is a
// measurement nobody made.
function toEcf(v) {
  if (v === null || v === undefined) return Ecf.nullValue;
  if (typeof v === "string") return Ecf.text(v);
  if (typeof v === "boolean") return Ecf.bool(v);
  if (typeof v === "number") {
    if (!Number.isInteger(v) || v < 0) throw new Error(`report carries a non-uint number: ${v}`);
    return Ecf.uint(BigInt(v));
  }
  if (v instanceof Uint8Array) return Ecf.bytes(v);
  if (Array.isArray(v)) return Ecf.array(v.map(toEcf));
  if (typeof v === "object") return Ecf.map(...Object.entries(v).map(([k, x]) => [k, toEcf(x)]));
  throw new Error(`report carries a value this arm cannot encode: ${typeof v}`);
}
if (process.env.EXT_CHECKS_OUT) {
  writeFileSync(process.env.EXT_CHECKS_OUT, Ecf.encodeEcf(toEcf(report)));
}
console.log(
  `ext-checks[${report.arm}]: ${checks.length} checks -> `
  + checks.map((c) => `${c.id.split("/").pop()}=${c.verdict}`).join(" "),
);

// EXPLICIT EXIT, and it is not a shortcut. This peer's client holds an open socket with no
// exported close, so node's event loop never drains and the arm hangs after reporting —
// measured: the first `make ext-checks` run with this arm sat past a 120 s timeout having
// already printed its verdict and written its report. `host-launch` reaps the HOST on exit;
// nothing reaps the client. A gate that produces a correct answer and then never returns is
// indistinguishable from one that hung before measuring, which is the state that reads as an
// infrastructure problem and gets the gate disabled (AP-4).
process.exit(0);

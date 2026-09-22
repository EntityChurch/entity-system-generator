// gates/type-parity/probe.mjs — the `typescript` arm.
//
// Import the staged package by name (through its `exports` map, not by a path into the
// source tree), call its `<ext>TypeEntities()`, print one JSON line: the peer's own
// content hash per type entity, plus a normalisation of its data tree.
//
// THIS ARM'S NORMALISER DOES THE MOST WORK OF THE THREE, and that is the interesting
// fact about this port. `python` hands back plain dicts and `rust` a `Value` enum;
// `typescript` holds the data as an ECF-TAGGED TREE -- `{kind:"map", pairs:[[k,v]...]}`,
// `{kind:"int", negative, argument}` -- so every value passes through a translation here
// that does not exist on the other two arms.
//
// That asymmetry is why `compare.py` cross-checks `data` against `hash`: the hash is
// computed by the peer's codec and never touches this function, so a bug in this
// translation shows up as a CONTRADICTION rather than as a divergence blamed on a port.

const subject = process.argv[2];

// DERIVED, NOT TABULATED. This arm shipped with a `SUBJECTS` map -- one entry per
// extension, in a file whose whole purpose is to be extension-agnostic, which is E x T =
// 1,196 hand-maintained rows at the full corpus. The mapping was never a decision: it is
// this target's naming convention applied to a slug. Derive it, and REFUSE if the
// derivation misses -- which a table cannot do, because a table cannot notice that a cell
// broke the convention.
if (!subject) {
  console.error("usage: probe.mjs <extension-slug>");
  process.exit(2);
}
const specifier = `@entity-core/extension-${subject}`;
const exportName = `${subject}TypeEntities`;

let mod;
try {
  mod = await import(specifier);
} catch (err) {
  console.error(
    `REFUSING: cannot import \`${specifier}\` for extension \`${subject}\` (${err.message}). ` +
      `The arm derives the specifier from this target's naming convention; a cell that ` +
      `breaks it is a finding, not a missing table entry.`,
  );
  process.exit(2);
}
if (typeof mod[exportName] !== "function") {
  console.error(
    `REFUSING: \`${specifier}\` exports no \`${exportName}\`. Every cell on this target ` +
      `publishes its materialised type entities under that name; one that does not is ` +
      `drift the \`sdk-surface\` gate should have caught.`,
  );
  process.exit(2);
}
const entities = mod[exportName]();

const hex = (bytes) => {
  if (!(bytes instanceof Uint8Array)) {
    // `contentHash`, not `hash`, on this port -- and the chunking-parity sibling paid for
    // learning that. A probe that hexed `undefined` to "" would report identical empty
    // hashes across three arms and read as perfect parity.
    throw new TypeError(`expected a Uint8Array content hash, got ${typeof bytes}`);
  }
  return Buffer.from(bytes).toString("hex");
};

// The ECF value tree -> canonical JSON. REFUSES on an unknown tag rather than falling
// through: an unhandled kind rendered as `undefined` would drop a field silently, and a
// dropped field is exactly the divergence this gate exists to see.
function normalise(v) {
  switch (v?.kind) {
    case "map": {
      const out = {};
      for (const [k, val] of v.pairs) {
        if (k?.kind !== "text") {
          throw new TypeError(`non-text map key of kind ${k?.kind} in a type entity`);
        }
        out[k.value] = normalise(val);
      }
      // Sorted, matching the other arms: the codec re-sorts map keys length-then-lex, so
      // declaration order provably does not reach the bytes. `hash` is the control on
      // whether dropping that distinction was right.
      return Object.fromEntries(Object.keys(out).sort().map((k) => [k, out[k]]));
    }
    case "array":
      return v.items.map(normalise);
    case "text":
      return v.value;
    case "bool":
      return v.value;
    case "null":
      return null;
    case "float":
      return v.value;
    case "int": {
      const n = v.negative ? -1n - BigInt(v.argument) : BigInt(v.argument);
      // Number, to match the other two arms; BigInt does not survive JSON.stringify and
      // the values in a type entity are small. Refuse rather than silently lose one.
      if (n > BigInt(Number.MAX_SAFE_INTEGER) || n < BigInt(Number.MIN_SAFE_INTEGER)) {
        throw new RangeError(`integer ${n} exceeds the safe range; would not survive JSON`);
      }
      return Number(n);
    }
    case "bytes":
      return { __bytes__: Buffer.from(v.value).toString("hex") };
    default:
      throw new TypeError(
        `REFUSING: unhandled ECF kind ${JSON.stringify(v?.kind)} in a type entity. ` +
          `Returning undefined here would drop the field silently.`,
      );
  }
}

const types = entities.map(([name, entity]) => ({
  name,
  hash: hex(entity.contentHash),
  data: normalise(entity.data),
}));

console.log(JSON.stringify({ port: "typescript", extension: subject, types }));

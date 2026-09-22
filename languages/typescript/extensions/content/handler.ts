/**
 * CONTENT §6 — the system content handler. Two operations, `get` (§6.2) and
 * `ingest` (§6.3), both hash-addressed at the params level and path-addressed at
 * the cap-scope level (§6.4).
 *
 * The handler is **optional** as an extension (§11.3) and type-agnostic by design
 * (§6): it serves any entity in the content store, not just blobs and chunks.
 */

import {
  Ecf,
  Entity,
  Envelope,
  HandlerResult,
  Status,
  errorResult,
  type ContentStore,
  type Handler,
  type HandlerContext,
  type HandlerOperations,
} from "entity-core-protocol-typescript";

import { ContentTypes, CONTENT_PATTERN } from "./types.js";

/**
 * Envelope + response overhead reserved out of the frame budget before entities are
 * packed. The response entity itself carries two hash arrays (33 B each plus CBOR
 * framing) and the envelope adds its own map framing; 4 KiB is comfortably above
 * both for any batch a caller can request within one frame.
 */
const FRAME_RESERVE_BYTES = 4096;

export interface ContentHandlerOptions {
  /**
   * The namespace prefix this handler instance serves (§6.4). `system/content` is
   * the default-namespace value §6.2 pins for the §6.1 manifest registration.
   *
   * **Topology.** Cycle 1 runs single-trust-domain (§6.4.1): `get` resolves any
   * hash in the content store and `ingest` writes the store without binding into
   * the tree. §6.4.1 makes that OPT-IN AND RESTRICTED — "MUST NOT be enabled as the
   * default configuration", and multi-party deployments running it are "out-of-spec
   * and security-defective". It is declared in `EXTENSION.toml [assumptions]
   * .topology` rather than assumed here, and the namespace-scoped topology (§6.4.2
   * Hash Tree Presence) is a declared cycle-1 gap, not a silent one.
   */
  readonly namespace?: string;
}

export class ContentHandler implements Handler {
  readonly pattern = CONTENT_PATTERN;
  readonly name = "content";

  /**
   * §6.1's manifest, declared here and published verbatim by `registerHandler`.
   *
   * This was `readonly string[]` for exactly one day. keystone's `Handler.operations`
   * carried operation NAMES only, so registration rendered `{get: {}, ingest: {}}` and
   * `installContent` had to re-write the interface entity afterwards to say what the
   * operations take and return. Routed as K-2; closed 2026-09-06 — and the sharper
   * version of the finding was theirs, not ours: the **wire** register op had always
   * forwarded a full §3.7 manifest, so the in-process surface was the narrower of the
   * two rather than both being narrow. The bare-name form still renders byte-identically,
   * so no bootstrap handler moved.
   */
  readonly operations: HandlerOperations = {
    get: { inputType: ContentTypes.GetRequest, outputType: ContentTypes.ContentResponse },
    ingest: { inputType: ContentTypes.IngestRequest, outputType: ContentTypes.IngestResult },
  };

  readonly #namespace: string;

  constructor(options: ContentHandlerOptions = {}) {
    this.#namespace = options.namespace ?? CONTENT_PATTERN;
  }

  async handle(ctx: HandlerContext): Promise<HandlerResult> {
    // §6.2 / §6.3 path-as-resource MUST. Checked FIRST, before the operation
    // switch, because it applies to both ops identically and because an unknown
    // operation with no resource should still report the resource failure a caller
    // can act on. `400 path_required` — the status is pinned by
    // GUIDE-EXTENSION-DEVELOPMENT §171, and the oracle checks only the CODE, so a
    // peer answering 404 passes the gate and fails the spec. We answer 400.
    if (ctx.resource === null) {
      return errorResult(
        Status.BadRequest,
        "path_required",
        `${CONTENT_PATTERN}:${ctx.operation} requires a resource naming the namespace path (§6.2/§6.3)`,
      );
    }

    // §6.4 step 2 — path-scope check, handler-level. Dispatch already verified the
    // resource against the grant's `resources` scope (§6.4 step 1), so this is
    // defence-in-depth: it refuses a target outside the namespace this instance
    // serves even if a grant somehow covered it.
    //
    // `capability_denied`, NOT `forbidden`. v3.7 corrected §6.4's pseudocode: `forbidden`
    // was defined in no code set — it is ENTITY-CORE-PROTOCOL §3.3's *fallback* for the
    // 403 status, not a code — and §3.3's 403 row names `capability_denied` as the default.
    const outside = ctx.resource.targets.find((t) => !withinNamespace(t, this.#namespace));
    if (outside !== undefined) {
      return errorResult(
        Status.Forbidden,
        "capability_denied",
        `resource target '${outside}' is outside namespace '${this.#namespace}' (§6.4)`,
      );
    }

    switch (ctx.operation) {
      case "get":
        return this.#get(ctx);
      case "ingest":
        return this.#ingest(ctx);
      default:
        // §6.6(2): "This spec does not define a `system/content:delete`." Removal is
        // local GC, never a protocol op — so an unknown verb is 501, not 404.
        return errorResult(Status.NotSupported, "unsupported_operation", ctx.operation);
    }
  }

  // ── §6.2 get ────────────────────────────────────────────────────────────────

  #get(ctx: HandlerContext): HandlerResult {
    let hashes: readonly Uint8Array[];
    try {
      hashes = Ecf.asArray(Ecf.require(ctx.params.data, "hashes")).map((h) => Ecf.asBytes(h));
    } catch {
      return errorResult(Status.BadRequest, "unexpected_params", "get expects {hashes: array_of system/hash} (§6.2)");
    }

    const store: ContentStore = ctx.peer.contentStore;

    // Amendment 1 §6.2 MUST: consult THE CONNECTION'S configured budget at
    // response-construction time, not a hardcoded 16 MiB literal. `frameBudget()`
    // prefers `connection.maxFrameBytes` and falls back to the peer default only
    // for an in-process dispatch, which has no connection and still needs a number.
    let remaining = ctx.frameBudget() - FRAME_RESERVE_BYTES;

    const found: Uint8Array[] = [];
    const missing: Uint8Array[] = [];
    const included: Entity[] = [];
    // Once the budget is exhausted every REMAINING hash goes to `missing` in
    // request order — §6.2 says "as many as fit (in request order)", so a small
    // entity after a large one does NOT get packed. Order is the contract; the
    // requester retries with `missing` and makes progress deterministically.
    let budgetExhausted = false;

    for (const hash of hashes) {
      const entity = store.get(hash);
      if (entity === undefined) {
        missing.push(hash);
        continue;
      }
      const cost = entity.wireBytes.length + hash.length;
      if (budgetExhausted || cost > remaining) {
        budgetExhausted = true;
        missing.push(hash);
        continue;
      }
      remaining -= cost;
      included.push(entity);
      found.push(hash);
    }

    // §6.2 Amendment 2: `pending` is OPTIONAL and SHOULD be populated only by an
    // implementation with sync-state visibility — an active subscription on the
    // namespace plus an inbox feeding the content store. This composition has
    // neither, so the field is OMITTED. Emitting an empty array would advertise a
    // capability we do not have; §6.2 says a receiver that omits it is telling the
    // caller to treat all `missing` as terminal, which is the truth here.
    const response = Entity.create(
      ContentTypes.ContentResponse,
      Ecf.map(
        ["found", Ecf.array(found.map((h) => Ecf.bytes(h)))],
        ["missing", Ecf.array(missing.map((h) => Ecf.bytes(h)))],
      ),
    );
    return HandlerResult.ok(response, included);
  }

  // ── §6.3 ingest ─────────────────────────────────────────────────────────────

  #ingest(ctx: HandlerContext): HandlerResult {
    const envelopeValue = Ecf.field(ctx.params.data, "envelope");
    const entityValue = Ecf.field(ctx.params.data, "entity");

    if (envelopeValue !== null && entityValue !== null) {
      return errorResult(Status.BadRequest, "ambiguous_input", "Specify envelope or entity, not both");
    }
    if (envelopeValue === null && entityValue === null) {
      return errorResult(Status.BadRequest, "missing_input", "Specify envelope or entity");
    }

    const store: ContentStore = ctx.peer.contentStore;

    // ── Entity mode: store a single entity. `root` is ABSENT from the result —
    // there is no envelope wrapper to pass through (§6.3), and the §11.1 MUST is
    // scoped to envelope mode with a non-null root.
    if (entityValue !== null) {
      let entity: Entity;
      try {
        entity = Entity.fromDecoded(entityValue);
      } catch (err) {
        return errorResult(Status.BadRequest, "unexpected_params", `entity: ${message(err)}`);
      }
      store.put(entity);
      return HandlerResult.ok(
        Entity.create(
          ContentTypes.IngestResult,
          Ecf.map(["root_hash", Ecf.bytes(entity.contentHash)], ["ingested_count", Ecf.uint(1n)]),
        ),
      );
    }

    // ── Envelope mode: store root + all included.
    //
    // `system/envelope` extends `core/envelope`, whose `root` is a REQUIRED
    // `core/entity`, so §6.3's `if envelope.root is not null` branch is unreachable
    // for a well-formed envelope and a missing root is a malformed request rather
    // than an empty-count success. Recorded in the authoring notes; not routed,
    // because the type declaration already answers it.
    let envelope: Envelope;
    try {
      envelope = Envelope.decode(Ecf.encodeEcf(envelopeValue as NonNullable<typeof envelopeValue>));
    } catch (err) {
      // `Envelope.decode` is where the §6.3 hash-validation MUST is enforced: it
      // rejects an included entry whose content hash does not match its map key
      // (core §3.1). Reusing it rather than re-implementing the check is the point
      // — a second implementation of "does this hash match" is a second thing that
      // can disagree with the peer about entity fidelity.
      return errorResult(Status.BadRequest, "hash_mismatch", `envelope: ${message(err)}`);
    }

    store.put(envelope.root);
    let count = 1;
    for (const entity of envelope.included.values()) {
      store.put(entity);
      count++;
    }

    // §11.1 MUST: `root` is included, inlined, in envelope mode. It lets a
    // continuation navigate `data.root.data.<field>` without dereferencing the
    // content store (§6.3.1).
    return HandlerResult.ok(
      Entity.create(
        ContentTypes.IngestResult,
        Ecf.map(
          ["root", Ecf.decodeEcf(envelope.root.wireBytes)],
          ["root_hash", Ecf.bytes(envelope.root.contentHash)],
          ["ingested_count", Ecf.uint(BigInt(count))],
        ),
      ),
    );
  }
}

/** A resource target is in-namespace if it IS the prefix or sits under it. */
function withinNamespace(target: string, namespace: string): boolean {
  const t = target.replace(/^\/+/, "");
  return t === namespace || t.startsWith(namespace + "/");
}

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

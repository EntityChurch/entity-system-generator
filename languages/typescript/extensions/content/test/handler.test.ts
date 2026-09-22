/**
 * §6 — the system content handler.
 *
 * **Everything a client can observe goes OVER THE WIRE**, from a second peer, through
 * the real dispatch chain. In-process handler calls would be faster and would measure
 * less; the failure this repo has already shipped once is a call site read as a
 * capability — a symbol present, reachable, consulted, and answering `501` behind the
 * call.
 *
 * §6.2's central wire contract is *"the fetched entities are delivered via the response
 * envelope's `included` map; `found` is the index that confirms which hashes are present
 * in `included`"*, and **that assertion now runs over the wire.** It could not, for one
 * day: `PeerSession.execute` built `new ExecuteResponse(response.root)` and dropped the
 * envelope, so a consumer on this peer's own client surface received the reference and
 * never the referent. Routed as K-3; closed upstream 2026-09-06, and their version of the
 * finding was bigger than ours — the same defect sat on `OutboundDispatchImpl.execute`,
 * the §6.13(b) path a handler uses to originate, which is the one that would have bitten
 * a composed system rather than a test.
 *
 * **What stays in-process is only what a wire client cannot construct**: a pinned frame
 * budget, which needs a `ConnectionState` a negotiated connection does not let you set.
 * That test says so on its own line.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ConnectionState,
  Ecf,
  Entity,
  Envelope,
  Execute,
  HandlerContext,
  Peer,
  ResourceTarget,
} from "entity-core-protocol-typescript";
import {
  ContentHandler,
  ContentTypes,
  CONTENT_PATTERN,
  createBlobFixed,
  ensureClosure,
  installContent,
  storeBlob,
} from "@entity-core/extension-content";

const NAMESPACE_TARGET = new ResourceTarget([CONTENT_PATTERN], null);

// ── over-the-wire rig ───────────────────────────────────────────────────────────

interface Rig {
  readonly host: Peer;
  exec(
    op: string,
    params: Entity,
    resource: ResourceTarget | null,
  ): Promise<{ status: number; result: Entity; included: ReadonlyMap<string, Entity> }>;
  close(): Promise<void>;
}

async function rig(): Promise<Rig> {
  const host = new Peer({ debugOpenGrants: true });
  installContent(host);
  const port = await host.listen(0);

  const client = new Peer();
  const session = await client.connect("127.0.0.1", port);
  const uri = `entity://${host.localPeerId}/${CONTENT_PATTERN}`;

  return {
    host,
    async exec(op, params, resource) {
      const response = await session.execute(uri, op, params, resource);
      return { status: response.statusCode, result: response.result, included: response.included };
    },
    async close() {
      await client.dispose();
      await host.dispose();
    },
  };
}

// ── in-process rig: the only thing a wire client cannot construct is a pinned budget ──

function inProcess(peer: Peer, op: string, params: Entity, opts: { resource?: ResourceTarget | null; frameBudget?: number } = {}) {
  const execute = Execute.build({
    requestId: "in-process-1",
    uri: `/${peer.localPeerId}/${CONTENT_PATTERN}`,
    operation: op,
    params,
    resource: opts.resource === undefined ? NAMESPACE_TARGET : opts.resource,
  });
  let connection: ConnectionState | null = null;
  if (opts.frameBudget !== undefined) {
    connection = new ConnectionState();
    connection.maxFrameBytes = opts.frameBudget;
  }
  const ctx = new HandlerContext({
    peer,
    execute,
    envelope: new Envelope(execute.entity, []),
    pattern: CONTENT_PATTERN,
    suffix: "",
    callerCapability: null,
    handlerGrant: null,
    author: null,
    connection,
  });
  return new ContentHandler().handle(ctx);
}

function errorCode(result: Entity): string | null {
  return result.type === "system/protocol/error" ? Ecf.optText(result.data, "code") : null;
}

function hashList(result: Entity, field: string): string[] {
  return Ecf.asArray(Ecf.require(result.data, field)).map((h) => Buffer.from(Ecf.asBytes(h)).toString("hex"));
}

// ── §6.2 / §6.3 path-as-resource MUST (wire) ────────────────────────────────────

test("§6.2 get without a resource -> 400 path_required", async () => {
  const r = await rig();
  try {
    const params = Entity.create(ContentTypes.GetRequest, Ecf.map(["hashes", Ecf.array([])]));
    const { status, result } = await r.exec("get", params, null);
    assert.equal(errorCode(result), "path_required");
    // The oracle checks the CODE only, so a peer answering 404 passes the gate and
    // fails the spec. GUIDE-EXTENSION-DEVELOPMENT §171 pins 400; assert the status too.
    assert.equal(status, 400, "§171 pins the status at 400, and nothing upstream checks it");
  } finally {
    await r.close();
  }
});

test("§6.3 ingest without a resource -> 400 path_required", async () => {
  const r = await rig();
  try {
    const target = Entity.create("test/marker", Ecf.emptyMap());
    const params = Entity.create(ContentTypes.IngestRequest, Ecf.map(["entity", Ecf.decodeEcf(target.wireBytes)]));
    const { status, result } = await r.exec("ingest", params, null);
    assert.equal(errorCode(result), "path_required");
    assert.equal(status, 400);
  } finally {
    await r.close();
  }
});

test("§6.4 a resource target outside the namespace -> 403", async () => {
  const r = await rig();
  try {
    const params = Entity.create(ContentTypes.GetRequest, Ecf.map(["hashes", Ecf.array([])]));
    const { status, result } = await r.exec("get", params, new ResourceTarget(["local/files"], null));
    assert.equal(status, 403);
    assert.equal(errorCode(result), "forbidden");
  } finally {
    await r.close();
  }
});

// ── §6.2 get (wire) ─────────────────────────────────────────────────────────────

test("§6.2 get names a resolved hash in `found`, an unknown one in `missing`, and DELIVERS the entity", async () => {
  const r = await rig();
  try {
    const blob = createBlobFixed(new Uint8Array(3000).fill(7), 1024);
    const blobHash = storeBlob(r.host.contentStore, blob);
    const unknown = new Uint8Array(33);
    unknown[1] = 0xab;

    const params = Entity.create(
      ContentTypes.GetRequest,
      Ecf.map(["hashes", Ecf.array([Ecf.bytes(blobHash), Ecf.bytes(unknown)])]),
    );
    const { status, result, included } = await r.exec("get", params, NAMESPACE_TARGET);

    assert.equal(status, 200, "a miss is not an error — §6.2 always answers {found, missing}");
    assert.equal(result.type, ContentTypes.ContentResponse);
    // §6.2 wire-shape contract (F4 audit landing): ARRAYS, not counters. Deriving a
    // count from an array is trivial; deriving an array from a count is not.
    assert.deepEqual(hashList(result, "found"), [blob.blob.contentHashHex]);
    assert.equal(hashList(result, "missing").length, 1);
    // THE contract: `found` is an index INTO `included`. A response naming a hash it did
    // not deliver is the reference-without-referent failure K-3 was, and it is the half
    // that could not be asserted over the wire until 2026-09-06.
    assert.ok(included.has(blob.blob.contentHashHex), "the resolved entity rides in envelope.included");
    assert.equal(included.size, 1, "and nothing the caller did not ask for");
    // Amendment 2: `pending` is OPTIONAL and advertises sync-state visibility. This
    // composition has no subscription and no inbox, so emitting it — even empty —
    // would claim a capability we do not have.
    assert.equal(Ecf.field(result.data, "pending"), null, "no sync-state visibility, so no `pending`");
  } finally {
    await r.close();
  }
});

test("§6.2 malformed params -> 400 unexpected_params, not a crash", async () => {
  const r = await rig();
  try {
    const params = Entity.create(ContentTypes.GetRequest, Ecf.map(["hashes", Ecf.text("not an array")]));
    const { status, result } = await r.exec("get", params, NAMESPACE_TARGET);
    assert.equal(status, 400);
    assert.equal(errorCode(result), "unexpected_params");
  } finally {
    await r.close();
  }
});

test("an unadvertised operation -> 501", async () => {
  const r = await rig();
  try {
    const { status, result } = await r.exec("delete", Entity.create("primitive/any", Ecf.emptyMap()), NAMESPACE_TARGET);
    assert.equal(status, 501);
    assert.equal(errorCode(result), "unsupported_operation");
    // §6.6(2): "This spec does not define a `system/content:delete`." Removal is a
    // local GC concern, never a protocol op.
  } finally {
    await r.close();
  }
});

test("§6 the handler is type-agnostic — any entity in the store, not just blobs", async () => {
  const r = await rig();
  try {
    const arbitrary = Entity.create("test/whatever", Ecf.map(["k", Ecf.text("v")]));
    r.host.contentStore.put(arbitrary);
    const params = Entity.create(
      ContentTypes.GetRequest,
      Ecf.map(["hashes", Ecf.array([Ecf.bytes(arbitrary.contentHash)])]),
    );
    const { status, included } = await r.exec("get", params, NAMESPACE_TARGET);
    assert.equal(status, 200);
    assert.ok(
      included.has(arbitrary.contentHashHex),
      "§6: 'It serves any entity type, not just blobs and chunks.'",
    );
  } finally {
    await r.close();
  }
});

// ── §6.2 frame budget — in-process, because a wire client cannot pin one ────────

test("§6.2 Amendment 1: the budget consulted is the CONNECTION's, and order is the contract", async () => {
  // The one test that stays in-process. A negotiated connection does not let a client
  // choose the peer's frame budget, so pinning one needs a hand-built `ConnectionState`
  // — and pinning it is the whole measurement: the peer default (16 MiB) fits both
  // entities and an 8 KiB CONNECTION budget fits neither, so a hardcoded literal would
  // answer identically twice.
  const peer = new Peer();
  const big = Entity.create("test/big", Ecf.map(["p", Ecf.bytes(new Uint8Array(64_000).fill(1))]));
  const small = Entity.create("test/small", Ecf.map(["p", Ecf.text("x")]));
  peer.contentStore.put(big);
  peer.contentStore.put(small);

  const params = Entity.create(
    ContentTypes.GetRequest,
    Ecf.map(["hashes", Ecf.array([Ecf.bytes(big.contentHash), Ecf.bytes(small.contentHash)])]),
  );

  // The peer default (16 MiB) fits both. A CONNECTION budget of 8 KiB fits neither,
  // and the two answers differing on the same peer is what proves the connection's
  // value is what was read — a hardcoded 16 MiB literal would answer identically twice.
  const wide = await inProcess(peer, "get", params);
  assert.deepEqual(hashList(wide.result, "found").length, 2);

  const squeezed = await inProcess(peer, "get", params, { frameBudget: 8192 });
  // §6.2: "include as many as fit (IN REQUEST ORDER) and move the remainder to
  // `missing`". Once the budget is exhausted the small entity does NOT get packed —
  // order is the contract, so the requester's retry makes deterministic progress.
  assert.deepEqual(hashList(squeezed.result, "missing"), [big.contentHashHex, small.contentHashHex]);
  assert.deepEqual(hashList(squeezed.result, "found"), []);
  assert.equal(squeezed.included.length, 0);
});

// ── §6.3 ingest (wire) ──────────────────────────────────────────────────────────

test("§6.3 entity mode stores one entity and omits `root`", async () => {
  const r = await rig();
  try {
    const target = Entity.create("test/marker", Ecf.map(["n", Ecf.uint(1n)]));
    const params = Entity.create(ContentTypes.IngestRequest, Ecf.map(["entity", Ecf.decodeEcf(target.wireBytes)]));
    const { status, result } = await r.exec("ingest", params, NAMESPACE_TARGET);

    assert.equal(status, 200);
    assert.equal(result.type, ContentTypes.IngestResult);
    assert.equal(Ecf.asUint(Ecf.require(result.data, "ingested_count")), 1n);
    assert.equal(
      Buffer.from(Ecf.asBytes(Ecf.require(result.data, "root_hash"))).toString("hex"),
      target.contentHashHex,
    );
    // §6.3: "In entity mode, `root` is absent — there is no envelope wrapper to pass through."
    assert.equal(Ecf.field(result.data, "root"), null);
    assert.ok(r.host.contentStore.contains(target.contentHash), "§6.3 post-ingest availability");
  } finally {
    await r.close();
  }
});

test("§6.3 + §11.1 MUST: envelope mode inlines `root` and counts root + included", async () => {
  const r = await rig();
  try {
    const inner = Entity.create("test/inner", Ecf.map(["v", Ecf.text("leaf")]));
    const root = Entity.create("test/wrapper", Ecf.map(["head", Ecf.bytes(inner.contentHash)]));
    const envelope = new Envelope(root, [inner]);
    const params = Entity.create(ContentTypes.IngestRequest, Ecf.map(["envelope", Ecf.decodeEcf(envelope.encode())]));
    const { status, result } = await r.exec("ingest", params, NAMESPACE_TARGET);

    assert.equal(status, 200);
    assert.equal(Ecf.asUint(Ecf.require(result.data, "ingested_count")), 2n);
    // The §11.1 MUST. It is what lets a continuation navigate `data.root.data.head`
    // without dereferencing the content store (§6.3.1).
    const inlined = Ecf.require(result.data, "root");
    assert.equal(Ecf.asText(Ecf.require(inlined, "type")), "test/wrapper");
    assert.ok(r.host.contentStore.contains(inner.contentHash));
    assert.ok(r.host.contentStore.contains(root.contentHash));
  } finally {
    await r.close();
  }
});

test("§6.3 both inputs -> ambiguous_input; neither -> missing_input", async () => {
  const r = await rig();
  try {
    const e = Entity.create("test/marker", Ecf.emptyMap());
    const envelope = new Envelope(e, []);

    const both = Entity.create(
      ContentTypes.IngestRequest,
      Ecf.map(["envelope", Ecf.decodeEcf(envelope.encode())], ["entity", Ecf.decodeEcf(e.wireBytes)]),
    );
    assert.equal(errorCode((await r.exec("ingest", both, NAMESPACE_TARGET)).result), "ambiguous_input");

    const neither = Entity.create(ContentTypes.IngestRequest, Ecf.emptyMap());
    assert.equal(errorCode((await r.exec("ingest", neither, NAMESPACE_TARGET)).result), "missing_input");
  } finally {
    await r.close();
  }
});

test("§6.3 is idempotent — content-addressed storage makes a re-put a no-op", async () => {
  const r = await rig();
  try {
    const payload = Entity.create("test/round", Ecf.map(["p", Ecf.text("trip")]));
    const params = Entity.create(ContentTypes.IngestRequest, Ecf.map(["entity", Ecf.decodeEcf(payload.wireBytes)]));
    const first = await r.exec("ingest", params, NAMESPACE_TARGET);
    const second = await r.exec("ingest", params, NAMESPACE_TARGET);
    assert.equal(first.status, 200);
    assert.equal(second.status, 200);
    assert.equal(
      Buffer.from(Ecf.asBytes(Ecf.require(second.result.data, "root_hash"))).toString("hex"),
      payload.contentHashHex,
    );

    const get = Entity.create(
      ContentTypes.GetRequest,
      Ecf.map(["hashes", Ecf.array([Ecf.bytes(payload.contentHash)])]),
    );
    assert.deepEqual(hashList((await r.exec("get", get, NAMESPACE_TARGET)).result, "found"), [payload.contentHashHex]);
  } finally {
    await r.close();
  }
});

// ── §6.1 manifest + §2 types, as the oracle reads them ──────────────────────────

test("§6.1 the published manifest carries the operation input/output types", async () => {
  const r = await rig();
  try {
    const iface = r.host.tree.get(`/${r.host.localPeerId}/system/handler/${CONTENT_PATTERN}`);
    assert.ok(iface !== undefined, "index entry at system/handler/system/content");
    assert.equal(Ecf.asText(Ecf.require(iface.data, "pattern")), CONTENT_PATTERN);
    const ops = Ecf.require(iface.data, "operations");
    // keystone's `registerHandler` renders `{get: {}, ingest: {}}` — its `Handler`
    // interface carries operation NAMES only. §6.1 declares input_type and output_type
    // for both ops, so `installContent` re-writes the interface entity. The oracle
    // checks key presence only; this assertion is the one that would notice a regression.
    assert.equal(Ecf.asText(Ecf.require(Ecf.require(ops, "get"), "input_type")), ContentTypes.GetRequest);
    assert.equal(Ecf.asText(Ecf.require(Ecf.require(ops, "get"), "output_type")), ContentTypes.ContentResponse);
    assert.equal(Ecf.asText(Ecf.require(Ecf.require(ops, "ingest"), "input_type")), ContentTypes.IngestRequest);
    assert.equal(Ecf.asText(Ecf.require(Ecf.require(ops, "ingest"), "output_type")), ContentTypes.IngestResult);
  } finally {
    await r.close();
  }
});

test("§11.1 the type entities the oracle reads are published", async () => {
  const r = await rig();
  try {
    for (const name of Object.values(ContentTypes)) {
      assert.ok(
        r.host.tree.isBound(`/${r.host.localPeerId}/system/type/${name}`),
        `${name} must be registered — registerHandler writes NO type entities (measured)`,
      );
    }
  } finally {
    await r.close();
  }
});

// ── §3.3 EnsureClosure ──────────────────────────────────────────────────────────

test("§3.3 closure: complete, missing_chunk, and blob_not_found are distinguished", () => {
  const peer = new Peer();
  const blob = createBlobFixed(new Uint8Array(2500).fill(9), 1024);
  const blobHash = storeBlob(peer.contentStore, blob);

  const ok = ensureClosure(peer.contentStore, blobHash);
  assert.equal(ok.complete, true);
  assert.equal(ok.complete && ok.totalSize, 2500);
  assert.equal(ok.complete && ok.chunkCount, 3);

  // A blob whose chunks were never stored. §3.3 orders the checks: the first missing
  // chunk reports `missing_chunk`, NOT `size_mismatch`, even though totals also disagree.
  const orphan = createBlobFixed(new Uint8Array(4096).fill(3), 1024);
  peer.contentStore.put(orphan.blob);
  const verdict = ensureClosure(peer.contentStore, orphan.blob.contentHash);
  assert.equal(verdict.complete, false);
  assert.equal(!verdict.complete && verdict.code, "missing_chunk");

  const absent = ensureClosure(peer.contentStore, new Uint8Array(33));
  assert.equal(!absent.complete && absent.code, "blob_not_found");
});

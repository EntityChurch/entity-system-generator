/**
 * §3.4 clause 2, in both directions, against a real grant rather than a stub.
 *
 * **The `rust` port cannot have this file and that asymmetry is the point.** There
 * `reassembleUnderCapability`'s equivalent takes a `&HandlerContext` whose fields are
 * `pub(crate)`, so no test can call the wrapper at all and the DECISION had to be split
 * out as a `pub(crate)` predicate to be measured (`src/sdk.rs`'s `authorization_tests`).
 * Here the context is caller-constructible — which is exactly clause 1's failure on this
 * port, routed as `K-24` — so the wrapper itself is directly reachable and the check is
 * measured where it lives. **The port that is weaker on clause 1 is the port on which
 * clause 2 is testable end to end**, and neither fact is a choice either port made.
 *
 * The contexts below are REAL `HandlerContext`s over a real `Peer`, not duck-typed
 * objects: `ctx.operation` is a getter over the EXECUTE and `ctx.peer.localPeerId` is the
 * canonicalization frame the predicate matches grants in, so a stub would be asserting on
 * a shape rather than on the decision. `test/export-surface.test.ts` keeps the duck-typed
 * cases, deliberately — they measure the two gates that fire BEFORE any capability is
 * read, and they must keep working for a caller holding no context at all.
 *
 * **CONTROL, executed 2026-09-16 with the SUBJECT REMOVED** — the `checkPathPermission`
 * branch deleted from `sdk.ts`, which is the state this port was in the day before:
 *
 *   # tests 4 / # pass 1 / # fail 3
 *
 * Three refusals red, `a covering capability authorizes` still green. That split is the
 * reading worth keeping: had the positive gone red too, the fixture would be broken
 * rather than the subject, and three reds would prove nothing (D15 sharpened — the
 * control is the absence of the subject).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CapabilityToken,
  Ecf,
  Entity,
  Envelope,
  Execute,
  GrantEntry,
  HandlerContext,
  Peer,
  PeerIdentity,
  ResourceTarget,
  Scope,
} from "entity-core-protocol-typescript";
import {
  ContentTypes,
  CONTENT_PATTERN,
  reassembleUnderCapability,
} from "@entity-core/extension-content";

const IDENTITY = PeerIdentity.fromSeed(new Uint8Array(32).fill(0x72));

/**
 * A capability token in the shape `checkPathPermission` walks.
 *
 * Self-signed through the peer's own `createRoot` rather than hand-assembled, because
 * `CapabilityToken`'s constructor parses `grants`, `granter`, `grantee` and `created_at`
 * and a hand-built map that omits any of them throws before the subject runs. It is never
 * dispatched: the predicate reads only `grants`, and the signature, chain, temporal bounds
 * and revocation are `verifyRequest`'s — which on the real path has already run before any
 * context exists.
 */
function capWith(operations: string[], handlers: string[], resources: string[]): CapabilityToken {
  return CapabilityToken.createRoot(
    IDENTITY,
    IDENTITY.identityHash,
    [
      new GrantEntry(
        new Scope(handlers, null),
        new Scope(resources, null),
        new Scope(operations, null),
        null,
        null,
        null,
      ),
    ],
    0n,
  ).token;
}

function context(
  peer: Peer,
  opts: { pattern?: string; operation?: string; capability: CapabilityToken | null },
): HandlerContext {
  const execute = Execute.build({
    requestId: "sdk-1",
    uri: `/${peer.localPeerId}/${CONTENT_PATTERN}`,
    operation: opts.operation ?? "get",
    params: Entity.create(ContentTypes.GetRequest, Ecf.map(["hashes", Ecf.array([])])),
    resource: new ResourceTarget([CONTENT_PATTERN], null),
  });
  return new HandlerContext({
    peer,
    execute,
    envelope: new Envelope(execute.entity, []),
    pattern: opts.pattern ?? CONTENT_PATTERN,
    suffix: "",
    callerCapability: opts.capability,
    handlerGrant: null,
    author: null,
    connection: null,
  });
}

function covering(): CapabilityToken {
  return capWith(["get"], [CONTENT_PATTERN], ["/peer1/system/content/docs"]);
}

/**
 * The target paths are written against the peer's OWN id, resolved at call time — the
 * predicate canonicalizes both the path and the grant's resource patterns in the local
 * peer's frame, so a literal `/peer1/...` would be a different path from the grant's on
 * every run and every refusal would pass for the wrong reason.
 */
function docs(peer: Peer): string {
  return `/${peer.localPeerId}/system/content/docs`;
}

function grantFor(peer: Peer, resources: string[], operations = ["get"], handlers = [CONTENT_PATTERN]) {
  return capWith(operations, handlers, resources);
}

test("§3.4: a covering capability authorizes", async () => {
  // THE POSITIVE CONTROL. Without it every refusal below is satisfied by a wrapper that
  // throws unconditionally, which is the cheapest way to pass a suite of denial tests
  // (D15). The blob is absent, so the expected ANSWER is a coded reassembly failure —
  // which is the authorization having been passed, not skipped.
  const peer = new Peer();
  try {
    const ctx = context(peer, { capability: grantFor(peer, [docs(peer)]) });
    const result = reassembleUnderCapability(ctx, docs(peer), new Uint8Array(33));
    assert.equal(result.ok, false);
    assert.equal(!result.ok && result.code, "blob_not_found");
  } finally {
    await peer.dispose();
  }
});

test("§3.4: a capability covering another path is refused", async () => {
  // The §3.4 escalation surface in one line: a consumer holding a real, verified,
  // non-root capability, reaching for bytes its grant does not cover.
  const peer = new Peer();
  try {
    const ctx = context(peer, { capability: grantFor(peer, [docs(peer)]) });
    assert.throws(
      () => reassembleUnderCapability(ctx, `/${peer.localPeerId}/system/content/secrets`, new Uint8Array(33)),
      /does not cover get on/,
    );
  } finally {
    await peer.dispose();
  }
});

test("§3.4: a capability for another operation is refused", async () => {
  const peer = new Peer();
  try {
    const ctx = context(peer, { operation: "ingest", capability: grantFor(peer, [docs(peer)]) });
    assert.throws(
      () => reassembleUnderCapability(ctx, docs(peer), new Uint8Array(33)),
      /does not cover ingest on/,
    );
  } finally {
    await peer.dispose();
  }
});

test("§3.4: a capability scoped to another handler is refused", async () => {
  const peer = new Peer();
  try {
    const ctx = context(peer, {
      capability: grantFor(peer, [docs(peer)], ["get"], ["system/tree"]),
    });
    assert.throws(
      () => reassembleUnderCapability(ctx, docs(peer), new Uint8Array(33)),
      /does not cover get on/,
    );
  } finally {
    await peer.dispose();
  }
});

test("§3.4: a context belonging to another handler is refused, with everything else covering", async () => {
  // Clause 1's residue, and the one case the pattern gate alone can produce. The
  // capability here COVERS everything asked — operation, handler scope and path all
  // match — so nothing but the `ctx.pattern` check can refuse it. The second assertion
  // is the discriminating half: the same capability under the right pattern is allowed
  // through to reassembly.
  const peer = new Peer();
  try {
    const broad = grantFor(peer, [`/${peer.localPeerId}/*`], ["get"], ["*"]);
    assert.throws(
      () =>
        reassembleUnderCapability(
          context(peer, { pattern: "system/files", capability: broad }),
          docs(peer),
          new Uint8Array(33),
        ),
      /requires a system\/content handler context/,
    );
    const allowed = reassembleUnderCapability(
      context(peer, { capability: broad }),
      docs(peer),
      new Uint8Array(33),
    );
    assert.equal(!allowed.ok && allowed.code, "blob_not_found", "control: only the pattern was wrong");
  } finally {
    await peer.dispose();
  }
});

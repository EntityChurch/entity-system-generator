/**
 * §5.1 recording and §3.2's self-guard, exercised through the REAL emit pathway.
 *
 * The recorder is registered on the peer's own `EmitBus` and driven by real `tree.put`
 * calls, never by calling `recordTransition` directly. That distinction is the whole
 * lesson of D13's Reach row: a body that works when you call it and is never reached by
 * dispatch is the failure this ecosystem has already shipped once. Here the equivalent
 * failure is a recorder that records correctly and is never invoked by the pathway.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { Ecf, Entity, Peer } from "entity-core-protocol-typescript";
import {
  configPath,
  historyConfig,
  HEAD_PREFIX,
  HistoryEvent,
  installHistory,
  resolveConfig,
} from "@entity-core/extension-history";

const TRACKED = "docs/report";

function payload(v: string): Entity {
  return Entity.create("system/validate/history-test", Ecf.map(["v", Ecf.text(v)]));
}

/** A peer with history installed and `*` configured — the composition's own posture. */
function rig(): { peer: Peer; install: ReturnType<typeof installHistory>; abs: (p: string) => string } {
  const peer = new Peer({ debugOpenGrants: true });
  const install = installHistory(peer);
  peer.tree.put(configPath(peer.localPeerId, "everything"), historyConfig({ pattern: "*" }));
  const abs = (p: string) => "/" + peer.localPeerId + "/" + p;
  return { peer, install, abs };
}

function headHashHex(peer: Peer, absTrackedPath: string): string | null {
  const h = peer.tree.getHash("/" + peer.localPeerId + "/" + HEAD_PREFIX + absTrackedPath);
  return h === undefined ? null : Buffer.from(h).toString("hex");
}

function transitionAt(peer: Peer, absTrackedPath: string): Entity {
  const headPath = "/" + peer.localPeerId + "/" + HEAD_PREFIX + absTrackedPath;
  const e = peer.tree.get(headPath);
  assert.ok(e !== undefined, `no head pointer at ${headPath}`);
  return e;
}

// ── §5.1 recording ──────────────────────────────────────────────────────────────

test("§5.1: a tracked write is recorded, with §2.1's `created` event", () => {
  const { peer, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));

  const t = transitionAt(peer, abs(TRACKED));
  assert.equal(t.type, "system/history/transition");
  assert.equal(Ecf.optText(t.data, "event"), HistoryEvent.Created);
  assert.equal(Ecf.optText(t.data, "path"), abs(TRACKED));
});

test("§2.1: the recorded event vocabulary is HISTORY's, not the core pathway's", () => {
  // The peer emits `modified`; §2.1's table says `updated`. This is the mapping, and it
  // is asserted on the SECOND write because the first is `created` in both vocabularies —
  // a test that only wrote once would pass with the mapping deleted.
  const { peer, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));
  peer.tree.put(abs(TRACKED), payload("v2"));

  const t = transitionAt(peer, abs(TRACKED));
  assert.equal(Ecf.optText(t.data, "event"), HistoryEvent.Updated);
  assert.notEqual(Ecf.optText(t.data, "event"), "modified");
});

test("§2.1: `created` has no previous_hash; `updated` carries the old one", () => {
  const { peer, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));
  const first = transitionAt(peer, abs(TRACKED));
  assert.equal(Ecf.optBytes(first.data, "previous_hash"), null);
  const v1Hash = Ecf.optBytes(first.data, "hash");
  assert.ok(v1Hash !== null);

  peer.tree.put(abs(TRACKED), payload("v2"));
  const second = transitionAt(peer, abs(TRACKED));
  assert.deepEqual(Ecf.optBytes(second.data, "previous_hash"), v1Hash);
});

test("§3.1: the chain links through `previous`, and the head advances", () => {
  const { peer, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));
  const firstHead = headHashHex(peer, abs(TRACKED));

  peer.tree.put(abs(TRACKED), payload("v2"));
  const secondHead = headHashHex(peer, abs(TRACKED));

  assert.notEqual(firstHead, secondHead, "the head pointer must advance");
  const second = transitionAt(peer, abs(TRACKED));
  const prev = Ecf.optBytes(second.data, "previous");
  assert.ok(prev !== null, "the second transition must link to the first");
  assert.equal(Buffer.from(prev).toString("hex"), firstHead);
});

test("§9.1 MUST: author, capability and timestamp are present on every transition", () => {
  const { peer, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));
  const t = transitionAt(peer, abs(TRACKED));

  assert.ok(Ecf.optBytes(t.data, "author") !== null);
  assert.ok(Ecf.optBytes(t.data, "capability") !== null);
  const ts = Ecf.optUint(t.data, "timestamp");
  assert.ok(ts !== null && ts > 0n);
});

test("the provenance of that author/capability is FALLBACK, and the module says so", () => {
  // THE MOST IMPORTANT ASSERTION IN THIS FILE. The test above passes on a presence check
  // and would keep passing if the values were meaningless — which today they are. The
  // peer's tree-change event carries no execution context (`EmitContext` is constructed
  // at zero sites), so `author` is the local peer and `capability` is our own grant on
  // EVERY write, including one that arrived from a remote caller.
  //
  // If this assertion ever fails because `fallbackContexts` is 0, the peer started
  // supplying a context and the four oracle `context_*` checks became meaningful. That is
  // the good failure, and it is the reason this is asserted rather than commented.
  const { peer, install, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));

  const stats = install.recorder.stats;
  // WAS `assert.equal(install.contextAvailable, false)` against a hardcoded constant —
  // an assertion about ANOTHER TEAM'S PEER that our own source supplied, which is why it
  // kept passing when keystone landed H8 on 2026-09-07. Now observed, and "not-observed"
  // rather than "no": this rig drives autonomous writes, so these events carried no
  // context. That is a fact about these events, not about the peer.
  assert.equal(install.contextAvailable(), "not-observed");
  assert.equal(stats.contextContexts, 0);
  assert.ok(stats.recorded > 0);
  // Every event that REACHED context construction fell back. The self-guarded ones return
  // before a context is built, so they are subtracted rather than compared — the first
  // version of this assertion equated `fallbackContexts` with `observed` and failed,
  // which is the test doing its job on the test.
  assert.equal(
    stats.fallbackContexts,
    stats.observed - stats.skippedSelfGuard,
    "every event that reached context construction lacked one (EXTENSION.toml [substrate.execution_context])",
  );
  assert.ok(stats.fallbackContexts > 0);
  assert.equal(install.recorder.recordedTransitions[0]?.provenance, "autonomous-fallback");
});

test("§5.1: caller_capability is omitted when it would equal capability", () => {
  // §5.1: recorded "only when it differs from capability". Under the fallback there is no
  // caller at all, so it must be absent — and `w6_caller_cap_absent` in the oracle checks
  // exactly this.
  const { peer, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));
  const t = transitionAt(peer, abs(TRACKED));
  assert.equal(Ecf.optBytes(t.data, "caller_capability"), null);
});

test("§2.1: `clock` is absent because CLOCK is not installed", () => {
  const { peer, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));
  const t = transitionAt(peer, abs(TRACKED));
  assert.equal(Ecf.field(t.data, "clock"), null);
});

// ── §3.2 the self-guard ─────────────────────────────────────────────────────────

test("§3.2: the head-pointer write does NOT recurse", () => {
  // Without the guard this is an unbounded loop: every head write is a tree write, which
  // emits, which records, which writes a head. The test is that it terminates AND that
  // the guard actually fired rather than the config failing to match.
  const { peer, install, abs } = rig();
  peer.tree.put(abs(TRACKED), payload("v1"));

  const stats = install.recorder.stats;
  assert.ok(stats.skippedSelfGuard > 0, "the guard must have fired on our own head write");
  // TWO, not one: the config write in `rig()` is itself a tracked write and §3.2 says it
  // SHOULD be recorded. Asserted as 2 because the first draft asserted 1, failed, and the
  // failure was the test's — the module was doing exactly what §3.2 asks.
  assert.equal(stats.recorded, 2, "the config write and the application write, both recorded");
  // The property that actually matters here is TERMINATION with a bounded head count:
  // one head pointer per tracked path, not a chain of heads recording heads.
  assert.equal(
    install.recorder.recordedTransitions.filter((r) => r.path === abs(TRACKED)).length,
    1,
    "the tracked path produced exactly one transition, and its head write produced none",
  );
});

test("§3.2: the guard covers `head`, NOT the whole history namespace", () => {
  // The easy wrong implementation guards `system/history/` and silently stops auditing
  // configuration changes. §3.2 says config writes "SHOULD be recorded as normal
  // transitions for audit purposes" — so the config write in `rig()` is itself recorded.
  const { peer, install } = rig();
  const cfg = configPath(peer.localPeerId, "everything");

  const recorded = install.recorder.recordedTransitions.map((t) => t.path);
  assert.ok(
    recorded.includes(cfg),
    `the config write at ${cfg} must be recorded; got ${JSON.stringify(recorded)}`,
  );
});

test("§2.2: a bare `*` config does NOT reach another peer's namespace", () => {
  // Written as the remote-guard test, and the failure corrected it into a better one.
  // `canonicalizePattern("*")` resolves to `/{local}/*` per core §5.4, so a remote path
  // matches no config and is never recorded. That is a real scoping property and the
  // reason §6.3's "match everything" example is narrower than it reads.
  const { peer, install } = rig();
  const remote = "z6MkfZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ";
  const remotePath = "/" + remote + "/project/readme";

  const before = install.recorder.stats.recorded;
  peer.tree.put(remotePath, payload("synced"));
  assert.equal(install.recorder.stats.recorded, before, "a bare `*` is local-only");
  assert.equal(resolveConfig(peer.tree, remotePath, peer.localPeerId).config, null);
});

test("§3.2: a REMOTE peer's history path IS trackable, and its head write is guarded", () => {
  // The §3.2 paragraph this exercises: "Remote peers' `system/history/` paths arriving via
  // sync MAY be tracked if a configuration pattern matches them. There is no recursion
  // risk: ... The local peer's resulting head pointer update is at
  // `/{local}/system/history/head/{remote}/system/history/...`, which is in the local
  // `system/history/head` namespace and therefore excluded by the check above."
  //
  // It needs a PEER-WILDCARD config, not `*` — see the test above.
  const peer = new Peer({ debugOpenGrants: true });
  const install = installHistory(peer);
  peer.tree.put(
    configPath(peer.localPeerId, "all-peers"),
    historyConfig({ pattern: "*/system/history/*" }),
  );

  const remote = "z6MkfZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ";
  const remoteHistoryPath = "/" + remote + "/system/history/head/whatever";

  const beforeGuard = install.recorder.stats.skippedSelfGuard;
  peer.tree.put(remoteHistoryPath, payload("synced"));
  const after = install.recorder.stats;

  // The remote write is tracked (not guarded — the guard is local-only)...
  const head = peer.tree.getHash(
    "/" + peer.localPeerId + "/" + HEAD_PREFIX + remoteHistoryPath,
  );
  assert.ok(head !== undefined, "a remote history path is trackable (§3.2)");
  // ...and the head pointer it produced, which lands in the LOCAL history namespace, is.
  assert.equal(
    after.skippedSelfGuard,
    beforeGuard + 1,
    "the resulting local head write must be excluded, or this recurses",
  );
});

// ── §2.2 / §6.2 configuration ───────────────────────────────────────────────────

test("§2.2: history is opt-in — an unconfigured peer records nothing", () => {
  const peer = new Peer({ debugOpenGrants: true });
  const install = installHistory(peer);
  peer.tree.put("/" + peer.localPeerId + "/" + TRACKED, payload("v1"));

  assert.equal(install.recorder.stats.recorded, 0);
  assert.ok(install.recorder.stats.skippedUnconfigured > 0);
});

test("§2.2: a disabled config records nothing, and decodes as disabled", () => {
  // The failure this guards: `enabled: false` encoded by an omit-empty rule would decode
  // as an ABSENT required field, `parseConfig` would skip the entity, and the path would
  // be UN-audited-by-accident rather than un-audited-by-instruction. Same outcome here,
  // opposite cause — so the assertion is on `resolveConfig` reporting it as a config that
  // was read and is disabled, not merely on nothing being recorded.
  const peer = new Peer({ debugOpenGrants: true });
  const install = installHistory(peer);
  peer.tree.put(
    configPath(peer.localPeerId, "off"),
    historyConfig({ pattern: "*", enabled: false }),
  );
  const abs = "/" + peer.localPeerId + "/" + TRACKED;
  peer.tree.put(abs, payload("v1"));

  const resolved = resolveConfig(peer.tree, abs, peer.localPeerId);
  assert.ok(resolved.config !== null, "the config must PARSE, not be skipped as malformed");
  assert.equal(resolved.config.enabled, false);
  assert.equal(resolved.skipped, 0, "no config was skipped as unreadable");
  assert.equal(install.recorder.stats.recorded, 0);
});

test("§5.1: an event type outside the config's list is not recorded", () => {
  const peer = new Peer({ debugOpenGrants: true });
  const install = installHistory(peer);
  peer.tree.put(
    configPath(peer.localPeerId, "creates-only"),
    historyConfig({ pattern: "*", events: [HistoryEvent.Created] }),
  );
  const abs = "/" + peer.localPeerId + "/" + TRACKED;

  peer.tree.put(abs, payload("v1"));
  const afterCreate = install.recorder.stats.recorded;
  peer.tree.put(abs, payload("v2"));
  const afterUpdate = install.recorder.stats.recorded;

  assert.equal(afterUpdate, afterCreate, "the `updated` event is not in the config's list");
});

test("§6.2: the most specific matching config wins over a general one", () => {
  const peer = new Peer({ debugOpenGrants: true });
  installHistory(peer);
  const abs = "/" + peer.localPeerId + "/" + TRACKED;

  peer.tree.put(configPath(peer.localPeerId, "everything"), historyConfig({ pattern: "*" }));
  peer.tree.put(
    configPath(peer.localPeerId, "docs"),
    historyConfig({ pattern: "docs/*", events: [HistoryEvent.Created] }),
  );

  const resolved = resolveConfig(peer.tree, abs, peer.localPeerId);
  assert.ok(resolved.config !== null);
  assert.equal(resolved.config.pattern, "docs/*", "the more literal pattern wins (§6.2 key 1)");
  assert.deepEqual(resolved.config.events, [HistoryEvent.Created]);
});

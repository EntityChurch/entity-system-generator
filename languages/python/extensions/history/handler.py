"""HISTORY §4 — the system history handler. ``query`` (§4.3.1) and ``rollback`` (§4.3.2).

**§4.2's dual capability model is where this port diverges most from `typescript`, and
the cause is a missing peer function rather than a language difference.**

§4.2 names core's ``check_path_permission`` (§6.3) for its second check. The `typescript`
peer exports it (``Permissions.checkPathPermission``). **This peer has no such function
at all** — ``entity_core.peer.capability`` exposes ``check_permission``, which takes an
EXECUTE entity and answers about the dispatch as a whole, and the grant-walking helpers
it would need (``_grants_of_token``, ``_matches_scope``) are leading-underscore.

So the second check is built here from the one public primitive that IS available,
``matches_pattern``, walking the caller token's grants directly. That is a
re-transcription of part of core §5.2's scope logic and it is the thing L18 warns about —
recorded in ``EXTENSION.toml [substrate.path_permission]`` rather than left to look like
a design choice.
"""

from __future__ import annotations

from typing import Any

from entity_core.peer.capability import (
    canonicalize,
    cap_resolve,
    check_permission,
    resolve_granter_peer_id,
)
from entity_core.peer.handlers import DispatchCtx, Outcome
from entity_core.peer.model import Entity
from entity_core.peer.wire import error_result

from .types import (
    DEFAULT_QUERY_LIMIT,
    HEAD_PREFIX,
    HISTORY_PATTERN,
    QUERY_PARAMS,
    QUERY_RESULT,
    ROLLBACK_PARAMS,
    ROLLBACK_RESULT,
)

#: A walk bound that is NOT in the spec. §2.3's `limit` is caller-supplied and unbounded
#: above; §4.3.1's loop walks until the chain ends. A caller asking for `limit: 2**53`
#: materialises the whole chain. Declared in EXTENSION.toml [assumptions].max_walk —
#: it changes an observable answer (`has_more` goes true earlier than a naive reading).
DEFAULT_MAX_WALK = 1000


def _err(status: int, code: str, message: str = "") -> Outcome:
    return Outcome(status, error_result(code, message))


def _resource_targets(exec_e: Entity) -> list[str] | None:
    resource = exec_e.field("resource")
    if not isinstance(resource, dict):
        return None
    targets = resource.get("targets")
    if not isinstance(targets, list) or not targets:
        return None
    return [str(t) for t in targets]


def _token_covers(
    peer, token: Entity, operation: str, path: str, handler_pattern: str, included
) -> bool:
    """§4.2 check 2, using the PEER'S OWN authorization function.

    **The first version of this hand-walked the token's grants** with the public
    ``matches_pattern``, because §4.2 names core's ``check_path_permission`` (§6.3) and
    this peer has no such function — ``entity_core.peer.capability`` exposes
    ``check_permission``, and the scope helpers it uses (``_grants_of_token``,
    ``_matches_scope``, ``_covered``, ``_canon``) are all leading-underscore.

    That version denied every request the oracle made and 23 of 34 checks failed on it.
    It was also the wrong shape regardless of the bug: re-transcribing part of core §5.2
    inside an extension is exactly what L18 and D12 warn about, and a second reading of a
    shared authorization algorithm is a security divergence waiting to be found by
    someone else.

    **So it reuses instead.** ``check_permission`` takes an EXECUTE entity and answers
    about operation + uri + resource against a token for a handler pattern — which is the
    whole of §4.2's second check if the EXECUTE describes the TARGET access rather than
    the history call. So we synthesise exactly that: operation ``get``/``put``, uri and
    resource naming the target path, handler pattern ``system/tree``.

    The synthesised entity is never signed, never dispatched and never leaves this
    function; it is an argument shaped the way the peer's own predicate expects. L7 — run
    what exists before building an instrument.
    """
    probe = Entity.make(
        "system/execute",
        {
            "uri": path,
            "operation": operation,
            "resource": {"targets": [path]},
        },
    )
    # `included` is threaded from the DispatchCtx rather than defaulted: `cap_resolve`
    # looks in the request's included map BEFORE the store, and a delegated caller
    # capability's parent chain rides in the envelope, not in our tree. Passing `None`
    # here raises on the first bytes lookup — the peer resolves included-first by design.
    granter = resolve_granter_peer_id(cap_resolve(included, peer.store), token) or peer.local_peer
    return check_permission(peer.local_peer, granter, probe, token, handler_pattern)


class HistoryHandler:
    """The §4.1 handler. Installed by :func:`entity_history.install_history`."""

    #: §4.1 / §9.3, in the mapped §3.7 form.
    OPERATIONS = ("query", "rollback")

    def __init__(self, peer, max_walk: int = DEFAULT_MAX_WALK) -> None:
        #: Registration-time capture — `python`'s DispatchCtx carries no peer (measured).
        self.peer = peer
        self.max_walk = max_walk

    # ── dispatch ─────────────────────────────────────────────────────────────

    def handle_op(self, op: str, ctx: DispatchCtx) -> Outcome:
        # §4.3.1/§4.3.2's EXECUTE examples both carry a `resource`, and
        # GUIDE-EXTENSION-DEVELOPMENT §4.1 makes a resource-less directly-callable op a
        # `400 path_required`. In [error_surface].unresolved: no spec code set defines it.
        if _resource_targets(ctx.exec) is None:
            return _err(
                400,
                "path_required",
                f"{HISTORY_PATTERN}:{op} requires a resource naming the handler path (§4.3)",
            )
        if op == "query":
            return self._query(ctx)
        if op == "rollback":
            return self._rollback(ctx)
        return _err(501, "unsupported_operation", op)

    # ── §4.2 the dual check ──────────────────────────────────────────────────

    def _check_target_access(self, ctx: DispatchCtx, op: str, target_path: str) -> Outcome | None:
        """``None`` on ALLOW, else the error to return.

        Check 1 ("can caller use the history handler?") is the DISPATCHER'S and is already
        done — a DispatchCtx exists only because it returned ALLOW. Re-running it here
        would re-derive an answer we have and would deny an in-process caller that
        legitimately has no token.

        Check 2 is ours, and nothing else performs it: the target path lives in ``params``,
        not in ``resource``, so the dispatcher's resource scoping never sees it.
        """
        target_op = "put" if op == "rollback" else "get"
        if ctx.caller_cap is None:
            # §7.1's purpose is that history must not widen what a caller can reach.
            # "No token" is not evidence of authority, so this denies rather than allows.
            return _err(
                403,
                "capability_denied",
                f"{op} requires a capability covering {target_op} on {target_path} (§4.2)",
            )
        # §4.2 passes "system/tree" as the handler pattern, NOT "system/history" — the
        # caller must hold authority over the target as a TREE path, exactly as if they
        # were reading or writing it directly. That is the crux of the dual model.
        if not _token_covers(
            self.peer, ctx.caller_cap, target_op, target_path, "system/tree", ctx.included
        ):
            return _err(
                403,
                "capability_denied",
                f"capability does not cover {target_op} on {target_path} (§4.2 dual check)",
            )
        return None

    def _head_path(self, canonical_target: str) -> str:
        return "/" + self.peer.local_peer + "/" + HEAD_PREFIX + canonical_target

    # ── §4.3.1 query ─────────────────────────────────────────────────────────

    def _query(self, ctx: DispatchCtx) -> Outcome:
        # `sub_entity`, not `field` + an `included` lookup. The params ride INSIDE the
        # EXECUTE entity on this peer, and the first draft of this reached for
        # `ctx.included.get_by_hash(ctx.exec.bytes_("params"))` — which returns None,
        # so every query answered `400 unexpected_params` and 23 of the 34 oracle checks
        # failed on one root cause. Found by running the category, not by reading it.
        params_e = ctx.exec.sub_entity("params")
        if params_e is None:
            return _err(400, "unexpected_params", "query expects a system/history/query-params entity")
        raw_path = params_e.text("path")
        if raw_path is None:
            return _err(400, "unexpected_params", "query expects {path: system/tree/path} (§2.3)")

        # §2.3: the handler canonicalizes short-form input before processing.
        path = canonicalize(self.peer.local_peer, raw_path) or raw_path

        denied = self._check_target_access(ctx, "query", path)
        if denied is not None:
            return denied

        limit = params_e.uint("limit") or DEFAULT_QUERY_LIMIT
        before = params_e.uint("before")
        since = params_e.bytes_("since")
        raw_events = params_e.field("events")
        events = [str(e) for e in raw_events] if isinstance(raw_events, list) else None

        head_hex = self.peer.store.hash_at(self._head_path(path))
        if not head_hex:
            # §4.3.1: no history -> empty result, NOT a 404.
            return Outcome(
                200,
                Entity.make(QUERY_RESULT, {"path": path, "transitions": [], "has_more": False}),
            )

        collected: list[dict] = []
        current: bytes | None = bytes.fromhex(head_hex)
        walked = 0
        while current is not None and len(collected) < limit and walked < self.max_walk:
            t = self.peer.store.get_by_hash(current)
            if t is None:
                break  # §4.3.1: "if transition is null: break"
            walked += 1
            # §4.3.1's filter ORDER, transcribed. `since` BREAKS (an exclusive lower bound
            # on the walk); `before` and `events` CONTINUE (skip one and keep walking).
            # Collapsing the three into one predicate changes the result set.
            if since is not None and current == since:
                break
            prev = t.bytes_("previous")
            ts = t.uint("timestamp")
            if before is not None and ts is not None and ts >= before:
                current = prev
                continue
            if events is not None and (t.text("event") or "") not in events:
                current = prev
                continue
            # The oracle decodes `transitions` as an array of the transition DATA MAPS
            # (`[]TransitionData`), not of entities and not of hashes. See the
            # `typescript` handler for the full reasoning; a hash array decodes as
            # nothing and an entity array decodes as all-zero fields, which would pass
            # `transition_recorded` and fail four checks later.
            collected.append(t.data)
            current = prev

        return Outcome(
            200,
            Entity.make(
                QUERY_RESULT,
                {
                    "path": path,
                    "head": bytes.fromhex(head_hex),
                    "transitions": collected,
                    "has_more": current is not None,
                },
            ),
        )

    # ── §4.3.2 rollback ──────────────────────────────────────────────────────

    def _rollback(self, ctx: DispatchCtx) -> Outcome:
        params_e = ctx.exec.sub_entity("params")
        if params_e is None:
            return _err(400, "unexpected_params", "rollback expects a rollback-params entity")
        raw_path = params_e.text("path")
        target_hash = params_e.bytes_("target_hash")
        if raw_path is None or target_hash is None:
            return _err(400, "unexpected_params", "rollback expects {path, target_hash} (§4.3.2)")

        path = canonicalize(self.peer.local_peer, raw_path) or raw_path

        denied = self._check_target_access(ctx, "rollback", path)
        if denied is not None:
            return denied

        # §7.5 History Exfiltration Prevention — THE security check of this operation.
        # Without it, `rollback` is an unrestricted `put` that bypasses every type and
        # validation path a real put has.
        if not self._is_in_history(path, target_hash):
            return _err(404, "not_in_history", "Target hash not found in history for this path")

        ent = self.peer.store.get_by_hash(target_hash)
        if ent is None:
            # In history, but GC'd from the store (§3.3). `500 storage_error` — core
            # §3.3's 500 row names it "a content-store or tree bind/read failed". NOT a
            # 404 (which would be indistinguishable from `not_in_history`, and false) and
            # NOT CONTENT's `blob_not_found` (another extension's code; §8.3 makes HISTORY
            # installable without CONTENT).
            return _err(
                500,
                "storage_error",
                "Target hash is in this path's history but the entity is no longer in the content store (§3.3 GC)",
            )

        # §4.3.2: "This goes through normal put, which will itself be recorded in
        # history." So this write fires the emit pathway and our own recorder observes
        # it — the rollback appears in the chain as an ordinary `updated`.
        self.peer.store.bind(path, ent)

        return Outcome(200, Entity.make(ROLLBACK_RESULT, {"path": path, "restored": target_hash}))

    def _is_in_history(self, path: str, target_hash: bytes) -> bool:
        """§4.3.2 ``is_in_history``, including the disjunct that is easy to drop.

        It matches ``hash`` **OR** ``previous_hash``. Dropping the second still passes a
        test that rolls back to a value the path once held; it fails only for the FIRST
        entity ever at the path, which is the oldest reachable state and the one an undo
        most wants.
        """
        head_hex = self.peer.store.hash_at(self._head_path(path))
        current: bytes | None = bytes.fromhex(head_hex) if head_hex else None
        walked = 0
        while current is not None and walked < self.max_walk:
            t = self.peer.store.get_by_hash(current)
            if t is None:
                return False
            walked += 1
            if t.bytes_("hash") == target_hash or t.bytes_("previous_hash") == target_hash:
                return True
            current = t.bytes_("previous")
        return False

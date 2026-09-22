"""``entity_content`` — CONTENT v3.6 for the `python` peer.

**The public surface.** What is not exported here is not part of it — and one omission is
a MUST rather than a taste: ``reassemble_content`` lives in ``_internal`` and is absent
from ``__all__`` (§3.4). ``test/test_export_surface.py`` asserts the omission, because a
MUST with no check is a sentence.

**Python cannot enforce that boundary and this module does not pretend otherwise.** In
the `typescript` port, node's ``exports`` map refuses a deep import into ``internal/``
and the test asserts on the resolver's refusal. Here the boundary is convention:
underscore, ``__all__``, and a test. Recorded as weaker rather than claimed as equal —
the same asymmetry D13 already records for this peer's own ``Outcome`` / ``DispatchCtx``.

Install model: **`sdk-native`** — in-process, against a live ``Peer``. Forced, not
chosen: the peer's ``system/handler:register`` wire op refuses ``system/*`` patterns
(core §6.2), and CONTENT's pattern IS ``system/content``.
"""

from __future__ import annotations

from dataclasses import dataclass

from entity_core.peer.model import Entity

from .chunking import (
    Blob,
    CdcParams,
    cdc_boundaries,
    cdc_params,
    create_blob_cdc,
    create_blob_fixed,
    gear_table,
    store_blob,
)
from .handler import ContentHandler
from .sdk import (
    ClosureVerdict,
    at_peer,
    bind_at_peer,
    create_descriptor,
    descriptor_matches_anchor,
    descriptor_path,
    ensure_closure,
    hash_hex_with_format,
    reassemble_under_capability,
)
from .types import (
    ALL_TYPES,
    BLOB,
    CHUNK,
    CHUNKING_FASTCDC_NC2,
    CHUNKING_FIXED,
    CONTENT_PATTERN,
    CONTENT_RESPONSE,
    DEFAULT_CHUNK_SIZE,
    DESCRIPTOR,
    GET_BATCH_SIZE,
    GET_REQUEST,
    INGEST_REQUEST,
    INGEST_RESULT,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    content_type_entities,
    publish_content_types,
)


@dataclass(frozen=True)
class ContentInstallation:
    """What :func:`install_content` actually wrote, so a caller can assert on it."""

    pattern: str
    interface_path: str
    type_paths: tuple[str, ...]
    handler_paths: tuple[str, ...]


#: §6.1's operations, in the §3.7 mapped form. Declared here because on this peer the
#: MODULE writes the interface entity — there is no registration API to hand it to.
_OPERATION_SPECS = {
    "get": {"input_type": GET_REQUEST, "output_type": CONTENT_RESPONSE},
    "ingest": {"input_type": INGEST_REQUEST, "output_type": INGEST_RESULT},
}


def install_content(peer, namespace: str = CONTENT_PATTERN) -> ContentInstallation:
    """Install CONTENT onto a live peer.

    **This function is the retarget.** The `typescript` port calls
    ``peer.registerHandler(handler)`` and the peer performs the §11.6.1 writes. **This
    peer has no registration surface at all** — no ``registerHandler``, no
    ``register_handler`` — so every write below is ours, through public names only:
    ``peer.store.bind``, ``peer.mint_token``, ``peer.identity.identity_hash``,
    ``peer.local_peer``, ``peer.handlers``.

    Measured, not read: `gates/host-seam/probe-seam.py` drove all four §11.6.1 writes by
    hand and then reached the installed body with a real EXECUTE. That probe is the
    reason this function's shape is what it is.

    **The order matters and is not arbitrary.** ``peer.handlers[pattern]`` is set LAST.
    The peer resolves a handler by walking the tree for a ``system/handler`` entity and
    only then consults the dict (measured: probe control C answers ``501`` when the tree
    is bound and the dict is not; control D answers ``404`` when the dict is set and the
    tree is not). Setting the dict first would open a window in which the pattern
    resolves to a body whose type entities are not yet published.
    """
    local = peer.local_peer

    def absolute(rel: str) -> str:
        return "/" + local + "/" + rel

    interface_rel = "system/handler/" + CONTENT_PATTERN
    handler_paths: list[str] = []

    # (1) The §11.6.1 handler manifest at the pattern path. This is what the peer's
    #     `_resolve_handler` walks the tree to find; without it the pattern 404s no
    #     matter what the dict holds.
    path = absolute(CONTENT_PATTERN)
    peer.store.bind(path, Entity.make("system/handler", {"interface": interface_rel}))
    handler_paths.append(path)

    # (2) The handler interface entity (discovery index) — §6.1's manifest, complete,
    #     with the §3.7 operation specs. On `typescript` this is `registerHandler`'s job
    #     and it published operation NAMES only until keystone 2026-09-06; here it was
    #     always ours, so this port never carried that workaround.
    interface_path = absolute(interface_rel)
    peer.store.bind(
        interface_path,
        Entity.make(
            "system/handler/interface",
            {
                "pattern": CONTENT_PATTERN,
                "name": "content",
                "operations": _OPERATION_SPECS,
            },
        ),
    )
    handler_paths.append(interface_path)

    # (3)+(4) Self-issued signed handler grant + its signature at the §3.5 invariant
    #         pointer, so dispatch-time grant validation can find and verify it.
    token, signature = peer.mint_token(peer.identity.identity_hash, [], None)
    grant_path = absolute("system/capability/grants/" + CONTENT_PATTERN)
    peer.store.bind(grant_path, token)
    handler_paths.append(grant_path)
    sig_path = absolute("system/signature/" + token.hash.hex())
    peer.store.bind(sig_path, signature)
    handler_paths.append(sig_path)

    # (5) The type entities. Neither peer's registration surface writes these, and the
    #     oracle's `type_*` checks fail all three §11.1 types unless the module does.
    type_paths = publish_content_types(peer)

    # (6) LAST: the executable body, into the container dispatch consults.
    peer.handlers[CONTENT_PATTERN] = ContentHandler(peer, namespace=namespace)

    return ContentInstallation(
        pattern=CONTENT_PATTERN,
        interface_path=interface_path,
        type_paths=tuple(type_paths),
        handler_paths=tuple(handler_paths),
    )


__all__ = [
    # install
    "ContentInstallation",
    "install_content",
    "ContentHandler",
    # types
    "ALL_TYPES",
    "BLOB",
    "CHUNK",
    "DESCRIPTOR",
    "GET_REQUEST",
    "CONTENT_RESPONSE",
    "INGEST_REQUEST",
    "INGEST_RESULT",
    "CONTENT_PATTERN",
    "CHUNKING_FIXED",
    "CHUNKING_FASTCDC_NC2",
    "DEFAULT_CHUNK_SIZE",
    "MIN_CHUNK_SIZE",
    "MAX_CHUNK_SIZE",
    "GET_BATCH_SIZE",
    "content_type_entities",
    "publish_content_types",
    # chunking
    "Blob",
    "CdcParams",
    "cdc_boundaries",
    "cdc_params",
    "create_blob_cdc",
    "create_blob_fixed",
    "gear_table",
    "store_blob",
    # sdk
    "ClosureVerdict",
    "at_peer",
    "bind_at_peer",
    "create_descriptor",
    "descriptor_matches_anchor",
    "descriptor_path",
    "ensure_closure",
    "hash_hex_with_format",
    "reassemble_under_capability",
]

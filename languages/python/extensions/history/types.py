"""HISTORY — the six owned entity types (§9.2, defined at §2.1–§2.4 and §4.3.2).

Same retarget cost CONTENT paid, and the same reason it is paid: `python`'s type-def
builders (``_type_def``, ``_fref``, ``_opt``, ``_farray`` in ``entity_core.peer.typedefs``)
are all leading-underscore, and an underscore is that peer's statement about its own
boundary. So these field maps are hand-built.

**The exposure is smaller here than it was for CONTENT, and that is worth naming.** A
wrong field map in CONTENT changes a blob's entity hash and silently breaks dedup with
every other implementation. A wrong field map here changes a *type entity's* hash, which
the oracle's ``type_*`` checks compare directly (`history.go`, six of them) — so the
failure is loud on the first run rather than silent forever. The two extensions sit on
opposite sides of that line and the difference is the type's role, not the language's.
"""

from __future__ import annotations

from typing import Any

from entity_core.peer.model import Entity

#: Type-path constants. One home for every literal the module binds or emits.
TRANSITION = "system/history/transition"
CONFIG = "system/history/config"
QUERY_PARAMS = "system/history/query-params"
QUERY_RESULT = "system/history/query-result"
ROLLBACK_PARAMS = "system/history/rollback-params"
ROLLBACK_RESULT = "system/history/rollback-result"

ALL_TYPES = (
    TRANSITION,
    CONFIG,
    QUERY_PARAMS,
    QUERY_RESULT,
    ROLLBACK_PARAMS,
    ROLLBACK_RESULT,
)

#: The handler pattern (§4.1).
HISTORY_PATTERN = "system/history"

#: §3.1 head-pointer prefix — and §3.2's self-guard subject. The SAME string, deliberately:
#: the guard targets what the engine writes, which is exactly this prefix.
HEAD_PREFIX = "system/history/head"

#: §6.1 — where configurations live. NOT self-guarded; §3.2 says config writes SHOULD be
#: recorded as normal transitions for audit purposes.
CONFIG_PREFIX = "system/history/config"

#: §2.1's event vocabulary. NOT the core pathway's — see :func:`from_core_event_type`.
EVENT_CREATED = "created"
EVENT_UPDATED = "updated"
EVENT_DELETED = "deleted"
EVENT_ACCESSED = "accessed"

#: §2.2 "Default events". `accessed` is opt-in and unreachable from an emit consumer
#: (§5.2 puts read audit inside the tree handler's `get`) — see EXTENSION.toml
#: [substrate.accessed_event].
DEFAULT_EVENTS = (EVENT_CREATED, EVENT_UPDATED, EVENT_DELETED)

#: §2.3 — "Maximum transitions to return. Default: 50".
DEFAULT_QUERY_LIMIT = 50


def from_core_event_type(core_event_type: str) -> str | None:
    """Map a core tree-change ``event_type`` onto §2.1's vocabulary.

    The only difference is ``modified`` -> ``updated``. ``None`` for anything else is
    deliberate: an unrecognised core event is never recorded as a nearest neighbour,
    because the event string is a field of a content-addressed entity and a wrong value
    there is a wrong hash forever.
    """
    if core_event_type == "created":
        return EVENT_CREATED
    if core_event_type == "modified":
        return EVENT_UPDATED
    if core_event_type == "deleted":
        return EVENT_DELETED
    return None


# ── field-spec builders (omit-empty; the ECF §1.3 absent-key convention) ──────


def _ref(type_name: str) -> dict[str, Any]:
    return {"type_ref": type_name}


def _opt(spec: dict[str, Any]) -> dict[str, Any]:
    out = dict(spec)
    out["optional"] = True
    return out


def _array(element: dict[str, Any]) -> dict[str, Any]:
    return {"array_of": element}


def _type_def(name: str, fields: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name}
    if fields:
        out["fields"] = {fname: fspec for fname, fspec in fields}
    return out


def history_type_defs() -> list[tuple[str, dict[str, Any]]]:
    """The six definitions, in §9.2's listed order.

    Kept field-for-field in step with ``../../typescript/extensions/history/types.ts``.
    `tools/sdk-parity.py` compares the exported NAMES across ports; nothing compares these
    field maps except the oracle's six ``type_*`` checks, which is why they are the gate
    this file is written against.
    """
    return [
        # §2.1 — fourteen fields. `author` and `capability` are the two §9.1 MUSTs and the
        # two the peer supplies no data for; see EXTENSION.toml [substrate.execution_context].
        (
            TRANSITION,
            _type_def(
                TRANSITION,
                [
                    ("path", _ref("system/tree/path")),
                    ("event", _ref("primitive/string")),
                    ("hash", _opt(_ref("system/hash"))),
                    ("previous_hash", _opt(_ref("system/hash"))),
                    ("author", _ref("system/hash")),
                    ("capability", _ref("system/hash")),
                    ("caller_capability", _opt(_ref("system/hash"))),
                    ("handler", _ref("system/tree/path")),
                    ("operation", _ref("primitive/string")),
                    ("timestamp", _ref("primitive/uint")),
                    ("clock", _opt(_ref("system/clock/state"))),
                    ("chain_id", _opt(_ref("primitive/string"))),
                    ("parent_chain_id", _opt(_ref("primitive/string"))),
                    ("previous", _opt(_ref("system/hash"))),
                ],
            ),
        ),
        # §2.2
        (
            CONFIG,
            _type_def(
                CONFIG,
                [
                    ("pattern", _ref("system/tree/path")),
                    ("enabled", _ref("primitive/bool")),
                    ("events", _opt(_array(_ref("primitive/string")))),
                    ("max_depth", _opt(_ref("primitive/uint"))),
                ],
            ),
        ),
        # §2.3
        (
            QUERY_PARAMS,
            _type_def(
                QUERY_PARAMS,
                [
                    ("path", _ref("system/tree/path")),
                    ("limit", _opt(_ref("primitive/uint"))),
                    ("since", _opt(_ref("system/hash"))),
                    ("before", _opt(_ref("primitive/uint"))),
                    ("events", _opt(_array(_ref("primitive/string")))),
                ],
            ),
        ),
        # §2.4
        (
            QUERY_RESULT,
            _type_def(
                QUERY_RESULT,
                [
                    ("path", _ref("system/tree/path")),
                    ("head", _opt(_ref("system/hash"))),
                    ("transitions", _array(_ref(TRANSITION))),
                    ("has_more", _ref("primitive/bool")),
                ],
            ),
        ),
        # §4.3.2
        (
            ROLLBACK_PARAMS,
            _type_def(
                ROLLBACK_PARAMS,
                [
                    ("path", _ref("system/tree/path")),
                    ("target_hash", _ref("system/hash")),
                ],
            ),
        ),
        (
            ROLLBACK_RESULT,
            _type_def(
                ROLLBACK_RESULT,
                [
                    ("path", _ref("system/tree/path")),
                    ("restored", _ref("system/hash")),
                ],
            ),
        ),
    ]


def history_type_entities() -> list[tuple[str, Entity]]:
    """``(type_name, system/type entity)`` for each of the six."""
    return [(name, Entity.make("system/type", data)) for name, data in history_type_defs()]


def publish_history_types(peer) -> list[str]:
    """Bind the type entities at ``system/type/{name}``.

    I1 (owned-namespace containment) holds structurally: every path is ``system/type/``
    plus a name from :data:`ALL_TYPES`, and ``system/type/*`` is the core's shared type
    index every extension writes into by design.
    """
    written: list[str] = []
    for name, ent in history_type_entities():
        path = "/" + peer.local_peer + "/system/type/" + name
        peer.store.bind(path, ent)
        written.append(path)
    return written


def history_entity(entity_type: str, data: dict) -> Entity:
    """Build one of our own entities without reaching for ``Entity.make`` at each site.

    Present in both ports because `tools/sdk-parity.py` compares the union: a helper that
    exists in one port and not the other is drift even when it is trivial, and the class
    of difference this gate exists to catch is exactly the trivial one nobody decided.
    """
    return Entity.make(entity_type, data)

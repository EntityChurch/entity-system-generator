"""CONTENT — the seven owned entity types (§2.1, §2.2, §2.4, §6.2, §6.3).

**This is the first place the retarget bites, and it is worth naming precisely.**

The `typescript` port renders its type entities through the PEER'S OWN ``TypeDef`` /
``FSpec`` builder, deliberately: the blob and chunk hashes are the deduplication
identity (§2.1), and §3.6.5 names "two impls disagreeing on the entity hash for the same
tuple" as a silent dedup-breaking failure, so reusing the peer's encoder removes one way
to disagree.

**`python` has no such builder to reuse.** Its equivalents — ``_type_def``, ``_fref``,
``_opt``, ``_farray`` in ``entity_core.peer.typedefs`` — are all leading-underscore, and
the one public entry, ``core_type_entities()``, returns the §9.5 core floor and nothing
else. Python enforces nothing, so we *could* import them; we do not, because
`AGENTS-STANDARD` makes a sibling's private surface read-only context and an
underscore is that peer's statement about its own boundary.

So the field maps below are hand-built. That is a real per-language cost and it lands on
exactly the surface where a mistake is silent: nothing in this module fails if a field
map is subtly wrong — the entity simply hashes differently from every other
implementation's, and dedup stops working for that type with no error anywhere.

**What catches it is not in this file.** It is `validate-peer`'s
``type_system.type_system_content_{blob,chunk,descriptor}_match``, which renders the
same three types from `entity-core-go`'s own independent transcription and compares
content hashes. Those checks are the reason this port can be hand-built at all.
"""

from __future__ import annotations

from typing import Any

from entity_core.peer.model import Entity

#: Type-path constants. One home for every literal the module binds or emits.
BLOB = "system/content/blob"
CHUNK = "system/content/chunk"
DESCRIPTOR = "system/content/descriptor"
GET_REQUEST = "system/content/get-request"
CONTENT_RESPONSE = "system/content/content-response"
INGEST_REQUEST = "system/content/ingest-request"
INGEST_RESULT = "system/content/ingest-result"

ALL_TYPES = (
    BLOB,
    CHUNK,
    DESCRIPTOR,
    GET_REQUEST,
    CONTENT_RESPONSE,
    INGEST_REQUEST,
    INGEST_RESULT,
)

#: The handler pattern (§6.1). Everything the module binds derives from this.
CONTENT_PATTERN = "system/content"

#: §10.1. v3.6 reconciled every site to 1 MiB; the v3.5 4 MiB reading is dead.
DEFAULT_CHUNK_SIZE = 1_048_576
MIN_CHUNK_SIZE = 65_536
MAX_CHUNK_SIZE = 8_388_608

#: §10.2 — the sender-side batching window, hashes per get request (§7.1).
GET_BATCH_SIZE = 16

#: §2.1 standardized `chunking` configuration identifiers.
CHUNKING_FIXED = 0
CHUNKING_FASTCDC_NC2 = 1


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
    """Render a ``system/type`` data map. Omit-empty: a type with no fields carries no
    ``fields`` key at all, which is what makes the canonical encoding stable regardless
    of declaration order (the codec re-sorts map keys length-then-lex)."""
    out: dict[str, Any] = {"name": name}
    if fields:
        out["fields"] = {fname: fspec for fname, fspec in fields}
    return out


def content_type_defs() -> list[tuple[str, dict[str, Any]]]:
    """The seven definitions, in the order §11.1 ranks them: the two MUSTs first.

    Field order inside a definition does NOT affect the rendered bytes, but it is kept in
    spec order so a reader can diff this against §2.1 / §2.4 / §6.2 / §6.3 line by line —
    and against ``../typescript/types.ts``, which is the same list in the other language.
    """
    return [
        # §2.1 — the chunk-list manifest. All four fields structural; no metadata, ever
        # (§2.3: an optional `content_type` here would split the dedup identity).
        (
            BLOB,
            _type_def(
                BLOB,
                [
                    ("total_size", _ref("primitive/uint")),
                    ("chunk_size", _ref("primitive/uint")),
                    ("chunking", _ref("primitive/uint")),
                    ("chunks", _array(_ref("system/hash"))),
                ],
            ),
        ),
        # §2.2 — one field, and the absence of the others is the point: no sequence
        # number, no parent ref, so identical bytes hash identically across blobs.
        (CHUNK, _type_def(CHUNK, [("payload", _ref("primitive/bytes"))])),
        # §2.4 — a consumption-format DECLARATION, not an attestation. §2.4's presence
        # rule (at least one of media_type / type_ref) is a validity constraint the type
        # system cannot express, so it is enforced in `sdk.py` where the descriptor is
        # built, not here.
        (
            DESCRIPTOR,
            _type_def(
                DESCRIPTOR,
                [
                    ("content", _ref("system/hash")),
                    ("media_type", _opt(_ref("primitive/string"))),
                    ("type_ref", _opt(_ref("system/hash"))),
                    ("name", _opt(_ref("primitive/string"))),
                    ("metadata", _opt(_ref("primitive/any"))),
                ],
            ),
        ),
        # §6.2 request/response.
        (GET_REQUEST, _type_def(GET_REQUEST, [("hashes", _array(_ref("system/hash")))])),
        # §6.2 + Amendment 2. `found` / `missing` are ARRAYS, not counters — the F4
        # cross-impl audit landing, and the one wire-shape mistake this response has
        # already made once. `pending` is the OPTIONAL sync-state sidecar; the field is
        # declared because the type is the wire contract, and separately not emitted.
        (
            CONTENT_RESPONSE,
            _type_def(
                CONTENT_RESPONSE,
                [
                    ("found", _array(_ref("system/hash"))),
                    ("missing", _array(_ref("system/hash"))),
                    ("pending", _opt(_array(_ref("system/hash")))),
                ],
            ),
        ),
        # §6.3 — exactly one of envelope / entity. Both optional in the type; the
        # exclusivity is a handler-level 400, per the §6.3 algorithm.
        (
            INGEST_REQUEST,
            _type_def(
                INGEST_REQUEST,
                [
                    ("envelope", _opt(_ref("system/envelope"))),
                    ("entity", _opt(_ref("core/entity"))),
                ],
            ),
        ),
        # §6.3 + §11.1 MUST: `root` is present in envelope mode and absent in entity
        # mode, which is exactly what `optional` encodes under the §1.3 absent-key rule.
        (
            INGEST_RESULT,
            _type_def(
                INGEST_RESULT,
                [
                    ("root", _opt(_ref("core/entity"))),
                    ("root_hash", _ref("system/hash")),
                    ("ingested_count", _ref("primitive/uint")),
                ],
            ),
        ),
    ]


def content_type_entities() -> list[tuple[str, Entity]]:
    """Materialize each definition as a ``system/type`` entity."""
    return [(name, Entity.make("system/type", data)) for name, data in content_type_defs()]


def publish_content_types(peer) -> list[str]:
    """Bind the type entities into the peer's tree at ``system/type/{name}``.

    I1 (owned-namespace containment) holds structurally: every path is ``system/type/``
    plus a name from :data:`ALL_TYPES`, and ``system/type/*`` is the core's published type
    index that every extension writes into by design (`GUIDE-EXTENSION-DEVELOPMENT` §4.3
    — a type name inside our owned prefix is ours; the index it is filed under is shared).
    """
    written: list[str] = []
    for name, entity in content_type_entities():
        path = "/" + peer.local_peer + "/system/type/" + name
        peer.store.bind(path, entity)
        written.append(path)
    return written

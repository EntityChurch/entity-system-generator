# spec-data snapshot — `history-v1.7`

**Immutable.** Operators never edit a snapshot. A defect in a snapshotted spec is routed upstream and
lands as a **new directory**, never as a local patch.

**Stamped:** 2026-09-06, from `entity-system-architecture` @ `ff67e33a8e0059a8f5b301c63977a59d3543dfdb`.
*(An internal SHA. This file is not a publication surface — `docs/status/` rules apply.)*

| File | sha256 | Version |
|---|---|---|
| `EXTENSION-HISTORY.md` | `5980bdc96d4818edbc43dd73a1152292e306f126e62d5e4d007ca48bd5fa850b` | 1.7 |
| `SYSTEM-COMPOSITION.md` | `084faf207da6ebb9d7e57fd05bf31a14228e1d23c821d7e4675ff6a971166627` | — (§2.2 consumer ordering, §1.4/§1.5 execution context) |
| `GUIDE-EXTENSION-DEVELOPMENT.md` | `4bbe1521ee89fd9eefc06e8f958f6f28f6d38d4f6c0254f813a00ca106b77dee` | — (§4.1 `path_required`, §9 grade) |

Verify:

```
sha256sum -c <<'EOF'
5980bdc96d4818edbc43dd73a1152292e306f126e62d5e4d007ca48bd5fa850b  EXTENSION-HISTORY.md
084faf207da6ebb9d7e57fd05bf31a14228e1d23c821d7e4675ff6a971166627  SYSTEM-COMPOSITION.md
4bbe1521ee89fd9eefc06e8f958f6f28f6d38d4f6c0254f813a00ca106b77dee  GUIDE-EXTENSION-DEVELOPMENT.md
EOF
```

**`SYSTEM-COMPOSITION.md` is in this snapshot and was not in CONTENT's, and that is the structural
difference between the two extensions.** CONTENT is a handler over the content store and needs no
composition facts. HISTORY is an **emit consumer at position 4** (§2.2), and its position, its class
(*bounded reactive*), and the execution-context field inventory it records (§1.4, §1.5) are all
normative in a document that is not `EXTENSION-HISTORY.md`. A snapshot that pinned only the
extension spec would leave the ordering unpinned, and ordering is the thing this extension's
correctness turns on.

---

## The §3.3 header, and why `[contract]` here reads `derived` rather than `transcribed`

`EXTENSION-CONTENT` and `EXTENSION-TYPE` are the only two specs in the 26 that carry
`GUIDE-EXTENSION-DEVELOPMENT` §3.3's declaration header
(`grep -lE 'Owned namespaces' specs/extensions/*.md | wc -l` → `2`). `EXTENSION-HISTORY` does not.

**That is a documentation gap, not a semantic one, and it does not stop anything.** The spec states
every fact the header would carry, in its body, normatively:

| `[contract]` field | Derived from | Confidence |
|---|---|---|
| `owned_types` | **§9.2 "Types Installed"** — an explicit six-line list | exact; this is a declaration in all but placement |
| `owned_ops` | **§9.3 / §4.1** — the handler manifest, `query` + `rollback` with input/output types | exact |
| `owned_namespaces` | **§3.1, §6.1** — `system/history/head/{path}`, `system/history/config/{name}`, handler at `system/history` | exact |
| `points_consumed` | **§5.1 + SYSTEM-COMPOSITION §2.2 position 4** | exact |
| `points_exposed` | nothing in the document exposes a registration hook | **inferred from absence** — the one field that is a reading rather than a reading-off |
| `owned_kinds` | no `properties.kind` value appears anywhere in the document | **inferred from absence** |

**Two of the eight are inferred from absence and are marked as such in `EXTENSION.toml`.** That is
the whole cost of the missing header, and it is recorded rather than hidden: `derived_from` names
the section for every field, and the two inferred fields say so. A reader can check every one
against this snapshot's digest, which is the property that made `[contract]` worth having.

**Routed with the built extension, not instead of it** — `ROUTING-2026-09-06-c-arch-*` asks for the
header on HISTORY with this table as the proposed content, so arch is reviewing a filled-in draft
rather than a request to do work.

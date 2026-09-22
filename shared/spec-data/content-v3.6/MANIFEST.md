# spec-data snapshot — `content-v3.6`

**Immutable.** Operators never edit a snapshot. A defect in a snapshotted spec is routed upstream and
lands as a **new directory**, never as a local patch. This is keystone's `shared/spec-data/` pattern,
copied deliberately: a generator's input scope is its output scope, and an unpinned input makes a
conformance number unreproducible.

**Stamped:** 2026-09-05, from `entity-system-architecture` @ `4b7be232550faf97c55a2b293d6906ec304367c7`.
*(An internal SHA. This file is not a publication surface — `docs/status/` rules apply.)*

| File | sha256 | Spec version |
|---|---|---|
| `EXTENSION-CONTENT.md` | `4bf4a43bd7b99adf20cb989581743348bbf8edf9c2a64f52a03764ddca03c5af` | 3.6 + Amendments 1–3 |
| `GUIDE-EXTENSION-DEVELOPMENT.md` | `4bbe1521ee89fd9eefc06e8f958f6f28f6d38d4f6c0254f813a00ca106b77dee` | — (cited for §171 `path_required`, §3.3 header contract, §4.3 namespace ownership, §9 grade) |

Verify:

```
sha256sum -c <<'EOF'
4bf4a43bd7b99adf20cb989581743348bbf8edf9c2a64f52a03764ddca03c5af  EXTENSION-CONTENT.md
4bbe1521ee89fd9eefc06e8f958f6f28f6d38d4f6c0254f813a00ca106b77dee  GUIDE-EXTENSION-DEVELOPMENT.md
EOF
```

**`extensions/content/EXTENSION.toml`'s `[contract]` block is a transcription of
`EXTENSION-CONTENT.md`'s header in this snapshot** — that digest is what makes the transcription
checkable. A transcription that drifts from its source is worse than no transcription, because it
reads as authority.

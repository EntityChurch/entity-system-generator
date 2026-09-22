# spec-data snapshot — `content-v3.7`

**Immutable.** Operators never edit a snapshot. A defect in a snapshotted spec is routed upstream and
lands as a **new directory**, never as a local patch. This is keystone's `shared/spec-data/` pattern,
copied deliberately: a generator's input scope is its output scope, and an unpinned input makes a
conformance number unreproducible.

**Stamped:** 2026-09-06, from `entity-system-architecture` @ `ff67e33a8e0059a8f5b301c63977a59d3543dfdb`.
*(An internal SHA. This file is not a publication surface — `docs/status/` rules apply.)*

| File | sha256 | Spec version |
|---|---|---|
| `EXTENSION-CONTENT.md` | `2a40b22b859b2a74f7de4d1c43b4655cb6ece2b791d7769f27fcc87efa65ee87` | 3.7 |
| `GUIDE-EXTENSION-DEVELOPMENT.md` | `4bbe1521ee89fd9eefc06e8f958f6f28f6d38d4f6c0254f813a00ca106b77dee` | — (cited for §171 `path_required`, §3.3 header contract, §4.3 namespace ownership, §9 grade) |

Verify:

```
sha256sum -c <<'EOF'
2a40b22b859b2a74f7de4d1c43b4655cb6ece2b791d7769f27fcc87efa65ee87  EXTENSION-CONTENT.md
4bbe1521ee89fd9eefc06e8f958f6f28f6d38d4f6c0254f813a00ca106b77dee  GUIDE-EXTENSION-DEVELOPMENT.md
EOF
```

**`extension-contracts/content/EXTENSION.toml`'s `[contract]` block is a transcription of
`EXTENSION-CONTENT.md`'s header in this snapshot** — that digest is what makes the transcription
checkable. A transcription that drifts from its source is worse than no transcription, because it
reads as authority.

---

## What moved from `content-v3.6`, and what it cost us

The predecessor snapshot is `../content-v3.6/` (`EXTENSION-CONTENT.md` @
`4bf4a43bd7b99adf20cb989581743348bbf8edf9c2a64f52a03764ddca03c5af`). It stays on disk: it is the
input the three cycle-1 conformance reports were measured against, and deleting it would make those
numbers unreproducible.

**The whole diff is 38 lines** (`diff <(…v3.6/EXTENSION-CONTENT.md) <(…v3.7/EXTENSION-CONTENT.md) | grep -cE '^[<>]'` → `38`),
and `GUIDE-EXTENSION-DEVELOPMENT.md` is **byte-identical** across the two snapshots — same digest,
above. So every §171 citation in this tree survives the re-pin unchanged.

Two normative changes reach generated code:

1. **§6.4's `403 forbidden` is corrected to `403 capability_denied`.** One site per port, plus its
   test. `forbidden` was defined nowhere; it is `ENTITY-CORE-PROTOCOL` §3.3's *fallback* for the
   status, not a code. This is the only behavioural change in the re-pin.
2. **New Appendix A — the handler's error-code table**, which the extension never had. It pins
   `ambiguous_input` / `missing_input` / `hash_mismatch` (400), `blob_not_found` (404),
   `blob_pending_sync` (**503**, newly distinguished by status) and `capability_denied` (403), and
   rules that the token is the `code` and never a label in `message`.

**Appendix A also settles, in our favour, a thing we had resolved by reading:** `verify_content`'s
`missing_chunk` / `empty_chunk` / `size_mismatch` are *internal predicate* returns and not wire
codes — which is exactly how all three ports already use them (`ensure_closure` verdicts, never an
`errorResult`). Where such a failure does reach the wire it is `500 storage_error`. No port changes.

**And `blob_pending_sync` moving to 503 changes nothing here, for a reason that is declared rather
than lucky.** §6.2's `get` answers `200` with `found` / `missing` lists; it never emits either code
on the wire. The codes live in `internal/reassemble`, whose caller maps them per §3.4's
sync-state-visibility predicate — and this composition has neither a subscription nor an inbox, so
the terminal arm is the correct one. See `[assumptions].pending_field`.

**Two defects in this snapshot are routed, not worked around** — `ROUTING-2026-09-06-b-arch-*`.
Appendix A declares itself *"the code set for this handler"* and omits `path_required`, which the
same document MUSTs at §6.2 and §6.3; and §3.4/§6.2 spell the terminal 404 `not_found` where
Appendix A pins `blob_not_found`. Both are transcribed into `[contract].error_codes` **as the
document states them**, with the contradiction recorded at the site rather than resolved here.

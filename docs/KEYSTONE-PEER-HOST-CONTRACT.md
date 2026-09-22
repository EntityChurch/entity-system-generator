# The keystone peer host contract — a pointer

**The contract is `entity-core-keystone`'s and lives in their tree.** This file is one line of
substance and exists so that a reader here lands on the right document instead of on our old draft.

> **`SPEC-KEYSTONE-PEER`, `H1…H9`, cited as**
> **`H<n> @ 62e1a1dd156bfd3e7760a86bf4b75b0433bd5e234d37fd5bc79c5823c3cd938a`**
> — `entity-core-keystone/docs/spec/SPEC-KEYSTONE-PEER.md`, v1.0, landed 2026-09-09, declared
> canonical and digest-pinned in their repo and gated by their `tools/keystone-spec-gate.py`.

Digest verified here from the file rather than from the packet that announced it:

```
$ sha256sum ../entity-core-keystone/docs/spec/SPEC-KEYSTONE-PEER.md
62e1a1dd156bfd3e7760a86bf4b75b0433bd5e234d37fd5bc79c5823c3cd938a
```

## Cite the digest, never a commit, and re-read when it moves

**H-numbers are append-only and amendments are never made in place.** A citation without a digest
resolves to whichever wording is current, which is not the same claim. This repo has already built
a probe against a superseded H1; our probes measure behaviour rather than wording so they survived
it, and that is luck rather than method.

## Why there is no copy of the requirement text here

Two copies of a contract is the summary-table failure D14 exists for, one artifact-kind up: the
second copy is corrected by packet, drifts, and then reads as authoritative because it is the one
in the tree you are already in. **We do not maintain a second copy.** The derivation and the
measurements that produced H1–H5 are archived at
`docs/archive/DRAFT-KEYSTONE-PEER-HOST-CONTRACT.md`; the requirement text is theirs.

## What this repo holds instead

- **Which faces each of our targets hosts, measured** — `[system.faces]` per composition, and
  `extension-contracts/*/EXTENSION.toml` `[substrate.*]`. A seam claim names a face or it names
  nothing (D13).
- **The probes** — `languages/<t>/gates/host-seam/`, which measure behaviour against the contract
  rather than restating it.
- **What our loader touches**, which is the façade question, routed 2026-09-09 —
  `docs/outbox/ROUTING-2026-09-09-b-keystone-*`.

**H8 and H9 are readings this repo routed** and are now normative there. That is the loop working,
and it is the reason not to keep our own copy: the contract improves in one place.

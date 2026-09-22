# rust × content-history — conformance, 2026-09-07

**Internal.** `rust` × (CONTENT v3.7 + HISTORY v1.7), composed onto a keystone
`entity-core-protocol-rust` peer and measured by `entity-core-go`'s `validate-peer`.

**Read §1.2 before §1.1.** This composition scores **7 of 34** in the `history` category
against a recorder that is working correctly, and the two facts are not in tension: every
check that reads a transition reads it through `system/history:query`, and on this peer
that operation cannot exist. A single line of the form *"N of M"* would describe the
oracle's access path and be read as a description of the extension.

**Measured at:** generator `HEAD` of this commit · keystone `8d800ba`, clean working tree
· oracle `../entity-core-keystone/output/s4-oracles/validate-peer` (gitignored local
build; see `PROVENANCE.txt` beside it).

---

## 1. The numbers

Every figure below is the `summary` block of the JSON report named beside it, printed by
the artifact rather than counted off a listing (D14).

### 1.1 `history` — six moved, and they are the ones that could

```
                 PASS  WARN  FAIL  SKIP   total
bare                1     0    29     4      34    status/history-report-2026-09-07-bare.json
composed            7     0    23     4      34    status/history-report-2026-09-07.json
```

**Six checks moved, all FAIL → PASS, and nothing else moved in either direction:**

```
type_transition       FAIL -> PASS   history type registered: system/type/system/history/transition
type_config           FAIL -> PASS   ... /config
type_query_params     FAIL -> PASS   ... /query-params
type_query_result     FAIL -> PASS   ... /query-result
type_rollback_params  FAIL -> PASS   ... /rollback-params
type_rollback_result  FAIL -> PASS   ... /rollback-result
```

That is the whole of what a third party measures about HISTORY on this peer. The six are
`client.TreeGet` on `system/type/system/history/*` and nothing more — they assert the
paths **resolve**, not that the entities are right. `validate-peer` has no HISTORY
analogue of `type_system_content_*_match`, which renders the type from the oracle's own
independent transcription and compares content hashes. See §4.

### 1.2 The 23 that could not move, and why that is not a score

Every one of them reaches a transition through `system/history:query` or
`system/history:rollback` — six call sites through two helpers in
`cmd/internal/validate/history.go`. The handler face is not installable on this peer
(§3), so all six fail at the request, and `BlockCheck` propagates severity **Fail** to
their 17 dependents.

**Meanwhile the recorder is running.** From the moment the composed peer serves, every
tree write it accepts is recorded as a §2.1 transition at `system/history/head/*`, and
the chain is real, correct and content-addressed. Measured over real loopback TCP with
both controls — `languages/rust/gates/host-seam/src/bin/probe.rs` scenario 4:

```
H. consumer registered, wire PUT then wire GET
   PUT  /{peer}/probe/wire-emit    200
   GET  the head pointer           200
   witness: author=rs-seam-9c41 (registration-time)  path (request field)  hash matches PUT
I. NO consumer, the identical two calls
   PUT                             200
   GET  the head pointer           404
```

The witness derives from **both** a request field and registration-time state, which is
what makes it inattributable to anything but our callback having run; the negative
distinguishes *"not installed"* from *"installed and never asked"*. D13 clause 2.

**So one extension's write face installs and its read face cannot.** That is a sharper
statement than `rust × CONTENT` could make — there, the un-installable handler meant the
extension did nothing at runtime — and it is a state no roster column with one value per
peer can spell.

### 1.3 One check passes on the BARE peer, and it is a §7.5 security check

```
bare:  rollback_invalid_hash_rejected  PASS
       "rollback with invalid hash returned status 404 (correctly rejected)"
```

§7.5 is History Exfiltration Prevention — the refusal that stops `rollback` being an
unrestricted write primitive. The check sends a fabricated hash and asserts
`resp.Status != 200`; a peer with **no history handler at all** answers `404
handler_not_found`, which is not 200.

This is measured, not inferred, and it is not specific to `rust`: the bare arm of the
`history` category is `1 PASS` on all three targets in this session's `make check-all`.
Routed to `entity-core-go`.

### 1.4 `content` and `type_system` — unchanged by the second extension

```
                 PASS  WARN  FAIL  SKIP   total
content   bare      4     0     5     4      13
content   composed  7     0     2     4      13     3 moved: type_blob, type_chunk, type_descriptor

type_sys  bare    112    11   323     0     446
type_sys  composed 118    11   317     0     446     6 moved: _fetch AND _match for the same three
```

Identical to `rust × content`. Adding a second extension moved nothing here, which is
what a category scoped to CONTENT's §11.1 types should do.

### 1.5 `--profile core` — 0 regressions, and the risk that did not materialise

```
ROUNDS: 2, 756 checks per arm
REGRESSIONS ATTRIBUTABLE TO THE COMPOSITION: 0
IMPROVEMENTS: 6   FLAKY: 0
status/core-arms-diff-2026-09-07.txt
```

**Stated as a result rather than as an absence.** This is the first composition whose
extension *writes to the tree while the oracle is driving it*: 756 checks' worth of wire
traffic, every tree write among them producing a head-pointer binding under
`system/history/head/`. If any core check enumerated a subtree, counted bindings or
asserted on a listing, the recorder would have changed its answer — our second failure
mode, the peer was right and we broke it. None did, across two rounds.

---

## 2. Unit tests

58 across four suites, run from the **staged** cell so `tests/` sees only `pub`:

```
tests/handler.rs    17   §4.2's dual check (with the ALLOW control), §4.3.1's filter order,
                         §4.3.2, §7.5, the walk bound, and every error code
tests/recorder.rs   15   §5.1, §3.2's guard (both directions), §6.2's shadowing rule, and
                         the real seam through a live Peer
tests/patterns.rs   11   §2.2 canonicalization, §6.2's three keys, HIST-CONFIG-SPECIFICITY-1
tests/sdk.rs         6   the positive control for the compile-fail arm, plus the surface
tests/types.rs       9   §2.1's fourteen fields, optionality, and the six published paths
```

Plus the compile-fail arm: `src/bin/deep_import.rs` refused with `error[E0603]: module
`internal` is private`, twice, interpreted only after the suites passed.

---

## 3. What was refused, and why the refusals are the composition's most important lines

**No §11.6.1 handler writes**, for either extension. Measured, both arms: `404
handler_not_found` with nothing bound, `501 no_handler_body` with all four bound. `404`
is the truth; `501` would say a handler exists and is broken. `tools/compose.py` makes
this structural — `[system.faces.*].handler = "not-installable"` drops the pattern from
the resolved plan, so a wiring program that would bind a manifest for a body that cannot
exist is not merely discouraged, it cannot be generated.

**No fabricated handler grant.** §2.1's autonomous `capability` is *"the handler grant"*.
`typescript` reads back the token its own `installHistory` minted; `python` keeps the one
it minted. **On this peer `Peer` exposes `create` and `dispatch` and nothing else** — no
mint — and there is no handler to grant for. So the host passes the local identity hash,
`author == capability` on every transition here, and the `COMPOSED` line prints
`handler_grant=false`. Minting something grant-shaped so the field looked less degenerate
would be making the audit trail claim an authority that does not exist.

---

## 4. What this composition does NOT establish

- **That HISTORY's six type entities are correct.** They are checked for *presence* and
  nothing else. Two of the three ports hand-build the field maps (the peers' own
  `TypeDef` builders are private), and no oracle compares a HISTORY type against an
  independent transcription. A subtly wrong map hashes differently from the other ports',
  dedup stops for that type, all six checks stay green, and nothing says so. That is an
  axis with no upstream authority and by D16 it should already have a gate. It does not.
- **That the query/rollback algorithms are right on this substrate.** `tests/handler.rs`
  is ours and the oracle never reaches that code here. `reached_by = []` for every SDK
  entry on this port.
- **Independent convergence.** Three ports of one reading, generated by one team from one
  snapshot. Cohort-consistent, not independent (L18).

---

## 5. Reproduce

```
make build       TARGET=rust COMPOSITION=content-history
make test        TARGET=rust COMPOSITION=content-history
make conformance TARGET=rust COMPOSITION=content-history ROUNDS=1
make regression  TARGET=rust COMPOSITION=content-history
podman run ... ./languages/rust/gates/host-seam/run     # scenario 4, arms H/I
```

`make check TARGET=rust COMPOSITION=content-history` runs all of the above plus
`plan-check`, `sdk-parity`, `structure`, `drivers`, `error-codes` and `citations`.

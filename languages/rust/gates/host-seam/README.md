# `host-seam` — the `rust` probe

**Axis:** `host-seam`. **Authority:** `GUIDE-CONFORMANCE` §7d (arch, proposed) + the keystone peer
host contract H1/H2/H6/H7. **Peer under test:** `entity-core-protocol-rust` (keystone, read-only).

```
sh languages/rust/gates/host-seam/probe-seam-rust.sh        # or: make probe
```

## The shape, and why it changed on 2026-09-12

Until keystone landed H1/H3/H6/H7/H9 on this peer (for our K-9), this probe could not be shaped
like its siblings — *install, then dispatch, then check the witness* — because there was nowhere to
install. It measured the absence instead: four §11.6.1 tree writes bound → `501 no_handler_body`,
and the same body called directly to prove dispatch never asked it. **That record is kept below;
the probe is now shaped like the other two, because the peer changed.**

On an AOT substrate some D13 questions are for the **compiler**, so this is still three invocations:

| | must | what it establishes |
|---|---|---|
| `access_control` | **compile** | the positive control — the peer is reachable as a library, and a body installs through `register_handler` |
| `access_absent` | **fail to compile, with EACH of `E0616` `E0609` `E0603` `E0624`** | keystone H3: the container behind the public registration call is not reachable |
| `probe` | run | H1 Reach · the emit face · H6 by value · H7 Reach |

**Each code, not a count.** The arm used to require four distinct diagnostics. Keystone measured it
still reporting four-of-four after `register_handler` went public, because the fixture's call had
turned into `E0061` (wrong argument count). A count survives a change of cause; a code does not.
An unclaimed error code is refused too — then the fixture failed for a reason it does not name.

## Result — `entity-core-keystone` read 2026-09-12, with H1 landed on the rust peer

```
== 2. access_absent ==
     error[E0603]: type alias `Outcome` is private
     error[E0616]: field `native_handlers` of struct `Peer` is private
     error[E0609]: no field `handlers` on type `Peer`
     error[E0624]: method `resolve_handler` is private
   claimed codes present: 4 of 4

Scenario 1 — H1
  A. nothing installed                      404  handler_not_found
  B. register_handler -> Ok                200  witness=rs-seam-9c41:hello   invocations 0 -> 1
  C. unregister_handler -> true            404  handler_not_found            invocations stay 1
Scenario 2 — emit face: D 1 event · E 0 events · F identical re-bind silent · G re-entrant write OK
Scenario 4 — emit face over the wire: H PUT -> consumer -> GET 200 · I no consumer -> GET 404
Scenario 3 — H6 by value: configured 3,145,749 -> read 3,145,749 · default -> 16,777,216
Scenario 5 — H7: K no evaluator 501 · L literal 200, evaluator asked 0x · M 200 value=43 · N declined 501
probe integrity: OK — every arm discriminated
```

**C is the arm that makes B attributable.** A alone says nothing is installed; B's witness folds a
request field into a registration nonce; C returns the peer to `404` with the counter unmoved, so the
`200` belonged to the install and to nothing else on the dispatch path. The binary exits non-zero if
any face the contracts claim installed measures NO.

## The pre-H1 record — `entity-core-keystone` read 2026-09-06, before H1 reached the rust peer

```
access_absent: E0603 struct `Outcome` is private · E0624 register_handler is private ·
               E0609 no field `handlers` · E0624 resolve_handler is private
Scenario 1: A nothing bound 404 · B all four §11.6.1 writes bound 501 no_handler_body ·
            C the body called DIRECTLY 200, invocations before=0 after dispatch=0 after direct=1
            => Reach (handler face): NO
Scenario 3: wire::MAX_FRAME 16777216, not configurable => UNSATISFIABLE-AND-VACUOUS
```

## What this measures, and what it does not

**One peer is one peer.** This says nothing about the other 45 and is not a substitute for
keystone's harness, which has to run in 46 toolchains — the part that is actually hard and is
theirs.

**Four layers green is still not the property**, and four layers red is not the whole story
either: `rust` fails three D13 layers on the *handler* face and passes all four on the *emit*
face. That is why D13 was amended to require a claim to name a face — see `AGENTS.md`.

## Boundaries

- **Read-only against `entity-core-keystone`.** The peer is consumed as a path dependency and
  is never patched. `CARGO_HOME` and `CARGO_TARGET_DIR` point into our `output/`, and the crate
  closure comes from keystone's own `cargo vendor` mirror, mounted read-only. Nothing is
  fetched (`--network=none`) and not one byte lands in their tree.
- **If a peer cannot host what we generate, that is a finding about the seam**, and it is
  routed. Routed here: `extension-contracts/content/arch/AUTHORING-NOTES.md` §3.4 and §3.5.

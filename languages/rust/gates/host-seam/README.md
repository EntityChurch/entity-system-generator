# `host-seam` — the `rust` probe

**Axis:** `host-seam`. **Authority:** `GUIDE-CONFORMANCE` §7d (arch, proposed) + the keystone peer
host contract H1/H2/H6/H7. **Peer under test:** `entity-core-protocol-rust` (keystone, read-only).

```
sh languages/rust/gates/host-seam/probe-seam-rust.sh        # or: make probe
```

## Why this one is shaped differently from `probe-seam.mjs` / `probe-seam.py`

Both sibling probes are shaped as *install, then dispatch, then check the witness*, because on
both of those peers a handler body can be installed after construction. **That shape does not
fit here and finding out why is the result.**

And a deeper difference: on `typescript` and `python`, *"is the symbol there"* is a question you
ask an object at runtime. On an AOT substrate it is a question you ask the **compiler**. A probe
that answered it with a grep would be reading source to decide what is true, which is exactly
what D13 exists to forbid. So this probe is three invocations, not one:

| | must | what it establishes |
|---|---|---|
| `access_control` | **compile** | the positive control — the peer IS reachable as a library |
| `access_absent` | **fail to compile** | Access · Read · Export, decided by rustc |
| `probe` | run | Reach · the emit face · the frame budget, by execution |

**The control is not optional.** A compile-fail check reports its strongest result when the
crate does not build at all — wrong rustc, missing vendor mirror, a moved symbol. "The symbol is
absent" and "this crate does not build here" are the same exit code. The driver refuses to
interpret `access_absent` unless `access_control` compiled in the same run (D15), and it
requires **four** distinct `error[E…]` diagnostics because a single early error can mask the
other three and turn one measurement into four claims.

## Result — keystone `8156792` + uncommitted working tree, 2026-09-06

```
== 1. access_control — MUST COMPILE ==
   compiled. The peer IS reachable as a library across the crate boundary.

== 2. access_absent — MUST FAIL TO COMPILE ==
   error[E0603]: struct `Outcome` is private
   error[E0624]: method `register_handler` is private
   error[E0609]: no field `handlers` on type `Peer`
   error[E0624]: method `resolve_handler` is private
   distinct type errors: 4 of 4 claimed

== 3. probe ==
Scenario 1 — the Reach layer (handler face)
  A. nothing bound                          404  handler_not_found
  B. all four §11.6.1 tree writes bound     501  no_handler_body
  C. that body called DIRECTLY              200  witness=rs-seam-9c41:hello
     invocations: before=0 after dispatch=0 after direct=1
  => Reach (handler face): NO

Scenario 2 — the emit face (§6.10 / §6.13(c))
  D. consumer registered, one bind          1 event   rs-seam-9c41:created:/<peer>/probe/emit
  E. no consumer, one bind                  0 events
  F. identical re-bind (no change)          1 event total
  => Reach (emit face): YES

Scenario 3 — the connection frame budget (CONTENT Am. 1 §6.2)
  wire::MAX_FRAME                           16777216
  => readable by a body: NO. And NOT configurable, so the by-value check K-1
     forced has no second arm here. UNSATISFIABLE-AND-VACUOUS, not a failed check.
```

**Scenario 1's three arms are the whole argument.** A alone would say "nothing is installed".
B alone would say "something is broken". **B against A** says the four tree writes took effect
and the peer resolved the pattern; **C** says the body works and its invocation counter went
`0 → 1` on a direct call while staying at `0` through the dispatch. Together they say the one
thing worth saying: *there is nowhere to install a body, so it was never asked.* That is D13's
required distinguisher between "not installed" and "installed and never asked", landing on a
third case neither sibling probe has ever had to express.

**Scenario 2 has two negatives and they are not redundant.** E is "no consumer → no events".
F is "an identical re-bind → **no additional** event", which is the arm that separates *the
counter tracks events* from *the counter tracks calls*. Only the first is the property §6.10
states, and only F can tell them apart.

**Scenario 3 is reported as vacuous rather than scored.** The `python` K-1 upgrade made the
frame-budget check measure **by value** — configure the peer to enforce 3,145,749, assert the
body reads back 3,145,749, and carry a negative arm that reads the 16 MiB default and rejects
it. Here there is no configuration to vary, so that comparison has no second arm. Saying so is
different from reporting a failure, and different again from reporting a pass.

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

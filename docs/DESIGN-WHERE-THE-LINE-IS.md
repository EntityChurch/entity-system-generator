# The keystone peer contract, and what varies by platform

**The goal, in the operator's words:** *"I work in this language. I use whatever — COBOL, Lisp. I go
to the system, I say I want to build a peer. I get the keystone peer. I pull the extensions."* Any
combination, and it composes itself properly.

This document is about what has to be true for that to work: which parts are **the same pattern
everywhere**, which are **free to vary by platform**, and what set of specs and interface layers
holds it together.

Companion to `DESIGN-THE-GENERATION-MODEL.md` (how a build runs).

---

## 1. A keystone peer is more than a core protocol peer

This is the layer the model turns on, and it did not previously have a name here.

**Anyone can write a core protocol peer.** The spec is public, the wire is fixed, and a peer that
speaks it correctly is conformant — full stop. It owes nothing to us.

**A keystone peer is that, plus the foundation the generator builds on.** It is the base into which
extensions get installed, so it has obligations a plain core protocol peer does not: it has to
*expose the hook points*. Core protocol does not require them, does not test them, and is right not
to — a peer that will never host an extension does not need them.

```
      ANY core protocol peer            A KEYSTONE peer
      ──────────────────────            ───────────────
      speaks the wire                   speaks the wire
      passes the 16 core categories     passes the 16 core categories
                                        + exposes the host contract  ◄── the extension foundation
                                        + declares its platform bindings
```

> **So there is a specification layer between "core protocol" and "an extension," and it is about the
> peer rather than about the protocol.** Core protocol says a peer dispatches to a handler; it does
> not say *a third party can add one*. That sentence has to be written somewhere, and the somewhere
> is a keystone peer requirement, not a core protocol requirement.

**The consequence for how we work:** whatever this repo needs to install extensions, **keystone
implements as the base**, once, per language. We do not carry per-language shims and we never patch a
peer. The requirement goes to keystone; keystone's peers grow it; every extension in that language
gets it for free.

## 2. The blocker this predicts, measured

**The prediction:** if the hook point is not a stated requirement and no gate checks it, peers will
have it inconsistently and nobody will notice, because core conformance cannot see the difference.

**That is what is there.** Source-read of `entity-core-keystone`'s generated peers, 2026-09-02:

| Peer | How dispatch resolves a pattern to a body | Can a third party add one? |
|---|---|---|
| **`go`** | `p.handlers map[string]handler`, consulted at `peer.go:414`, then falls through to the entity-native `expression_path` path | **Yes** — there is an index. It is unexported, but it exists |
| **`typescript`** | `registerHandler(handler: Handler)`, public (`peer.ts:173`) | **Yes** |
| **`haskell`** | a hardcoded `case` on the pattern string (`EntityCore/Peer.hs:840–847`): `"system/tree" → treeHandler`, `"system/capability" → capabilityHandler`, … `_ → entityNativeDispatch` | **No.** There is no index. Adding a handler means editing `Peer.hs` |

**All three are fully conformant.** They pass the same 68-category oracle, including the eleven-check
`core_register_*` family — because `system/handler:register` writes *tree entities*, and writing tree
entities is not the same as having somewhere to bind a body. Haskell's `handlersHandler` does the
writes correctly and there is nothing behind it.

> **This is the whole argument for §1 in one measurement.** Two peers, both conformant, one of which
> can host an extension and one of which cannot — and no gate anywhere distinguishes them. Generating
> CONTENT for Haskell would fail at the last step, for a reason that is nobody's bug.

**Scope, honestly:** three peers verified by source read, at least two distinct shapes. **The
cohort-wide census has not been taken** and a grep does not settle it — the shapes differ too much
between paradigms for a pattern match to be trusted. Taking it properly is cheap and it is the first
thing to do (§5).

## 3. What must be identical, and what is free to vary

The operator's framing: *"Lisp has a certain way it manages modules, a certain way it manages
extensions. Not every language will do that the same. But the pattern needs to be the same."*

| | Must be identical everywhere | Free to vary by platform |
|---|---|---|
| **Installing a handler** | that a third party *can*, after construction, without editing the peer; that it writes §11.6.1's tree entities; that collision is refused; that close unregisters both sides | the call's name and shape — `WithHandler`, `registerHandler`, a typeclass instance, a method on a class |
| **Installing an emit consumer** | that a third party can register on the emit pathway; that registration order **is** the §2.2 order; that classification and self-guarding hold | the mechanism — `AddNamedSyncHook` in Go, something else per language |
| **Composition** | the §2.2 nine-position order, its constraints, cascade depth, convergence | nothing. This is protocol-observable |
| **Module structure** | that an extension is a separate unit depending on the peer package | everything about *how* — Cargo crate, npm package, ASDF system, COBOL copybook, Lisp package |
| **Consumption** | that both "run it as a peer" and "use it as a library" are reachable | which are available, and what "library" even means, per platform |
| **The wire** | all of it | nothing |

**The test for the right-hand column:** *could two peers both be correct and answer differently?* If
yes, it is a **declared profile value** — never a spec MUST, never a generator assumption. That is
why `AddNamedSyncHook` is a profile fact and not a spec gap, and it is why a `register_consumer`
primitive was drafted here and withdrawn.

**The test for the left-hand column:** *if two peers answer differently, does something break for the
person composing a system?* If yes, it is a requirement — and the layer it belongs to is decided by
§4.

## 4. The set of specs and interface layers

What has to exist for the goal in the header to work. Most of it does.

| Layer | Document | State |
|---|---|---|
| **The wire** | `ENTITY-CORE-PROTOCOL`, `ENTITY-CBOR-ENCODING`, `ENTITY-NATIVE-TYPE-SYSTEM` | ✅ exists, and is not ours to change for this |
| **What each extension is** | `EXTENSION-*.md` × 26 | ✅ exists |
| **How extensions compose** | `SYSTEM-COMPOSITION` — emit pathway, the §2.2 order, cascade, convergence | ✅ exists, normative, 859 lines |
| **What a peer *is* as a configuration** | `GUIDE-PEER-COMPOSITIONS` — *"a peer is a configuration: identity + installed handlers + installed extensions + grants + tree state"*, with named tiers (*"core protocol only"* … *"revision + history + identity"*) | ✅ exists — this is already the mix-and-match vocabulary |
| **The handler install contract** | `SDK-OPERATIONS` §11.6 — `register_handler`, four mutations, 409, handle lifecycle, per-language body shapes | ✅ exists. **The authorization gap is CLOSED, and not the way the proposal asked** — this row read *"§6.2's reservation is unscoped, so installing at `system/{ext}` is refused; `PROPOSAL-EXTENSION-HOST-INSTALL-SEAM` D1."* D1 asked to **narrow** the reservation to the wire register path; `ENTITY-CORE-PROTOCOL` 0.8.2.13 **withdrew it entirely**, so install authorization at any path is the ordinary §6.13 capability check on `resource`. A peer that refuses `system/*` and a peer that permits it are both conformant. The two peers we compose against still refuse — see `extension-contracts/content/EXTENSION.toml [substrate.wire_install_refusal]` |
| **The keystone peer host contract** | **— nothing —** | ❌ **the gap.** What a keystone peer must expose to be an extension foundation: a real dispatch index, a consumer registration point, both reachable after construction. §2 shows what its absence costs |
| **The platform bindings** | `profile.toml` `[host]` — the names of those hooks per language, module system, consumption modes | ❌ not yet; mechanical once the contract exists |
| **Conformance for it** | a host-contract check | ❌ not yet. Cannot be a pure wire check — the harness must install through the public API and the oracle assert over the wire (`GUIDE-CONFORMANCE` §7d, proposed) |

**Two documents to write, not seven.** The corpus is in better shape than the gap list suggests: the
composition semantics, the extension definitions, the peer-as-configuration vocabulary and the
handler install contract are all already there and none of them is ours to invent.

**Where the host contract lives is a real question and I do not think it is settled.** It is a
requirement on *keystone peers*, not on core protocol peers, so it does not belong in
`entity-core-protocol`. Two candidates: an arch-authored spec that keystone implements (consistent
with arch being the spec authority), or a keystone-owned profile contract that arch reviews. **The
first fits the existing ownership lines better**; it is worth one operator call before drafting.

## 5. What to do next

1. **Take the census.** Per peer: is there a dispatch index reachable after construction, or a
   hardcoded switch? Is there a consumer registration point? By source read, not grep — §2 shows the
   shapes are too different for a pattern match. This sizes everything else.
2. **Draft the host contract** off that census, so it describes what the peers that *do* have it
   already do, rather than something invented.
3. **Route it to keystone** as a base requirement, with the profile fields it implies.
4. **Then pick a few peers and build one extension**, which is where the real answers are.

**On reading the specs:** they are in `entity-system-architecture` in this same checkout. Read them
there. If a copy is convenient, copy them. Divergence can be checked against the public mirror if
anyone ever wonders. This is not a step that needs ceremony and it is not a blocker on anything.

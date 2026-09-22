# Census — can a keystone peer host a handler it wasn't compiled with?

**Method:** source read of the dispatch resolution site in each peer. Not a grep — the shapes differ
too much between paradigms for a pattern match to be trusted, and a first attempt at one produced
noise in both directions.

**Measured against** `entity-core-keystone`'s generated peers, 2026-09-02. **12 of 46 peers.** The remaining 34 are unmeasured
and are recorded as unknown, not as absent.

---

## 1. The result

Two shapes, splitting about two to one.

> **Read the shape column as shape only.** *Indexed* means the peer resolves through a container, not
> that a third party can reach it. Of the seven below, **exactly one — `typescript` — is reachable**,
> and it is the only peer in the cohort measured by execution (§4). `csharp` has the entry point, the
> registry and the writes, and **the whole assembly is `internal`** (§4a). Conflating shape with
> reachability produced the original selection and then produced the second one; it was warned about
> in §5 of this document's first draft, twice ignored, and is now `AGENTS.md` **D13**.

### Indexed — a `pattern → handler` container consulted at dispatch

| Peer | Evidence |
|---|---|
| `go` | `handlers map[string]handler` (`src/peer/peer.go:28`), consulted `peer.go:414`, then entity-native fallback |
| `python` | `self.handlers.get(stripped)` (`src/entity_core/peer/peer.py:333`) |
| `java` | `private final Map<String, Handler> handlers = new HashMap<>(); // pattern → handler` (`Peer.java:35`) |
| `kotlin` | `private val handlers = HashMap<String, Handler>() // pattern → handler` (`Peer.kt:32`) |
| `ruby` | `@handlers = {} # pattern → handler instance` (`peer.rb:34`), read `peer.rb:762` |
| `typescript` | `registerHandler(handler: Handler): void` — **public** (`src/peer.ts:173`) |
| `csharp` | handler classes carrying `public string Pattern => "system/tree"` (`Handlers/TreeHandler.cs:17`) — registry shape |

### Hardcoded — a `case`/`switch`/`EVALUATE` on the pattern literal

| Peer | Evidence |
|---|---|
| `rust` | `"system/tree" => self.tree_handler(exec)` (`src/peer/core.rs:436`) |
| `haskell` | `case stripLocal p pattern of "system/tree" -> treeHandler p exec …` (`EntityCore/Peer.hs:840–847`) |
| `swift` | `case "system/tree": return try await treeHandler(…)` (`Sources/EntityCoreProtocol/Peer.swift:435`) |
| `elixir` | `defp route_to_handler` — `case strip_local(t, pattern) do "system/tree" -> tree_handler(t, exec) …` (`lib/entity_core/peer.ex:1155–1167`) |
| `cobol` | `EVALUATE TRUE / WHEN …` (`src/handlers.cob:490`) |

**Every hardcoded peer ends its switch with the same default:** `_ -> entity_native_dispatch(pattern)`
— the §6.13(a) path for a dynamically-registered handler whose body is a `compute` expression in the
tree. **So all of them support dynamic registration of an *entity-native* body and none of them has
anywhere to put a *language-native* one.**

## 2. The finding that matters: this is not a substrate constraint

**Rust, Swift and Elixir all have first-class hash maps and first-class functions.** So does Haskell.
Nothing about those languages forced a hardcoded switch — and nothing about Go, Ruby or Kotlin forced
a map. The split does not track paradigm, ecosystem, or typing discipline.

> **It tracks nothing, because nothing asked.** Core protocol requires that a peer dispatch to its
> bootstrap handlers and return `404 handler_not_found` for anything else. Both shapes do that
> perfectly. The requirement *"a third party can add a handler after construction"* has never been
> written down, so roughly a third of the cohort didn't implement it, at random.

**And no gate can see it.** All 12 pass the same 68 categories, including the eleven-check
`core_register_*` family — because `system/handler:register` writes *tree entities*, and writing tree
entities is not the same as having somewhere to bind a body. The hardcoded peers do the writes
correctly and there is nothing behind them.

**Cost if we had not looked:** generating an extension for `rust` or `haskell` would fail at the last
step of an otherwise-green pipeline, for a reason that is nobody's bug.

## 3. What this makes the ask

Not a rewrite. **For the hardcoded peers the change is mechanical** — replace the `case` with a lookup
into a map seeded with the same bootstrap entries, keeping the entity-native fallback as the default
arm. The switch already *is* a table; it is written in control flow instead of data.

Drafted here, routed to keystone, and now THEIRS: `SPEC-KEYSTONE-PEER` `H1…H9 @ 62e1a1dd…`. Our draft is archived; `docs/KEYSTONE-PEER-HOST-CONTRACT.md` is the pointer.

## 4. The peer selection — REVISED 2026-09-02 after keystone's review

**The original pick was wrong in its most important assumption.** `go` was chosen as *"the cheapest
proof the pipeline runs; the seam already exists, so a failure here is our bug and nothing else's."*
**`go`'s index is private** — written only from `bootstrap.go:121,153`, with `Identity`/`Store`/
`LocalPeer`/`Listen` the exported surface. So all three original peers needed a peer change, and a
failure would have been ambiguous between *the contract is wrong* and *our edit is wrong*. **There
was no control.**

> **REVISED AGAIN 2026-09-02 (second pass). `julia` is not the control and never was.**
> Its `register_handler!` writes `p.handlers`, and **`p.handlers` is read by nothing** — exhaustive
> search of the pod. Dispatch resolves out of the **store** (`resolve_handler`, `peer.jl:628`) and
> runs a hardcoded equality chain (`:674–678`); the map is S3 residue that S4's rewrite orphaned
> (`status/PHASE-S4.md:13`, `peer.jl` marked *"Rewritten"*). See
> `SPEC-KEYSTONE-PEER` H1 @ `62e1a1dd…` (drafted here as `DRAFT-KEYSTONE-PEER-HOST-CONTRACT.md`, now archived). **Three peers, two seats, three days, one error class:
> the entry point is not the seam — the seam is the line that reads the container.**

| Peer | Change needed | Role |
|---|---|---|
| **`typescript`** | **none** | **the control, and now MEASURED rather than read** (`poc/ts-content-seam/probe-seam.mjs`, against keystone's `typescript` peer, 2026-09-02): a language-native body installed through public `registerHandler` (`peer.ts:173`) is reached by dispatch over the wire; the negative control returns `404`. Library-first runtime. A failure here is the generator's, unambiguously |
| ~~`csharp`~~ | **more than `go`** | **RETRACTED 2026-09-03 — see §4a. `internal sealed class Peer`.** Every type in the assembly is `internal`; `RegisterHandler` is a public member of an inaccessible class. `cpp`'s failure at assembly scope. Not a control, and it fails H4 as well |
| **`go`** | expose ≈20 lines | index exists **and is read** (`peer.go:414`, re-verified); needs a public entry point |
| **`rust`** | table + exposure ≈80 lines | proves the H1 change in a language where handler storage is a real design question (`Box<dyn Fn>`, `Send + Sync + 'static`) |
| ~~`julia`~~ | **more than `go`** | **demoted.** Needs the store writes *and* a dispatch-path read, i.e. the full seam. Worth keeping on the list precisely because it is the fourth shape, but not first and not as a control |

**`cpp` is not a control either.** Keystone proposed it alongside `julia`; its `register_handler` is
**private** (`peer.hpp:91`, after `private:` at `:75`), as are `lookup_handler`, `handlers_` and the
`Handler` typedef itself. It is the `go` shape exactly.

### 4a. `csharp` is not a control — RETRACTED 2026-09-03, and this one was ours

**Measured against keystone's `csharp` peer, 2026-09-03.** `Peer.cs:23` reads `internal sealed class Peer : IPeerServices,
IAsyncDisposable`. The `public void RegisterHandler(IHandler handler)` at `:177` is a **public member
of an internal class**, which is not externally accessible in C#. And it is not one type: enumerating
every top-level declaration in `src/`, **the only externally accessible types in the whole assembly
are ten exception classes and `PeerId`.** `Peer`, `IHandler`, `HandlerContext`, `HandlerResult`,
`IPeerServices`, `EntityTree`, `ContentStore`, `EmitBus` — all `internal`.

`InternalsVisibleTo` names five friend assemblies (`Tests`, `Conformance`, `Agility`, `Smoke`,
`Host`), **all inside keystone's own tree.** A module this repo generates is not on that list and
cannot be added by us without patching the peer, which ends the cohort property.

**So `csharp` fails H1 (no reachable entry point), fails H1's second half (the body type cannot be
named), and fails H4** — while shipping as `PackageId = entity-core-protocol-csharp`, a library
package whose entire public surface is its exception hierarchy.

> **Fourth instance of the one error class, and the second by this seat.** keystone read `cpp`'s
> symbol past a `private:`; we read `julia`'s export past a dead map; we then read `csharp`'s
> `public` past an `internal` **on the enclosing declaration 154 lines above the line we cited**. The
> access question is not *"is this member public"* — it is **"is this member reachable from outside
> the compilation/packaging boundary,"** and the boundary is not always the class. See `AGENTS.md`
> **D13**.

**`rust` drags three peers.** `rust-wasm` and `rust-wasm-wasmtime` are path-deps on `../rust` whose
artifacts the census reuses under `NOBUILD=1`, and `datalog` carries its own Rust dispatch. Budget
the forced rebuilds or repeat keystone's 2026-08-28 stale-`.wasm` result.

**Near-term, adding `python`** (a hand-written reference exists for behaviour comparison) **and
`haskell`** (hardest idiom — purity and `IO` make "install a callback" a genuine design question; if
the pattern holds there it holds generally).

**Held for round two:** `cobol` and the ISA peers, and `sql` / `datalog` — keystone's own
`PEER-ATLAS` §5 calls the query-native pair *"the one region that kept paying,"* which makes them the
most interesting **second** target, not the first. Bring them a working pipeline rather than debug
two things at once.

**Peer health is not a constraint:** keystone reports all 46 at `756 · 0F` on the current pin.

## 5. What is still unmeasured

- **The consumer registration surface.** This census covers *handler* dispatch only. Whether each peer
  exposes an emit-consumer registration point is a second census — **and keystone has since largely
  answered it: `go/src/peer/store.go:74` `RegisterTreeConsumer` is exported, `rust/src/peer/store.rs:76`
  `pub fn register_tree_consumer` (so `rust` is hardcoded for H1 *and* has a public consumer seam —
  the axes do not correlate), with an indicative seam in ~22 peers.** §6.10/§6.13(c) made the emit
  pathway a reachable MUST with zero consumers, so every peer built it. **H2 is much cheaper than
  budgeted.**
- ~~**Whether the indexed peers' indexes are reachable.**~~ **Measured three times, and it inverted
  the selection three times.** Of the seven "indexed" peers **only `typescript` is reachable**;
  `go`, `java`, `kotlin`, `python` and `ruby` have no registration surface, and `csharp`'s is behind
  an `internal` assembly (§4a). **`julia` and `cpp` were not in the sample at all** — and neither is
  compliant: `cpp`'s `register_handler` is private, `julia`'s is public and writes a **dead map**.
  **Three lessons now, and the third is the one that generalizes.** *(a)* A caveat in the evidence
  document does not travel to the document that cites it — this §5 said "shape ≠ reachability" and the
  contract's summary line ignored it. *(b)* **"Reachable" has two halves and this census only ever
  measured one.** *Can a third party write to the container* is the registration site; *does anything
  read it* is the resolution site. The method line at the top of this document says the resolution
  site, and for `julia` — the one peer the whole first cycle was staked on — it was not done. **A
  container is not a seam until something reads it**, and the read is the cheap half to check.
  *(c)* **A source read is not a measurement, and after four wrong nominations we stop making them.**
  `typescript` is now measured by execution (§4). Every other peer's `[host]` state reads **`unknown`
  until a harness executes**, and this repo nominates no further control from a source read — the
  §7d harness selects the second peer, not a reviewer.
- **A third shape exists.** `prolog` resolves via a §6.6 backward tree-walk off the store
  (`ec_peer.pl:391`), runtime-mutable natively through `assertz`. The binary taxonomy above is
  incomplete and should not harden into the contract's vocabulary.
- **34 peers by arch; keystone has since measured all 26 M1/M2/M3** and is taking the remainder as
  `[host]` blocks in 46 `profile.toml`s plus a roster column, rather than as a document — *"a table
  rots; a profile value is checkable."* The 20 probes stay **unknown, not absent.**

# gates/eligible — do we build on this peer at all?

**The consumer side of the keystone peer contract.** Keystone certifies each peer against one
interface and publishes `protocol-generator/<peer>/status/KEYSTONE-PEER-REPORT.json`. We do not
re-measure what that report certifies. We read it, and we refuse to build a composition whose
declared needs meet a row that is not `pass`.

```
make eligible TARGET=rust COMPOSITION=compute     # one composition
make eligible-control                              # the planted-defect self-test
```

## What it reads, and nothing else

| input | from |
|---|---|
| what each extension needs | `extension-contracts/<ext>/EXTENSION.toml [requires]` |
| what the launch path needs | `gates/eligible/LAUNCH.toml [requires]` |
| the vocabulary | keystone's `requirements.toml` (REQUIRED, MODULE) and `CONTRACT-DRAFT.md` §5 (pending) — read every run, never copied |
| the verdict and the rows | keystone's report: `verdict`, `requirements[].{name, verdict}` |
| that the report is about THIS peer and THIS contract | `contract_digest` recomputed from keystone's three contract files; `delivery.{commit, tree_dirty}` against keystone's git |

## Verdicts

- **ELIGIBLE** — certified, every name we require is `pass`, the report is about the peer source
  and the contract text we are building against.
- **NOT ELIGIBLE** — anything else. A missing row is `unknown`, and `unknown` is not `pass`.
- **PRE-CONTRACT** — the target's `profile.toml [peer_contract]` declares the peer is not yet under
  the contract. Loud on every run, failed by `--strict`, and failed outright once a report exists.
- **PENDING** — a name we build on that keystone lists as not yet measured (`embed.data` today).
  Printed every run; `--strict-pending` fails it.
- **REFUSING** — the gate could not answer (no extensions, an empty vocabulary, a report with no
  rows, a report whose own verdict contradicts its rows).

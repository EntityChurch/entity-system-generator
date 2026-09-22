# Memory — index

**What this repo has learned, by subject. `AGENTS.md` is what you need BEFORE your first
change; this is what you need WHEN YOU HIT THE THING IT DESCRIBES.** Nothing here loads by
default. Open one file when its trigger fires, and read the whole file rather than grepping it
— every entry in here exists because something plausible turned out to be false, and the
mechanism is the part worth having.

Each file carries the ratified **disciplines** for its subject, with the incidents they were
promoted from. `AGENTS.md` states each discipline in one line and points here for the evidence;
where the two differ, **this is the canonical text and `AGENTS.md`'s line is the summary.**

## The files

| file | open it when | holds |
|---|---|---|
| [THE-SEAM-AND-THE-FOUR-FACES.md](THE-SEAM-AND-THE-FOUR-FACES.md) | you are about to claim a peer can host something — a `[host]` row, a `[system.faces]` value, a roster column, or *"this peer supports X"* in a packet | **D13** (four layers, at the packaging boundary, naming a FACE) · **D23** (an absent face is an UNMEASURED face) |
| [INSTRUMENTS-AND-CONTROLS.md](INSTRUMENTS-AND-CONTROLS.md) | you are writing or changing any check, gate, probe, resolver or differential — or believing a green one | **D15** (+4 sharpenings) · **D19** · **D21** |
| [EVIDENCE-AND-CITATIONS.md](EVIDENCE-AND-CITATIONS.md) | you are putting a number, a path, or a claim about another repo into a document, a packet or a declaration file | **D14** (+ its declared limit) · **D18** · **D22** |
| [GATES-AND-WHAT-READS-THEM.md](GATES-AND-WHAT-READS-THEM.md) | you are adding a new KIND of artifact to this tree, or a second implementation of anything | **D16** (ten instances) · **D24** |
| [THE-TARGET-MAJOR-TREE.md](THE-TARGET-MAJOR-TREE.md) | you are editing under `languages/<target>/`, or putting a literal in a driver or a gate arm | **D17** (+ its declared limit) · **D20** |
| [SUBSTRATES-AND-PORTS.md](SUBSTRATES-AND-PORTS.md) | you are starting a port to a new substrate, or asking whether the methodology tier should move | the running record of what each of the nine compositions did to the substrate model |

## Where the rest of it lives

Two neighbours, neither of them memory, and the distinction is load-bearing:

- **`docs/ANTI-PATTERNS.md`** — the *catalog*: one named failure mode per entry, each with the
  commit that produced it. That is the **evidence base**; this directory is the **rules promoted
  from it**. An incident that has bitten once is an anti-pattern; a second incident in a
  different shape is what makes it a discipline ([METHODOLOGY.md] §*the promotion ladder*).
- **`docs/status/`** — dated, episodic, written once. *Where are we this week.* Nothing in here
  carries a date in its prose; when the truth changes, the entry is **rewritten**, because git
  holds the history and a memory file that accumulates is the file this directory exists to
  prevent.

## The rule that bounds this directory

> **An entry that could become a check SHOULD become one — and then it is deleted from here.**

Memory is where a finding waits **while it is still only prose**. It is not where findings
retire. So the maintenance pass is not *"trim the file"*; it is, per entry: *could a test, a lint
rule, a build assertion or a gate make this impossible instead of merely documented?* If yes,
that is a work item on `docs/status/LEDGER-generator-open-work.md`, and when it lands the entry
comes out, replaced at most by one line naming the check.

**This repo is unusually well placed to do that and has not yet done it here.** Every discipline
below D13 already names an enforcement point, so the promotion question for most of these is not
*"could this be a check"* but **"the check exists — is the prose still carrying anything the check
does not?"** That pass has not been run. It is `W-31`.

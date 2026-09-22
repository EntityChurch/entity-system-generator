# entity-system-generator — `make <verb>` over podman.
#
# The host needs `make`, `podman`, `python3` >= 3.11, POSIX `sh` and `git` -- declared in
# `tools/tooling.toml [host]` and checked by `make toolchain`. No mise, no just, no bespoke
# toolchain manager. Every verb has a `-native` opt-in that runs on the host toolchain
# instead of in a container, per AGENTS-STANDARD.
#
# THE COMPILED half runs in a container; the NEUTRAL half runs on the host and is
# STDLIB-ONLY. That boundary is the invariant (`docs/adr/0001-*`), not the list above it.
#
#   make build            compose + build one composition on one target
#   make test             the extension cells' unit tests
#   make conformance      validate-peer -category <ext> against the composed peer
#   make regression       the two-arm core-profile diff (bare vs composed)
#   make expectation      the composition's declared baseline vs the report beside it
#   make check            build + test + conformance + regression + expectation + plan-check
#                         + sdk-parity + structure + drivers + error-codes + citations
#                         + glue + req-coverage + toolchain + scale --check
#   make check-all        every (target, composition), then the cross-target gates
#   make plan-check       assert the resolved plan is reproducible
#   make probe            the host-seam probes (D13)
#   make parity           the chunking-parity gate, one corpus through every target
#   make type-parity      every port's type entities agree, by content hash (G-3)
#   make error-codes      every wire code a port emits is declared with an authority (D16)
#   make citations        every path a declaration file cites resolves (D18)
#   make toolchain        the host contract is declared, and the host half stays stdlib-only
#   make req-coverage     every requirement the spec declares is mapped to an instrument
#   make ext-checks       the authored extension checks, both arms (Kind C -- never a verdict)
#   make clean            remove every target's output/
#   make reap             remove any container this repo left behind (label-scoped, safe)
#
# THIS REPO CLEANS UP AFTER ITSELF. Every container it starts is labelled and time-bounded
# (`PODMAN_TIMEOUT`), so a hanging gate cannot strand one. `make reap` is the backstop and
# is safe to run at any time. Do not hand anyone a `ps | grep` and a list of PIDs.
#
# THE LAYOUT IS TARGET-MAJOR. A target is a unified bundle:
#
#   languages/<target>/{profile.toml, build, test, host-entry,
#                       extensions/<ext>/, compositions/<name>/, gates/<gate>/, output/}
#
# so the two coordinates are the target and the composition inside it:
#
#   make check TARGET=rust COMPOSITION=content

TARGET      ?= typescript
COMPOSITION ?= content

# ── the matrix is DATA, read off the filesystem ─────────────────────────────────
#
# Not a maintained list. `gates/README.md` inherits keystone's rule -- one runner, the
# matrix as data -- on their measured incident: 31 peers carried a `run-origination-core.sh`
# and 15 did not, for no reason anyone had declared, and the whole axis turned out to be
# one oracle flag nobody passed. Every list below is a `wildcard`, so a new target is a
# directory and never a Makefile edit.
TARGETS       = $(notdir $(wildcard languages/*))
COMPOSITIONS  = $(notdir $(wildcard languages/$(TARGET)/compositions/*))
PROBE_TARGETS  = $(patsubst languages/%/gates/host-seam/run,%,$(wildcard languages/*/gates/host-seam/run))
PARITY_TARGETS = $(patsubst languages/%/gates/chunking-parity/run,%,$(wildcard languages/*/gates/chunking-parity/run))
TYPES_TARGETS  = $(patsubst languages/%/gates/type-parity/run,%,$(wildcard languages/*/gates/type-parity/run))
# The extension axis of type-parity is a wildcard too: the gate is per (extension x arm),
# so a new contract directory joins the cohort without a Makefile edit, exactly as a new
# target directory does.
TYPES_EXTS     = $(notdir $(wildcard extension-contracts/*))

# ── the toolchain image comes from the PROFILE, which is now parsed ─────────────
#
# It used to be three `*_IMAGE` variables plus a 3-way `$(if $(filter ...))` chain, while
# `languages/<t>/profile.toml [toolchain] image` declared the same fact and was read by
# NOTHING -- twenty greps for the filename across the tree returned twenty docs and
# comments. That is AP-2: a fact computed correctly, then copied into a document that
# outlived it, with the executing copy silently winning. At forty targets the chain would
# have been a forty-way branch. `tools/compose.py` REFUSES a profile missing this field.
image_of = $(shell python3 -c "import tomllib,sys;print(tomllib.load(open('languages/$(1)/profile.toml','rb'))['toolchain']['image'])" 2>/dev/null)
IMAGE     = $(call image_of,$(TARGET))

ROOT      := $(CURDIR)
CHURCH    := $(abspath $(ROOT)/..)
REPO      := $(notdir $(ROOT))

# `--network=none` everywhere: nothing is fetched at build time. The sibling tree is
# mounted READ-ONLY and our own tree is remounted writable on top of it, so a relative
# `../entity-core-keystone` resolves exactly as it does on the host while staying
# unwritable. `--security-opt label=disable` rather than `:Z`: `:Z` would RELABEL
# another team's tree, which is a write to their tree even though it changes no bytes.
# EVERY CONTAINER THIS REPO STARTS CARRIES OUR LABEL, and it is not cosmetic: it is what
# makes `make reap` able to clean up exactly our own containers and provably nothing else.
# This box runs many concurrent sessions and several other projects' containers; a cleanup
# that matches on an image name, a mount path or a `ps | grep` would eventually catch one
# of theirs. A label we set is the only filter that cannot.
PODMAN_LABEL = entity-system-generator

PODMAN_RUN = podman run --rm --network=none --security-opt label=disable \
	--label "$(PODMAN_LABEL)=1" \
	-v "$(CHURCH):/church:ro" \
	-v "$(ROOT):/church/$(REPO)" \
	-w "/church/$(REPO)"

# ── the hang budget, and why it is a podman flag rather than a `timeout` ────────────────
#
# `tools/host-launch` boots a peer, runs a client against it, and HAD NO TIME BOUND AT ALL
# -- neither did any arm. So a client that hangs holds the container open forever, and the
# gate that hangs is `make ext-checks`, whose `rust` arm hangs on its first EXECUTE by
# construction today. Run it N times, strand N containers and N peer processes.
#
# That is exactly what happened: eighteen invocations over two days left seven live
# processes and three containers up for 39 hours, and the seat that made them could not
# clean them up -- process killing is denied here by fleet policy AND by a deny rule, so
# the mess landed on the operator. THE INSTRUMENT THAT CANNOT BOUND ITSELF IS THE DEFECT,
# not the policy that stopped us papering over it.
#
# `--timeout` is podman's own: conmon kills the container when the clock expires, so the
# cleanup is done by the thing that created it and needs no `kill`, no `timeout` binary,
# and no privilege this seat does not have. `timeout podman run ...` -- the previous
# session's approach -- signals the CLIENT and routinely leaves the container behind,
# which is how three of them survived a SIGKILL of their launcher.
#
# The value is generous on purpose: a false red costs the instrument (AP-4), and the
# measured worst case is ~2.5 min per arm on `rust`. This is a HANG bound, not a
# performance budget.
PODMAN_TIMEOUT ?= 900
RUN_BOUNDED    = $(PODMAN_RUN) --timeout $(PODMAN_TIMEOUT)

# `RUN` is BOUNDED, because every use of it launches a peer through `tools/host-launch`,
# which has no time bound of its own. `PODMAN_RUN` stays unbounded for `build`, where a
# cold `cargo` compile legitimately runs long and a bound would be a false red.
RUN     = $(RUN_BOUNDED) $(IMAGE)
TDIR    = languages/$(TARGET)
REPORTS = $(TDIR)/output/$(COMPOSITION)/reports
PLAN    = $(TDIR)/output/$(COMPOSITION)/PLAN.json
SYSTEM  = $(TDIR)/compositions/$(COMPOSITION)/SYSTEM.toml

# The gate categories are the COMPOSITION'S, read from the resolved plan, not a constant.
# They were `content` for the first two compositions and that was fine until a third one
# needed `type_system` as well -- because on its peer the types face installs and the
# handler face cannot, so the category that measures it is a different category. A driver
# that kept the constant would have run the one gate this composition cannot move and
# reported nothing.
CATEGORIES = $(shell python3 -c "import json;print(' '.join(json.load(open('$(PLAN)'))['gate'].get('categories',['content'])))" 2>/dev/null || echo content)

.PHONY: all build test conformance regression check check-all plan plan-check probe \
        parity clean sdk-parity structure drivers error-codes error-codes-control \
        scale scale-control type-parity glue glue-control \
        req-coverage req-coverage-control ext-checks ext-checks-control \
        expectation expectation-control diff-arms-control \
        citations citations-control toolchain toolchain-control \
        build-native test-native \
        conformance-native probe-native

all: check

# ── plan ────────────────────────────────────────────────────────────────────────
# Resolution is language-neutral, so it runs on the host's python3 (stdlib only,
# tomllib). It refuses I6/I7/I9 before anything is staged, and now also refuses a target
# whose profile is missing a field something executes.
plan:
	./tools/compose.py $(TDIR)/compositions/$(COMPOSITION)

plan-check: plan
	./tools/compose.py $(TDIR)/compositions/$(COMPOSITION) --check

# ── build / test / gate ─────────────────────────────────────────────────────────
#
# There is no LANGUAGE variable any more, and its absence is the point. It used to be
# DERIVED from the resolved plan so that `COMPOSITION=py-content LANGUAGE=typescript`
# could not be spelled. Under target-major the pair is a PATH:
# `languages/rust/compositions/content` either exists or it does not, so the mismatch has
# no location and the derivation hack is deleted rather than moved.
build: plan
	$(RUN) ./$(TDIR)/build $(COMPOSITION)

test:
	$(RUN) ./$(TDIR)/test $(COMPOSITION)

# Every category the composition declares, in BOTH arms. The bare arm is not optional
# here and it is not only a regression guard: the rust composition moves 6 checks in
# `type_system` and 3 in `content`, and without a baseline "6 of 446 pass" would be
# indistinguishable from "the peer already passed them".
#
# THE ROUND SET IS CLEARED FIRST, and that `rm -f` is the structural half of AP-22. A
# report is identified by its FILENAME and written in place, so a `ROUNDS=1` run left the
# previous run's `-2.json` on disk and the next `ROUNDS=2` diff read a report hours older
# than round 1 as a round of this run. Twelve of the tree's thirty-four round-sets were in
# that state when it was found, and the check it hid -- `history/w6_caller_cap_absent` --
# was reported as FLAKY rather than as a regression. `diff-arms.py` refuses the shape as
# well; deleting is what makes it unconstructible.
conformance:
	@mkdir -p $(REPORTS)
	@for c in $(CATEGORIES); do \
		rm -f $(REPORTS)/bare-$$c-*.json $(REPORTS)/composed-$$c-*.json; \
		for r in $$(seq 1 $(ROUNDS)); do \
			echo "conformance: $$c round $$r/$(ROUNDS) composed"; \
			$(RUN) ./tools/host-launch $(TARGET) $(COMPOSITION) \
				-category $$c -json-out /church/$(REPO)/$(REPORTS)/composed-$$c-$$r.json \
				>/dev/null 2>&1 || exit 1; \
			echo "conformance: $$c round $$r/$(ROUNDS) bare"; \
			$(RUN_BOUNDED) -e BARE=1 $(IMAGE) ./tools/host-launch $(TARGET) $(COMPOSITION) \
				-category $$c -json-out /church/$(REPO)/$(REPORTS)/bare-$$c-$$r.json \
				>/dev/null 2>&1 || exit 1; \
		done; \
		echo "=== $$c: bare vs composed ==="; \
		./tools/diff-arms.py --straddle $(SYSTEM) \
			--bare $$(for r in $$(seq 1 $(ROUNDS)); do echo $(REPORTS)/bare-$$c-$$r.json; done) \
			--composed $$(for r in $$(seq 1 $(ROUNDS)); do echo $(REPORTS)/composed-$$c-$$r.json; done) \
			|| exit 1; \
	done

# The guard for OUR second failure mode, which is one keystone never has: the peer was
# right and we broke it. Two arms differing by the composition and nothing else.
#
# ROUNDS defaults to 2 because one round cannot tell a flaky check from a regression,
# and it manufactured one on its second execution: a concurrency check whose verdict
# turns on a 50 ms floor that both arms straddle by under a millisecond. Raise it when
# a verdict matters.
#
# COST, measured rather than quoted from the first driver: ~35 s per arm per round on
# `typescript` and `python`, and **~2.5 min on `rust`**. The peer is not slower; the
# oracle drives the same 756 checks. A `make check TARGET=rust` is a ten-minute command,
# and knowing that before running it is the difference between waiting and assuming it hung.
ROUNDS ?= 2

regression:
	@mkdir -p $(REPORTS)
	@rm -f $(REPORTS)/bare-core-*.json $(REPORTS)/composed-core-*.json
	@for r in $$(seq 1 $(ROUNDS)); do \
		echo "regression: round $$r/$(ROUNDS) bare"; \
		$(RUN_BOUNDED) -e BARE=1 $(IMAGE) ./tools/host-launch $(TARGET) $(COMPOSITION) \
			-profile core -json-out /church/$(REPO)/$(REPORTS)/bare-core-$$r.json >/dev/null 2>&1; \
		echo "regression: round $$r/$(ROUNDS) composed"; \
		$(RUN) ./tools/host-launch $(TARGET) $(COMPOSITION) \
			-profile core -json-out /church/$(REPO)/$(REPORTS)/composed-core-$$r.json >/dev/null 2>&1; \
	done
	./tools/diff-arms.py --straddle $(SYSTEM) \
		--bare $$(for r in $$(seq 1 $(ROUNDS)); do echo $(REPORTS)/bare-core-$$r.json; done) \
		--composed $$(for r in $$(seq 1 $(ROUNDS)); do echo $(REPORTS)/composed-core-$$r.json; done)

# ── the SDK surface gate ────────────────────────────────────────────────────────
# OURS, because nobody upstream owns it (D16). Per EXTENSION and language-neutral, which
# is why it names an `extension-contracts/` directory and not a target: `[sdk_surface]`
# is the CROSS-PORT contract, and a comparison table sharded per port stops being a
# comparison. It reads each port's public entry point out of `languages/*/extensions/<ext>/`.
#
# Host python3, stdlib only, no container.
EXTENSION ?= extension-contracts/content

sdk-parity:
	./tools/sdk-parity.py $(EXTENSION)

# ── the error-code surface gate ─────────────────────────────────────────────────
# The second axis with no upstream authority (D16), and the one that LOOKED covered: the
# oracle's `content` category asserts exactly two codes and nothing anywhere asserts the
# rest. Added at the CONTENT v3.6 -> v3.7 re-pin, which is the event that produced the
# failure it catches -- three ports emitting `forbidden` after the spec had replaced it.
#
# `--strict` promotes every `unresolved` code to an error. Off by default so the gate is
# honest on the day it was written rather than green because it was scoped around what
# already passes; the flag is the switch that gets flipped when upstream pins them.
error-codes:
	./tools/check-error-codes.py

# D15's control, separate on purpose: it plants a bogus code and asserts each target's
# pattern extracts it. An instrument observed only passing is not an instrument.
error-codes-control:
	./tools/check-error-codes.py --self-test

# ── the requirement-coverage map ────────────────────────────────────────────────
# The axis with the MOST upstream coverage, and therefore the one nobody was asking about.
# `validate-peer`'s `history` category is 34 checks deep and cites HISTORY section numbers; its
# `content` category is 13. Neither answers — and nothing anywhere answered — how many of the
# spec's OWN §9.1 / §11 requirement rows those checks reach.
#
# It compares two inventories that both already exist (the spec's conformance section, and the
# `checks[]` of the reports we already produce) and requires `EXTENSION.toml [conformance]` to
# declare what measures each row. An undeclared row is a failure, so a re-pin cannot add or
# re-word a requirement unnoticed. It is NOT a second scorer and produces no conformance verdict.
#
# Its first run against the real contracts failed on a §11.4 row missed while transcribing the
# inventory by hand, which is the argument for the gate in one line.
req-coverage:
	./tools/req-coverage.py

req-coverage-control:
	./tools/req-coverage.py --self-test

# ── the authored extension checks ───────────────────────────────────────────────
# Kind C under keystone's VERIFICATION-ARCHITECTURE: authored from the SPEC at the oracle's
# own normative target, never from its source, and NEVER a conformance verdict -- the
# operator's standing condition is that an official green requires the suite we do not
# author. These exist because `make req-coverage` names 11 binding requirements measured by
# nothing, and a gap that is a list is worth more than a gap that is an argument.
#
# The definitions are LANGUAGE-NEUTRAL DATA (`extension-contracts/<ext>/checks/*.toml`);
# the arm is a transport binding that knows no extension by name. Adding an extension adds
# data; adding a target adds one arm. Check logic in an arm would be the per-cell quadrant,
# which `make scale` measures at 96% of the projection.
#
# BOTH ARMS ALWAYS. The rule that admits a check is that composed passes and bare does not:
# a check that reports the same verdict with the extension absent is measuring something
# else, which is exactly the shape of four of the thirteen checks in the oracle's own
# `content` category (AP-19). The arms are a `wildcard`, so a new target joins by adding
# `languages/<t>/gates/ext-checks/run` and never by editing this file.
EXTCHECK_TARGETS = $(patsubst languages/%/gates/ext-checks/run,%,$(wildcard languages/*/gates/ext-checks/run))
EXTCHECK_OUT     = output/ext-checks
EXTCHECK_COMP   ?= content-history

# The corpus travels as CANONICAL ECF, not JSON, and the encoder is a peer's own codec
# (`tools/tooling.toml [ecf_codec]`, `docs/DESIGN-THE-CBOR-INTERCHANGE-LAYER.md`). The emit
# step therefore runs IN A CONTAINER: `import entity_core` pulls the peer's Ed25519
# dependency through its package `__init__`, so the codec cannot be loaded on a bare host --
# which is a finding about the library's separability, recorded where it was measured.
ECF_TOOLCHAIN = $(shell python3 -c "import tomllib;print(tomllib.load(open('tools/tooling.toml','rb'))['ecf_codec']['toolchain'])")
ECF_IMAGE     = $(call image_of,$(ECF_TOOLCHAIN))

ext-checks:
	@echo "ext-checks arms: $(EXTCHECK_TARGETS)  composition: $(EXTCHECK_COMP)"
	@mkdir -p $(EXTCHECK_OUT)
	$(PODMAN_RUN) $(ECF_IMAGE) ./gates/ext-checks/schema.py --emit $(EXTCHECK_OUT)/checks.cbor
	@for t in $(EXTCHECK_TARGETS); do \
		img=$$(python3 -c "import tomllib;print(tomllib.load(open('languages/$$t/profile.toml','rb'))['toolchain']['image'])"); \
		for arm in composed bare; do \
			echo "=== ext-checks: $$t / $(EXTCHECK_COMP) / $$arm ==="; \
			bare_env=""; [ "$$arm" = bare ] && bare_env="-e BARE=1"; \
			$(RUN_BOUNDED) $$bare_env \
				-e CLIENT=./languages/$$t/gates/ext-checks/run \
				-e EXT_CHECKS_DEFS=/church/$(REPO)/$(EXTCHECK_OUT)/checks.cbor \
				-e EXT_CHECKS_OUT=/church/$(REPO)/$(EXTCHECK_OUT)/$$t-$$arm.cbor \
				$$img ./tools/host-launch $$t $(EXTCHECK_COMP) || exit 1; \
		done; \
	done
	$(PODMAN_RUN) $(ECF_IMAGE) ./gates/ext-checks/compare.py \
		--expect-arms "$(shell echo '$(EXTCHECK_TARGETS)' | tr ' ' ',')" \
		--all-targets "$(shell echo '$(TARGETS)' | tr ' ' ',')" \
		--composition $(EXTCHECK_COMP) \
		$(EXTCHECK_OUT)/*-composed.cbor $(EXTCHECK_OUT)/*-bare.cbor

ext-checks-control:
	./gates/ext-checks/compare.py --self-test
	./gates/ext-checks/schema.py --self-test

# ── the temporal baseline ───────────────────────────────────────────────────────
# AP-18's owed enforcement point. `conformance` and `regression` are two-arm diffs and
# their baseline is in the ARM, never in TIME -- so a composition that STOPS doing
# something it used to do reads as `bare FAIL vs composed FAIL`, which is no difference,
# which is not a regression. `history/w6_caller_cap_absent` went PASS -> FAIL on two
# targets with every gate in this tree green.
#
# `--require` is the no-silent-caps rule, said by the caller that knows: the composition
# `make check` just ran MUST have reports, or the gate refuses rather than reporting a
# clean verdict over the other five. A composition with no reports at all is normal on a
# clean checkout and is reported and counted, never failed -- a false red costs the
# instrument.
expectation:
	./tools/check-expectation.py --require $(TDIR)/compositions/$(COMPOSITION)

expectation-control:
	./tools/check-expectation.py --self-test

# D15's control for the regression differ itself, which had none until AP-22: it plants
# an out-of-order round pair (the live 17:41/13:05 shape) and requires the refusal.
diff-arms-control:
	./tools/diff-arms.py --self-test

check: build test conformance regression expectation plan-check sdk-parity structure drivers error-codes citations glue req-coverage toolchain
	./tools/scale-report.py --check

# Every (target, composition), then the cross-target gates LAST because they need every
# port staged. Both loops are wildcards over the tree.
check-all:
	@for t in $(TARGETS); do \
		for c in $$(ls languages/$$t/compositions 2>/dev/null); do \
			echo "=== $$t / $$c ==="; \
			$(MAKE) --no-print-directory check TARGET=$$t COMPOSITION=$$c || exit 1; \
		done; \
	done
	@echo "=== cross-target ==="
	$(MAKE) --no-print-directory parity
	$(MAKE) --no-print-directory type-parity

# ── the structure gates ─────────────────────────────────────────────────────────
# Both are OURS and both are the axis-with-no-upstream-authority kind (D16), so both
# ship with executed controls and a vacuity refusal.
#
#   structure  the mirror rule -- a per-target subtree holds only units the root declares
#   drivers    a driver literal that differs across targets is an undeclared profile field
structure:
	./tools/check-structure.py

drivers:
	./tools/check-drivers.py

# ── the citation gate ───────────────────────────────────────────────────────────
# D18. D13's enforcement point is a citation and D14's is a citation, and until this
# existed nothing checked that the cited PATH was real -- so a claim could carry a
# perfectly-formed citation to a file that had never been written. Its first run found
# three, including a `probe =` on the block recording the most consequential substrate
# fact this repo has measured, naming a gate that has never existed.
citations:
	./tools/check-citations.py

# ── the host contract ───────────────────────────────────────────────────────────
# The charter said `make` + `podman` and nothing else; `make check` runs eleven
# `tools/*.py` on the host and the Makefile itself shells `python3 -c` before it can pick
# an image. Nobody had ever declared Python as the tooling language -- checked, and there
# was no such statement in the tree. Python and Bash are DE FACTO dependencies across these
# projects -- reached for despite the stated standard, which is a discipline failure at
# project scale and NOT a sanction. Written up as `docs/adr/0001-the-host-toolchain-contract.md`.
#
# THE INVARIANT IS NOT THE INVENTORY. What this gates is the boundary: the host half is
# STDLIB-ONLY, and anything needing a third-party library runs in a container. That was
# tested for real on 2026-09-08 -- the ECF codec cannot load on a bare host, and the two
# entry points reaching it were containerised rather than the host contract widened.
#
# It reads TWO doors, because the obvious one is not enough: an AST scan of `import`
# statements reports this tree as 100% stdlib and is right BY ACCIDENT -- the one genuine
# third-party dependency arrives through `__import__(decl["package"])` with its name held
# in a TOML file. Caught in review, before the first run.
toolchain:
	./tools/check-toolchain.py

# D15: four planted defects, one per rule, all four required to be caught. Separate on
# purpose -- an instrument observed only passing is not an instrument.
toolchain-control:
	./tools/check-toolchain.py --self-test

# ── the cost model ──────────────────────────────────────────────────────────────
# What grows, and by what multiplier. Every file in the tree multiplies by exactly one
# thing (1, E, T, E*T, T*C) and its LOCATION decides which, so the cost model is a
# classification of the tree rather than an opinion about it.
#
# `make scale` is a REPORT and is deliberately not in `make check`: a gate needs a
# threshold and there is no evidence yet for what a per-cell budget should be. Inventing
# one so a gate becomes possible is the speculation the promotion ladder refuses.
#
# `--check` IS in `make check`, and it gates the one invariant here that needs no
# threshold: every tracked path is classified. That is D16's question in executable form
# -- when a new kind of artifact appears in this tree, what reads it?
scale:
	./tools/scale-report.py

scale-control:
	./tools/scale-report.py --self-test

# ── the glue gate ───────────────────────────────────────────────────────────────
# `make scale` measures MASS per multiplier class, and mass is the wrong instrument for
# this: a neutral file that grows a 46-way branch is still one file in the `neutral`
# column -- x1 by location and O(T) by edit cost. This measures IDENTITY LEAKAGE.
#
#   a language-neutral file names no specific TARGET      <- FAILS
#   a per-target file names no specific EXTENSION         <- CENSUS, see the tool
#
# Its first run found `tools/sdk-parity.py` carrying three per-target EXTRACTORS behind a
# {target: fn} dispatch plus a {target: filename} table -- ~120 lines of per-language
# parsing in the neutral half, which at 46 targets is a 46-way branch in the one file whose
# job is to be finished. Both halves moved to the homes existing rules already named:
# the value to `profile.toml` (D17), the procedure to `languages/<t>/gates/sdk-surface/`
# (§1.2b). Output verified name-for-name identical across the move.
glue:
	./tools/check-glue.py

glue-control:
	./tools/check-glue.py --self-test

# D15's control, separate on purpose: it plants two unresolvable citations and requires
# both to be caught. An instrument observed only passing is not an instrument.
citations-control:
	./tools/check-citations.py --self-test

# ── the host-seam probes ────────────────────────────────────────────────────────
# D13: a capability claim cites an executed probe, or it reads `unknown`.
#
# One uniform entry point per (gate x target) -- `languages/<t>/gates/host-seam/run`.
# This target used to be three hand-written invocations with three different calling
# conventions; the conventions moved into the arms, where they are each one target's
# business, and what is left is an iteration.
probe:
	@echo "host-seam arms: $(PROBE_TARGETS)"
	@for t in $(PROBE_TARGETS); do \
		echo "=== host-seam: $$t ==="; \
		$(RUN_BOUNDED) $$(python3 -c "import tomllib;print(tomllib.load(open('languages/$$t/profile.toml','rb'))['toolchain']['image'])") \
			./languages/$$t/gates/host-seam/run || exit 1; \
	done

# ── chunking parity ─────────────────────────────────────────────────────────────
# One corpus, every target's transcription of §3.6, compared byte for byte.
#
# §3.7 classifies §3.2/§3.6 as CONFORMANCE algorithms, and a divergence between two of
# them does not fail loudly: every blob still reassembles and the peers simply stop
# deduplicating with each other. No error, no status, and -- checked at ed9b547 --
# no check in the oracle's `content` category chunks anything at all. §3.6.5's cross-impl
# vectors are a Stage-4 byproduct that does not exist yet.
#
# Requires every arm's composition staged (`make build TARGET=<t>`), because each arm
# consumes its port THROUGH THE PACKAGING BOUNDARY rather than out of the source tree --
# the same discipline the host-seam probes follow. The arms REFUSE rather than skip when
# their stage is missing.
PARITY_OUT       = output/chunking-parity
PARITY_TARGET   ?= 4096
# The floor is the number of arms that exist, and the arms are ECHOED before the run:
# `gates/README.md` -- no silent caps. A dropped arm changes the printed list, so the
# verdict can never quietly be reached over fewer ports than it claims.
PARITY_MIN_PORTS ?= $(words $(PARITY_TARGETS))

parity:
	@echo "chunking-parity arms ($(PARITY_MIN_PORTS)): $(PARITY_TARGETS)"
	./gates/chunking-parity/corpus.py --out $(PARITY_OUT)/corpus.bin
	@mkdir -p $(PARITY_OUT)
	@for t in $(PARITY_TARGETS); do \
		echo "=== chunking-parity: $$t ==="; \
		$(RUN_BOUNDED) $$(python3 -c "import tomllib;print(tomllib.load(open('languages/$$t/profile.toml','rb'))['toolchain']['image'])") \
			./languages/$$t/gates/chunking-parity/run \
			/church/$(REPO)/$(PARITY_OUT)/corpus.bin $(PARITY_TARGET) \
			> $(PARITY_OUT)/$$t.json || exit 1; \
	done
	./gates/chunking-parity/compare.py --min-ports $(PARITY_MIN_PORTS) $(PARITY_OUT)/*.json

# ── type parity ─────────────────────────────────────────────────────────────────
# Every port's materialised type entities, compared by the PEER'S OWN content hash and by
# a normalisation of the field map. `REVIEW-CYCLE-2` §4.2, routed as G-3: the oracle's
# `type_*` checks assert that the type path RESOLVES and never look at what is there, so a
# port with a subtly wrong field map scores identically to one that got it right — while
# silently failing to dedup that type with every other peer.
#
# The extension is an axis here, unlike chunking-parity: types are per-extension, so the
# runner is a double loop over two wildcards and the counts are ECHOED before each verdict.
#
# TYPES_MIN_PORTS floors at the number of arms that EXIST rather than at a constant, and
# a target whose arm cannot run for the day (a peer mid-rebuild, a missing stage) shows up
# as a smaller echoed list rather than as a quietly narrower verdict.
TYPES_OUT        = output/type-parity
TYPES_MIN_PORTS ?= $(words $(TYPES_TARGETS))

type-parity:
	@echo "type-parity arms ($(TYPES_MIN_PORTS)): $(TYPES_TARGETS)"
	@echo "type-parity extensions: $(TYPES_EXTS)"
	@mkdir -p $(TYPES_OUT)
	@for e in $(TYPES_EXTS); do \
		rm -f $(TYPES_OUT)/$$e-*.json; \
		for t in $(TYPES_TARGETS); do \
			echo "=== type-parity: $$e x $$t ==="; \
			$(RUN_BOUNDED) $$(python3 -c "import tomllib;print(tomllib.load(open('languages/$$t/profile.toml','rb'))['toolchain']['image'])") \
				./languages/$$t/gates/type-parity/run $$e \
				> $(TYPES_OUT)/$$e-$$t.json || exit 1; \
		done; \
		./gates/type-parity/compare.py --min-ports $(TYPES_MIN_PORTS) \
			$(TYPES_OUT)/$$e-*.json || exit 1; \
	done

# ── -native opt-ins ─────────────────────────────────────────────────────────────
# Same drivers, host toolchain. They will disagree with the container when the host's
# node or python differs from the image's; that disagreement is a real signal, so
# neither is silently substituted for the other.
build-native: plan
	GENERATOR_ROOT=$(ROOT) ./$(TDIR)/build $(COMPOSITION)

test-native:
	GENERATOR_ROOT=$(ROOT) ./$(TDIR)/test $(COMPOSITION)

conformance-native:
	GENERATOR_ROOT=$(ROOT) ./tools/host-launch $(TARGET) $(COMPOSITION) -category content

probe-native:
	./$(TDIR)/gates/host-seam/run

# Every target's output, plus the cross-target output at the root.
clean:
	rm -rf output/ languages/*/output/

# ── reap: clean up after ourselves, in one command ──────────────────────────────
#
# THE RULE THIS EXISTS FOR: this repo cleans up its own containers. It does not hand the
# operator a `ps | grep` and a list of PIDs to work through -- that is not a cleanup
# procedure, it is a mess with instructions attached, and it happened.
#
# Scoped by OUR LABEL and nothing else. Not an image name, not a mount path, not a process
# name: this box runs several other projects' containers and many concurrent sessions, and
# every one of those filters would eventually match one of theirs. `--filter label=` can
# only match a container this Makefile started.
#
# It prints what it will remove before removing it, and prints the count afterwards, so a
# run that reaps nothing is distinguishable from a run that could not look -- keystone's
# survey printed `absent` where it meant `could not look` and it cost five peers (D14).
#
# `make reap` is safe to run at any time, including while nothing is wrong. With
# `--timeout` on the bounded runs, it should never find anything; if it does, that is a
# gate that outran its budget and worth knowing about.
.PHONY: reap
reap:
	@ids=$$(podman ps -aq --filter "label=$(PODMAN_LABEL)=1"); \
	if [ -z "$$ids" ]; then \
		echo "reap: 0 containers labelled $(PODMAN_LABEL) -- nothing of ours is running"; \
	else \
		echo "reap: removing $$(echo $$ids | wc -w) container(s) labelled $(PODMAN_LABEL):"; \
		podman ps -a --filter "label=$(PODMAN_LABEL)=1" \
			--format "  {{.Names}}  {{.Status}}  {{.Command}}"; \
		podman rm -f $$ids >/dev/null; \
		echo "reap: done, $$(podman ps -aq --filter "label=$(PODMAN_LABEL)=1" | wc -l) remaining"; \
	fi

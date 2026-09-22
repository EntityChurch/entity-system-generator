# entity-system-generator — `make <verb>` over podman.
#
# The host needs `make` + `podman` and nothing else. No mise, no just, no bespoke
# toolchain manager. Every verb has a `-native` opt-in that runs on the host toolchain
# instead of in a container, per AGENTS-STANDARD.
#
#   make build            compose + build one composition on one target
#   make test             the extension cells' unit tests
#   make conformance      validate-peer -category <ext> against the composed peer
#   make regression       the two-arm core-profile diff (bare vs composed)
#   make check            build + test + conformance + regression + plan-check + sdk-parity
#                         + structure + drivers + error-codes + citations + glue
#                         + req-coverage + scale --check
#   make check-all        every (target, composition), then the cross-target gates
#   make plan-check       assert the resolved plan is reproducible
#   make probe            the host-seam probes (D13)
#   make parity           the chunking-parity gate, one corpus through every target
#   make type-parity      every port's type entities agree, by content hash (G-3)
#   make error-codes      every wire code a port emits is declared with an authority (D16)
#   make citations        every path a declaration file cites resolves (D18)
#   make req-coverage     every requirement the spec declares is mapped to an instrument
#   make clean            remove every target's output/
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
PODMAN_RUN = podman run --rm --network=none --security-opt label=disable \
	-v "$(CHURCH):/church:ro" \
	-v "$(ROOT):/church/$(REPO)" \
	-w "/church/$(REPO)"

RUN     = $(PODMAN_RUN) $(IMAGE)
TDIR    = languages/$(TARGET)
REPORTS = $(TDIR)/output/$(COMPOSITION)/reports
PLAN    = $(TDIR)/output/$(COMPOSITION)/PLAN.json

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
        req-coverage req-coverage-control \
        citations citations-control \
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
conformance:
	@mkdir -p $(REPORTS)
	@for c in $(CATEGORIES); do \
		for r in $$(seq 1 $(ROUNDS)); do \
			echo "conformance: $$c round $$r/$(ROUNDS) composed"; \
			$(RUN) ./tools/host-launch $(TARGET) $(COMPOSITION) \
				-category $$c -json-out /church/$(REPO)/$(REPORTS)/composed-$$c-$$r.json \
				>/dev/null 2>&1 || exit 1; \
			echo "conformance: $$c round $$r/$(ROUNDS) bare"; \
			$(PODMAN_RUN) -e BARE=1 $(IMAGE) ./tools/host-launch $(TARGET) $(COMPOSITION) \
				-category $$c -json-out /church/$(REPO)/$(REPORTS)/bare-$$c-$$r.json \
				>/dev/null 2>&1 || exit 1; \
		done; \
		echo "=== $$c: bare vs composed ==="; \
		./tools/diff-arms.py \
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
	@for r in $$(seq 1 $(ROUNDS)); do \
		echo "regression: round $$r/$(ROUNDS) bare"; \
		$(PODMAN_RUN) -e BARE=1 $(IMAGE) ./tools/host-launch $(TARGET) $(COMPOSITION) \
			-profile core -json-out /church/$(REPO)/$(REPORTS)/bare-core-$$r.json >/dev/null 2>&1; \
		echo "regression: round $$r/$(ROUNDS) composed"; \
		$(RUN) ./tools/host-launch $(TARGET) $(COMPOSITION) \
			-profile core -json-out /church/$(REPO)/$(REPORTS)/composed-core-$$r.json >/dev/null 2>&1; \
	done
	./tools/diff-arms.py \
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

check: build test conformance regression plan-check sdk-parity structure drivers error-codes citations glue req-coverage
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
		$(PODMAN_RUN) $$(python3 -c "import tomllib;print(tomllib.load(open('languages/$$t/profile.toml','rb'))['toolchain']['image'])") \
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
		$(PODMAN_RUN) $$(python3 -c "import tomllib;print(tomllib.load(open('languages/$$t/profile.toml','rb'))['toolchain']['image'])") \
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
			$(PODMAN_RUN) $$(python3 -c "import tomllib;print(tomllib.load(open('languages/$$t/profile.toml','rb'))['toolchain']['image'])") \
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

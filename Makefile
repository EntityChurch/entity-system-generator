# entity-system-generator — `make <verb>` over podman.
#
# The host needs `make` + `podman` and nothing else. No mise, no just, no bespoke
# toolchain manager. Every verb has a `-native` opt-in that runs on the host toolchain
# instead of in a container, per AGENTS-STANDARD.
#
#   make build            compose + build the default composition
#   make test             the extension cells' unit tests
#   make conformance      validate-peer -category content against the composed peer
#   make regression       the two-arm core-profile diff (bare vs composed)
#   make check            build + test + conformance + regression
#   make plan-check       assert the resolved plan is reproducible
#   make clean            remove output/
#
# Override the composition:  make check COMPOSITION=ts-content

COMPOSITION ?= ts-content

# LANGUAGE is DERIVED from the resolved plan, never passed alongside the composition.
# A composition already names its peer's language; accepting it twice is the drift D14 is
# about, and the failure would be silent — `make check COMPOSITION=py-content` with a
# stale LANGUAGE would run the typescript driver against a python stage and report the
# import error as a build failure.
LANGUAGE = $(shell python3 -c "import json,sys; print(json.load(open('output/$(COMPOSITION)/PLAN.json'))['language'])" 2>/dev/null || echo UNRESOLVED)

ROOT      := $(CURDIR)
CHURCH    := $(abspath $(ROOT)/..)
REPO      := $(notdir $(ROOT))

# The node toolchain is ANOTHER TEAM'S IMAGE, used read-only and recorded as a
# dependency rather than assumed. See languages/typescript/profile.toml [toolchain].
NODE_IMAGE   ?= localhost/entity-core-keystone/node24:latest
PYTHON_IMAGE ?= localhost/entity-core-keystone/python-toolchain:latest
RUST_IMAGE   ?= localhost/entity-core-keystone/rust-toolchain:latest

# `--network=none` everywhere: nothing is fetched at build time. The sibling tree is
# mounted READ-ONLY and our own tree is remounted writable on top of it, so a relative
# `../entity-core-keystone` resolves exactly as it does on the host while staying
# unwritable. `--security-opt label=disable` rather than `:Z`: `:Z` would RELABEL
# another team's tree, which is a write to their tree even though it changes no bytes.
PODMAN_RUN = podman run --rm --network=none --security-opt label=disable \
	-v "$(CHURCH):/church:ro" \
	-v "$(ROOT):/church/$(REPO)" \
	-w "/church/$(REPO)"

NODE_RUN = $(PODMAN_RUN) $(NODE_IMAGE)
PY_RUN   = $(PODMAN_RUN) $(PYTHON_IMAGE)
RUST_RUN = $(PODMAN_RUN) $(RUST_IMAGE)

# The image the composition's own language needs. `make` resolves this lazily, so the
# plan only has to exist by the time a recipe runs — which `build` guarantees via `plan`.
LANG_IMAGE = $(if $(filter python,$(LANGUAGE)),$(PYTHON_IMAGE),\
             $(if $(filter rust,$(LANGUAGE)),$(RUST_IMAGE),$(NODE_IMAGE)))
LANG_RUN   = $(PODMAN_RUN) $(LANG_IMAGE)

REPORTS = output/$(COMPOSITION)/reports

# The gate categories are the COMPOSITION'S, read from the resolved plan, not a constant.
# They were `content` for the first two compositions and that was fine until a third one
# needed `type_system` as well — because on its peer the types face installs and the
# handler face cannot, so the category that measures it is a different category. A driver
# that kept the constant would have run the one gate this composition cannot move and
# reported nothing.
CATEGORIES = $(shell python3 -c "import json;print(' '.join(json.load(open('output/$(COMPOSITION)/PLAN.json'))['gate'].get('categories',['content'])))" 2>/dev/null || echo content)

.PHONY: all build test conformance regression check plan plan-check probe clean \
        sdk-parity build-native test-native conformance-native probe-native

all: check

.PHONY: check-all

# ── plan ────────────────────────────────────────────────────────────────────────
# Resolution is language-neutral, so it runs on the host's python3 (stdlib only,
# tomllib). It refuses I6/I7/I9 before anything is staged.
plan:
	./tools/compose.py compositions/$(COMPOSITION)

plan-check: plan
	./tools/compose.py compositions/$(COMPOSITION) --check

# ── build / test / gate ─────────────────────────────────────────────────────────
build: plan
	$(LANG_RUN) ./languages/$(LANGUAGE)/build $(COMPOSITION)

test:
	$(LANG_RUN) ./languages/$(LANGUAGE)/test $(COMPOSITION)

# Every category the composition declares, in BOTH arms. The bare arm is not optional
# here and it is not only a regression guard: `rs-content` moves 6 checks in
# `type_system` and 3 in `content`, and without a baseline "6 of 446 pass" would be
# indistinguishable from "the peer already passed them".
conformance:
	@mkdir -p $(REPORTS)
	@for c in $(CATEGORIES); do \
		for r in $$(seq 1 $(ROUNDS)); do \
			echo "conformance: $$c round $$r/$(ROUNDS) composed"; \
			$(LANG_RUN) ./languages/$(LANGUAGE)/host-launch $(COMPOSITION) \
				-category $$c -json-out /church/$(REPO)/$(REPORTS)/composed-$$c-$$r.json \
				>/dev/null 2>&1 || exit 1; \
			echo "conformance: $$c round $$r/$(ROUNDS) bare"; \
			$(PODMAN_RUN) -e BARE=1 $(LANG_IMAGE) ./languages/$(LANGUAGE)/host-launch $(COMPOSITION) \
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
# oracle drives the same 756 checks. The difference is that `--profile core` on this
# peer spends most of its time in the categories the other two answer from a warm JIT.
# A `make check COMPOSITION=rs-content` is a ten-minute command, and knowing that
# before running it is the difference between waiting and assuming it hung.
ROUNDS ?= 2

regression:
	@mkdir -p $(REPORTS)
	@for r in $$(seq 1 $(ROUNDS)); do \
		echo "regression: round $$r/$(ROUNDS) bare"; \
		$(PODMAN_RUN) -e BARE=1 $(LANG_IMAGE) ./languages/$(LANGUAGE)/host-launch $(COMPOSITION) \
			-profile core -json-out /church/$(REPO)/$(REPORTS)/bare-core-$$r.json >/dev/null 2>&1; \
		echo "regression: round $$r/$(ROUNDS) composed"; \
		$(LANG_RUN) ./languages/$(LANGUAGE)/host-launch $(COMPOSITION) \
			-profile core -json-out /church/$(REPO)/$(REPORTS)/composed-core-$$r.json >/dev/null 2>&1; \
	done
	./tools/diff-arms.py \
		--bare $$(for r in $$(seq 1 $(ROUNDS)); do echo $(REPORTS)/bare-core-$$r.json; done) \
		--composed $$(for r in $$(seq 1 $(ROUNDS)); do echo $(REPORTS)/composed-core-$$r.json; done)

# ── the SDK surface gate ────────────────────────────────────────────────────────
# OURS, because nobody upstream owns it. arch does not mandate the SDK surface and that
# is correct -- conformance lives on the wire. But we generate N ports of one extension
# and we want them to be the same extension, so the standard is ours to set.
#
# Host python3, stdlib only, no container: it reads three source files and a TOML block.
# EXTENSION is the extension directory, not the composition -- this axis is per-extension
# and language-neutral, like `plan`.
EXTENSION ?= extensions/content

sdk-parity:
	./tools/sdk-parity.py $(EXTENSION)

check: build test conformance regression plan-check sdk-parity

# Every composition, in sequence. The retarget claim is "a composition names things and
# declares nothing new", and this target is what would fail if that stopped being true.
COMPOSITIONS ?= ts-content py-content rs-content
check-all:
	@for c in $(COMPOSITIONS); do \
		echo "=== $$c ==="; \
		$(MAKE) --no-print-directory check COMPOSITION=$$c || exit 1; \
	done
	@# Cross-port gates run LAST, because they need every port staged. `parity` is the
	@# one instrument in the ecosystem that puts one corpus through more than one
	@# transcription of §3.6 -- see the target for why nothing upstream does.
	@echo "=== cross-port ==="
	$(MAKE) --no-print-directory parity

# ── the host-seam probes ────────────────────────────────────────────────────────
# D13: a capability claim cites an executed probe, or it reads `unknown`.
probe:
	$(NODE_RUN) node gates/host-seam/probe-seam.mjs
	$(PY_RUN) sh -c 'cd gates/host-seam && python probe-seam.py \
		--peer-root /church/entity-core-keystone/protocol-generator/python'
	$(RUST_RUN) sh gates/host-seam/rust/probe-seam-rust.sh

# ── chunking parity ─────────────────────────────────────────────────────────────
# One corpus, three transcriptions of §3.6, compared byte for byte.
#
# §3.7 classifies §3.2/§3.6 as CONFORMANCE algorithms, and a divergence between two of
# them does not fail loudly: every blob still reassembles and the peers simply stop
# deduplicating with each other. No error, no status, and -- checked at ed9b547 --
# no check in the oracle's `content` category chunks anything at all. §3.6.5's cross-impl
# vectors are a Stage-4 byproduct that does not exist yet.
#
# Requires all three compositions staged (`make build COMPOSITION=<c>` for each), because
# each arm consumes its port THROUGH THE PACKAGING BOUNDARY rather than out of the source
# tree -- the same discipline the host-seam probes follow.
PARITY_OUT = output/chunking-parity
PARITY_TARGET ?= 4096

.PHONY: parity
parity:
	./gates/chunking-parity/corpus.py --out $(PARITY_OUT)/corpus.bin
	@# The node arm is STAGED, not run in place: ESM resolves a bare specifier relative
	@# to the importing FILE, so a probe run from outside the stage cannot see the staged
	@# package however the cwd is set. Copying it in is what makes `@entity-core/...`
	@# resolve through the package's own `exports` map, which is the point of the arm.
	cp gates/chunking-parity/probe.mjs output/ts-content/build/parity-probe.mjs
	$(NODE_RUN) sh -c 'cd output/ts-content/build && node parity-probe.mjs \
		/church/$(REPO)/$(PARITY_OUT)/corpus.bin $(PARITY_TARGET)' > $(PARITY_OUT)/typescript.json
	$(PY_RUN) sh -c 'PYTHONPATH=/church/$(REPO)/output/py-content/build \
		PYTHONDONTWRITEBYTECODE=1 python3 gates/chunking-parity/probe.py \
		$(PARITY_OUT)/corpus.bin $(PARITY_TARGET)' > $(PARITY_OUT)/python.json
	$(RUST_RUN) sh -c 'CARGO_HOME=/church/$(REPO)/output/.cargo-home \
		CARGO_TARGET_DIR=/church/$(REPO)/output/.parity-target \
		sh -c "cd gates/chunking-parity/rust && cargo run --offline --quiet -- \
		/church/$(REPO)/$(PARITY_OUT)/corpus.bin $(PARITY_TARGET)"' > $(PARITY_OUT)/rust.json
	./gates/chunking-parity/compare.py --min-ports 3 $(PARITY_OUT)/*.json

# ── -native opt-ins ─────────────────────────────────────────────────────────────
# Same drivers, host toolchain. They will disagree with the container when the host's
# node or python differs from the image's; that disagreement is a real signal, so
# neither is silently substituted for the other.
build-native: plan
	GENERATOR_ROOT=$(ROOT) ./languages/$(LANGUAGE)/build $(COMPOSITION)

test-native:
	GENERATOR_ROOT=$(ROOT) ./languages/$(LANGUAGE)/test $(COMPOSITION)

conformance-native:
	GENERATOR_ROOT=$(ROOT) ./languages/$(LANGUAGE)/host-launch $(COMPOSITION) -category content

probe-native:
	node gates/host-seam/probe-seam.mjs

clean:
	rm -rf output/

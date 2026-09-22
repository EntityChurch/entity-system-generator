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
LANGUAGE    ?= typescript

ROOT      := $(CURDIR)
CHURCH    := $(abspath $(ROOT)/..)
REPO      := $(notdir $(ROOT))

# The node toolchain is ANOTHER TEAM'S IMAGE, used read-only and recorded as a
# dependency rather than assumed. See languages/typescript/profile.toml [toolchain].
NODE_IMAGE   ?= localhost/entity-core-keystone/node24:latest
PYTHON_IMAGE ?= localhost/entity-core-keystone/python-toolchain:latest

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

REPORTS = output/$(COMPOSITION)/reports

.PHONY: all build test conformance regression check plan plan-check probe clean \
        build-native test-native conformance-native probe-native

all: check

# ── plan ────────────────────────────────────────────────────────────────────────
# Resolution is language-neutral, so it runs on the host's python3 (stdlib only,
# tomllib). It refuses I6/I7/I9 before anything is staged.
plan:
	./tools/compose.py compositions/$(COMPOSITION)

plan-check: plan
	./tools/compose.py compositions/$(COMPOSITION) --check

# ── build / test / gate ─────────────────────────────────────────────────────────
build: plan
	$(NODE_RUN) ./languages/$(LANGUAGE)/build $(COMPOSITION)

test:
	$(NODE_RUN) ./languages/$(LANGUAGE)/test $(COMPOSITION)

conformance:
	@mkdir -p $(REPORTS)
	$(NODE_RUN) ./languages/$(LANGUAGE)/host-launch $(COMPOSITION) \
		-category content -json-out /church/$(REPO)/$(REPORTS)/content.json

# The guard for OUR second failure mode, which is one keystone never has: the peer was
# right and we broke it. Two arms differing by the composition and nothing else.
#
# ROUNDS defaults to 2 because one round cannot tell a flaky check from a regression,
# and it manufactured one on its second execution: a concurrency check whose verdict
# turns on a 50 ms floor that both arms straddle by under a millisecond. Raise it when
# a verdict matters; the run is ~35 s per arm per round.
ROUNDS ?= 2

regression:
	@mkdir -p $(REPORTS)
	@for r in $$(seq 1 $(ROUNDS)); do \
		echo "regression: round $$r/$(ROUNDS) bare"; \
		$(PODMAN_RUN) -e BARE=1 $(NODE_IMAGE) ./languages/$(LANGUAGE)/host-launch $(COMPOSITION) \
			-profile core -json-out /church/$(REPO)/$(REPORTS)/bare-core-$$r.json >/dev/null 2>&1; \
		echo "regression: round $$r/$(ROUNDS) composed"; \
		$(NODE_RUN) ./languages/$(LANGUAGE)/host-launch $(COMPOSITION) \
			-profile core -json-out /church/$(REPO)/$(REPORTS)/composed-core-$$r.json >/dev/null 2>&1; \
	done
	./tools/diff-arms.py \
		--bare $$(for r in $$(seq 1 $(ROUNDS)); do echo $(REPORTS)/bare-core-$$r.json; done) \
		--composed $$(for r in $$(seq 1 $(ROUNDS)); do echo $(REPORTS)/composed-core-$$r.json; done)

check: build test conformance regression plan-check

# ── the host-seam probes ────────────────────────────────────────────────────────
# D13: a capability claim cites an executed probe, or it reads `unknown`.
probe:
	$(NODE_RUN) node gates/host-seam/probe-seam.mjs
	$(PY_RUN) sh -c 'cd gates/host-seam && python probe-seam.py \
		--peer-root /church/entity-core-keystone/protocol-generator/python'

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

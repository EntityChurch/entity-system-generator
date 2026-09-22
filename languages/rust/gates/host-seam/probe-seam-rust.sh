#!/bin/sh
# languages/rust/gates/host-seam/probe-seam-rust.sh — the whole `rust` host-seam probe.
#
# Three invocations, because on this substrate the D13 layers are not all runtime
# questions:
#
#   1. `access_control`  MUST COMPILE   — the positive control for (2).
#   2. `access_absent`   MUST NOT COMPILE — H3: the container behind the public registration call,
#                                         decided by rustc, one required error code per claim.
#   3. `probe`           runs           — H1 Reach, the emit face, H6 by value, H7 Reach.
#
# (1) exists because a compile-fail check with no positive control reports its
# strongest result when the toolchain is broken (D15, false green). If the control
# does not compile, this script refuses to interpret (2) at all.
#
#   sh languages/rust/gates/host-seam/probe-seam-rust.sh
#
# Offline by construction: the crate closure comes from keystone's own `cargo vendor`
# mirror, mounted read-only. Nothing is fetched and nothing in their tree is written.

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
# Four levels up from languages/<target>/gates/host-seam, not three: this arm moved
# under its target when the layout went target-major.
ROOT="${GENERATOR_ROOT:-$(cd "$HERE/../../../.." && pwd)}"
TARGET_DIR="$(cd "$HERE/../.." && pwd)"
PEER="${PEER_ROOT:-$ROOT/../entity-core-keystone/protocol-generator/rust}"
VENDOR="${VENDOR_DIR:-$PEER/output/vendor}"

[ -d "$PEER/src" ] || { echo "probe-seam-rust: no peer at $PEER" >&2; exit 3; }
[ -d "$VENDOR" ] || { echo "probe-seam-rust: no vendored crate mirror at $VENDOR" >&2
  echo "  It is keystone's gitignored offline build material (their run-s4.sh makes it)." >&2
  echo "  Without it a --network=none build cannot resolve ed25519-dalek/sha2." >&2; exit 3; }

# A cargo home we own. Never keystone's, and never the host's.
export CARGO_HOME="$TARGET_DIR/output/.cargo-home"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$TARGET_DIR/output/.probe-target}"
mkdir -p "$CARGO_HOME" "$CARGO_TARGET_DIR"
cat > "$CARGO_HOME/config.toml" <<EOF
[source.crates-io]
replace-with = "vendored-sources"
[source.vendored-sources]
directory = "$VENDOR"
EOF

cd "$HERE"
CARGO="cargo --offline --quiet"

echo "== 1. access_control — MUST COMPILE (the positive control) =="
if $CARGO build --bin access_control 2>"$CARGO_TARGET_DIR/control.err"; then
  echo "   compiled. The peer IS reachable as a library across the crate boundary."
else
  echo "   FAILED TO COMPILE." >&2
  cat "$CARGO_TARGET_DIR/control.err" >&2
  echo "   REFUSING to interpret the compile-fail fixture: with the control broken," >&2
  echo "   'the symbol is absent' and 'this crate does not build' are the same exit code." >&2
  exit 1
fi
"$CARGO_TARGET_DIR/debug/access_control"
echo

echo "== 2. access_absent — MUST FAIL TO COMPILE, with EACH claimed code (keystone H3) =="
if $CARGO build --bin access_absent --features compile-fail-fixture \
     2>"$CARGO_TARGET_DIR/absent.err"; then
  echo "   IT COMPILED. That is a real change in the peer, not a probe failure:" >&2
  echo "   the container behind register_handler has become reachable. Re-measure H3." >&2
  exit 1
fi
echo "   did not compile, as required. The errors, which ARE the measurement:"
grep -E "^error\[E[0-9]+\]:" "$CARGO_TARGET_DIR/absent.err" | sed 's/^/     /'
# EACH CODE, NOT A COUNT. Until 2026-09-12 this arm required four distinct diagnostics, and keystone
# measured it passing four-of-four against a peer where one of the four claims had become FALSE —
# `register_handler` went public and the fixture's call turned into E0061 (wrong argument count). A
# count survives a change of cause; a code does not. Each claim names its code and each is required.
MISSING=""
for code in E0616 E0609 E0603 E0624; do
  grep -qE "^error\[$code\]:" "$CARGO_TARGET_DIR/absent.err" || MISSING="$MISSING $code"
done
OTHER="$(grep -E "^error\[E[0-9]+\]:" "$CARGO_TARGET_DIR/absent.err" | grep -vE "^error\[(E0616|E0609|E0603|E0624)\]:" || true)"
echo "   claimed codes present: $(( 4 - $(echo $MISSING | wc -w) )) of 4  (command: grep -E '^error\[<code>\]:' absent.err per code)"
[ -z "$MISSING" ] && [ -z "$OTHER" ] || {
  echo "   REFUSING: missing [$MISSING ] / unclaimed errors:" >&2
  [ -n "$OTHER" ] && echo "$OTHER" | sed 's/^/     /' >&2
  echo "   A missing code is a claim that stopped being true; an unclaimed one means the fixture" >&2
  echo "   failed for a reason it does not name, and then it measured the build, not the peer." >&2
  exit 1; }
echo

echo "== 3. probe — Reach · emit face · frame budget (executed) =="
$CARGO build --bin probe
"$CARGO_TARGET_DIR/debug/probe"

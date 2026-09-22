#!/bin/sh
# gates/host-seam/rust/probe-seam-rust.sh — the whole `rust` host-seam probe.
#
# Three invocations, because on this substrate the D13 layers are not all runtime
# questions:
#
#   1. `access_control`  MUST COMPILE   — the positive control for (2).
#   2. `access_absent`   MUST NOT COMPILE — Access, Read and Export, decided by rustc.
#   3. `probe`           runs           — Reach, the emit face, the frame budget.
#
# (1) exists because a compile-fail check with no positive control reports its
# strongest result when the toolchain is broken (D15, false green). If the control
# does not compile, this script refuses to interpret (2) at all.
#
#   sh gates/host-seam/rust/probe-seam-rust.sh
#
# Offline by construction: the crate closure comes from keystone's own `cargo vendor`
# mirror, mounted read-only. Nothing is fetched and nothing in their tree is written.

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${GENERATOR_ROOT:-$(cd "$HERE/../../.." && pwd)}"
PEER="${PEER_ROOT:-$ROOT/../entity-core-keystone/protocol-generator/rust}"
VENDOR="${VENDOR_DIR:-$PEER/output/vendor}"

[ -d "$PEER/src" ] || { echo "probe-seam-rust: no peer at $PEER" >&2; exit 3; }
[ -d "$VENDOR" ] || { echo "probe-seam-rust: no vendored crate mirror at $VENDOR" >&2
  echo "  It is keystone's gitignored offline build material (their run-s4.sh makes it)." >&2
  echo "  Without it a --network=none build cannot resolve ed25519-dalek/sha2." >&2; exit 3; }

# A cargo home we own. Never keystone's, and never the host's.
export CARGO_HOME="$ROOT/output/.cargo-home"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$ROOT/output/.probe-target}"
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

echo "== 2. access_absent — MUST FAIL TO COMPILE (Access · Read · Export) =="
if $CARGO build --bin access_absent --features compile-fail-fixture \
     2>"$CARGO_TARGET_DIR/absent.err"; then
  echo "   IT COMPILED. That is a real change in the peer, not a probe failure:" >&2
  echo "   a public install surface has appeared. Re-measure and update D13's rows." >&2
  exit 1
fi
echo "   did not compile, as required. The errors, which ARE the measurement:"
grep -E "^error\[E[0-9]+\]:" "$CARGO_TARGET_DIR/absent.err" | sed 's/^/     /'
# D14: cite the command that PRINTS the count, and count the right thing. Matching
# `^error:` too would sweep in rustc's own "could not compile ... due to N previous
# errors" summary line and report 5 where the fixture makes 4 claims -- an off-by-one
# in the direction that overstates, which is AP-1's exact shape.
echo "   distinct type errors: $(grep -cE "^error\[E[0-9]+\]:" "$CARGO_TARGET_DIR/absent.err") \
of 4 claimed  (command: grep -cE '^error\[E[0-9]+\]:' absent.err)"
[ "$(grep -cE "^error\[E[0-9]+\]:" "$CARGO_TARGET_DIR/absent.err")" -eq 4 ] || {
  echo "   REFUSING: the fixture makes four independent claims and rustc did not" >&2
  echo "   report four. A single early error can mask the other three, and then" >&2
  echo "   'it did not compile' is one measurement being read as four." >&2; exit 1; }
echo

echo "== 3. probe — Reach · emit face · frame budget (executed) =="
$CARGO build --bin probe
"$CARGO_TARGET_DIR/debug/probe"

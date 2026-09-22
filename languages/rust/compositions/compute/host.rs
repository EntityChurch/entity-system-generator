//! rust / compute — the composition host. **The wiring program.**
//!
//! One core peer (`entity-core-protocol-rust`, keystone, read-only), one extension (COMPUTE v3.29),
//! and the wiring program that installs it. Its twins are
//! `../../../typescript/compositions/compute/host.ts` and `../../../python/compositions/compute/host.py`.
//!
//! # This host is keystone's host plus one install (W-18, the keystone peer contract S1)
//!
//! `run_host(argv, configure)` is keystone's own host as a library function — `embed.host_main` in
//! their `KEYSTONE-PEER-REPORT.json`. It parses the CLI (`run.cli`), loads the named identity
//! (`run.identity`), applies the posture, calls `configure` **before listening**, prints the one
//! readiness record (`run.ready`) and serves. The bare arm of `make regression` is the same function
//! with a no-op closure, so the two arms now differ in exactly the install below.
//!
//! What this file used to carry and no longer does: a CLI parser, a PEM keypair loader, a base64
//! decoder and an accept loop — a hand copy of keystone's `main` that had already drifted from it
//! (no `--seed-policy`, no `--bind`, a `peer_id=` line where theirs is a JSON record).
//!
//! # What this host installs
//!
//! **All five faces**, through one `install_compute` — the other two ports' call.

use std::io::Write;
use std::process::exit;

use entity_compute::{install_compute, EvaluatorLimits, ALL_TYPES, DEFAULT_MAX_DEPTH, DEFAULT_MAX_OPS};

use entity_core_protocol::peer::run_host;

fn main() {
    exit(run_host(std::env::args().skip(1), |peer| {
        // PLAN.json install_order = ["COMPUTE"]. `[compute]` in SYSTEM.toml carries §9.3's limits,
        // which are these constants; the other two ports carry the same numbers. The consumer-last
        // ordering is inside `install_compute`, as it is on the other two ports.
        let compute = install_compute(
            peer,
            EvaluatorLimits {
                max_operations: DEFAULT_MAX_OPS,
                max_depth: DEFAULT_MAX_DEPTH,
            },
        )
        .map_err(|e| format!("install COMPUTE: {e}"))?;

        // The proof-of-install line, on stderr so no harness parsing `LISTENING` trips on it. The
        // evaluator face is the value READ BACK off the peer, not a constant. It is printed from
        // inside `configure` — before the readiness record — because `run_host_with`'s extra record
        // fields are fixed before `configure` runs and so cannot carry what the install read back.
        eprintln!(
            "COMPOSED extensions=COMPUTE pattern={} types={} of {} handler=installed evaluator={} \
             consumers=1 rebuilt={} watched={}",
            compute.pattern,
            compute.type_paths.len(),
            ALL_TYPES.len(),
            compute.evaluator_face,
            compute.rebuilt,
            compute.engine.registered_dependencies(),
        );
        let _ = std::io::stderr().flush();
        Ok(())
    }));
}

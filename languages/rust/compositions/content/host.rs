//! rust / content — the composition host. **The wiring program.**
//!
//! One core peer (`entity-core-protocol-rust`, keystone, read-only), one extension (CONTENT v3.7),
//! and the wiring program that installs it.
//!
//! # This host is keystone's host plus one install (W-18, the keystone peer contract S1)
//!
//! `run_host(argv, configure)` is keystone's own host as a library function — `embed.host_main` in
//! their `KEYSTONE-PEER-REPORT.json`. CLI, named identity, posture, the one readiness record and the
//! accept loop are theirs; `configure` runs before listening. The bare arm of `make regression` is
//! the same function with a no-op closure. The hand copy of their `main` this file used to carry —
//! parser, PEM loader, base64 decoder, accept loop — is deleted.
//!
//! The composition-specific line is `COMPOSED ...` on stderr, which `host-launch` requires: a
//! composed peer that silently installed nothing is indistinguishable from a bare one to everything
//! except the failing checks, which would then read as defects in the PEER.
//!
//! # What this host installs
//!
//! `install_content` — the handler through `Peer::register_handler` (the contract's `install.handler`)
//! and the seven type entities.

use std::io::Write;
use std::process::exit;

use entity_content::{install_content, ALL_TYPES};
use entity_core_protocol::peer::run_host;

fn main() {
    exit(run_host(std::env::args().skip(1), |peer| {
        // One extension, so the order is trivially satisfied and is stated anyway: the first
        // two-extension composition is where an unstated ordering rule becomes an ordering bug
        // (SYSTEM-COMPOSITION §2.2).
        let installed = install_content(peer, None).map_err(|e| format!("install CONTENT: {e}"))?;

        // The proof-of-install line, naming every face. Printed inside `configure`, before the
        // readiness record: `run_host_with`'s extra record fields are fixed before `configure` runs.
        eprintln!(
            "COMPOSED CONTENT pattern={} types={} of {} handler=installed",
            installed.pattern,
            installed.type_paths.len(),
            ALL_TYPES.len()
        );
        for path in &installed.type_paths {
            eprintln!("COMPOSED   bind {path}");
        }
        let _ = std::io::stderr().flush();
        Ok(())
    }));
}

//! rust / content-history — the composition host. **The wiring program.**
//!
//! One core peer (`entity-core-protocol-rust`, keystone, read-only), two extensions
//! (CONTENT v3.7 and HISTORY v1.10), and the wiring program that installs them.
//!
//! Its twins are `../../../typescript/compositions/content-history/host.ts` and
//! `../../../python/compositions/content-history/host.py`, and the three are worth diffing: the
//! composition-specific part is the imports, the install calls and the config write.
//!
//! # This host is keystone's host plus the installs (W-18, the keystone peer contract S1)
//!
//! `run_host(argv, configure)` is keystone's own host as a library function — `embed.host_main` in
//! their `KEYSTONE-PEER-REPORT.json`. CLI, named identity, posture, the one readiness record and the
//! accept loop are theirs; `configure` runs before listening. The bare arm of `make regression` is
//! the same function with a no-op closure. The hand copy of their `main` this file used to carry is
//! deleted.
//!
//! # What this host installs
//!
//! **Every face of both extensions**, through `install_content` and `install_history` — the other
//! two ports' calls. Both handlers go in through `Peer::register_handler` (`install.handler`).
//!
//! **This composition was the sharpest case of D13's face amendment**, and the record is kept in
//! `SYSTEM.toml`: before H1, HISTORY's recorder installed and ran while its read face could not be
//! installed, so the `history` category scored 7 of 34 against a working recorder. Now
//! `register_handler` binds a grant, `install_history` reads its hash back, and the `COMPOSED`
//! line's `handler_grant` field reports what was read.

use std::io::Write;
use std::process::exit;

use entity_content::{install_content, ALL_TYPES as CONTENT_TYPES};
use entity_history::{
    config_path, history_config, install_history, ALL_TYPES as HISTORY_TYPES,
};

use entity_core_protocol::peer::run_host;

fn main() {
    exit(run_host(std::env::args().skip(1), |peer| {
        let local = peer.local_peer.clone();

        // ── the composition, in the normative order ──────────────────────────────
        //
        // PLAN.json install_order = ["CONTENT", "HISTORY"]. Neither declares a dependency on the
        // other and §2.2's consumer positions do not separate them, because CONTENT registers no
        // consumer — so for THIS pair the order carries no constraint and is stated anyway.
        //
        // **The order that DOES matter is inside HISTORY** — types and handler before the recorder,
        // or the audit log opens with ten writes nobody performed — and it is inside
        // `install_history`, as on the other two ports.
        let content = install_content(peer, None).map_err(|e| format!("install CONTENT: {e}"))?;
        let history = install_history(peer, None).map_err(|e| format!("install HISTORY: {e}"))?;

        // ── Composition POLICY: configure history (§6.1, §6.3). ──────────────────
        //
        // Not extension code. §6.1: configuration "uses the standard tree `put`" and needs no
        // handler operation, so which paths a deployment audits is the composition's call.
        //
        // `pattern: "*"` is §6.3's own worked example for "a peer that wants history for all
        // paths". It is also what the oracle requires without saying so: the history category
        // writes to `system/validate/history-ext/*` and never configures history first.
        //
        // Bound AFTER the consumer is registered, matching the other two ports. **The write records
        // itself**: the consumer fires after the bind lands, so the config resolves for its own
        // event, and §3.2 says config paths "SHOULD be recorded as normal transitions for audit
        // purposes" — measured by `tests/recorder.rs`'s real-seam arm (`recorded == 1`).
        peer.store.bind(
            &config_path(&local, "everything"),
            &history_config("*", true, None, None, None),
        );

        // The proof-of-install line. It reports what was written AND what was refused, because a
        // report naming only what happened lets the absence read as an oversight. Printed inside
        // `configure`, before the readiness record.
        let stats = history.recorder.stats();
        eprintln!(
            "COMPOSED extensions=CONTENT,HISTORY types={} of {} handlers={},{} \
             consumers=1 context_available={} handler_grant={} recorded={} observed={}",
            content.type_paths.len() + history.type_paths.len(),
            CONTENT_TYPES.len() + HISTORY_TYPES.len(),
            content.pattern,
            history.pattern,
            history.context_available(),
            history.handler_grant_available,
            stats.recorded,
            stats.observed,
        );
        for path in content.type_paths.iter().chain(history.type_paths.iter()) {
            eprintln!("COMPOSED   bind {path}");
        }
        let _ = std::io::stderr().flush();

        // THE POST-TRAFFIC OBSERVATION, on a MONITOR THREAD.
        //
        // The other two ports print `COMPOSED-FINAL` from a SIGTERM handler; this peer ends by
        // signal with no hook (keystone's `run.stop` binding), so a shutdown line would never run.
        // An observation placed on the path that CAUSES the thing it observes cannot see the last
        // one — a latch at the top of the accept loop never fired, because connections are served
        // on spawned threads and the writes land after the loop has blocked. So: an independent
        // poller, spawned here and outliving `configure`. It observes rather than participates.
        let watch = history.recorder.clone();
        std::thread::spawn(move || {
            let mut latched = false;
            loop {
                std::thread::sleep(std::time::Duration::from_millis(100));
                if !latched && watch.context_observed() == "yes" {
                    latched = true;
                    let st = watch.stats();
                    eprintln!(
                        "COMPOSED-FINAL context_available=yes contexts={} fallbacks={} \
                         observed={} recorded={}",
                        st.context_contexts, st.fallback_contexts, st.observed, st.recorded
                    );
                    let _ = std::io::stderr().flush();
                }
            }
        });
        Ok(())
    }));
}

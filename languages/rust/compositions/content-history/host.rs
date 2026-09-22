//! rust / content-history — the composition host. **The wiring program.**
//!
//! One core peer (`entity-core-protocol-rust`, keystone, read-only), two extensions
//! (CONTENT v3.7 and HISTORY v1.7), and the wiring program that installs what CAN be
//! installed.
//!
//! Its twins are `../../../typescript/compositions/content-history/host.ts` and
//! `../../../python/compositions/content-history/host.py`, and the three are worth
//! diffing: the composition-specific part is the imports, the install calls and the
//! config write; everything else — the CLI, the readiness line, the teardown — is the
//! LANGUAGE's, which is why `languages/<target>/` owns those and a composition does not.
//!
//! **Speaks keystone's host CLI verbatim** — `--port` / `--name` / `--validate` /
//! `--debug-open-grants`, one `LISTENING ...` line on stdout — so the same `host-launch`
//! contract and the same oracle invocation work across all three targets.
//!
//! # What this host installs, and the two lines it will not cross
//!
//! **It does not perform CONTENT's or HISTORY's §11.6.1 handler writes.** Measured, both
//! arms, `gates/host-seam/rust`: `404 handler_not_found` with nothing bound and `501
//! no_handler_body` with all four bound. `404` is the truth — no handler exists — and
//! `501` would say one exists and is broken. It would also move a `--profile core` check
//! for a reason that has nothing to do with either extension.
//!
//! **And it does not fabricate a handler grant.** §2.1's autonomous `capability` is "the
//! handler grant"; there is no mint on this peer and no handler to grant for, so the
//! recorder identity carries the local identity hash for both `author` and `capability`
//! and the `COMPOSED` line says `handler_grant=false`. Minting something grant-shaped so
//! the field looked less degenerate would be making the audit trail claim an authority
//! that does not exist.
//!
//! # What IS installed, and the asymmetry that is this composition's finding
//!
//! Types for both extensions, and **HISTORY's emit consumer, which runs**. From the
//! moment this peer serves, every tree write it accepts is recorded as a §2.1 transition
//! and the chain is real. Nothing can read it over the wire — §4.3's read paths are
//! operations on a handler that cannot exist — so `validate-peer -category history` will
//! score 7 of 34 against a recorder that is working perfectly. The `COMPOSED` line
//! reports the recorder's own count so a reader has a number that is about the extension
//! rather than about the oracle's access path.

use std::io::Write;
use std::process::exit;
use std::sync::Arc;

use entity_content::{install_content_types, ALL_TYPES as CONTENT_TYPES};
use entity_history::{
    config_path, history_config, install_history_recorder, install_history_types, RecorderIdentity,
    ALL_TYPES as HISTORY_TYPES,
};

use entity_core_protocol::peer::transport;
use entity_core_protocol::peer::{CreateOptions, Peer};

fn main() {
    let mut port: u16 = 7777;
    let mut open_grants = false;
    let mut validate = false;
    let mut seed = [0u8; 32];
    let mut named = false;

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--port" => {
                let v = args.next().unwrap_or_else(|| die("--port requires an integer"));
                port = v.parse().unwrap_or_else(|_| die("bad --port value"));
            }
            "--name" => {
                let name = args.next().unwrap_or_else(|| die("--name requires a value"));
                seed = load_seed_from_name(&name);
                named = true;
            }
            "--validate" => validate = true,
            "--debug-open-grants" => open_grants = true,
            "-h" | "--help" => {
                println!(
                    "usage: composed-host [--port N] [--name NAME] [--validate] [--debug-open-grants]"
                );
                return;
            }
            other => die(&format!("unknown argument '{other}'")),
        }
    }
    if !named {
        // The cohort's fixed conformance seed, so peer_id is deterministic and matches
        // what the validator derives. Never random: a random seed would make every run a
        // different peer and the two arms incomparable.
        seed = [0x11u8; 32];
    }

    let peer = Arc::new(Peer::create(CreateOptions {
        seed,
        open_grants,
        conformance: validate,
    }));
    let local = peer.local_peer.clone();

    // ── the composition, in the normative order ──────────────────────────────
    //
    // PLAN.json install_order = ["CONTENT", "HISTORY"]. Neither declares a dependency on
    // the other and §2.2's consumer positions do not separate them, because CONTENT
    // registers no consumer — so for THIS pair the order carries no constraint and is
    // stated anyway.
    //
    // **The order that DOES matter is inside HISTORY**, and on this target it is the
    // caller's to get right rather than the extension's. The other two ports register the
    // consumer inside a single `install_history`, after their own §11.6.1 writes and type
    // publication. Here the faces install through two calls, so: types first, recorder
    // LAST. Otherwise the recorder observes its own installation and the audit log opens
    // with six type writes nobody performed.
    let content = install_content_types(&peer.store, &local);
    let history_types = install_history_types(&peer.store, &local);

    // §2.1's autonomous-case identity, captured once. `handler_grant_hash` is the local
    // identity hash and NOT a grant — see the module doc and
    // `HistoryRecorderInstallation::handler_grant_available`.
    let history = install_history_recorder(
        &peer,
        RecorderIdentity {
            local_identity_hash: peer.identity.identity_hash.clone(),
            handler_grant_hash: peer.identity.identity_hash.clone(),
            local_peer: local.clone(),
        },
    );

    // ── Composition POLICY: configure history (§6.1, §6.3). ──────────────────
    //
    // Not extension code. §6.1: configuration "uses the standard tree `put`" and needs no
    // handler operation, so which paths a deployment audits is the composition's call.
    //
    // `pattern: "*"` is §6.3's own worked example for "a peer that wants history for all
    // paths". It is also what the oracle requires without saying so: the history category
    // writes to `system/validate/history-ext/*` and never configures history first.
    //
    // Bound AFTER the consumer is registered, matching the other two ports. The write
    // fires an event the recorder observes and does not record — there is no config yet
    // at the moment the config arrives — so the first config write can never be in the
    // audit trail on any port. A later one can, which is what §3.2 asks for when it says
    // config paths "SHOULD be recorded as normal transitions for audit purposes".
    peer.store.bind(
        &config_path(&local, "everything"),
        &history_config("*", true, None, None),
    );

    let listener = transport::listen(port).unwrap_or_else(|e| die(&format!("listen failed: {e}")));
    let bound = listener.local_addr().map(|a| a.port()).unwrap_or(port);
    println!(
        "LISTENING 127.0.0.1:{bound} peer_id={local} open_grants={open_grants} validate={validate}"
    );
    let _ = std::io::stdout().flush();

    // The proof-of-install line. It reports what was written AND what was refused,
    // because a report naming only what happened lets the absence read as an oversight.
    // A composed peer that silently installed nothing is indistinguishable from a bare
    // one to everything except the failing checks, which would then read as defects in
    // the PEER.
    let stats = history.recorder.stats();
    eprintln!(
        "COMPOSED extensions=CONTENT,HISTORY types={} of {} handler=NOT-INSTALLABLE \
         (see gates/host-seam/rust) consumers=1 context_available={} handler_grant={} \
         recorded={} observed={}",
        content.type_paths.len() + history_types.type_paths.len(),
        CONTENT_TYPES.len() + HISTORY_TYPES.len(),
        history.context_available(),
        history.handler_grant_available,
        stats.recorded,
        stats.observed,
    );
    for path in content
        .type_paths
        .iter()
        .chain(history_types.type_paths.iter())
    {
        eprintln!("COMPOSED   bind {path}");
    }
    let _ = std::io::stderr().flush();

    // THE POST-TRAFFIC OBSERVATION, on a MONITOR THREAD.
    //
    // The other two ports print `COMPOSED-FINAL` from a SIGTERM handler; this host blocks
    // in `incoming()` with no signal hook, so a TERM kills it outright and a shutdown line
    // would never run.
    //
    // The first attempt latched at the top of the accept loop and NEVER FIRED, which is
    // worth keeping in the record because it looked right: the check runs before each
    // `accept`, connections are served on spawned threads, and the writes therefore land
    // *after* the loop has already blocked waiting for a connection that never comes. An
    // observation placed on the path that CAUSES the thing it observes cannot see the
    // last one -- and the last one is the whole run when the oracle uses a single
    // connection.
    //
    // So: an independent poller. It observes rather than participates, which is the only
    // arrangement that can report on the final event.
    {
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
    }

    for stream in listener.incoming() {
        match stream {
            Ok(s) => {
                transport::set_no_delay(&s);
                let p = peer.clone();
                std::thread::spawn(move || transport::serve_connection(p, s));
            }
            Err(e) => eprintln!("accept failed: {e}"),
        }
    }
}

/// The entity-core PEM at `~/.entity/peers/NAME/keypair`: base64(32-byte seed) between
/// BEGIN/END lines. The Go `entity-peer` / peer-manager convention, and the same one
/// keystone's own host implements — reproduced here rather than called, because their
/// loader is private to their `bin`.
fn load_seed_from_name(name: &str) -> [u8; 32] {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/root".to_string());
    let path = format!("{home}/.entity/peers/{name}/keypair");
    let text =
        std::fs::read_to_string(&path).unwrap_or_else(|e| die(&format!("cannot read {path}: {e}")));
    let body: String = text
        .lines()
        .filter(|l| !l.starts_with("-----"))
        .collect::<Vec<_>>()
        .join("");
    let decoded = base64_decode(body.trim())
        .unwrap_or_else(|| die(&format!("{path}: body is not valid base64")));
    if decoded.len() != 32 {
        die(&format!(
            "{path}: seed is {} bytes, expected 32",
            decoded.len()
        ));
    }
    let mut seed = [0u8; 32];
    seed.copy_from_slice(&decoded);
    seed
}

/// Standard base64 decode, no padding tolerance beyond `=`. Hand-rolled for the same
/// reason the peer hand-rolls base58: this is a build artifact in a `--network=none`
/// build, and adding a registry dependency to read one 44-character string would put a
/// crate in the closure that the extensions themselves do not need.
fn base64_decode(s: &str) -> Option<Vec<u8>> {
    const ALPHABET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut acc: u32 = 0;
    let mut bits: u32 = 0;
    let mut out = Vec::new();
    for c in s.bytes() {
        if c == b'=' {
            break;
        }
        let v = ALPHABET.iter().position(|&a| a == c)? as u32;
        acc = (acc << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((acc >> bits) as u8);
        }
    }
    Some(out)
}

fn die(msg: &str) -> ! {
    eprintln!("composed-host: {msg}");
    exit(2);
}

//! rust / content-history — the composition host. **The wiring program.**
//!
//! One core peer (`entity-core-protocol-rust`, keystone, read-only), two extensions
//! (CONTENT v3.7 and HISTORY v1.10), and the wiring program that installs them.
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
//! # What this host installs
//!
//! **Every face of both extensions**, through `install_content` and `install_history` — the other
//! two ports' calls. Both handlers go in through `Peer::register_handler` (keystone H1).
//!
//! **This composition was the sharpest case of D13's face amendment**, and the record is kept in
//! `SYSTEM.toml`: before H1, HISTORY's recorder installed and ran while its read face could not be
//! installed, so the `history` category scored 7 of 34 against a working recorder, and the host
//! passed the local identity hash as §2.1's "handler grant" because there was no grant. Now
//! `register_handler` binds one, `install_history` reads its hash back, and the `COMPOSED` line's
//! `handler_grant` field reports what was read.

use std::io::Write;
use std::process::exit;
use std::sync::Arc;

use entity_content::{install_content, ALL_TYPES as CONTENT_TYPES};
use entity_history::{
    config_path, history_config, install_history, ALL_TYPES as HISTORY_TYPES,
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
    // **The order that DOES matter is inside HISTORY** — types and handler before the recorder, or
    // the audit log opens with ten writes nobody performed — and it is inside `install_history`, as
    // on the other two ports.
    let content = install_content(&peer, None).unwrap_or_else(|e| die(&format!("install CONTENT: {e}")));
    let history = install_history(&peer, None).unwrap_or_else(|e| die(&format!("install HISTORY: {e}")));

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
    // itself**: the consumer fires after the bind lands, so the config resolves for its own event,
    // and §3.2 says config paths "SHOULD be recorded as normal transitions for audit purposes".
    // This comment said the opposite until 2026-09-12, when `tests/recorder.rs`'s real-seam arm was
    // first run against `install_history` and measured `recorded == 1` after this one write.
    peer.store.bind(
        &config_path(&local, "everything"),
        &history_config("*", true, None, None, None),
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
    for path in content
        .type_paths
        .iter()
        .chain(history.type_paths.iter())
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

//! rust / compute — the composition host. **The wiring program.**
//!
//! One core peer (`entity-core-protocol-rust`, keystone, read-only), one extension (COMPUTE v3.29),
//! and the wiring program that installs what CAN be installed. Its twins are
//! `../../../typescript/compositions/compute/host.ts` and `../../../python/compositions/compute/host.py`;
//! the CLI, the readiness line and the key loading are this LANGUAGE's and are identical to
//! `../content-history/host.rs`.
//!
//! **Speaks keystone's host CLI verbatim** — `--port` / `--name` / `--validate` /
//! `--debug-open-grants`, one `LISTENING ...` line on stdout.
//!
//! # What this host installs
//!
//! **All five faces**, through one `install_compute` — the other two ports' call. The handler goes in
//! through `Peer::register_handler` and the evaluator through `Peer::set_expression_evaluator`, both
//! keystone's H1/H7, landed on this peer for K-9. Until they landed this host installed two faces of
//! five and bound no manifest, because a manifest with no body behind it answers
//! `501 no_handler_body` — a peer reporting a broken handler instead of an absent one.

use std::io::Write;
use std::process::exit;
use std::sync::Arc;

use entity_compute::{install_compute, EvaluatorLimits, ALL_TYPES, DEFAULT_MAX_DEPTH, DEFAULT_MAX_OPS};

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

    // ── the composition ─────────────────────────────────────────────────────────
    //
    // PLAN.json install_order = ["COMPUTE"]. `[compute]` in SYSTEM.toml carries §9.3's limits, which
    // are these constants; the other two ports carry the same numbers. The consumer-last ordering is
    // inside `install_compute`, as it is on the other two ports.
    let compute = install_compute(
        &peer,
        EvaluatorLimits {
            max_operations: DEFAULT_MAX_OPS,
            max_depth: DEFAULT_MAX_DEPTH,
        },
    )
    .unwrap_or_else(|e| die(&format!("install COMPUTE: {e}")));

    let listener = transport::listen(port).unwrap_or_else(|e| die(&format!("listen failed: {e}")));
    let bound = listener.local_addr().map(|a| a.port()).unwrap_or(port);
    println!(
        "LISTENING 127.0.0.1:{bound} peer_id={local} open_grants={open_grants} validate={validate}"
    );
    let _ = std::io::stdout().flush();

    // The proof-of-install line, on stderr so no harness parsing `LISTENING` trips on it. The
    // evaluator face is the value READ BACK off the peer, not a constant.
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

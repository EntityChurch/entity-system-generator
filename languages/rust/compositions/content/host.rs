//! rs-content — the composition host.
//!
//! One core peer (`entity-core-protocol-rust`, keystone, read-only), one extension
//! (CONTENT v3.7), and the wiring program that installs what CAN be installed.
//!
//! **Speaks keystone's host CLI verbatim** — `--port` / `--name` / `--validate` /
//! `--debug-open-grants`, one `LISTENING ...` line on stdout — so the same
//! `host-launch` contract and the same oracle invocation work across all three
//! languages. The composition-specific line is `COMPOSED ...` on stderr, which
//! `host-launch` requires: a composed peer that silently installed nothing is
//! indistinguishable from a bare one to everything except the failing checks, which
//! would then read as defects in the PEER.
//!
//! # What this host installs
//!
//! `install_content` — the handler through `Peer::register_handler` (keystone H1) and the seven
//! type entities. Until H1 landed on this peer the host installed the types and nothing else, and
//! deliberately bound no manifest: with no body behind it the peer answered `501 no_handler_body`,
//! a broken handler where the truth was an absent one. `register_handler` binds the entities and
//! the body together, so that line has nothing left to refuse.

use std::io::Write;
use std::process::exit;
use std::sync::Arc;

use entity_content::{install_content, ALL_TYPES};
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
        // what the validator derives. Never random: a random seed would make every run
        // a different peer and the two arms incomparable.
        seed = [0x11u8; 32];
    }

    let peer = Arc::new(Peer::create(CreateOptions {
        seed,
        open_grants,
        conformance: validate,
    }));

    // ── the composition, in the normative order ──────────────────────────────
    // One extension, so the order is trivially satisfied and is stated anyway: the
    // first two-extension composition is where an unstated ordering rule becomes an
    // ordering bug (SYSTEM-COMPOSITION §2.2).
    let installed = install_content(&peer, None).unwrap_or_else(|e| die(&format!("install CONTENT: {e}")));

    let listener = transport::listen(port).unwrap_or_else(|e| die(&format!("listen failed: {e}")));
    let bound = listener.local_addr().map(|a| a.port()).unwrap_or(port);
    println!(
        "LISTENING 127.0.0.1:{bound} peer_id={} open_grants={open_grants} validate={validate}",
        peer.local_peer
    );
    let _ = std::io::stdout().flush();

    // The proof-of-install line, naming every face, so a peer that installed nothing is
    // distinguishable from a bare one by something other than failing checks.
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
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| die(&format!("cannot read {path}: {e}")));
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
/// build and adding a registry dependency to read one 44-character string would put a
/// crate in the closure that the extension itself does not need.
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

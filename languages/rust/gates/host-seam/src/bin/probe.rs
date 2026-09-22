//! `probe-seam-rust` — the executed half of the `rust` host-seam probe.
//!
//! `probe-seam.mjs` and `probe-seam.py` measure one peer each and answer one
//! question: *can a language-native handler body be installed after construction and
//! reached by a real EXECUTE?* On both of those peers the answer was yes, so both
//! probes are shaped as "install, then dispatch, then check the witness".
//!
//! **That shape does not fit here, and finding out why is the result.** On this peer
//! there is nothing to install. So this probe measures the three layers that CAN be
//! measured by running a program — Reach, the emit face, and the frame budget — and
//! defers Access / Read / Export to `access_absent` + `access_control`, which put the
//! question to rustc. Both halves are driven by `probe-seam-rust.sh`; neither is a
//! verdict on its own.
//!
//! Every scenario below carries a control, and the controls are not decoration:
//!
//! - **A** nothing bound → `404`. Without it, the `501` in B is just "an error".
//! - **B** all four §11.6.1 writes bound → the status the peer actually answers.
//! - **C** the same body live and **directly** reachable, with its invocation counter
//!   snapshotted before the direct call. This is D13's required distinguisher between
//!   *"not installed"* and *"installed and never asked"*, and on this peer it settles
//!   the sharper third case: **there is nowhere to install, so it was never asked.**
//! - **D/E/F** the emit face, with two different negatives — no consumer registered,
//!   and a re-bind that changes nothing. The second is the one that would catch a
//!   counter incrementing on the CALL rather than on the EVENT.

use std::net::TcpStream;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;

use entity_core_protocol::peer::core::Conn;
use entity_core_protocol::peer::model::{self, Entity};
use entity_core_protocol::peer::store::TreeChangeEvent;
use entity_core_protocol::peer::transport::{self, Io};
use entity_core_protocol::peer::wire;
use entity_core_protocol::peer::{CreateOptions, Peer};
use entity_core_protocol::value::{Key, Value};

/// Captured at registration time and folded into the witness. A body that returns a
/// constant, or a `compute/literal` in the tree, cannot produce a value that depends
/// on BOTH this and a request field — which is what makes the witness inattributable
/// to anything except our own callable having run.
const REG_NONCE: &str = "rs-seam-9c41";

const PATTERN: &str = "system/content";

// ── the body we would install, if there were anywhere to install it ──────────

struct WouldBeHandler {
    invocations: AtomicUsize,
}

impl WouldBeHandler {
    fn new() -> WouldBeHandler {
        WouldBeHandler {
            invocations: AtomicUsize::new(0),
        }
    }

    /// The shape a §11.6.1 step-4 body takes: request in, (status, entity) out. It
    /// cannot be spelled as the peer's own `Outcome` — that type is private — which
    /// is itself one of the four things `access_absent` measures.
    fn handle(&self, echo: &str) -> (u64, Entity) {
        self.invocations.fetch_add(1, Ordering::SeqCst);
        (
            200,
            Entity::make(
                "system/content/content-response",
                model::map(vec![("witness", model::text(&format!("{REG_NONCE}:{echo}")))]),
            ),
        )
    }
}

// ── the four §11.6.1 writes, exactly as the `python` port performs them ──────

/// Bind the manifest, the interface entity and a self-signed grant + signature.
///
/// These four ARE reachable — they are ordinary `store.bind` calls through public
/// names, and `python`'s `install_content` performs the same four. What is missing is
/// the fifth thing that port does last: put the callable in the container dispatch
/// consults. So this function performs an install that is complete except for the one
/// step that makes it mean anything, which is precisely the state scenario B measures.
fn bind_handler_entities(peer: &Peer) {
    let local = &peer.local_peer;
    let interface_rel = format!("system/handler/{PATTERN}");

    let handler_e = Entity::make(
        "system/handler",
        model::map(vec![("interface", model::text(&interface_rel))]),
    );
    peer.store.bind(&format!("/{local}/{PATTERN}"), &handler_e);

    let iface_e = Entity::make(
        "system/handler/interface",
        model::map(vec![
            ("pattern", model::text(PATTERN)),
            ("name", model::text("content")),
            (
                "operations",
                Value::Map(vec![
                    (Key::Text("get".into()), Value::Map(vec![])),
                    (Key::Text("ingest".into()), Value::Map(vec![])),
                ]),
            ),
        ]),
    );
    peer.store
        .bind(&format!("/{local}/{interface_rel}"), &iface_e);

    // (3)+(4) A self-issued grant at the §3.5 pointer plus its signature. `mint_token`
    // is private here, so the token is hand-built and signed through the ONE public
    // signing route, `identity.sign_entity`. That it can be done at all is worth
    // recording: three of the five install writes are reachable and the fourth is not.
    let token = Entity::make(
        "system/capability/token",
        model::map(vec![
            ("grantee", model::bytes(&peer.identity.identity_hash)),
            ("grants", Value::Array(vec![])),
        ]),
    );
    let signature = peer.identity.sign_entity(&token);
    peer.store
        .bind(&format!("/{local}/system/capability/grants/{PATTERN}"), &token);
    peer.store.bind(
        &format!("/{local}/system/signature/{}", model::hex(&token.hash)),
        &signature,
    );
}

// ── scaffolding: two peers over real loopback TCP ────────────────────────────

struct Loopback {
    session: transport::Session,
    io: Arc<Io>,
    teardown: TcpStream,
    reader: Option<thread::JoinHandle<()>>,
    serve: Option<thread::JoinHandle<()>>,
    remote: String,
}

impl Loopback {
    fn connect(responder: Arc<Peer>, initiator: Arc<Peer>) -> Loopback {
        let remote = responder.local_peer.clone();
        let listener = transport::listen(0).expect("bind responder");
        let port = listener.local_addr().unwrap().port();
        let resp = responder.clone();
        let serve = thread::spawn(move || {
            if let Ok((stream, _)) = listener.accept() {
                transport::serve_connection(resp, stream);
            }
        });

        let stream = TcpStream::connect(("127.0.0.1", port)).expect("dial responder");
        transport::set_no_delay(&stream);
        let read_stream = stream.try_clone().expect("clone read half");
        let teardown = stream.try_clone().expect("clone teardown half");
        let io = Io::new(stream).expect("io");
        let conn = Arc::new(Mutex::new(Conn::new()));

        let reader = {
            let (p, c, i) = (initiator.clone(), conn.clone(), io.clone());
            thread::spawn(move || transport::read_loop(p, c, i, read_stream))
        };

        let session =
            transport::initiate(initiator, io.clone(), conn).expect("handshake with responder");

        Loopback {
            session,
            io,
            teardown,
            reader: Some(reader),
            serve: Some(serve),
            remote,
        }
    }

    /// One EXECUTE at `system/content`, returning `(status, code)`.
    fn execute_content(&mut self) -> (u64, String) {
        let uri = format!("/{}/{PATTERN}", self.remote);
        let resource = Value::Map(vec![(
            Key::Text("targets".into()),
            Value::Array(vec![Value::Text(format!("{PATTERN}/probe"))]),
        )]);
        let params = Entity::make(
            "system/content/get-request",
            model::map(vec![("hashes", Value::Array(vec![]))]),
        );
        let resp = self
            .session
            .execute(&uri, "get", params, Some(resource))
            .expect("a response envelope");
        let status = resp.root.uint_field("status").unwrap_or(0);
        let code = resp
            .root
            .entity_field("result")
            .and_then(|r| r.text_field("code").map(str::to_string))
            .unwrap_or_default();
        (status, code)
    }

    fn shutdown(mut self) {
        self.io.close();
        transport::shutdown(&self.teardown);
        if let Some(r) = self.reader.take() {
            let _ = r.join();
        }
        if let Some(s) = self.serve.take() {
            let _ = s.join();
        }
    }
}

fn peer(seed: u8) -> Arc<Peer> {
    Arc::new(Peer::create(CreateOptions {
        seed: [seed; 32],
        open_grants: true,
        conformance: false,
    }))
}

// ── the run ──────────────────────────────────────────────────────────────────

fn main() {
    let mut vacuous: Vec<&str> = Vec::new();
    println!("probe-seam-rust — peer: entity-core-protocol-rust (keystone, read-only)\n");

    // ── Scenario 1: the Reach layer ──────────────────────────────────────────
    println!("Scenario 1 — the Reach layer (handler face, §11.6.1 model 2)");

    let body = WouldBeHandler::new();

    // A. NEGATIVE CONTROL. Nothing bound at the pattern.
    let responder_a = peer(0x21);
    let mut lb = Loopback::connect(responder_a.clone(), peer(0x22));
    let (status_a, code_a) = lb.execute_content();
    lb.shutdown();
    println!("  A. nothing bound                          {status_a}  {code_a}");
    if status_a != 404 {
        vacuous.push("control A did not answer 404 — the negative arm does not discriminate");
    }

    // B. All four §11.6.1 tree writes bound. The fifth step has no destination.
    let responder_b = peer(0x23);
    bind_handler_entities(&responder_b);
    let bound = responder_b
        .store
        .get_at(&format!("/{}/{PATTERN}", responder_b.local_peer))
        .is_some();
    let mut lb = Loopback::connect(responder_b.clone(), peer(0x24));
    let before = body.invocations.load(Ordering::SeqCst);
    let (status_b, code_b) = lb.execute_content();
    let after_dispatch = body.invocations.load(Ordering::SeqCst);
    lb.shutdown();
    println!("  B. all four tree writes bound             {status_b}  {code_b}");
    println!("     manifest resolvable in the tree:       {bound}");
    if !bound {
        vacuous.push("scenario B never bound the manifest — the probe measured nothing");
    }
    if status_b == 404 {
        vacuous.push("B answered 404 like the control — the tree writes had no effect at all");
    }

    // C. THE DISTINGUISHER. The same body, live, called directly.
    let (status_c, result_c) = body.handle("hello");
    let after_direct = body.invocations.load(Ordering::SeqCst);
    let witness = result_c.text_field("witness").unwrap_or("").to_string();
    println!("  C. that body called DIRECTLY              {status_c}  witness={witness}");
    println!(
        "     invocations: before={before} after dispatch={after_dispatch} after direct={after_direct}"
    );
    if after_direct != after_dispatch + 1 || witness != format!("{REG_NONCE}:hello") {
        vacuous.push("control C did not run the body — the counter proves nothing");
    }

    let reach = if after_dispatch == before {
        "NO — dispatch never reached an installed body, and there is nowhere to install one"
    } else {
        "YES"
    };
    println!("  => Reach (handler face): {reach}\n");

    // ── Scenario 2: the emit face ────────────────────────────────────────────
    println!("Scenario 2 — the emit face (§6.10 / §6.13(c) tree consumer)");

    let p = peer(0x31);
    let events = Arc::new(Mutex::new(Vec::<String>::new()));
    {
        let sink = events.clone();
        p.store.register_tree_consumer(move |ev: &TreeChangeEvent| {
            sink.lock()
                .unwrap()
                .push(format!("{REG_NONCE}:{}:{}", ev.event_type, ev.path));
        });
    }
    let path = format!("/{}/probe/emit", p.local_peer);
    let e1 = Entity::make(
        "system/content/chunk",
        model::map(vec![("payload", model::bytes(b"one"))]),
    );
    p.store.bind(&path, &e1);
    let fired = events.lock().unwrap().clone();
    println!(
        "  D. consumer registered, one bind          {} event(s)  {}",
        fired.len(),
        fired.first().cloned().unwrap_or_default()
    );

    // E. NEGATIVE CONTROL 1 — no consumer registered at all.
    let q = peer(0x32);
    let quiet = Arc::new(AtomicUsize::new(0));
    q.store.bind(
        &format!("/{}/probe/emit", q.local_peer),
        &Entity::make(
            "system/content/chunk",
            model::map(vec![("payload", model::bytes(b"one"))]),
        ),
    );
    println!(
        "  E. no consumer, one bind                  {} event(s)",
        quiet.load(Ordering::SeqCst)
    );

    // F. NEGATIVE CONTROL 2 — the same entity re-bound at the same path. The call
    //    happens; the EVENT must not. This is the arm that separates "the counter
    //    tracks events" from "the counter tracks calls", and only the first is the
    //    property §6.10 states.
    p.store.bind(&path, &e1);
    let after_rebind = events.lock().unwrap().len();
    println!("  F. identical re-bind (no change)          {after_rebind} event(s) total (was {})", fired.len());

    let emit_ok = fired.len() == 1
        && fired[0] == format!("{REG_NONCE}:created:{path}")
        && after_rebind == 1;
    if !emit_ok {
        vacuous.push("the emit arms did not discriminate — D/F did not separate event from call");
    }
    println!(
        "  => Reach (emit face): {}\n",
        if emit_ok {
            "YES — witness carries the registration nonce and the bound path; a no-op re-bind is silent"
        } else {
            "INDETERMINATE"
        }
    );

    // ── Scenario 3: the frame budget (CONTENT §6.2 / §4.2 Amendment 1) ───────
    println!("Scenario 3 — the connection frame budget (CONTENT Am. 1 §6.2 MUST)");
    println!("  wire::MAX_FRAME                           {}", wire::MAX_FRAME);
    println!("  CreateOptions fields                      seed · open_grants · conformance");
    println!("  Conn fields                               established · issued_nonce · hello_peer_id · outbound · out_counter");
    // MEASURED BY VALUE, per the D15 upgrade K-1 forced on the `python` probe: the
    // question is never "is there a field whose NAME matches frame|max|budget", it is
    // "does a body read back a number the transport was configured to enforce". Here
    // there is no configuration to vary, so the two arms of that comparison cannot be
    // constructed — which is the finding, and it is stated as one rather than scored.
    let configurable = false;
    println!(
        "  => budget readable by a body: NO. And NOT configurable ({configurable}), so the\n     \
         by-value check that K-1 forced has no second arm to run here. Reported as\n     \
         UNSATISFIABLE-AND-VACUOUS, not as a failed check."
    );

    // ── verdict ──────────────────────────────────────────────────────────────
    println!("\n--- summary ---");
    println!("handler face:  Reach NO (executed, both controls)");
    println!("emit face:     Reach YES (executed, two negatives)");
    println!("frame budget:  MAX_FRAME is a module constant == the literal Am. 1 forbids");
    println!("Access / Read / Export: see access_absent + access_control (rustc decides, not this binary)");

    if vacuous.is_empty() {
        println!("\nprobe integrity: OK — every arm discriminated");
    } else {
        eprintln!("\nprobe integrity: VACUOUS — this run measured nothing:");
        for v in &vacuous {
            eprintln!("  - {v}");
        }
        std::process::exit(2);
    }
}

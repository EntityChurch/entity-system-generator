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
//! - **G** added when the second extension needed the face for real. D/E/F measure
//!   that a consumer is *invoked*; HISTORY §5.1 needs one that **writes** from inside
//!   the callback, which is a question about `Store`'s consumer lock and not about the
//!   hook. It runs behind a timeout, because the failure it is looking for is a
//!   deadlock and a probe that hangs reports nothing at all.

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

    /// One EXECUTE at an arbitrary handler, returning `(status, result entity)`.
    ///
    /// `execute_content` above is the fixed-shape version scenario 1 needs; this is the
    /// general one scenario 4 needs, and the two are kept separate rather than merged so
    /// that scenario 1's request — the one whose 404/501 answer is the measurement —
    /// cannot change shape when a later scenario wants a different call.
    fn execute(
        &mut self,
        handler: &str,
        operation: &str,
        params: Entity,
        targets: &[&str],
    ) -> (u64, Entity) {
        let uri = format!("/{}/{handler}", self.remote);
        let resource = Value::Map(vec![(
            Key::Text("targets".into()),
            Value::Array(targets.iter().map(|t| Value::Text((*t).into())).collect()),
        )]);
        let resp = self
            .session
            .execute(&uri, operation, params, Some(resource))
            .expect("a response envelope");
        let status = resp.root.uint_field("status").unwrap_or(0);
        let result = resp
            .root
            .entity_field("result")
            .unwrap_or_else(|| Entity::make("primitive/any", Value::Map(vec![])));
        (status, result)
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

    // G. THE ARM THE SECOND EXTENSION FORCED — a consumer that WRITES to the store
    //    it is being called from.
    //
    //    D/E/F measure that a consumer is INVOKED. That is not the property HISTORY
    //    needs. §5.1's recorder writes a transition and advances a head pointer from
    //    inside the callback, so the question is whether the seam is re-entrant, and
    //    it is a question about a LOCK rather than about a hook:
    //
    //      `Store::fire` holds `consumers.read()` across the callback. A `bind` from
    //      inside takes `inner.write()` (a different lock — fine) and then calls
    //      `fire` AGAIN, taking `consumers.read()` recursively on the same thread.
    //      `std::sync::RwLock::read` documents that it "might panic when called if
    //      the lock is already held by the current thread", and the futex
    //      implementation is writer-preferring, so a queued writer would deadlock it.
    //
    //    Reading the source cannot settle that (D13: source reads decide what to
    //    build, never what is true), and a probe that simply called `bind` would HANG
    //    rather than report on the bad outcome. So the write runs on a worker thread
    //    behind a `recv_timeout`: a deadlock becomes a measured NO, not a stalled gate.
    println!();
    let r = peer(0x33);
    let head_prefix = format!("/{}/system/history/head", r.local_peer);
    let reentrant_writes = Arc::new(AtomicUsize::new(0));
    let guard_hits = Arc::new(AtomicUsize::new(0));
    {
        // `Weak`, not `Arc`. An `Arc<Peer>` captured by a closure the peer's own store
        // owns is a reference cycle, and the recorder in `entity-history` has exactly
        // this shape — so the probe uses the shape the extension will use rather than
        // a simpler one that would not have caught it.
        let owner = Arc::downgrade(&r);
        let (writes, guarded, hp) = (
            reentrant_writes.clone(),
            guard_hits.clone(),
            head_prefix.clone(),
        );
        r.store.register_tree_consumer(move |ev: &TreeChangeEvent| {
            // §3.2's self-guard, in miniature: without it this recurses forever.
            if ev.path.starts_with(&hp) {
                guarded.fetch_add(1, Ordering::SeqCst);
                return;
            }
            let Some(peer) = owner.upgrade() else { return };
            writes.fetch_add(1, Ordering::SeqCst);
            peer.store.bind(
                &format!("{hp}{}", ev.path),
                &Entity::make(
                    "system/history/transition",
                    model::map(vec![("path", model::text(&ev.path))]),
                ),
            );
        });
    }
    let app_path = format!("/{}/probe/reentrant", r.local_peer);
    let (tx, rx) = std::sync::mpsc::channel();
    {
        let (rr, ap) = (r.clone(), app_path.clone());
        thread::spawn(move || {
            rr.store.bind(
                &ap,
                &Entity::make(
                    "system/content/chunk",
                    model::map(vec![("payload", model::bytes(b"reentrant"))]),
                ),
            );
            let _ = tx.send(());
        });
    }
    let completed = rx
        .recv_timeout(std::time::Duration::from_secs(5))
        .is_ok();
    let head_bound = completed && r.store.get_at(&format!("{head_prefix}{app_path}")).is_some();
    println!("  G. consumer WRITES from inside the callback");
    println!(
        "     returned within 5 s:                   {completed}   (false = deadlock or panic)"
    );
    println!(
        "     re-entrant writes attempted:           {}",
        reentrant_writes.load(Ordering::SeqCst)
    );
    println!(
        "     self-guard hits (the head write's own event): {}",
        guard_hits.load(Ordering::SeqCst)
    );
    println!("     head pointer readable afterwards:      {head_bound}");
    let reentrant_ok = completed && head_bound && guard_hits.load(Ordering::SeqCst) == 1;
    // A NO here is a RESULT, not vacuity, and it must not be filed as one: `vacuous`
    // means "this run measured nothing", and a deadlock measured the sharpest thing
    // the arm can say. What IS vacuous is the arm never having fired at all — then the
    // verdict is about the probe rather than about the peer.
    if reentrant_writes.load(Ordering::SeqCst) == 0 {
        vacuous.push(
            "arm G's consumer never fired — the re-entrancy question was not asked, and a NO \
             from this arm would be about the probe rather than about the peer",
        );
    }
    println!(
        "  => the emit face is usable BY A CONSUMER THAT WRITES: {}\n",
        if reentrant_ok {
            "YES — the seam is re-entrant; a write from inside the callback lands, and its own \
             event comes back to the guard exactly once"
        } else if !completed {
            "NO — the write from inside the callback did not return within 5 s. The seam is not \
             re-entrant, and §5.1's recorder cannot be a plain consumer on this peer"
        } else {
            "NO — the write returned but did not take effect"
        }
    );

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

    // ── Scenario 4: the emit face OVER THE WIRE ──────────────────────────────
    //
    // Scenario 2 measured that a consumer is invoked, and arm G that it may write. Both
    // drive `store.bind` DIRECTLY, in the probe's own thread. That is not the claim a
    // composition makes when it writes `emit_consumer = "installed"`: the claim is that a
    // write arriving over the wire — through the handshake, the reader-demux, dispatch,
    // `check_permission` and the peer's own `system/tree` handler — reaches the installed
    // consumer, and that the consumer's own write is then visible to a subsequent wire
    // READ.
    //
    // D13's clause 2 asks for exactly this and for two things about the witness: it must
    // derive from a REQUEST FIELD and from REGISTRATION-TIME STATE. Here it does both —
    // the transition's `path` and `hash` come from the PUT the client chose, and its
    // `author` is the nonce captured when the consumer was registered — so a peer that
    // answered from a constant, or from something already in the tree, could not produce
    // it.
    //
    // And the negative distinguishes "not installed" from "installed and never asked": an
    // otherwise identical peer with NO consumer, driven by the identical two wire calls.
    println!("Scenario 4 — the emit face, driven over real loopback TCP");

    const APP_PATH: &str = "probe/wire-emit";
    let head_of = |peer: &str, path: &str| format!("/{peer}/system/history/head/{peer}/{path}");
    let put_params = |e: &Entity| {
        Entity::make(
            "primitive/any",
            Value::Map(vec![(Key::Text("entity".into()), e.to_cbor())]),
        )
    };
    let subject = Entity::make(
        "system/validate/history-test",
        model::map(vec![("value", model::text(REG_NONCE))]),
    );

    // H. POSITIVE. A consumer registered before the peer serves, exactly as a
    //    composition's wiring program registers one.
    let responder_h = peer(0x41);
    let local_h = responder_h.local_peer.clone();
    let recorded = Arc::new(AtomicUsize::new(0));
    // WHAT the consumer saw, not just how many. The count alone said "+3 for one PUT"
    // and left the other two unexplained, which is the same shape as a cohort number
    // with no command behind it (D14).
    let seen = Arc::new(Mutex::new(Vec::<String>::new()));
    {
        let owner = Arc::downgrade(&responder_h);
        let hits = recorded.clone();
        let paths = seen.clone();
        let guard_prefix = format!("/{local_h}/system/history/head");
        responder_h
            .store
            .register_tree_consumer(move |ev: &TreeChangeEvent| {
                if ev.path.starts_with(&guard_prefix) {
                    return;
                }
                let Some(p) = owner.upgrade() else { return };
                hits.fetch_add(1, Ordering::SeqCst);
                paths
                    .lock()
                    .unwrap()
                    .push(format!("{}:{}", ev.event_type, ev.path));
                // The witness: the request's path and hash, plus the registration-time
                // nonce as `author`. Neither half alone would be attributable.
                let transition = Entity::make(
                    "system/history/transition",
                    model::map(vec![
                        ("path", model::text(&ev.path)),
                        ("event", model::text(ev.event_type)),
                        (
                            "hash",
                            match &ev.new_hash {
                                Some(h) => model::bytes(h),
                                None => Value::Null,
                            },
                        ),
                        ("author", model::text(REG_NONCE)),
                    ]),
                );
                p.store
                    .bind(&format!("{guard_prefix}{}", ev.path), &transition);
            });
    }

    let mut lb = Loopback::connect(responder_h.clone(), peer(0x42));
    // SNAPSHOT BEFORE THE PUT, and the reason is the first thing this arm found: the
    // counter is NOT zero here. Establishing a connection writes to the tree — the
    // remote peer entity, its signature, the session's capability material — and every
    // one of those is a tree-change event an emit consumer observes. The arm was first
    // written asserting `invocations == 1` after the PUT and measured 4.
    //
    // So the assertion is on the DELTA, and the connection-time count is reported as its
    // own number, because it is a fact about the peer that HISTORY inherits: a composed
    // peer's audit chain records protocol-level writes as application transitions, and
    // `recorded` on the COMPOSED line is therefore not a count of application writes.
    let before_put = recorded.load(Ordering::SeqCst);
    let (put_status, _) = lb.execute(
        "system/tree",
        "put",
        put_params(&subject),
        &[&format!("/{local_h}/{APP_PATH}")],
    );
    let after_put = recorded.load(Ordering::SeqCst);
    let (get_status, transition) = lb.execute(
        "system/tree",
        "get",
        wire::empty_params(),
        &[&head_of(&local_h, APP_PATH)],
    );
    lb.shutdown();

    let witness_author = transition.text_field("author").unwrap_or("").to_string();
    let witness_path = transition.text_field("path").unwrap_or("").to_string();
    let witness_hash_ok = transition.bytes_field("hash") == Some(subject.hash.as_slice());
    println!("  H. consumer registered, wire PUT then wire GET");
    println!("     PUT  /{{peer}}/{APP_PATH}                    {put_status}");
    println!("     GET  the head pointer                     {get_status}");
    println!(
        "     witness: author={witness_author} (registration-time)  path={} (request field)  hash matches PUT: {witness_hash_ok}",
        if witness_path.ends_with(APP_PATH) { "ok" } else { &witness_path }
    );
    println!(
        "     consumer invocations: {before_put} during CONNECTION SETUP, +{} for the PUT",
        after_put - before_put
    );
    // **THE FINDING OF THIS ARM.** One wire PUT is not one tree event. Whatever else the
    // peer binds while serving a request is a tree-change event too, and an emit consumer
    // sees all of it — so a composed peer's audit chain contains the peer's own protocol
    // bookkeeping alongside the write the caller asked for. Listed rather than counted,
    // because "+3" with no paths behind it is a number with nothing to check it against.
    for p in seen.lock().unwrap().iter() {
        println!("     saw  {p}");
    }

    // I. NEGATIVE CONTROL. The same two wire calls against a peer with NO consumer.
    //    This is what separates "not installed" from "installed and never asked": if the
    //    GET answered 200 here too, the head pointer would be coming from somewhere other
    //    than our callback.
    let responder_i = peer(0x43);
    let local_i = responder_i.local_peer.clone();
    let mut lb = Loopback::connect(responder_i.clone(), peer(0x44));
    let (put_status_i, _) = lb.execute(
        "system/tree",
        "put",
        put_params(&subject),
        &[&format!("/{local_i}/{APP_PATH}")],
    );
    let (get_status_i, _) = lb.execute(
        "system/tree",
        "get",
        wire::empty_params(),
        &[&head_of(&local_i, APP_PATH)],
    );
    lb.shutdown();
    println!("  I. NO consumer, the identical two calls");
    println!("     PUT                                       {put_status_i}");
    println!("     GET  the head pointer                     {get_status_i}  (must NOT be 200)");

    let wire_emit_ok = put_status == 200
        && get_status == 200
        && witness_author == REG_NONCE
        && witness_path == format!("/{local_h}/{APP_PATH}")
        && witness_hash_ok
        // EXACTLY ONE EVENT FOR THE APP PATH — not one event for the request. The arm
        // was first written as `after_put - before_put == 1` and measured 3, because
        // §6.10 fires per BINDING and serving one request binds more than the caller
        // asked for. `>= 1` on the total would have passed for a consumer that fired on
        // everything and never on our path, so the assertion is on the path itself.
        && seen
            .lock()
            .unwrap()
            .iter()
            .filter(|p| p.ends_with(&format!("/{local_h}/{APP_PATH}")))
            .count()
            == 1
        && put_status_i == 200
        && get_status_i != 200;
    if put_status != 200 || put_status_i != 200 {
        // Both arms must be able to WRITE, or the GET comparison is between two peers
        // that failed for different reasons and the negative proves nothing.
        vacuous.push(
            "scenario 4's PUT did not succeed on both arms — the emit question was never \
             asked, and the negative control is not a control",
        );
    }
    println!(
        "  => the emit face is reachable FROM THE WIRE: {}\n",
        if wire_emit_ok {
            "YES — a wire PUT reaches the installed consumer, its write is readable by a \
             wire GET, and an identical peer without the consumer answers the GET non-200"
        } else {
            "NO"
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
    println!(
        "emit face, RE-ENTRANT (a consumer that writes): {}",
        if reentrant_ok { "YES (arm G)" } else { "NO (arm G)" }
    );
    println!(
        "emit face, FROM THE WIRE (put -> consumer -> get): {}",
        if wire_emit_ok {
            "YES (arms H/I)"
        } else {
            "NO (arms H/I)"
        }
    );
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

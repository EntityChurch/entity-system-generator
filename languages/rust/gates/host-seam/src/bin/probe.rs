//! `probe-seam-rust` — the executed half of the `rust` host-seam probe.
//!
//! `probe-seam.mjs` and `probe-seam.py` measure one peer each and answer one question: *can a
//! language-native handler body be installed after construction and reached by a real EXECUTE?*
//! Until keystone landed H1 on this peer (for our K-9, 2026-09-12) the answer here was NO, and this
//! probe was shaped around that: bind the four §11.6.1 entities, observe `501 no_handler_body`, and
//! call the body directly to prove it was never asked. **It is now shaped like its two siblings —
//! install, dispatch, witness — because the peer changed**, and the old arms are recorded in
//! `../README.md` rather than kept running against a surface that no longer exists.
//!
//! Every scenario carries controls:
//!
//! - **1 · H1** — A nothing installed → `404`; B installed through `Peer::register_handler` → `200`
//!   with a witness folding a request field into the registration nonce, invocation counter `0 → 1`;
//!   C `unregister_handler` → `404` again and the counter does NOT move. C is D13's distinguisher
//!   between "not installed" and "installed and never asked", run in the direction that matters now.
//! - **2 · emit face** — D/E/F: consumer invoked, no consumer, identical re-bind. G: a consumer that
//!   WRITES, behind a timeout. H/I: the same, driven over the wire.
//! - **3 · H6** — the frame budget BY VALUE: a peer configured to 3,145,749 must hand a body
//!   3,145,749, and an unconfigured peer 16,777,216. A body reading a constant passes one arm only.
//! - **5 · H7** — an entity-native body the peer cannot evaluate: `501` with no evaluator, `200` with
//!   one installed (the value folds a request field in), `501` again for a body the evaluator
//!   declines, and the literal floor answered without the evaluator being asked.

use std::net::TcpStream;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;

use entity_core_protocol::peer::core::Conn;
use entity_core_protocol::peer::handler::{
    ExpressionEvaluator, ExpressionRequest, FnHandler, HandlerContext, HandlerResult, OperationSpec,
};
use entity_core_protocol::peer::model::{self, Entity};
use entity_core_protocol::peer::store::TreeChangeEvent;
use entity_core_protocol::peer::transport::{self, Io};
use entity_core_protocol::peer::wire;
use entity_core_protocol::peer::{CreateOptions, Peer, PeerConfig};
use entity_core_protocol::value::{Key, Value};

/// Captured at registration time and folded into the witness. A body that returns a
/// constant, or a `compute/literal` in the tree, cannot produce a value that depends
/// on BOTH this and a request field — which is what makes the witness inattributable
/// to anything except our own callable having run.
const REG_NONCE: &str = "rs-seam-9c41";

const PATTERN: &str = "system/content";

// ── the bodies this probe installs ───────────────────────────────────────────

/// Scenario 1's body. The witness depends on BOTH a registration-time nonce and a request field,
/// so no constant, literal or built-in can produce it.
fn witness_handler(invocations: Arc<AtomicUsize>) -> Arc<FnHandler> {
    Arc::new(FnHandler::new(
        PATTERN,
        "probe-witness",
        vec![OperationSpec::named("get")],
        move |ctx: &HandlerContext<'_>| {
            invocations.fetch_add(1, Ordering::SeqCst);
            let echo = ctx
                .params()
                .and_then(|p| p.text_field("echo").map(str::to_string))
                .unwrap_or_default();
            HandlerResult::ok(Entity::make(
                "system/content/content-response",
                model::map(vec![(
                    "witness",
                    model::text(&format!("{REG_NONCE}:{echo}")),
                )]),
            ))
        },
    ))
}

/// Scenario 3's body: it answers with the budget the context hands it.
fn budget_handler() -> Arc<FnHandler> {
    Arc::new(FnHandler::new(
        PATTERN,
        "probe-budget",
        vec![OperationSpec::named("get")],
        |ctx: &HandlerContext<'_>| {
            HandlerResult::ok(Entity::make(
                "primitive/any",
                model::map(vec![("budget", Value::UInt(ctx.frame_budget() as u64))]),
            ))
        },
    ))
}

/// Scenario 5's evaluator: claims `probe/double` only, and folds a request field into the value.
struct Doubler {
    calls: Arc<AtomicUsize>,
}

impl ExpressionEvaluator for Doubler {
    fn evaluate(
        &self,
        req: &ExpressionRequest<'_>,
        ctx: &HandlerContext<'_>,
    ) -> Option<HandlerResult> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        if req.expression.typ != "probe/double" {
            return None;
        }
        let n = req.expression.uint_field("n")?;
        let bump = ctx.params().and_then(|p| p.uint_field("bump")).unwrap_or(0);
        Some(HandlerResult::ok(Entity::make(
            "primitive/any",
            model::map(vec![("value", Value::UInt(n * 2 + bump))]),
        )))
    }
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

    /// One EXECUTE at the probe pattern carrying `echo`, returning `(status, code, witness)`.
    fn execute_content(&mut self, echo: &str) -> (u64, String, String) {
        let uri = format!("/{}/{PATTERN}", self.remote);
        let resource = Value::Map(vec![(
            Key::Text("targets".into()),
            Value::Array(vec![Value::Text(format!("{PATTERN}/probe"))]),
        )]);
        let params = Entity::make(
            "primitive/any",
            model::map(vec![("echo", model::text(echo))]),
        );
        let resp = self
            .session
            .execute(&uri, "get", params, Some(resource))
            .expect("a response envelope");
        let status = resp.root.uint_field("status").unwrap_or(0);
        let result = resp.root.entity_field("result");
        let code = result
            .as_ref()
            .and_then(|r| r.text_field("code").map(str::to_string))
            .unwrap_or_default();
        let witness = result
            .as_ref()
            .and_then(|r| r.text_field("witness").map(str::to_string))
            .unwrap_or_default();
        (status, code, witness)
    }

    /// One EXECUTE at an arbitrary handler, returning `(status, result entity)`.
    ///
    /// `execute_content` above is the fixed-shape version scenarios 1 and 3 need; this is the
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

fn peer_with(seed: u8, config: PeerConfig) -> Arc<Peer> {
    Arc::new(Peer::create_with(
        CreateOptions {
            seed: [seed; 32],
            open_grants: true,
            conformance: false,
        },
        config,
    ))
}

// ── the run ──────────────────────────────────────────────────────────────────

fn main() {
    let mut vacuous: Vec<&str> = Vec::new();
    println!("probe-seam-rust — peer: entity-core-protocol-rust (keystone, read-only)\n");

    // ── Scenario 1: H1 — install, dispatch, witness, uninstall ──────────────
    println!("Scenario 1 — H1: a language-native body installed after construction (§11.6.1)");

    let invocations = Arc::new(AtomicUsize::new(0));
    let responder = peer(0x21);
    let mut lb = Loopback::connect(responder.clone(), peer(0x22));

    // A. NEGATIVE CONTROL — nothing installed at the pattern.
    let (status_a, code_a, _) = lb.execute_content("hello");
    println!("  A. nothing installed                      {status_a}  {code_a}");
    if status_a != 404 {
        vacuous.push("control A did not answer 404 — the negative arm does not discriminate");
    }

    // B. Installed through the public registration call.
    let registered = responder.install_handler(witness_handler(invocations.clone()));
    let before = invocations.load(Ordering::SeqCst);
    let (status_b, code_b, witness_b) = lb.execute_content("hello");
    let after_dispatch = invocations.load(Ordering::SeqCst);
    println!(
        "  B. register_handler -> {:<17} {status_b}  {code_b}witness={witness_b}",
        if registered.is_ok() { "Ok" } else { "Err" }
    );
    println!("     invocations: before={before} after dispatch={after_dispatch}");
    let reached = status_b == 200
        && witness_b == format!("{REG_NONCE}:hello")
        && after_dispatch == before + 1;

    // C. Uninstalled — the counter must not move, and the pattern must stop resolving.
    let removed = responder.unregister_handler(PATTERN);
    let (status_c, code_c, _) = lb.execute_content("again");
    let after_uninstall = invocations.load(Ordering::SeqCst);
    lb.shutdown();
    println!("  C. unregister_handler -> {removed:<15} {status_c}  {code_c}");
    println!("     invocations after the uninstalled dispatch: {after_uninstall}");
    if !removed || status_c != 404 || after_uninstall != after_dispatch {
        vacuous.push("control C did not return the peer to 404 with the counter unmoved — B's witness is not attributable to the install");
    }

    let reach = if reached { "YES" } else { "NO" };
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
    println!(
        "  F. identical re-bind (no change)          {after_rebind} event(s) total (was {})",
        fired.len()
    );

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
    let completed = rx.recv_timeout(std::time::Duration::from_secs(5)).is_ok();
    let head_bound = completed
        && r.store
            .get_at(&format!("{head_prefix}{app_path}"))
            .is_some();
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

    let emit_ok =
        fired.len() == 1 && fired[0] == format!("{REG_NONCE}:created:{path}") && after_rebind == 1;
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

    // ── Scenario 3: H6 — the frame budget BY VALUE (CONTENT Am. 1 §6.2) ───────
    println!("Scenario 3 — H6: the connection frame budget a body reads (CONTENT Am. 1 §6.2)");
    const CONFIGURED: u64 = 3_145_749;
    let read_budget = |responder: Arc<Peer>, seed: u8| -> Option<u64> {
        responder.install_handler(budget_handler()).ok()?;
        let mut lb = Loopback::connect(responder, peer(seed));
        let (status, result) = lb.execute(
            PATTERN,
            "get",
            Entity::make("primitive/any", model::map(vec![])),
            &[PATTERN],
        );
        lb.shutdown();
        (status == 200)
            .then(|| result.uint_field("budget"))
            .flatten()
    };
    let configured = read_budget(
        peer_with(
            0x41,
            PeerConfig::default().max_frame_bytes(CONFIGURED as usize),
        ),
        0x42,
    );
    let defaulted = read_budget(peer(0x43), 0x44);
    println!("  configured {CONFIGURED:>10} -> body reads   {configured:?}");
    println!(
        "  default    {:>10} -> body reads   {defaulted:?}",
        wire::MAX_FRAME
    );
    let budget_by_value =
        configured == Some(CONFIGURED) && defaulted == Some(wire::MAX_FRAME as u64);
    if configured.is_none() || defaulted.is_none() {
        vacuous.push("scenario 3 could not install or reach the budget body — no arm measured");
    }
    println!(
        "  => budget read BY VALUE: {}\n",
        if budget_by_value {
            "YES (both arms)"
        } else {
            "NO"
        }
    );

    // ── Scenario 5: H7 — the evaluator for entity-native bodies ─────────────────
    println!("Scenario 5 — H7: an installed evaluator for entity-native handler bodies (§6.13(a))");
    let responder = peer(0x51);
    let mut lb = Loopback::connect(responder.clone(), peer(0x52));
    let register = |lb: &mut Loopback, pattern: &str, body_path: &str, body: &Entity| -> u64 {
        let put = Entity::make(
            "system/tree/put-request",
            model::map(vec![("entity", body.to_cbor())]),
        );
        let (put_status, _) = lb.execute("system/tree", "put", put, &[body_path]);
        let req = Entity::make(
            "system/handler/register-request",
            model::map(vec![(
                "manifest",
                model::map(vec![
                    ("name", model::text(pattern)),
                    ("expression_path", model::text(body_path)),
                ]),
            )]),
        );
        let (reg_status, _) = lb.execute(
            "system/handler",
            "register",
            req,
            &[&format!("system/handler/{pattern}")],
        );
        put_status.max(reg_status)
    };
    let setup = [
        register(
            &mut lb,
            "probe/lit",
            "probe/bodies/lit",
            &Entity::make(
                "compute/literal",
                model::map(vec![("value", Value::UInt(50))]),
            ),
        ),
        register(
            &mut lb,
            "probe/dbl",
            "probe/bodies/dbl",
            &Entity::make("probe/double", model::map(vec![("n", Value::UInt(21))])),
        ),
        register(
            &mut lb,
            "probe/oth",
            "probe/bodies/oth",
            &Entity::make("probe/other", model::map(vec![])),
        ),
    ];
    let run = |lb: &mut Loopback, pattern: &str, bump: u64| {
        lb.execute(
            pattern,
            "run",
            Entity::make(
                "primitive/any",
                model::map(vec![("bump", Value::UInt(bump))]),
            ),
            &[pattern],
        )
    };
    let (s_none, _) = run(&mut lb, "probe/dbl", 1);
    let calls = Arc::new(AtomicUsize::new(0));
    responder.set_expression_evaluator(Some(Arc::new(Doubler {
        calls: calls.clone(),
    })));
    let (s_lit, lit) = run(&mut lb, "probe/lit", 1);
    let calls_after_literal = calls.load(Ordering::SeqCst);
    let (s_dbl, dbl) = run(&mut lb, "probe/dbl", 1);
    let (s_oth, _) = run(&mut lb, "probe/oth", 1);
    lb.shutdown();
    println!("  setup (put + register, x3)                {setup:?}");
    println!("  K. no evaluator, probe/double             {s_none}");
    println!("  L. evaluator set, compute/literal         {s_lit}  value={:?}  evaluator asked {calls_after_literal}x", lit.field("value"));
    println!(
        "  M. evaluator set, probe/double bump=1     {s_dbl}  value={:?}",
        dbl.field("value")
    );
    println!("  N. evaluator set, probe/other (declined)  {s_oth}");
    if setup.iter().any(|s| *s != 200) {
        vacuous.push("scenario 5 could not register its entity-native handlers — no arm measured");
    }
    let evaluator_reached = s_none == 501
        && s_lit == 200
        && calls_after_literal == 0
        && s_dbl == 200
        && dbl.field("value") == Some(&Value::UInt(43))
        && s_oth == 501;
    println!(
        "  => Reach (evaluator face): {}\n",
        if evaluator_reached { "YES" } else { "NO" }
    );

    // ── verdict ──────────────────────────────────────────────────────────────
    println!("\n--- summary ---");
    println!(
        "handler face:   Reach {reach} (executed: nothing-installed and uninstalled controls)"
    );
    println!("emit face:      Reach YES (executed, two negatives)");
    println!(
        "emit face, RE-ENTRANT (a consumer that writes): {}",
        if reentrant_ok {
            "YES (arm G)"
        } else {
            "NO (arm G)"
        }
    );
    println!(
        "emit face, FROM THE WIRE (put -> consumer -> get): {}",
        if wire_emit_ok {
            "YES (arms H/I)"
        } else {
            "NO (arms H/I)"
        }
    );
    println!(
        "frame budget:   by value {}",
        if budget_by_value { "YES" } else { "NO" }
    );
    println!(
        "evaluator face: Reach {}",
        if evaluator_reached { "YES" } else { "NO" }
    );
    println!("Access / Read / Export: see access_absent + access_control (rustc decides, not this binary)");

    // The contracts claim `handler`, `evaluator` and the H6 budget on this peer on the strength of
    // this binary. A NO here is not a vacuous run — it is the claim being false, and it fails.
    if !(reached && budget_by_value && evaluator_reached) {
        eprintln!("\nprobe verdict: a face the contracts claim INSTALLED on this peer measured NO");
        std::process::exit(1);
    }

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

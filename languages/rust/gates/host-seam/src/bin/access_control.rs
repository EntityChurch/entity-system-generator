//! **POSITIVE CONTROL for the compile-fail method. This binary MUST COMPILE.**
//!
//! Every symbol below is one the probe reports as *reachable across the crate
//! boundary*. If this file stops compiling, the sibling `access_absent` fixture's
//! failure means nothing: "the symbol is absent" and "this crate cannot see the peer
//! at all" produce the identical rustc exit code, and a compile-fail check without
//! this control reports its strongest result when the toolchain is broken.
//!
//! That is D15's false-green, in the one shape a compile-time instrument can take.

use entity_core_protocol::peer::core::Conn;
use entity_core_protocol::peer::model::{self, Entity};
use entity_core_protocol::peer::store::{Store, TreeChangeEvent};
use entity_core_protocol::peer::wire;
use std::sync::Arc;

use entity_core_protocol::peer::capability::check_path_permission;
use entity_core_protocol::peer::handler::{
    ExpressionEvaluator, FnHandler, Handler, HandlerContext, HandlerResult, LocalExecute, OperationSpec,
};
use entity_core_protocol::peer::{CreateOptions, Envelope, Peer, PeerConfig};

fn main() {
    // Access, the parts that ARE public: construct the peer, reach its store, reach
    // its identity, and drive a dispatch. All of it across the crate boundary.
    let peer = Peer::create(CreateOptions {
        seed: [0x11; 32],
        open_grants: true,
        conformance: false,
    });
    let _: &Store = &peer.store;
    let _: &str = &peer.local_peer;
    let _: &[u8] = &peer.identity.identity_hash;

    // The emit face: `register_tree_consumer` is public, and `TreeChangeEvent` is a
    // public struct with public fields, so a third party can both install a consumer
    // and NAME what it receives. Both halves matter -- Access without Export is a
    // callback whose argument you cannot destructure.
    peer.store.register_tree_consumer(|ev: &TreeChangeEvent| {
        let _ = (ev.event_type, &ev.path, &ev.new_hash, &ev.previous_hash);
    });

    // Entity construction and the tree/content store operations an extension needs.
    let e = Entity::make(
        "system/content/chunk",
        model::map(vec![("payload", model::bytes(b"control"))]),
    );
    peer.store.put_entity(&e);
    peer.store.bind("/x/y", &e);
    let _ = peer.store.get_by_hash(&e.hash);
    let _ = peer.store.get_at("/x/y");
    let _ = model::hex(&e.hash);

    // Inbound dispatch: `Peer::dispatch` is public. Note what this proves and what it
    // does not -- it is the entry point for a request ARRIVING, not a way to install
    // anything to answer one.
    let mut conn = Conn::new();
    let exec = wire::make_execute(wire::ExecuteFields {
        request_id: "control",
        uri: "system/protocol/connect",
        operation: "hello",
        params: wire::empty_params(),
        resource: None,
        author: None,
        capability: None,
    });
    let _ = peer.dispatch(&mut conn, &Envelope::new(exec));

    // The host contract a third party installs through (keystone H1, H3, H6, H7, H9, K-5). Named
    // here so that `access_absent`'s claims are about what is BEHIND these, not about these.
    let _: fn(&Peer, Arc<dyn Handler>) -> _ = Peer::install_handler;
    let _: fn(&Peer, &str) -> bool = Peer::unregister_handler;
    let _: fn(&Peer, Option<Arc<dyn ExpressionEvaluator>>) = Peer::set_expression_evaluator;
    let _: fn(&Peer) -> usize = Peer::max_frame_bytes;
    let _: fn(&str, &str, &Entity, &str, &str) -> bool = check_path_permission;
    let _ = PeerConfig::default().max_frame_bytes(1 << 20);
    let _ = |c: &HandlerContext<'_>| -> usize { c.frame_budget() };
    let _ = |c: &HandlerContext<'_>, l: LocalExecute| -> HandlerResult { c.dispatch_execute(l) };
    let installed = peer.install_handler(Arc::new(FnHandler::new(
        "app/control",
        "control",
        vec![OperationSpec::named("run")],
        |_ctx: &HandlerContext<'_>| HandlerResult::ok(Entity::make("primitive/any", model::map(vec![]))),
    )));
    assert!(installed.is_ok() && peer.has_native_handler("app/control"));

    println!("access_control: compiled and ran -- the peer IS reachable as a library, and a body installs");
}

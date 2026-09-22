//! **THIS BINARY MUST FAIL TO COMPILE. That failure is the measurement.**
//!
//! Behind `required-features = ["compile-fail-fixture"]`, so a plain `cargo build`
//! never touches it; only `probe-seam-rust.sh` builds it, and only to require the
//! failure. Its positive control is `access_control.rs`, which names the symbols that
//! ARE there and must compile in the same invocation.
//!
//! Four claims, one per line below, each an independent compile error:
//!
//!   1. **Access** — there is no public entry point that installs a language-native
//!      handler body. `Peer`'s entire public surface is `create` and `dispatch`.
//!   2. **Read** — there is no container of native bodies to consult. `Peer` has no
//!      `handlers` field of any visibility that a caller could write.
//!   3. **Export** — the body type cannot be named. `Outcome` is a bare `struct` in
//!      `peer::core` with no `pub`, so a third party cannot construct or return one.
//!   4. **Read, the other half** — `resolve_handler` and `dispatch_outcome` are
//!      private, so there is not even a route to ask what a pattern resolves to.
//!
//! On `typescript` and `python` these four questions were answered by a running
//! program poking at an object. Here they are answered by rustc, and the answer is
//! stronger for it: a missing symbol in this language is not a convention, a
//! docstring, or a leading underscore. It is not there.

use entity_core_protocol::peer::{CreateOptions, Peer};

fn main() {
    let peer = Peer::create(CreateOptions {
        seed: [0x11; 32],
        open_grants: true,
        conformance: false,
    });

    // (1) Access — the §11.6.1 step-4 write, "bind the language-native body".
    peer.register_handler("system/content", |_ctx| unimplemented!());

    // (2) Read — the container `typescript` calls `handlerRegistry` and `python`
    //     calls `peer.handlers`. There is no such field here at any visibility.
    peer.handlers.insert("system/content".to_string(), ());

    // (3) Export — the body's return type.
    let _: entity_core_protocol::peer::core::Outcome = unimplemented!();

    // (4) Read — the resolution path itself.
    let _ = peer.resolve_handler("/x/system/content");
}

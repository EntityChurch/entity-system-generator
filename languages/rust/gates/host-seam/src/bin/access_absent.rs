//! **THIS BINARY MUST FAIL TO COMPILE. That failure is the measurement.**
//!
//! Behind `required-features = ["compile-fail-fixture"]`, so a plain `cargo build` never touches
//! it; only `probe-seam-rust.sh` builds it, and only to require the failure. Its positive control is
//! `access_control.rs`, which names the symbols that ARE there and must compile in the same run.
//!
//! # What it claims now, and what it claimed until 2026-09-12
//!
//! It claimed the handler face had **no public install path**: `register_handler` private
//! (`E0624`), no `handlers` field (`E0609`), `Outcome` private (`E0603`), `resolve_handler` private
//! (`E0624`). Keystone landed H1 for K-9 and `register_handler` became public — and, as their reply
//! packet pointed out, this fixture then STILL produced four errors, one of them a wrong-argument
//! count on the now-public method. **A compile-fail arm that counts errors survived a change of
//! cause.** So the driver now requires each claim's exact code, not a count.
//!
//! The claims are keystone's **H3** — *"exposing the raw container instead of a registration call
//! does not satisfy H1"* — the registration call is public (see `access_control.rs`) and everything
//! BEHIND it is not:
//!
//!   1. `E0616` — the native-body container `route` reads is a private field.
//!   2. `E0609` — there is no `handlers` field at any visibility (the `python` spelling).
//!   3. `E0603` — `peer::core::Outcome`, the dispatcher's internal result, does not export.
//!   4. `E0624` — `resolve_handler`, the §6.6 walk, is a private method.

use entity_core_protocol::peer::{CreateOptions, Peer};

fn main() {
    let peer = Peer::create(CreateOptions {
        seed: [0x11; 32],
        open_grants: true,
        conformance: false,
    });

    // (1) H3 — the container behind `register_handler`.
    let _ = peer.native_handlers.read();

    // (2) the raw container under `python`'s name.
    peer.handlers.insert("system/content".to_string(), ());

    // (3) the dispatcher's internal outcome type.
    let _: Option<entity_core_protocol::peer::core::Outcome> = None;

    // (4) the resolution path itself.
    let _ = peer.resolve_handler("/x/system/content");
}

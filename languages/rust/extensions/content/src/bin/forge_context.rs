//! **THIS BINARY MUST FAIL TO COMPILE. The failure is §3.4's clause-1 measurement.**
//!
//! CLAIMS: E0451
//!
//! `reassemble_under_capability` demands `&HandlerContext`, and this fixture is the claim
//! that makes that demand mean anything: **a consumer cannot build one.**
//!
//! Until 2026-09-16 the wrapper demanded `&DispatchAuthority`, a crate-private token that
//! was genuinely unforgeable and proved the wrong proposition — *you came through this
//! crate's handler*, whose `handle_op` is also callable in-process. `HandlerContext` proves
//! *the dispatcher authorized you*: its fields are `pub(crate)` in the peer crate
//! (`HandlerContext`, `protocol-generator/rust/src/peer/handler.rs:470`), `Peer::route` is
//! the only site in the peer tree that builds one (`core.rs:911`), and it is reached only
//! after §5.2's `check_permission` ALLOWs.
//!
//! **The CONSTRUCTION is attempted, not the call**, and that is the point. A consumer who
//! cannot construct a context has no route to the wrapper at all, which is the whole of
//! §3.4's *"without an explicit capability-checking wrapper"* on this port. A rejected CALL
//! would only prove the signature, which `tests/sdk.rs` already asserts from the positive
//! side.
//!
//! **And the refusal is broader than this note first claimed.** It was written expecting
//! `E0451` to name one field, so that a `pub` on any single field would leave the fixture
//! still failing on the next one and the code alone would prove nothing about the others.
//! Observed output:
//!
//! > `error[E0451]: fields `peer`, `envelope`, `execute`, `pattern`, `suffix`,
//! > `caller_capability`, `handler_grant`, `conn` and `depth` of struct `HandlerContext`
//! > are private`
//!
//! `rustc` enumerates **every** private field in one diagnostic, so this fixture's failure
//! text is a per-field inventory of the anchor — and a field opening up would change the
//! list without changing the code, which is the shape a claim hides in. The driver matches
//! on the CODE, so it would not see that; the inventory is recorded in
//! `EXTENSION.toml [substrate.capability_wrapper]` where a re-measurement compares it.

fn main() {
    let _ = entity_core_protocol::peer::handler::HandlerContext {
        peer: unimplemented!(),
        envelope: unimplemented!(),
        execute: unimplemented!(),
        pattern: unimplemented!(),
        suffix: unimplemented!(),
        caller_capability: unimplemented!(),
        handler_grant: unimplemented!(),
        conn: unimplemented!(),
        depth: unimplemented!(),
    };
}

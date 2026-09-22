//! **THIS BINARY MUST FAIL TO COMPILE. The failure is the §3.4 measurement.**
//!
//! Behind `required-features = ["compile-fail-fixture"]`, so a normal build never
//! touches it. `languages/rust/test` builds it once, requires the failure, and runs
//! `tests/export_surface.rs` as the positive control in the same invocation.
//!
//! The three ports assert the same MUST against three different mechanisms:
//!
//! - `typescript` — `assert.rejects(() => import("...:/internal/reassemble.js"))`, with
//!   the specifier assembled at RUNTIME so node's resolver is the layer that refuses.
//!   Written as a literal first, and then `tsc` killed the build at TS2307 before the
//!   assertion ran — AP-3, "the check passing and the check being unrunnable look
//!   identical from the outside".
//! - `python` — asserts the convention holds AND that it can be walked around, because
//!   there the boundary is a promise and claiming parity would be a D13 error.
//! - here — the compiler refuses, and the analogue of AP-3 is the reason this fixture
//!   is not just "a test that imports the module". A test file that fails to compile
//!   fails the whole `cargo test` invocation and is indistinguishable from a broken
//!   crate, so the refusal has to be requested deliberately and scored deliberately.

fn main() {
    // The §3.4 primitive, reached the only way it could be reached: by naming the
    // private module. `error[E0603]: module `internal` is private`.
    let _ = entity_content::internal::reassemble::reassemble_content;

    // And the type it returns, for the same reason.
    let _: entity_content::internal::reassemble::Reassembled = unimplemented!();
}

//! **THIS BINARY MUST FAIL TO COMPILE. The failure is the boundary measurement.**
//!
//! CLAIMS: E0603
//!
//! Behind `required-features = ["compile-fail-fixture"]`, so a normal build never
//! touches it. `languages/rust/test` builds it once, requires the failure to be
//! `error[E0603]` *specifically*, and runs the cell's integration tests as the positive
//! control in the same invocation — because "it did not compile" is otherwise
//! indistinguishable from "the crate does not build here at all", which is the D15 false
//! green in its purest form.
//!
//! **CONTENT had §3.4 to point at. HISTORY has no such clause**, and the line is ours to
//! draw (D16, the position `[sdk_surface]` put us in). It is drawn at
//! `record_transition` because a caller who can reach it can append a forged entry to an
//! audit chain — choosing its own `author` and `capability`, at any path, linked into
//! the real chain by `previous`. §7.2 calls the capability field the answer to *"under
//! what authority?"*; a forgeable answer is worse than no answer, because it is
//! believed.

fn main() {
    // The recorder body, reached the only way it could be reached: by naming the private
    // module. `error[E0603]: module `internal` is private`.
    let _ = entity_history::internal::recorder::record_transition;

    // And the config lookup behind it, which is how a forger would find the head to
    // link onto.
    let _ = entity_history::internal::recorder::find_history_config;
}

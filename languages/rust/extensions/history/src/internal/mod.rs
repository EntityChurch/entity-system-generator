//! **NOT `pub` at the crate root.** `lib.rs` declares `mod internal;` without it, so
//! everything below is invisible outside this crate — `error[E0603]`, not a convention
//! and not an underscore.
//!
//! # What is behind the boundary, and why it is a sharper line than CONTENT's
//!
//! CONTENT put `reassemble_content` here because §3.4 has a MUST that says to. HISTORY
//! has no such clause; the line is ours to draw (D16, the same position `[sdk_surface]`
//! put us in). It is drawn here because **a caller able to reach
//! [`recorder::record_transition`] could append a forged entry to an audit chain** —
//! any `author`, any `capability`, at any path, linked into the real chain by
//! `previous` and content-addressed exactly like a real one. §7.2 calls the capability
//! field the answer to *"under what authority?"*, and a forgeable answer is worse than
//! no answer, because it is believed.
//!
//! The three ports draw the same line with three different amounts of force, and that
//! difference is measured rather than asserted:
//!
//! | port | mechanism | who refuses |
//! |---|---|---|
//! | `typescript` | the `exports` map | node, at resolve time |
//! | `python` | leading-underscore convention | **nobody** — the test asserts it can be walked around |
//! | `rust` | no `pub` on `mod internal` | **rustc**, at compile time |
//!
//! `src/bin/deep_import.rs` is this port's fixture and `languages/rust/test` builds it
//! expecting `error[E0603]` specifically — any other error means the arm measured the
//! build rather than the boundary.

pub(crate) mod recorder;

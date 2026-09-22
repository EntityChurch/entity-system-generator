//! **NOT `pub` at the crate root.** `lib.rs` declares `mod internal;` without it, so everything
//! below is invisible outside this crate — `error[E0603]`, enforced by rustc.
//!
//! # What is behind the boundary, and why the line is sharper here than for CONTENT or HISTORY
//!
//! `evaluator::evaluate` takes its whole authority as an `EvalContext`. A caller able to build one
//! could set `has_content_store_access` — §4.2 Tier 0, the evaluator as the content-store oracle
//! §4.2 exists to prevent — or pass `can_read_path` that always answers true, which is §6.2's
//! capability check removed. The public [`crate::sdk::ComputeEvaluator`] builds the context itself
//! and exposes only the settings a caller legitimately supplies.
//!
//! | port | mechanism | who refuses |
//! |---|---|---|
//! | `typescript` | the `exports` map | node, at resolve time |
//! | `python` | leading-underscore convention | **nobody** — its test asserts the walk-around works |
//! | `rust` | no `pub` on `mod internal` | **rustc**, at compile time |
//!
//! `reactive::ReactiveEngine` and `reactive::deterministic_id` are re-exported from `lib.rs`: the
//! engine reads its authority from the installation grant on the subgraph metadata and widens
//! nothing, and the id is a cross-peer identity rather than an internal detail.

pub(crate) mod evaluator;
pub(crate) mod reactive;
pub(crate) mod subgraph;

#[cfg(test)]
mod apply_handler_tests;

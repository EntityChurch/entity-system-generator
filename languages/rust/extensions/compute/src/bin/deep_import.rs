//! **THIS BINARY MUST FAIL TO COMPILE. The failure is the boundary measurement.**
//!
//! CLAIMS: E0603
//!
//! Behind `required-features = ["compile-fail-fixture"]`; `languages/rust/test` builds it once and
//! requires `error[E0603]` specifically, with the cell's integration tests as the positive control.
//!
//! The line is drawn at the evaluator because its context IS its authority: a caller who can name
//! `EvalContext` can build one with §4.2 Tier 0 switched on, or with a path predicate that always
//! answers yes.

fn main() {
    // The evaluator body, reached the only way it could be: by naming the private module.
    let _ = entity_compute::internal::evaluator::evaluate;

    // And the install audit, whose refusals are the only record of what a subgraph may touch.
    let _ = entity_compute::internal::subgraph::audit_subgraph;
}

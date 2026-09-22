//! **Private module. Declared `mod internal;` in `lib.rs`, with no `pub`.**
//!
//! This is the §3.4 boundary in this language, and it is the third distinct mechanism
//! for one MUST across three ports:
//!
//! | | boundary object | enforced by | can a consumer walk around it? |
//! |---|---|---|---|
//! | `typescript` | the `exports` map in `package.json` | node, at resolve time | no — `ERR_PACKAGE_PATH_NOT_EXPORTED` |
//! | `python` | convention: `_internal` + `__all__` + a test | **nothing** | **yes**, and the test asserts that it can |
//! | `rust` | the absence of `pub` on this `mod` | **rustc, at compile time** | no — `E0603`, and there is no dynamic route |
//!
//! **Strongest of the three on §3.4's first clause, and weakest on its second**, which
//! is the finding this port produced and neither of the others could. §3.4 says two
//! things: do not expose `reassemble_content` publicly, *and* put an explicit
//! capability-checking wrapper in front of it. Those two clauses do not move together.
//! See `sdk::reassemble_under_capability` for the second, where this substrate has the
//! least to work with, because the peer's dispatch context type is private and there
//! is no dispatcher-minted token to demand.
//!
//! Recorded in `EXTENSION.toml [substrate.export_boundary]` as three strengths on two
//! clauses, not as one verdict. Reporting one verdict for materially different
//! boundaries is the D13 error.

pub(crate) mod reassemble;

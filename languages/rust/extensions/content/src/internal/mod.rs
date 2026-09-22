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
//! **Strongest of the three on §3.4's first clause.** §3.4 says two things: do not
//! expose `reassemble_content` publicly, *and* put an explicit capability-checking wrapper
//! in front of it. Those two clauses do not move together. See
//! `sdk::reassemble_under_capability` for the second: its token is crate-private, and it
//! checks no capability. (This port was first recorded as weakest on the second clause,
//! because until keystone's H1 on 2026-09-12 the peer had no dispatcher-built context to
//! demand; the 2026-09-12 review found the other two ports' contexts caller-constructible.)
//!
//! Recorded in `EXTENSION.toml [substrate.export_boundary]` as three strengths on two
//! clauses, not as one verdict. Reporting one verdict for materially different
//! boundaries is the D13 error.

pub(crate) mod reassemble;

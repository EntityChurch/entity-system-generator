# `seed-policy` — can this target's peer be put in a posture where authorization is observable?

**The question this gate asks is not about an extension.** It asks what *posture* we are able to
measure in, which is the thing that decides whether a whole class of our findings is observable at
all.

## Why it exists

Every conformance run in this repo launches the peer under test with `--debug-open-grants`
(`tools/host-launch:137`), which selects the degenerate `default → *` seed policy. Under it **every
capability in the corpus is the wide-open admin grant**, so an extension that checks authorization
per tree read and one that answers `return true` unconditionally produce **identical** numbers.

Two of the five findings routed as `ROUTING-2026-09-10-d-arch-*` are exactly that class —
`EXTENSION-COMPUTE` §3.3's install audit collecting a read path set that Phase 2 then
capability-checks. This tree asserted for a day that those were *"invisible to the corpus in
principle"* and credited `validate-peer` with the launch. **Both halves were wrong**: the oracle
dials `-addr` and launches nothing, and the posture is one we choose. Corrected 2026-09-11, routed
as `ROUTING-2026-09-11-arch-the-posture-we-measure-in-is-ours-and-it-is-deprecated` §1.

**So the correction owes a measurement, not a sentence.** `unmeasured` is only an honest downgrade
from `unmeasurable` if a posture that *would* measure it demonstrably exists on the substrate. That
is what this gate establishes, per target.

## What an arm must report

Three arms over one predicate, and the third is what makes the second mean anything:

| policy | in-scope read | out-of-scope read | what it establishes |
|---|---|---|---|
| `default → *` (the degenerate debug seed) | permit | **permit** | the posture we run in is **undiscriminating** — the negative control, and it is the posture itself |
| a **narrow** declared policy | permit | **refuse** | authorization is **observable** on this peer |
| the §4.4 discovery floor | refuse | refuse | the resource scope is genuinely **read** — without this row, "narrow refuses" is equally explained by a policy that refuses everything |

**The third row is the one a reviewer should look for first.** A two-arm version of this gate
passes identically whether the peer consults the resource scope or merely counts grants, which is
D15's false-green in its cheapest form.

## What it does NOT establish

**This is an in-process predicate measurement, not a wire probe**, and the distinction is the whole
of D13's Reach layer. It shows the peer's `checkPathPermission` discriminates when handed a narrow
grant. It does **not** show that a capability *delivered by §4.6 authenticate from a declared seed
policy* reaches an extension's install audit over the wire — that needs a host that accepts
`--seed-policy`, and **no host binary in the keystone cohort implements one** (routed as
`ROUTING-2026-09-11-b-keystone-*` §1; the format and examples exist at
`shared/seed-policy/`, the CLI plumbing does not).

So an arm here reads on the **`policy_discriminates`** axis and says nothing about `handler`
reach. A roster row citing this gate names that axis or it is over-claiming (D13's face amendment:
a seam claim names a face, or it names nothing).

## Substrate note — the arms will not be uniform, and that is the finding

`typescript` can run all three arms because its peer takes a `SeedPolicy` **value**
(`Peer({seedPolicy})`, with `debugOpenGrants` documented *"ignored when seedPolicy is supplied"*).
`python` and `rust` expose `open_grants: bool` over two hardcoded scopes and **cannot construct a
policy in between at all** — so on those targets the narrow arm has nothing to construct, and the
correct output is `REFUSING`, not a pass. Tracked as keystone `K-7`.

**An arm that cannot build the narrow policy refuses; it never reports two green arms as a
verdict.** Two arms out of three is the vacuity case this axis has, and a gate that can only say
PASS or FAIL has no way to say *"I did not measure anything"* (D15, sharpened).

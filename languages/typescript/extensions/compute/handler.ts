/**
 * COMPUTE §3 — the `system/compute` handler.
 *
 * §3.1 declares three operations and we declare all three, which is a DECISION and
 * not a transcription: §10.2 lists *"Compute handler at `system/compute/*`"* and
 * *"Install and uninstall operations — required if reactive mode is implemented"* as
 * SHOULDs, while §10.1 MUSTs three behaviours OF the install operation. Four
 * documents, three answers (`ROUTING-2026-09-09-d-arch-*` §4).
 *
 * **What settled it for this port is the oracle, and that is worth stating plainly
 * rather than dressing up as a spec reading.** `entity-core-go`'s `validate-peer`
 * declares `handler_op_install` and `handler_op_uninstall` whose body is
 * `FailCheck("compute handler missing operation: " + op)` — a hard FAIL on a manifest
 * that omits either, and 6 of the category's 128 checks are blocked behind
 * `handler_op_install`. So the measurable answer is three, the spec's answer is
 * ambiguous, and we declare three and route the ambiguity.
 *
 * **All three operations are implemented as of 2026-09-10.** Through the previous
 * session `install` and `uninstall` answered `501 not_implemented` naming §3.3,
 * because the audit SEALS `authorized_data_hashes` — a §4.2 Tier 2 authorization
 * surface — and a half-built audit produces a subgraph admitting hashes nobody
 * validated. The audit is now complete (`internal/subgraph.ts`), so the four phases
 * run in order and Tier 2 is non-empty for the first time in this corpus.
 *
 * **The four phases are PRE-FLIGHT then COMMIT, and §3.3 makes that atomicity
 * normative.** Phases 1–2b decide; Phases 3–4 write. A re-install whose audit fails
 * leaves the previous (possibly frozen) metadata unchanged, so a caller can retry
 * with a different capability or a corrected expression without losing the frozen
 * state. Nothing below writes anything before the last check has passed.
 */

import {
  Ecf,
  Entity,
  HandlerResult,
  Permissions,
  Status,
  errorResult,
  type CapabilityToken,
  type Handler,
  type HandlerContext,
  type HandlerOperations,
  type codec,
} from "entity-core-protocol-typescript";

import {
  CODE_AMBIGUOUS_RESOURCE,
  CODE_INVALID_EXPRESSION,
  CODE_NOT_FOUND,
  CODE_PERMISSION_DENIED,
  COMPUTE_PATTERN,
  DEFAULT_MAX_DEPTH,
  DEFAULT_MAX_OPS,
  INSTALL_REQUEST,
  INSTALL_RESULT,
  PROCESSES_PREFIX,
  RESULT,
  SUBGRAPH,
  isComputeExpression,
} from "./types.js";
import { ComputeEvaluator, type EvaluatorLimits } from "./sdk.js";
import { canonicalize, hexOf } from "./internal/evaluator.js";
import {
  AuditRefusal,
  auditSubgraph,
  grantCovers,
  type AuditContext,
  type SubgraphAudit,
} from "./internal/subgraph.js";
import { deterministicId, type ReactiveEngine } from "./internal/reactive.js";

export interface ComputeHandlerOptions {
  /** §9.3 `peer_default_max_ops`. §10.4 makes the value implementation-defined. */
  readonly maxOperations?: number;
  /** §9.3 `peer_default_max_depth` / `RECOMMENDED_MAX_DEPTH`. */
  readonly maxDepth?: number;
}

export class ComputeHandler implements Handler {
  readonly pattern = COMPUTE_PATTERN;
  readonly name = "compute";

  /**
   * §3.1's manifest, verbatim — including the input/output types.
   *
   * `eval` declares `primitive/any` on BOTH sides and that is the spec's shape, not
   * a placeholder: the input is any compute expression entity and the output is a
   * value, a `compute/result` or a `compute/error`. A narrower declaration here would
   * be a claim §3.2 does not make.
   */
  readonly operations: HandlerOperations = {
    eval: {
      inputType: "primitive/any",
      outputType: "primitive/any",
    },
    install: {
      inputType: INSTALL_REQUEST,
      outputType: INSTALL_RESULT,
    },
    uninstall: {
      // §3.1: "empty-params per V7 §3.2". There is no
      // `system/compute/uninstall-request` — the type was eliminated in v3.12 and
      // uninstall uses the path-as-resource convention. The declaration header still
      // names one; that is the §9.2 drift, filed.
      inputType: "primitive/any",
      outputType: "system/protocol/status",
    },
  };

  readonly #limits: EvaluatorLimits;
  /**
   * §7's engine, or `null` when reactive mode is not installed.
   *
   * **Nullable rather than always-present, and that is a face distinction rather than
   * defensive coding** (D13's face amendment). `install` writes subgraph metadata
   * whose whole purpose is to be woken by §7.2, and §3.3's *"Expressions without
   * installation"* clause is explicit that reactive mode requires an installation
   * grant. A handler that accepted an install with no engine behind it would answer
   * 200 for an operation that can never do anything — the `501`-shaped lie one level
   * up. So the handler refuses, naming the face.
   */
  readonly #engine: ReactiveEngine | null;

  constructor(options: ComputeHandlerOptions = {}, engine: ReactiveEngine | null = null) {
    this.#limits = {
      maxOperations: options.maxOperations ?? DEFAULT_MAX_OPS,
      maxDepth: options.maxDepth ?? DEFAULT_MAX_DEPTH,
    };
    this.#engine = engine;
  }

  async handle(ctx: HandlerContext): Promise<HandlerResult> {
    switch (ctx.operation) {
      case "eval":
        return this.#eval(ctx);
      case "install":
        return this.#install(ctx);
      case "uninstall":
        return this.#uninstall(ctx);
      default:
        return errorResult(
          Status.BadRequest,
          "unknown_operation",
          `${COMPUTE_PATTERN} has no operation '${ctx.operation}' (§3.1)`,
        );
    }
  }

  /**
   * §3.2 `handle_eval`.
   *
   * **The three refusals below are in §3.2's order and each has its own code.** The
   * ordering matters for the same reason §4.1's builtin-path shape check does: a
   * resolution failure and a not-an-expression failure are different codes, and
   * deciding them in the other order would make the answer depend on which fault a
   * malformed request hits first.
   *
   * **And the last line is the one that surprises people.** An evaluated
   * `compute/error` comes back at **status 200** with the error as the result entity
   * (F10, and v3.19c's normative clarification for `permission_denied`). 4xx is
   * reserved for authorization of the REQUEST, before evaluation. A caller detects a
   * computed error by `result.type == "compute/error"`, never by the status — and a
   * port that maps it to 4xx would look more correct and be less interoperable.
   */
  async #eval(ctx: HandlerContext): Promise<HandlerResult> {
    // §3.2: "eval requires exactly one resource target (the expression path)".
    if (ctx.resource === null || ctx.resource.targets.length !== 1) {
      return errorResult(
        Status.BadRequest,
        "ambiguous_resource",
        "eval requires exactly one resource target (the expression path)",
      );
    }
    const expressionUri = ctx.resource.targets[0] as string;

    const absolute = expressionUri.startsWith("/")
      ? expressionUri
      : "/" + ctx.localPeerId + "/" + expressionUri;
    const expression = ctx.peer.tree.get(absolute);
    if (expression === undefined) {
      return errorResult(Status.NotFound, "not_found", "No entity at path");
    }
    if (!isComputeExpression(expression.type)) {
      return errorResult(
        Status.BadRequest,
        "invalid_expression",
        "Entity at path is not a compute expression",
      );
    }

    const evaluator = new ComputeEvaluator(ctx.peer, this.#limits);
    // §3.2: for an explicit eval the subgraph root IS the expression URI. For an
    // installed subgraph it comes from `root_expression_path` — "same value,
    // different source", which is why this is a parameter and not a constant.
    const outcome = evaluator.evaluateAt(expression, absolute, {
      budget: readBudgetOverride(ctx),
      // §6.2, PER TREE READ — and this line is a CORRECTION of a finding this repo
      // routed and got wrong. Through 2026-09-10 `[assumptions].capability_check_scope`
      // read *"the peer exposes no path-scope predicate over [the caller's token] that
      // an extension can call"*, so §6.2 was satisfied at the dispatch boundary only
      // and a caller reaching `system/compute:eval` could read any path. That claim
      // was false when it was written: `Permissions.checkPathPermission` is public on
      // this peer, it takes a `CapabilityToken`, and **our own
      // `TRACKER-entity-core-keystone.md` carries it as H9, CLOSED.** We routed the
      // primitive's absence on `python`, watched it land, and then wrote in a
      // different contract that it did not exist. D12/L8 in its plainest form — a
      // source read, never re-run against the tree it describes.
      //
      // `callerCapability` is null only for an in-process dispatch with no verified
      // token, where there is nothing to narrow with and the dispatch boundary is
      // again the whole of the answer.
      ...pathAuthority(ctx.callerCapability, ctx.localPeerId),
    });

    if (outcome.error !== null) {
      // F10 — an evaluated error is a VALUE at 200.
      return HandlerResult.ok(outcome.error.toEntity());
    }

    // §2.4 — a primitive result is wrapped in a `compute/result` carrying the source
    // expression's hash; an entity result travels as itself. §3.2's entity-native
    // unwrapping table is the same split read from the other side.
    const value = outcome.value;
    if (value instanceof Entity) {
      return HandlerResult.ok(value);
    }
    return HandlerResult.ok(
      Entity.create(
        RESULT,
        Ecf.map(["value", value], ["expression", Ecf.bytes(expression.contentHash)]),
      ),
    );
  }

  /**
   * §3.3 `handle_install` — the four phases, in order, pre-flight before commit.
   *
   * **Read the phase boundary as the security boundary.** Phase 2 asks whether the
   * CALLER's capability covers every impure operation the subgraph will perform;
   * everything after installation runs under that same grant (§7.2's *"Authorization
   * source"*) and is never re-audited. So Phase 2 is the only moment at which the
   * question is asked, and Phase 2b's `authorized_data_hashes` is the only record of
   * the answer. That is why this operation refused to ship half-built.
   */
  async #install(ctx: HandlerContext): Promise<HandlerResult> {
    const engine = this.#engine;
    if (engine === null) {
      return errorResult(
        Status.NotSupported,
        "not_implemented",
        "system/compute:install requires §7 reactive mode, which is not installed in " +
          "this composition (the emit_consumer face). An install with no engine behind " +
          "it would record a subgraph nothing can ever wake.",
      );
    }

    // §3.3: "install requires exactly one resource target (the root expression path)".
    if (ctx.resource === null || ctx.resource.targets.length !== 1) {
      return errorResult(
        Status.BadRequest,
        CODE_AMBIGUOUS_RESOURCE,
        "install requires exactly one resource target (the root expression path)",
      );
    }
    const rootPath = canonicalize(ctx.resource.targets[0] as string, ctx.localPeerId);

    const expression = ctx.peer.tree.get(rootPath);
    if (expression === undefined) {
      return errorResult(Status.NotFound, CODE_NOT_FOUND, "No expression at path");
    }
    if (!isComputeExpression(expression.type)) {
      return errorResult(
        Status.BadRequest,
        CODE_INVALID_EXPRESSION,
        "Entity at path is not a compute expression",
      );
    }

    // ── Phase 1 — audit the subgraph ────────────────────────────────────────────
    const auditCtx: AuditContext = {
      tree: ctx.peer.tree,
      contentStore: ctx.peer.contentStore,
      localPeerId: ctx.localPeerId,
      // §4.2 step 1 — the envelope's `included` map, ALREADY keyed by lowercase hex
      // (`Envelope.included`). The audit resolves through it before the content
      // store, which is what lets an installer carry an embedded capability's chain
      // in the EXECUTE rather than having to publish it first; CP1's adversarial
      // vector arrives exactly that way.
      included: ctx.envelope.included,
      author: ctx.author,
    };
    const audit = auditSubgraph(expression, rootPath, auditCtx);
    if (audit instanceof AuditRefusal) {
      return errorResult(audit.status, audit.code, audit.message);
    }

    // ── Phase 2 — the caller's capability covers every impure operation ─────────
    const capability = ctx.callerCapability;
    if (capability === null) {
      return errorResult(
        Status.Forbidden,
        CODE_PERMISSION_DENIED,
        "install requires a verified caller capability to audit against",
      );
    }
    // §PR-8: a grant's RESOURCE patterns canonicalize on the GRANTER's frame, not the
    // verifier's, so a bare `*` on a foreign-granted capability means `/{granter}/*`
    // and does not reach this peer's namespace. Deriving it here rather than passing
    // the local id is what keeps the audit from over-admitting a cross-peer grant.
    const granterPeerId = Permissions.resolveGranterPeerId(capability, ctx.envelope, ctx.localPeerId);

    for (const path of audit.readPaths) {
      if (!Permissions.checkPathPermission("get", path, capability, "system/tree", ctx.localPeerId)) {
        return errorResult(Status.Forbidden, CODE_PERMISSION_DENIED, "Caller capability does not cover read: " + path);
      }
    }
    for (const target of audit.handlerTargets) {
      if (!grantCovers(capability, target.path, target.operation, target.resource, ctx.localPeerId, granterPeerId)) {
        return errorResult(
          Status.Forbidden,
          CODE_PERMISSION_DENIED,
          "Caller capability does not cover handler: " + target.path + "." + (target.operation ?? ""),
        );
      }
    }

    const requested = readResultPathOverride(ctx);
    const resultPath = requested === null ? rootPath + "/result" : canonicalize(requested, ctx.localPeerId);
    if (!Permissions.checkPathPermission("put", resultPath, capability, "system/tree", ctx.localPeerId)) {
      return errorResult(
        Status.Forbidden,
        CODE_PERMISSION_DENIED,
        "Caller capability does not cover result write: " + resultPath,
      );
    }
    for (const path of audit.writePaths) {
      const canonical = canonicalize(path, ctx.localPeerId);
      if (!Permissions.checkPathPermission("put", canonical, capability, "system/tree", ctx.localPeerId)) {
        return errorResult(Status.Forbidden, CODE_PERMISSION_DENIED, "Caller capability does not cover write: " + canonical);
      }
    }

    // ── Phase 2b — validate `compute/lookup/hash` data references (v3.7 D5/D6) ──
    //
    // THE SET THIS LOOP BUILDS IS THE ONE §4.2 TIER 2 TRUSTS WITHOUT RE-CHECKING.
    // Each entry is validated three ways — the hint path resolves, the entity there
    // hashes to the referenced value, and the caller may read that path — and only
    // then is the hash admitted. A `compute/lookup/hash` with no hint is refused
    // outright: resolving it would need a reverse index this port does not have, and
    // §3.3 makes "or reject" one of the three permitted dispositions.
    const authorizedDataHashes: Uint8Array[] = [];
    for (const entry of audit.dataHashes) {
      if (entry.path === null) {
        return errorResult(
          Status.BadRequest,
          "no_authorization_path",
          "compute/lookup/hash without path hint requires reverse index or content_store_access",
        );
      }
      const hintPath = canonicalize(entry.path, ctx.localPeerId);
      const bound = ctx.peer.tree.get(hintPath);
      if (bound === undefined) {
        return errorResult(Status.NotFound, CODE_NOT_FOUND, "No entity at hint path: " + hintPath);
      }
      if (hexOf(bound.contentHash) !== hexOf(entry.hash)) {
        return errorResult(
          Status.BadRequest,
          "hash_mismatch",
          "Entity at " + hintPath + " has hash " + hexOf(bound.contentHash) +
            ", expression references " + hexOf(entry.hash),
        );
      }
      if (!Permissions.checkPathPermission("get", hintPath, capability, "system/tree", ctx.localPeerId)) {
        return errorResult(Status.Forbidden, CODE_PERMISSION_DENIED, "Caller grant does not cover tree GET at: " + hintPath);
      }
      authorizedDataHashes.push(entry.hash);
    }

    // ── Phase 3 — commit the subgraph metadata ─────────────────────────────────
    const subgraphPath = canonicalize(PROCESSES_PREFIX, ctx.localPeerId) + "/" + deterministicId(rootPath);

    // §3.3, and this clause is the one an implementation drops: the caller's
    // capability entity MUST reach the content store before its hash is recorded.
    // The grant is only in the envelope for the length of this EXECUTE; §7.2 fetches
    // it by hash on every re-evaluation, and a subgraph whose grant cannot be
    // resolved freezes with `installation_grant_invalid` the first time it fires.
    ctx.peer.contentStore.put(capability.entity);

    const subgraph = Entity.create(
      SUBGRAPH,
      Ecf.map(
        ["root_expression_path", Ecf.text(rootPath)],
        ["root_expression", Ecf.bytes(expression.contentHash)],
        ["installation_grant", Ecf.bytes(capability.contentHash)],
        ["installed_by", ctx.author === null ? null : Ecf.bytes(ctx.author)],
        ["result_path", Ecf.text(resultPath)],
        ["status", Ecf.text("active")],
        // The SEVENTH field. §2.5's type block declares six; §3.3 Phase 3 writes this
        // one, §4.2 reads it, §10.1 MUSTs it by name, and `entity-core-go`'s
        // `ComputeSubgraphData` carries it `omitempty`. Omitted when empty so the
        // bytes agree with the reference for the common case.
        ...(authorizedDataHashes.length > 0
          ? ([["authorized_data_hashes", Ecf.array(authorizedDataHashes.map((h) => Ecf.bytes(h)))]] as const)
          : []),
      ),
    );
    ctx.peer.tree.put(subgraphPath, subgraph, ctx.emitContext());

    // ── Phase 4 — register dependencies, then evaluate once ────────────────────
    engine.register(subgraphPath, rootPath, audit);
    // §3.3's re-installation clause SHOULDs an initial evaluation, and doing it on
    // every install rather than only on re-install is what makes the two paths one
    // path: a `result_path` that is absent until the first dependency changes is a
    // second state for every downstream reader to handle. It also clears a
    // `compute/error` left by a frozen predecessor, which is the other half of that
    // SHOULD.
    engine.evaluateNow(subgraphPath, ctx.emitContext());

    return HandlerResult.ok(
      Entity.create(
        INSTALL_RESULT,
        Ecf.map(
          ["subgraph_path", Ecf.text(subgraphPath)],
          ["impure_operations", impureOperations(audit)],
          ["result_path", Ecf.text(resultPath)],
        ),
      ),
    );
  }

  /**
   * §3.4 `handle_uninstall` — clear the registrations, delete the metadata.
   *
   * **The expression entities are NOT deleted**, and §3.4 says so in one line: they
   * remain in the tree as inert data. Uninstall withdraws the installation grant's
   * standing authorization; it does not withdraw the program.
   */
  async #uninstall(ctx: HandlerContext): Promise<HandlerResult> {
    const engine = this.#engine;
    if (engine === null) {
      return errorResult(
        Status.NotSupported,
        "not_implemented",
        "system/compute:uninstall requires §7 reactive mode, which is not installed in this composition",
      );
    }
    if (ctx.resource === null || ctx.resource.targets.length !== 1) {
      return errorResult(
        Status.BadRequest,
        CODE_AMBIGUOUS_RESOURCE,
        "uninstall requires exactly one resource target (the subgraph path)",
      );
    }
    const subgraphPath = canonicalize(ctx.resource.targets[0] as string, ctx.localPeerId);
    const subgraph = ctx.peer.tree.get(subgraphPath);
    if (subgraph === undefined || subgraph.type !== SUBGRAPH) {
      return errorResult(Status.NotFound, CODE_NOT_FOUND, "No installed subgraph at path");
    }

    engine.unregister(subgraphPath);
    ctx.peer.tree.remove(subgraphPath, ctx.emitContext());

    // §3.4 returns `{status: 200}` and nothing else. The STATUS is the answer and it
    // rides the EXECUTE_RESPONSE, so the result entity is the peer's empty-ack shape
    // rather than a body — §3.1's manifest names `system/protocol/status` as the
    // output type and core defines no such entity type, which is the §9.2 drift
    // already filed. Minting one here would put a type on the wire no registry knows.
    return HandlerResult.ok(Entity.create("primitive/any", Ecf.emptyMap()));
  }
}

/**
 * §3.3's `impure_operations` — the audit's four categories, as the install result's
 * `primitive/any` payload.
 *
 * Reported verbatim rather than summarized. The caller asked the handler to audit a
 * graph on its behalf and this is the audit; a count would tell it that N things were
 * checked without telling it which, and the reason the field is `primitive/any` in
 * §2.6 is that its shape is the audit's shape.
 */
function impureOperations(audit: SubgraphAudit): codec.EcfValue {
  return Ecf.map(
    ["read_paths", Ecf.array(audit.readPaths.map((p) => Ecf.text(p)))],
    [
      "handler_targets",
      Ecf.array(
        audit.handlerTargets.map((t) =>
          Ecf.map(
            ["path", Ecf.text(t.path)],
            ["operation", t.operation === null ? null : Ecf.text(t.operation)],
          ),
        ),
      ),
    ],
    ["write_paths", Ecf.array(audit.writePaths.map((p) => Ecf.text(p)))],
    ["data_hashes", Ecf.array(audit.dataHashes.map((d) => Ecf.bytes(d.hash)))],
  );
}

/**
 * §6.2 / §6.3's two path predicates, built from the caller's own capability.
 *
 * **Two predicates and not one**, because §6.3's table gives the two operations
 * different authorities: a tree READ rides `ctx.capability`, and a `store` WRITE rides
 * the caller's capability with the handler explicitly forbidden from substituting its
 * own grant (no silent escalation). They happen to be the same token here and they are
 * not the same question, so collapsing them would hide that a future port with a
 * handler grant has a decision to make.
 *
 * Returns an empty object when there is no token — spreading nothing leaves
 * `EvaluateOptions`' permissive defaults in place, which is the honest answer for a
 * dispatch that arrived with no capability to narrow.
 */
function pathAuthority(
  capability: CapabilityToken | null,
  localPeerId: string,
): { canReadPath?: (p: string) => boolean; canWritePath?: (p: string) => boolean } {
  if (capability === null) return {};
  return {
    canReadPath: (path) => Permissions.checkPathPermission("get", path, capability, "system/tree", localPeerId),
    canWritePath: (path) => Permissions.checkPathPermission("put", path, capability, "system/tree", localPeerId),
  };
}

/**
 * §2.6 — `install-request.result_path`, optional. `null` means "use the default".
 *
 * Takes the CONTEXT and not the params entity, for the reason in
 * {@link readBudgetOverride}: `HandlerContext.params` is a getter that decodes, and
 * decoding is the step that can throw.
 */
function readResultPathOverride(ctx: HandlerContext): string | null {
  try {
    return Ecf.optText(ctx.params.data, "result_path");
  } catch {
    return null;
  }
}

/**
 * §3.2 — `params` optionally carries operation knobs (`{budget: ...}`).
 *
 * Returns `null` when absent, which is different from returning the default: the
 * default lives in one place (the handler's constructor, from §9.3) and a `null`
 * here means *"the caller did not ask"*, so the two cannot drift apart. §5.2's
 * minimum rule then applies between this and any capability constraint.
 *
 * **IT TAKES THE CONTEXT RATHER THAN THE ENTITY, AND THE OLD SIGNATURE WAS A BUG.**
 * `HandlerContext.params` is a getter over `Execute.params`, which DECODES a nested
 * `{type, data, content_hash}` map — so the throw this function's `catch` was written
 * for happens while evaluating the ARGUMENT, one frame outside the `try`. A malformed
 * params entity therefore escaped the handler as an exception instead of being read as
 * *"the caller did not ask"*. Found by `test/reactive.test.ts`'s handler-level §6.2
 * test, whose own first draft built the params field wrong — the instrument's defect
 * and the subject's defect were the same misunderstanding, one on each side.
 */
function readBudgetOverride(ctx: HandlerContext): number | null {
  try {
    const budget = Ecf.optUint(ctx.params.data, "budget");
    return budget === null ? null : Number(budget);
  } catch {
    // A params entity with no map body at all — `primitive/any` admits that, and
    // §3.2 treats params as optional. Not an error.
    return null;
  }
}

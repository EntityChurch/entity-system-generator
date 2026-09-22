"""Module-private internals. NOT part of the public surface.

`python` enforces nothing here and this port says so rather than borrowing the
`typescript` port's guarantee: there, `package.json`'s `exports` map makes
``import "@entity-core/extension-compute/internal/evaluator.js"`` fail at RESOLVE time, so
`test/export-surface.test.ts` asserts on the module resolver's refusal. Here a determined
consumer can ``import entity_compute._internal.evaluator`` and it works — the underscore,
``__all__`` and a test are the whole boundary.

**For THIS extension that gap is larger than it was for CONTENT or HISTORY, and the
difference is worth naming.** :func:`~entity_compute._internal.evaluator.evaluate` takes
its entire authority as an argument: a caller that constructs an
:class:`~entity_compute._internal.evaluator.EvalContext` with
``has_content_store_access=True`` has §4.2 Tier 0, which turns the evaluator into the
content-store oracle §4.2 exists to prevent. On `typescript` the resolver refuses that
reach; here nothing does. ``test/test_export_surface.py`` asserts BOTH that the convention
holds AND that it can be walked around, so the two ports' boundary claims are not read as
equal (``EXTENSION.toml [substrate].python_boundary_is_convention``).
"""

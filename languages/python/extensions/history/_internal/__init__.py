"""Module-private. Nothing here is re-exported from ``entity_history``.

`python` enforces nothing — a determined consumer can import
``entity_history._internal.recorder`` and it works. ``test/test_export_surface.py``
asserts BOTH that the convention holds AND that it can be walked around, so this port's
boundary claim is not read as equal to the `typescript` port's, where node's ``exports``
map refuses the deep import at resolve time.
"""

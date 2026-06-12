"""Read-only public collectors, one module per registry.

Each registry module exposes a single entry function that takes the exact
registry name and returns a plain dict with the keys ``reconcile`` consumes:
``published_version``, ``downloads`` (a :class:`cockpit.model.Downloads`-shaped
dict), ``evidence`` (a :class:`cockpit.model.Evidence`-shaped dict),
``http_status`` (the version probe's HTTP status), and ``error``.

Collectors never decide reconcile *state*; they only report facts. Mapping facts
to ``green``/``stale``/``missing``/``broken``/``unknown`` happens in
:mod:`cockpit.version` and :mod:`cockpit.reconcile`. The network primitive is
:func:`cockpit.http.get_json`, which never raises on an HTTP/transport error.
"""

from __future__ import annotations

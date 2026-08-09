"""The package version, in its own module so nothing has to import the package to read it.

``fabricate.packet`` stamps the version into every ``design.json``, and the top-level
``__init__`` re-exports it. If both went through ``jansky_forge/__init__.py`` the two would
form an import cycle, so the single source of truth lives here.

Kept in step with ``pyproject.toml`` and ``CITATION.cff``; the release workflow refuses to
publish when they disagree.
"""

from __future__ import annotations

__version__ = "0.9.0"

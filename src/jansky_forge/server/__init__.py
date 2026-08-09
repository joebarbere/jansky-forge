"""The optional web UI (M9).

``pip install 'jansky-forge[ui]'`` then ``jansky-forge serve``. The library and CLI work
unchanged without it — nothing outside this package imports a web framework.
"""

from __future__ import annotations

from jansky_forge.server.app import create_app

__all__ = ["create_app"]

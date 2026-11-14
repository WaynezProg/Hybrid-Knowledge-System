"""Where the contract schemas and default routing rules are read from.

In a checkout (also an editable install) they are the repository's own
``specs/*/contracts`` and ``config/routing_rules.yaml``. A built wheel carries a copy
under ``hks/_resources`` (see ``setup.py``), because those folders lie outside the
package.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PACKAGED = Path(__file__).resolve().parents[1] / "_resources"


@lru_cache(maxsize=1)
def resource_root() -> Path:
    repository = Path(__file__).resolve().parents[3]
    if (repository / "specs").is_dir() and (repository / "config" / "routing_rules.yaml").is_file():
        return repository
    return PACKAGED

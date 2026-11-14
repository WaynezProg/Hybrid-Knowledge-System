"""Copies the run-time data that lies outside the package into the wheel.

``hks`` reads contract schemas from ``specs/*/contracts`` and the default routing rules
from ``config/routing_rules.yaml``. A wheel only holds ``src/hks``, so a copy goes to
``hks/_resources`` at build time; ``hks.core.resources`` falls back to it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent


class BuildWithResources(build_py):
    def run(self) -> None:
        super().run()
        if self.editable_mode:
            return
        target = Path(self.build_lib) / "hks" / "_resources"
        sources = [ROOT / "config" / "routing_rules.yaml"]
        sources += [
            path for path in sorted((ROOT / "specs").glob("*/contracts/**/*")) if path.is_file()
        ]
        for source in sources:
            copy = target / source.relative_to(ROOT)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, copy)


setup(cmdclass={"build_py": BuildWithResources})

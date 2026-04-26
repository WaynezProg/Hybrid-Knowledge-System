from __future__ import annotations

import pytest

from hks.errors import KSError
from hks.workspace.validation import shell_export_command, validate_workspace_id


def test_workspace_id_validation_rejects_path_like_values() -> None:
    with pytest.raises(KSError):
        validate_workspace_id("../bad")


def test_shell_export_command_quotes_single_quotes() -> None:
    assert shell_export_command("/tmp/a'b") == "export KS_ROOT='/tmp/a'\"'\"'b'"


from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import SEED
from windesk import cli
from windesk.config import Settings


def test_build_command_writes_warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(env="test", seed_dir=SEED, warehouse_path=tmp_path / "wh.duckdb")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("windesk.config.get_settings", lambda: settings)
    assert cli.main(["build"]) == 0
    assert (tmp_path / "wh.duckdb").exists()


def test_unknown_command_exits_with_usage() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["nope"])
    assert exc.value.code == 2

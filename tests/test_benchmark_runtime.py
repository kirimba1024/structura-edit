import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, Qt

import benchmark_runtime
from benchmark_runtime import NativeSession, isolated_data
from structura_edit.overview_store import snapshot_directory


def test_benchmark_copies_only_caches_and_restores_environment(tmp_path, monkeypatch):
    source, world = tmp_path / "personal", tmp_path / "world"
    directory = snapshot_directory(source, world, "minecraft:overworld")
    directory.mkdir(parents=True)
    (directory / "current.json").write_text(json.dumps({"file": "snapshot.sqlite"}))
    snapshot = directory / "snapshot.sqlite"
    snapshot.write_bytes(b"immutable overview")
    geometry = source / "geometry" / "textures" / "section.npz"
    geometry.parent.mkdir(parents=True)
    geometry.write_bytes(b"cached geometry")
    (source / "drafts").mkdir()
    monkeypatch.setenv("STRUCTURA_EDIT_DATA", str(source))
    monkeypatch.setenv("AMULET_LEVEL_CACHE_DIR", "previous")
    monkeypatch.setattr(benchmark_runtime, "open_snapshot", lambda path: dict(path=str(path), metadata=dict(volatile=False)))
    with isolated_data(world, True) as (root, seeded):
        data = Path(os.environ["STRUCTURA_EDIT_DATA"])
        assert seeded == dict(overview=True, geometry_files=1)
        copied = snapshot_directory(data, world, "minecraft:overworld") / snapshot.name
        assert copied.read_bytes() == snapshot.read_bytes()
        assert not (data / "drafts").exists()
        copied.write_bytes(b"test changed only its copy")
        (data / "geometry/textures/section.npz").write_bytes(b"test geometry")
        assert os.environ["AMULET_LEVEL_CACHE_DIR"] == str(root / "amulet")
    assert not root.exists()
    assert snapshot.read_bytes() == b"immutable overview"
    assert geometry.read_bytes() == b"cached geometry"
    assert os.environ["STRUCTURA_EDIT_DATA"] == str(source)
    assert os.environ["AMULET_LEVEL_CACHE_DIR"] == "previous"
    assert not list(source.rglob("*.lock"))


def test_reuse_does_not_fall_back_to_building_missing_cache(tmp_path):
    with pytest.raises(FileNotFoundError):
        with isolated_data(tmp_path / "world", True, tmp_path / "missing"):
            pytest.fail("Missing overview must fail before opening the world")


def test_isolation_cleans_up_on_error(tmp_path, monkeypatch):
    monkeypatch.delenv("STRUCTURA_EDIT_DATA", raising=False)
    with pytest.raises(RuntimeError, match="cancelled"):
        with isolated_data(tmp_path, False) as (root, _):
            raise RuntimeError("cancelled")
    assert "STRUCTURA_EDIT_DATA" not in os.environ
    assert not root.exists()


def test_focus_interruption_invalidates_even_after_reactivation(monkeypatch):
    screen = object()
    window = SimpleNamespace(isActiveWindow=lambda: True, isMinimized=lambda: False, screen=lambda: screen,
                             plotter=SimpleNamespace(render_window=SimpleNamespace(GetSize=lambda: (2760, 1600))))
    session = SimpleNamespace(window=window, viewport=(2760, 1600), screen=screen, interruptions=[],
                              require_active=True, viewport_ready=True)
    app = SimpleNamespace(applicationState=lambda: Qt.ApplicationState.ApplicationActive)
    monkeypatch.setattr(benchmark_runtime, "QApplication", SimpleNamespace(instance=lambda: app))
    NativeSession.check(session)
    NativeSession.eventFilter(session, window, QEvent(QEvent.Type.WindowDeactivate))
    with pytest.raises(RuntimeError, match="active native window"):
        NativeSession.check(session)
    session.interruptions.clear()
    session.viewport = (1380, 800)
    with pytest.raises(RuntimeError, match="viewport"):
        NativeSession.check(session)

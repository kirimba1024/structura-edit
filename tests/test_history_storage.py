import sqlite3

from structura_edit import EditSession


def test_branching_removes_unreachable_rows_and_cache(edit):
    for _ in range(100):
        edit.apply(edit.set_block((0, 0, 0), "minecraft:gold_block"))
        edit.undo()
    history = edit.history
    with sqlite3.connect(history.path) as db:
        assert db.execute("SELECT count(*) FROM changes").fetchone()[0] == 1
    assert len(history._cache) == len(history.entries) == 1
    assert history._cached_bytes > 0
    assert edit.redo() and edit.state_at((0, 0, 0)) == "minecraft:gold_block"


def test_history_byte_budget_evicts_large_records(structure):
    from structura_edit.cell_data import CellData
    from structura_edit.changes import ChangeSet, _Cell, _Delta

    edit = EditSession.from_structure(structure, history_cache_bytes=4096)
    data = CellData(record='{large:"' + 'x' * 20_000 + '"}')
    change = ChangeSet(edit._id, edit.revision, "Large record", (
        _Delta((0, 0, 0), edit._cell((0, 0, 0)), _Cell("minecraft:gold_block", data=data)),))
    edit.apply(change)
    assert not edit.history._cache and edit.history._cached_bytes == 0
    assert edit.undo() and edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert edit.redo() and edit._cell((0, 0, 0)).data == data


def test_sqlite_failure_preserves_document_and_redo_branch(edit, monkeypatch):
    import sqlite3
    import structura_edit.history as storage
    import pytest

    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    edit.undo()
    before = edit.snapshot().present.copy(), edit.revision, tuple(edit.history.entries), edit.dirty
    def failed(*args, **kwargs):
        raise sqlite3.OperationalError('disk is full')
    monkeypatch.setattr(storage.sqlite3, 'connect', failed)
    with pytest.raises(sqlite3.OperationalError):
        edit.apply(edit.set_block((0, 0, 0), 'minecraft:diamond_block'))
    assert (edit.snapshot().present, edit.revision, tuple(edit.history.entries), edit.dirty) == before
    assert edit.can_redo

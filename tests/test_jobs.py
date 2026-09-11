import time
from pathlib import Path

import pytest

from structura_edit.jobs import Worker
from structura_edit.task_protocol import TaskSuccess
from structura_edit.tasks import execute


def wait(worker, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = worker.poll()
        if result is not None:
            return result
        time.sleep(0.01)
    raise AssertionError("Worker did not finish")


def wait_stopped(worker):
    end = time.monotonic() + 5
    while worker.stopping and time.monotonic() < end:
        time.sleep(0.001)
    assert not worker.stopping


def test_recipe_failure_is_atomic(edit):
    with pytest.raises(RuntimeError, match="intentional"):
        execute("recipe", {"session": edit, "selection": edit.select(), "code": 'edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))\nraise RuntimeError("intentional")'})
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert not edit.dirty


def test_recipe_output_retains_last_characters_across_writes(edit):
    text = "a" * 6000 + "b" * 6000 + "c" * 6000 + "d" * 6000
    change, output = execute("recipe", {"session": edit, "selection": edit.select(),
                                      "code": 'for letter in "abcd": print(letter * 6000, end="")'})
    assert output == text[-16_000:]
    assert not change and not edit.dirty


def test_recipe_stdout_reports_full_write_length(edit):
    _, output = execute("recipe", {"session": edit, "selection": edit.select(),
                                  "code": 'import sys\ncount = sys.stdout.write("x" * 20_000)\nprint(count)'})
    assert len(output) == 16_000 and output.endswith("20000\n")


@pytest.mark.parametrize('fixture', ['edit', 'world_edit'])
def test_recipe_history_is_bounded_without_losing_undo_redo(request, fixture, tmp_path):
    session = request.getfixturevalue(fixture)
    session.history.cache_bytes = 2048
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    code = '''for index in range(40):
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block' if index % 2 else 'minecraft:glass'))
assert edit.history._cached_bytes <= edit.history.cache_bytes
assert len(edit.history.entries) == 40
for _ in range(40): assert edit.undo()
assert not edit.undo() and edit.state_at((0, 0, 0)) == 'minecraft:stone'
for _ in range(40): assert edit.redo()
assert not edit.redo()
print(edit.history.path)
'''
    change, output = execute('recipe', dict(session=session, selection=session.select(), code=code), scratch_dir=str(scratch))
    assert len(change) == 1 and not session.dirty and not session.can_undo
    assert not list(scratch.iterdir()) and not Path(output.strip()).exists()
    session.apply(change)
    assert session.state_at((0, 0, 0)) == 'minecraft:gold_block'
    assert session.undo() and session.state_at((0, 0, 0)) == 'minecraft:stone'


@pytest.mark.parametrize('disk_failure', [False, True])
def test_recipe_failure_cleans_journal_and_preserves_source_redo(edit, tmp_path, monkeypatch, disk_failure):
    import sqlite3

    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    edit.undo()
    history = tuple(edit.history.entries), edit.history.cursor, edit.revision
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    if disk_failure:
        def fail(*args, **kwargs):
            raise sqlite3.OperationalError('disk full')
        monkeypatch.setattr(sqlite3, 'connect', fail)
    with pytest.raises(sqlite3.OperationalError if disk_failure else RuntimeError):
        execute('recipe', dict(session=edit, selection=edit.select(), code='''for _ in range(3):
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:glass'))
raise RuntimeError('intentional')'''), scratch_dir=str(scratch))
    assert not list(scratch.iterdir())
    assert (tuple(edit.history.entries), edit.history.cursor, edit.revision) == history
    assert edit.can_redo and not edit.dirty


@pytest.mark.parametrize("index", [0.5, True, -1, 100, "1", None])
def test_invalid_history_position_is_rejected_before_changing_document(edit, index):
    edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))
    with pytest.raises(ValueError, match="Invalid history position"):
        execute("history", {"session": edit, "index": index})
    assert edit.history.cursor == 1 and edit.state_at((0, 0, 0)) == "minecraft:glass"


def test_history_task_reports_progress_in_both_directions(edit):
    for state in ("minecraft:glass", "minecraft:gold_block", "minecraft:diamond_block"):
        edit.apply(edit.set_block((0, 0, 0), state))
    progress = []
    for index, expected in ((0, "minecraft:stone"), (3, "minecraft:diamond_block")):
        result = execute("history", {"session": edit, "index": index}, lambda *update: progress.append(update))
        assert result is edit and edit.state_at((0, 0, 0)) == expected
    assert progress == [("History", done, 3) for done in (1, 2, 3, 1, 2, 3)]


def test_worker_cancel_and_recover(edit, tmp_path):
    worker = Worker()
    try:
        marker = tmp_path / 'started'
        worker.submit("recipe", session=edit.fork(), selection=edit.select(), code=
                      f"from pathlib import Path\nedit.apply(edit.set_block((0, 0, 0), 'minecraft:glass'))\nPath({str(marker)!r}).touch()\nwhile True: pass")
        scratch = Path(worker._scratch.name)
        deadline = time.monotonic() + 20
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists() and list(scratch.rglob('history.sqlite'))
        with pytest.raises(RuntimeError):
            worker.submit("recipe")
        worker.close()
        wait_stopped(worker)
        assert not scratch.exists()
        assert not edit.dirty
        worker.submit("recipe", session=edit.fork(), selection=edit.select(), code='edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))\nprint("done")')
        reply = wait(worker)
        assert isinstance(reply, TaskSuccess), reply
        assert not list(Path(worker._scratch.name).iterdir())
        result = reply.payload
        change, output = result
        assert output == "done\n"
        edit.apply(change)
        assert edit.state_at((0, 0, 0)) == "minecraft:glass"
        assert edit.undo()
        assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    finally:
        worker.close()


def test_failed_worker_start_removes_its_scratch_directory(edit, monkeypatch):
    import multiprocessing.process
    import structura_edit.jobs as jobs

    created = []
    temporary = jobs.TemporaryDirectory
    def track(**kwargs):
        directory = temporary(**kwargs)
        created.append(Path(directory.name))
        return directory
    def fail(self):
        raise OSError('process creation failed')
    monkeypatch.setattr(jobs, 'TemporaryDirectory', track)
    monkeypatch.setattr(multiprocessing.process.BaseProcess, 'start', fail)
    worker = Worker()
    with pytest.raises(OSError, match='process creation failed'):
        worker.submit('recipe', session=edit, selection=edit.select(), code='pass')
    assert created and all(not path.exists() for path in created)
    assert not worker.busy and worker._process is None and worker._scratch is None
    worker.close()


def test_changed_code_requires_restart_before_loading_mixed_modules(tmp_path):
    from structura_edit.runtime_code import CodeVersion

    path = tmp_path / "example.py"
    path.write_text("value = 1\n")
    version = CodeVersion((tmp_path,))
    version.check()
    path.write_text("value = 20\n")
    with pytest.raises(RuntimeError, match="Restart Structura"):
        version.check()


def test_worker_search_returns_pages_and_observes_edits_after_cache_reuse(edit):
    worker = Worker()
    try:
        for query, count in (({"kind": "all", "limit": 1}, 3), ({"text": "chest"}, 1)):
            worker.submit("object_search", session=edit.fork(), query=query)
            reply = wait(worker)
            assert isinstance(reply, TaskSuccess), reply
            page = reply.payload
            assert page.total == count and len(page.rows) == 1
        edit.apply(edit.set_block((1, 0, 0), "minecraft:air"))
        worker.submit("object_search", session=edit.fork(), query={"text": "chest"})
        reply = wait(worker)
        assert isinstance(reply, TaskSuccess), reply
        page = reply.payload
        assert page.total == 0
    finally:
        worker.close()


def test_unknown_task_does_not_spawn_a_process():
    worker = Worker()
    with pytest.raises(ValueError, match='Unknown task'):
        worker.submit('unknown')
    assert worker._process is None and not worker.busy

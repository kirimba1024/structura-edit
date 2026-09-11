import time

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


def test_worker_cancel_and_recover(edit):
    worker = Worker()
    try:
        worker.submit("recipe", session=edit.fork(), selection=edit.select(), code="while True: pass")
        with pytest.raises(RuntimeError):
            worker.submit("recipe")
        worker.close()
        wait_stopped(worker)
        assert not edit.dirty
        worker.submit("recipe", session=edit.fork(), selection=edit.select(), code='edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))\nprint("done")')
        reply = wait(worker)
        assert isinstance(reply, TaskSuccess), reply
        result = reply.payload
        change, output = result
        assert output == "done\n"
        edit.apply(change)
        assert edit.state_at((0, 0, 0)) == "minecraft:glass"
        assert edit.undo()
        assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    finally:
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

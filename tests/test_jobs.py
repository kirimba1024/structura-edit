import time

import pytest

from structura_edit.jobs import Worker, execute


def wait(worker, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = worker.poll()
        if result is not None:
            return result
        time.sleep(0.01)
    raise AssertionError("Worker did not finish")


def test_recipe_failure_is_atomic(edit):
    with pytest.raises(RuntimeError, match="intentional"):
        execute("recipe", {"session": edit, "selection": edit.select(), "code": 'edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))\nraise RuntimeError("intentional")'})
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert not edit.dirty


def test_worker_cancel_and_recover(edit):
    worker = Worker()
    try:
        worker.submit("recipe", session=edit.fork(), selection=edit.select(), code="while True: pass")
        with pytest.raises(RuntimeError):
            worker.submit("recipe")
        worker.close()
        assert not edit.dirty
        worker.submit("recipe", session=edit.fork(), selection=edit.select(), code='edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))\nprint("done")')
        success, result = wait(worker)
        assert success, result
        change, output = result
        assert output == "done\n"
        edit.apply(change)
        assert edit.state_at((0, 0, 0)) == "minecraft:glass"
        assert edit.undo()
        assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    finally:
        worker.close()

from threading import Event

from amulet_nbt import CompoundTag, IntTag, StringTag, from_snbt

from structura_edit.nbt_search import PAGE_SIZE, find_nbt


def test_nested_mod_and_modern_inventory_formats_keep_paths():
    root = from_snbt('''{storage:{slots:[{Slot:2b,id:"mod:rare_gem",Count:3b,
        components:{"minecraft:container":[{slot:7,item:{id:"other:gem",count:200}}]}}]},
        decoy:{id:42,Count:1},unrelated:{id:"mod:object"}}''')
    page = find_nbt(root, items=True)
    assert page.total == 2 and not page.limited
    assert page.rows[0].columns[:3] == ("2", "mod:rare_gem", "3")
    assert page.rows[1].columns[:3] == ("—", "other:gem", "200")
    assert page.rows[1].count_path == ("storage", "slots", 0, "components", "minecraft:container", 0, "item", "count")
    assert find_nbt(root, "RARE gem", items=True).total == 1
    assert find_nbt(root, "components other", items=True).total == 1


def test_fields_match_names_paths_values_and_full_strings():
    root = from_snbt('{energy:9007199254740993L,custom:{label:"rare_gem"},array:[I;0,42,0]}')
    root["long_text"] = StringTag("x" * 1000 + "hidden match")
    for text, path in [("9007199254740993", ("energy",)), ("custom rare gem", ("custom", "label")),
                       ("42", ("array", 1)), ("hidden match", ("long_text",))]:
        page = find_nbt(root, text)
        assert page.total == 1 and page.rows[0].path == path
    assert len(find_nbt(root, "hidden match").rows[0].columns[2]) <= 200


def test_results_are_paged_without_hiding_later_matches():
    root = CompoundTag({f"value_{i}": IntTag(i) for i in range(PAGE_SIZE * 2 + 3)})
    first = find_nbt(root, "value")
    second = find_nbt(root, "value", offset=PAGE_SIZE)
    last = find_nbt(root, "value", offset=PAGE_SIZE * 2)
    assert first.total == PAGE_SIZE * 2 + 3
    assert len(first.rows) == len(second.rows) == PAGE_SIZE
    assert len(last.rows) == 3
    assert len({row.path for page in (first, second, last) for row in page.rows}) == first.total


def test_cancellation_and_limits_are_explicit(monkeypatch):
    import structura_edit.nbt_search as module
    root = CompoundTag({f"value_{i}": IntTag(i) for i in range(1000)})
    cancel = Event()
    cancel.set()
    assert find_nbt(root, cancel=cancel) is None
    monkeypatch.setattr(module, "MAX_FIELDS", 20)
    page = find_nbt(root, "missing")
    assert not page.rows and page.limited
    assert find_nbt(CompoundTag(), "missing").limited is False


def test_deep_tree_search_is_bounded_and_nonrecursive():
    root = IntTag(1)
    for _ in range(200):
        root = CompoundTag({"nested": root})
    assert find_nbt(root, "missing").limited

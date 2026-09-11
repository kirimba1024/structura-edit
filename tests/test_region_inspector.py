from structura_edit.region_inspector import region_details, RegionInspector


def test_region_inspection_includes_all_materials_containers_and_entities(edit):
    blocks, data, entities, total = region_details(edit, edit.select())
    assert total == 2
    assert {row[0] for row in blocks} == {'minecraft:stone', 'minecraft:chest[facing=north]'}
    assert data[0][0] == (1, 0, 0)
    assert entities[0][0] == 'entity:0'
    blocks, data, entities, total = region_details(edit, edit.select(((0, 0, 0), (1, 1, 1))))
    assert total == 1 and not data and not entities


def test_region_inspector_virtual_tables_and_async_completion(qt_app, edit):
    from PySide6.QtCore import QEventLoop, QTimer

    dialog = RegionInspector(None, edit, edit.select())
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if not dialog.timer.isActive() else None)
    poll.start(10)
    QTimer.singleShot(3000, loop.quit)
    try:
        loop.exec()
        assert not dialog.timer.isActive()
        assert [model.rowCount() for model in dialog.models] == [2, 1, 1]
        assert '2 blocks · 1 entity' in dialog.info.text()
        assert 'Blocks (2)' == dialog.tabs.tabText(0)
    finally:
        poll.stop()
        dialog.shutdown()
        dialog.close()

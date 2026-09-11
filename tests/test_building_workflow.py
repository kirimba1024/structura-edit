import pytest
from structura_core import save_structure
from structura_core.export_schematic import export_schematic

from building_fixture import building_source, content
from structura_edit import EditSession
from structura_edit.drafts import restore_draft, save_draft
from structura_edit.planar import extrude, planar_selection


@pytest.mark.parametrize('suffix', ['.nbt', '.schem'])
def test_wall_floors_take_save_undo_and_recovery_preserve_building(tmp_path, suffix):
    source = building_source()
    original = tmp_path / ('original' + suffix)
    if suffix == '.schem':
        export_schematic(source, original)
    else:
        save_structure(source, original, source.size)
    original_bytes = original.read_bytes()
    session = EditSession.open(original)
    face = planar_selection(session, (3, 2, 0), (0, 0, -1))
    assert face.volume == 157
    assert (2, 1, 0) not in face and (10, 2, 0) not in face
    session.apply(extrude(session, face, (0, 0, -1), 1))
    assert session.origin == (0, 0, -1)
    session.apply(session.stack(session.select(), 3, (0, 6, 0), include_air=True))
    before_move = content(session.snapshot()), session.origin
    session.apply(session.paste(session.copy(session.select()), (-40, -3, -32), take=True, include_air=True))
    moved = content(session.snapshot()), session.origin
    assert len(moved[0][2]) == len(moved[0][3]) == 4
    assert {value['Items'].to_snbt() for value in moved[0][2].values()} == {source.block_nbt[(2, 1, 0)]['Items'].to_snbt()}
    assert session.undo() and (content(session.snapshot()), session.origin) == before_move
    assert session.redo() and (content(session.snapshot()), session.origin) == moved
    working = session.save(tmp_path / ('working' + suffix))
    assert not session.dirty and content(EditSession.open(working).snapshot()) == moved[0]
    if suffix == '.schem':
        assert EditSession.open(working).origin == moved[1]
    assert session.undo() and session.dirty
    saved_bytes = working.read_bytes()
    draft = save_draft(session, root=tmp_path / 'drafts')
    recovered = restore_draft(draft)
    assert recovered.dirty and not recovered.can_undo
    assert (content(recovered.snapshot()), recovered.origin) == before_move
    assert working.read_bytes() == saved_bytes and original.read_bytes() == original_bytes
    recovered.save()
    assert not recovered.dirty and content(EditSession.open(working).snapshot()) == before_move[0]
    if suffix == '.schem':
        assert EditSession.open(working).origin == before_move[1]
    assert original.read_bytes() == original_bytes

import pytest

from structura_edit.height_slice import HeightSlice
from structura_edit.render_source import RenderSource


@pytest.mark.parametrize('height', [HeightSlice(), HeightSlice('below', 0), HeightSlice('layer', 1)])
def test_dense_sections_match_sparse_source_with_edits_nbt_and_halo(edit, height):
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:air'))
    edit.apply(edit.set_block((3, 1, 2), 'minecraft:oak_log[axis=x]'))
    sparse, dense = RenderSource(edit, height), RenderSource(edit, height)
    dense.prepare_grid()
    for lower, upper in [((0, 0, 0), edit.size), ((1, 0, 0), (4, 2, 2)), ((0, 1, 0), (4, 2, 3))]:
        left, right = sparse.region(lower, upper), dense.region(lower, upper)
        assert {p: left.palette_raw[i] for p, i in left.present.items()} == {p: right.palette_raw[i] for p, i in right.present.items()}
        assert left.block_nbt == right.block_nbt
        assert left.size == right.size

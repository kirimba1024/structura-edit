import pytest
from amulet_nbt import from_snbt

from structura_core.entity_positions import shift_entity
from structura_edit.entity_transform import new_identity, payloads, transform_record


def test_nested_passengers_move_rotate_rebase_and_get_distinct_ids():
    record = from_snbt('''{pos:[2d,3d,4d],blockPos:[2,3,4],nbt:{id:"minecraft:pig",Pos:[2d,3d,4d],
        Passengers:[{id:"mod:rider",Pos:[3d,4d,4d],custom:{keep:5L},
        Passengers:[{id:"mod:pet",Pos:[3d,5d,4d]}]}]}}''')
    original = record.to_snbt()
    shifted = shift_entity(record, (-16, -32, -48))
    assert shift_entity(shifted, (16, 32, 48)) == record
    assert tuple(float(v) for v in shifted["nbt"]["Passengers"][0]["Passengers"][0]["Pos"]) == (-13, -27, -44)
    transform_record(record, angle=90, center=(2, 3, 4))
    rider = record["nbt"]["Passengers"][0]
    assert tuple(float(v) for v in rider["Pos"]) == (2, 4, 5)
    assert tuple(float(v) for v in rider["Passengers"][0]["Pos"]) == (2, 5, 5)
    transform_record(record, offset=(1.25, 2, -3))
    assert tuple(float(v) for v in rider["Pos"]) == (3.25, 6, 2)
    assert rider["custom"] == from_snbt(original)["nbt"]["Passengers"][0]["custom"]
    new_identity(record["nbt"])
    assert len({payload["UUID"].to_snbt() for payload in payloads(record["nbt"])}) == 3


def test_hanging_entity_rotates_anchor_and_facing_with_unknown_data_intact():
    record = from_snbt('''{pos:[1.5d,2.5d,3.5d],blockPos:[1,2,3],nbt:{id:"minecraft:item_frame",
        Pos:[1.5d,2.5d,3.5d],TileX:1,TileY:2,TileZ:3,Facing:2b,custom:{keep:4L}}}''')
    before = record.to_snbt()
    for _ in range(4):
        transform_record(record, angle=90, center=(0, 0, 0))
    expected = from_snbt(before)
    assert record["pos"] == expected["pos"] and record["blockPos"] == expected["blockPos"]
    assert record["nbt"]["Facing"] == expected["nbt"]["Facing"]
    assert record["nbt"]["custom"] == expected["nbt"]["custom"]
    with pytest.raises(ValueError, match="90 degrees"):
        transform_record(record, angle=45)


def test_mirror_preserves_separate_painting_anchor_and_rotates_motion_without_translation():
    record = from_snbt('''{pos:[2d,3d,1.03125d],blockPos:[1,2,1],nbt:{id:"minecraft:painting",
        Facing:2b,Rotation:[180f,0f],Motion:[1d,2d,3d],custom:{keep:5L}}}''')
    transform_record(record, flip="x", angle=90, center=(2, 0, 2), offset=(10, 5, 7))
    assert record["blockPos"] == from_snbt("[12,7,9]")
    assert record["pos"] == from_snbt("[12.96875d,8d,9d]")
    assert record["nbt"]["Motion"] == from_snbt("[-3d,2d,-1d]")
    assert record["nbt"]["custom"] == from_snbt("{keep:5L}")

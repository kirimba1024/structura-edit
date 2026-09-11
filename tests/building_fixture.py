from itertools import product

from amulet_nbt import from_snbt
from structura_core import Structure, state_key

from structura_edit.picking import EMPTY


def building_source():
    source = Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[32,6,24],author:"Building workflow",
        palette:[{Name:"minecraft:stone"},{Name:"minecraft:chest"},{Name:"minecraft:glass"}],
        blocks:[{pos:[2,1,0],state:1,nbt:{id:"minecraft:chest",Items:[{Slot:0b,id:"minecraft:diamond",count:3}]}}],
        entities:[{pos:[4.5d,1d,4.5d],blockPos:[4,1,4],
                   nbt:{id:"minecraft:armor_stand",CustomName:"Builder",UUID:[I;1,2,3,4]}}]
    }'''))
    source.present.update({(x, y, z): 0 for x, y, z in product(range(32), range(5), range(24))
                           if y == 0 or x in (0, 31) or z in (0, 23)})
    source.present[(2, 1, 0)] = 1
    source.present[(10, 2, 0)] = source.present[(11, 2, 0)] = 2
    source.validate()
    return source


def content(source):
    states = tuple(state_key(raw) for raw in source.palette_raw)
    blocks = {point: states[index] for point, index in source.present.items()
              if states[index].split('[', 1)[0] not in EMPTY}
    entities = sorted(source.entities, key=lambda record: tuple(float(v) for v in record['pos']))
    return source.size, blocks, source.block_nbt, entities

from amulet_nbt import CompoundTag, IntTag, ListTag, from_snbt
from structura_core import Structure


def batch_structure(count=150):
    root = from_snbt('''{DataVersion:3955,size:[150,2,2],
        palette:[{Name:"minecraft:chest"}],blocks:[],
        entities:[{pos:[1d,1d,1d],blockPos:[1,1,1],nbt:{id:"minecraft:pig",CustomName:"Old",UUID:[I;1,2,3,4]}},
                  {pos:[2d,1d,1d],blockPos:[2,1,1],nbt:{id:"minecraft:pig",CustomName:"Old",UUID:[I;5,6,7,8]}}]}''')
    root['size'][0] = IntTag(max(3, count))
    root['blocks'] = ListTag([CompoundTag({'pos': ListTag([IntTag(x), IntTag(0), IntTag(0)]), 'state': IntTag(0),
                                          'extra': from_snbt('{keep:42L}'),
                                          'nbt': from_snbt('{id:"minecraft:chest",Items:[{Slot:0b,id:"minecraft:diamond",count:3b}],custom:42L}')})
                             for x in range(count)])
    return Structure.from_root(root)

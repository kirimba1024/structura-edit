from structura_edit.section_cache import SectionCache


def test_cache_is_lru_bounded_by_bytes_and_invalidated_by_resources():
    cache = SectionCache(limit=10)
    bank = object()
    a = cache.key('a', None, bank)
    b = cache.key('b', None, bank)
    c = cache.key('c', None, bank)
    cache.put(a, {'geometry_bytes': 4})
    cache.put(b, {'geometry_bytes': 4})
    assert cache.get(a)
    cache.put(c, {'geometry_bytes': 4})
    assert cache.get(b) is None and cache.get(a) and cache.get(c)
    assert cache.bytes == 8
    assert cache.key('a', None, object()) != a
    assert not cache.entries and cache.bytes == 0


def test_cache_bounds_empty_sections_and_detects_halo_changes():
    cache = SectionCache()
    bank = object()
    for index in range(3000):
        cache.put(cache.key(index, None, bank), {'geometry_bytes': 0})
    assert len(cache.entries) == 2048
    source = {'present': {(16, 0, 0): 1}}
    before = cache.key(source, None, bank)
    source['present'][(16, 0, 0)] = 2
    assert before != cache.key(source, None, bank)


def test_cache_reuses_sections_across_palette_reordering_and_unrelated_states():
    from types import SimpleNamespace
    import numpy as np
    from structura_core import parse_state
    from structura_core.block_array import BlockArray

    def source(palette, values):
        return SimpleNamespace(size=(2, 1, 1), palette_raw=[parse_state(name) for name in palette],
                               palette=palette, present=BlockArray(np.array(values, np.int32).reshape(2, 1, 1)),
                               block_nbt={}, entities=[])
    cache, bank = SectionCache(), object()
    first = source(['minecraft:stone', 'minecraft:dirt'], [0, 1])
    reordered = source(['minecraft:gold_block', 'minecraft:dirt', 'minecraft:stone'], [2, 1])
    assert cache.key(first, None, bank) == cache.key(reordered, None, bank)
    reordered.present[(1, 0, 0)] = 0
    assert cache.key(first, None, bank) != cache.key(reordered, None, bank)

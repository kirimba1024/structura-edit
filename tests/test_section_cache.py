from structura_edit.section_cache import SectionCache


def test_cache_is_lru_bounded_by_bytes_and_invalidated_by_resources():
    cache = SectionCache(limit=10)
    bank = object()
    a = cache.key('a', (0, 0, 0), None, bank)
    b = cache.key('b', (0, 0, 0), None, bank)
    c = cache.key('c', (0, 0, 0), None, bank)
    cache.put(a, {'geometry_bytes': 4})
    cache.put(b, {'geometry_bytes': 4})
    assert cache.get(a)
    cache.put(c, {'geometry_bytes': 4})
    assert cache.get(b) is None and cache.get(a) and cache.get(c)
    assert cache.bytes == 8
    assert cache.key('a', (0, 0, 0), None, object()) != a
    assert not cache.entries and cache.bytes == 0


def test_cache_bounds_empty_sections_and_detects_halo_changes():
    cache = SectionCache()
    bank = object()
    for index in range(3000):
        cache.put(cache.key(index, (0, 0, 0), None, bank), {'geometry_bytes': 0})
    assert len(cache.entries) == 2048
    source = {'present': {(16, 0, 0): 1}}
    before = cache.key(source, (0, 0, 0), None, bank)
    source['present'][(16, 0, 0)] = 2
    assert before != cache.key(source, (0, 0, 0), None, bank)

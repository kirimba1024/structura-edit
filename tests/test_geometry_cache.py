from types import SimpleNamespace

import numpy as np

from structura_edit.geometry_cache import GeometryCache
from structura_edit.section_cache import SectionCache


def test_disk_cache_reuses_geometry_after_restart_and_rejects_damage(tmp_path, monkeypatch):
    monkeypatch.setattr('structura_edit.geometry_cache.storage_root', lambda: tmp_path / 'cache')
    assets = tmp_path / 'assets'
    assets.mkdir()
    bank = SimpleNamespace(context=SimpleNamespace(root=assets))
    key = SectionCache().key('stone', None, bank)
    data = dict(meshes=[], flat=[(np.zeros((4, 3), np.float32), np.array([4, 0, 1, 2, 3]), (12, 34, 56, 255))],
                geometry_bytes=88, warnings=[], textured=False)
    cache = GeometryCache(bank)
    cache.put(key, data)
    next_key = SectionCache().key('stone', None, bank)
    assert key != next_key
    result = GeometryCache(bank).get(next_key)
    assert result['signature'] == next_key and result['geometry_bytes'] == 88
    assert np.array_equal(result['flat'][0][0], data['flat'][0][0])
    cache.path(key).write_bytes(b'broken archive')
    assert cache.get(key) is None


def test_section_geometry_survives_origin_changes_without_remeshing(tmp_path, monkeypatch):
    from structura_edit import preview

    builds = []
    assets = tmp_path / 'assets'
    assets.mkdir()
    bank = SimpleNamespace(context=SimpleNamespace(root=assets), available=lambda: False)
    monkeypatch.setattr(preview, 'texture_bank', lambda assets: bank)
    monkeypatch.setattr(preview, '_sections', SectionCache())
    monkeypatch.setattr('structura_edit.geometry_cache.storage_root', lambda: tmp_path / 'cache')
    def build(*args):
        builds.append(args)
        return dict(meshes=[], flat=[(np.zeros((4, 3), np.float32), np.array([4, 0, 1, 2, 3]), (12, 34, 56, 255))],
                    geometry_bytes=88, warnings=[], textured=False)
    monkeypatch.setattr(preview, 'build_geometry', build)
    first = preview.build_sections({'a': ('stone', (0, 0, 0), None)}, reset=True)['sections']['a']
    next_view = preview.build_sections({'b': ('stone', (-64, 0, 128), None)}, reset=True)['sections']['b']
    assert len(builds) == 1 and first['signature'] != next_view['signature']
    assert first['packets'] is next_view['packets']
    assert next_view['position'] == (-64, 0, 128)

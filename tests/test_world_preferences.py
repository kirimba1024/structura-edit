import json

import pytest

from structura_edit.loading import DEFAULT_RADIUS, DEFAULT_VERTICAL_RADIUS
from structura_edit.world_preferences import load_distance, save_distance


@pytest.mark.parametrize('value', [None, [], {'radius': True, 'vertical_radius': 32}, {'radius': 999, 'vertical_radius':32}, {'radius': 2, 'vertical_radius': 0}])
def test_bad_preferences_fall_back_to_editor_defaults(tmp_path, monkeypatch, value):
    monkeypatch.setenv('STRUCTURA_EDIT_DATA', str(tmp_path))
    (tmp_path/'world-view.json').write_text(json.dumps(value))
    assert load_distance() == (DEFAULT_RADIUS, DEFAULT_VERTICAL_RADIUS)
    assert DEFAULT_RADIUS == 6


def test_distance_survives_restart_without_changing_cli_override(tmp_path, monkeypatch):
    monkeypatch.setenv('STRUCTURA_EDIT_DATA', str(tmp_path))
    save_distance(8, 48)
    assert load_distance() == (8, 48)
    (tmp_path/'world-view.json').write_text('{bad')
    assert load_distance() == (6, None)

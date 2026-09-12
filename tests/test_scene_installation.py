from types import SimpleNamespace

import pytest

from structura_edit.scene import Scene


class Actor:
    def __init__(self):
        self.visible = True
        self.position = (0, 0, 0)

    def GetPosition(self):
        return self.position

    def SetPosition(self, *position):
        self.position = position

    def SetVisibility(self, visible):
        self.visible = visible


@pytest.fixture
def scene():
    actors = []
    plotter = SimpleNamespace(renderer=SimpleNamespace(RemoveActor=actors.remove))
    scene = Scene(plotter)
    def add(section):
        if section.get('fail'):
            raise ValueError('Invalid mesh')
        actor = Actor()
        actors.append(actor)
        scene.ghost_actors[actor] = 'added', 1, True
        return [actor]
    scene._add_section_steps = add
    data = {'reset': True, 'sections': {'old': {'geometry_bytes': 1}}}
    scene.replace(data, 1)
    return scene, actors


def replacement():
    return {'reset': True, 'sections': {'first': {'geometry_bytes': 2}, 'second': {'geometry_bytes': 3}}}


def test_scene_stays_visible_until_replacement_is_complete(scene):
    scene, actors = scene
    old = scene.actors[0]
    steps = scene.replace_steps(replacement(), 2)
    assert next(steps)
    assert old.visible and scene.actors == [old] and scene.display_revision == 1
    assert len(actors) == 2 and not actors[-1].visible
    assert next(steps)
    assert scene.actors == [old] and len(actors) == 3
    assert not next(steps, False)
    assert old not in actors and all(actor.visible for actor in actors)
    assert scene.display_revision == 2 and sum(scene.section_bytes.values()) == 5
    assert set(scene.ghost_actors) == set(actors)


@pytest.mark.parametrize('fail', [False, True])
def test_cancelled_or_failed_installation_keeps_old_scene(scene, fail):
    scene, actors = scene
    old = scene.actors[0]
    data = replacement()
    data['sections']['second']['fail'] = fail
    steps = scene.replace_steps(data, 2)
    next(steps)
    if fail:
        with pytest.raises(ValueError, match='Invalid mesh'):
            next(steps)
    else:
        steps.close()
    assert actors == scene.actors == [old] and old.visible
    assert scene.display_revision == 1 and scene.section_bytes == {'old': 1}
    assert set(scene.ghost_actors) == {old}


def test_origin_shift_keeps_matching_actors_and_entity_picking_bounds(scene):
    scene, actors = scene
    old = actors[0]
    scene.signatures['old'] = ('content', (0, 0, 0))
    scene.entity_bounds = {'bat': ((1, 2, 3), (2, 3, 4))}
    scene.shift((-48, 0, 16))
    assert old.position == (-48, 0, 16)
    assert scene.entity_bounds['bat'] == ((-47, 2, 19), (-46, 3, 20))
    assert scene.entity_boxes.tolist() == [[[-47, 2, 19], [-46, 3, 20]]]
    scene.replace({'reset': True, 'sections': {'old': {
        'geometry_bytes': 1, 'signature': ('content', (-48, 0, 16))}}}, 2)
    assert actors == [old] and scene.actors == [old] and old.visible
    assert scene.display_revision == 2

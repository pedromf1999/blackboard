from beeref.config import KeyboardSettings


def wheel(action_id):
    for action in KeyboardSettings.MOUSEWHEEL_ACTIONS.values():
        if action.id == action_id:
            return action
    raise AssertionError(action_id)


def test_the_wheel_zooms_the_other_way_round_by_default(view):
    """Wheel away to zoom in, the way the rest of this desk works."""

    assert wheel('zoom1').get_inverted() is True
    assert wheel('zoom2').get_inverted() is True


def test_that_is_the_default_rather_than_a_stored_choice(view):
    """So it counts as unchanged and restoring defaults keeps it."""

    assert wheel('zoom1').inverted is True
    assert wheel('zoom1').controls_changed() is False


def test_panning_is_left_the_way_it_was(view):
    for action_id in ('pan_horizontal1', 'pan_vertical1'):
        assert wheel(action_id).get_inverted() is False


def test_it_can_still_be_turned_back(view):
    zoom = wheel('zoom1')
    try:
        zoom.set_inverted(False)
        assert zoom.get_inverted() is False
        assert zoom.controls_changed() is True
    finally:
        zoom.set_inverted(True)

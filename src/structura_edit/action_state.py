from dataclasses import dataclass


@dataclass(frozen=True)
class ActionState:
    action: str
    label: str
    enabled: bool
    reason: str = ""


def history_action(session, direction, *, busy=False, preview=False, placing=False, stroke=False):
    if stroke:
        return ActionState("cancel-stroke", "Cancel stroke" if direction == "undo" else "Redo", direction == "undo" and not busy)
    if direction == "undo" and (placing or preview):
        action = "cancel-placement" if placing else "cancel-preview"
        return ActionState(action, "Cancel placement" if placing else "Cancel preview", not busy)
    label = direction.title()
    if session is not None:
        previous = getattr(session.history, direction + "_label")
        label += " " + previous if previous else ""
    enabled = bool(session is not None and not session.readonly and not busy and not preview and not placing
                   and getattr(session, "can_" + direction))
    return ActionState(direction, label, enabled)

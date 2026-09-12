from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .changes import ChangeSet
    from .session import EditSession


@dataclass(frozen=True)
class ActionState:
    action: str
    label: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True)
class EditorCapabilities:
    ready: bool
    editable: bool
    can_select: bool
    can_keep_selecting: bool
    can_operate: bool
    can_choose_material: bool
    can_apply: bool
    can_discard: bool
    can_save: bool
    can_save_as: bool
    can_inspect: bool
    can_export: bool
    can_copy: bool
    can_place: bool
    can_seek_history: bool
    can_save_draft: bool


def editor_capabilities(session: Optional[EditSession], *, busy: bool = False, protected: bool = False,
                        selected: bool = False, preview: Optional[ChangeSet] = None, scene_ready: bool = False,
                        placing: bool = False, repeating: bool = False, stroke: bool = False, world: bool = False,
                        placement_ready: bool = False, selection_busy: Optional[bool] = None) -> EditorCapabilities:
    ready = session is not None and not busy
    editable = session is not None and not session.readonly and not busy
    dirty = session is not None and session.dirty
    current_preview = (session is not None and preview is not None and bool(preview)
                       and (preview.document_id, preview.base_revision) == (session._id, session.revision))
    transient = placing or repeating or stroke
    selectable = session is not None and not transient
    selection_busy = busy if selection_busy is None else selection_busy
    settled = ready and preview is None and not transient
    writable = settled and editable
    return EditorCapabilities(
        ready=ready, editable=editable, can_select=selectable and not selection_busy, can_keep_selecting=selectable,
        can_operate=editable and selected and not transient, can_choose_material=selectable and not busy,
        can_apply=editable and scene_ready and not stroke and (placement_ready if placing else current_preview),
        can_discard=not protected and (preview is not None or transient),
        can_save=writable and (not world or dirty), can_save_as=writable and not world,
        can_inspect=settled, can_export=settled and selected, can_copy=settled and selected and scene_ready,
        can_place=writable and scene_ready, can_seek_history=writable, can_save_draft=writable)


def history_action(session: Optional[EditSession], direction: Literal['undo', 'redo'], *, busy: bool = False,
                   preview: bool = False, placing: bool = False, stroke: bool = False) -> ActionState:
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

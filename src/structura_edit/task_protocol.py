from __future__ import annotations

from dataclasses import dataclass
from copy import copy, deepcopy
from enum import Enum, auto
from typing import Any, Callable, ClassVar, Dict, Literal, Optional, Tuple, Union, TYPE_CHECKING

from .height_slice import HeightSlice
from .destination_rule import DestinationRule

if TYPE_CHECKING:
    from .cell_set import CellSet
    from .changes import ChangeSet, Selection
    from .condition import Condition
    from .mix import Mix
    from .nbt_batch import NbtTargets
    from .placement import Placement
    from .session import EditSession


TaskKind = Literal[
    'overview_build', 'overview_open', 'overview_read', 'overview_surface', 'open', 'world',
    'save', 'apply', 'history', 'render', 'render_preview', 'export_review', 'export', 'map',
    'objects', 'object_search', 'nbt_targets', 'nbt_batch', 'operation', 'paint', 'planar',
    'connected', 'fragment_save', 'fragment_list', 'fragment_load', 'draft_save', 'draft_list',
    'draft_restore', 'catalog', 'item_icons', 'changes', 'backups', 'restore_backup', 'conflicts',
    'clipboard', 'placement', 'placement_plan', 'placement_area', 'repeat', 'recipe',
]
ProgressCallback = Callable[[str, int, int], None]
Region = Union['Selection', 'CellSet']
Position = Tuple[int, int, int]


class TaskState(Enum):
    IDLE = auto()
    STARTING = auto()
    RUNNING = auto()
    CANCELLING = auto()
    FAILED = auto()


class SubmitResult(Enum):
    STARTED = auto()
    BUSY = auto()
    FAILED_TO_START = auto()

    def __bool__(self) -> bool:
        return self is SubmitResult.STARTED


@dataclass(frozen=True)
class OperationCommand:
    kind: ClassVar[TaskKind] = 'operation'
    mode: str
    selection: Region
    values: Dict[str, Any]
    height: Optional[HeightSlice] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'values', deepcopy(self.values))


@dataclass(frozen=True)
class RecipeCommand:
    kind: ClassVar[TaskKind] = 'recipe'
    code: str
    selection: Region
    height: Optional[HeightSlice] = None


@dataclass(frozen=True)
class RepeatCommand:
    kind: ClassVar[TaskKind] = 'repeat'
    selection: Region
    copies: int
    step: Position
    include_air: bool = False
    include_blocks: bool = True
    include_entities: bool = True
    destination: DestinationRule = DestinationRule()
    height: Optional[HeightSlice] = None


@dataclass(frozen=True)
class PlacementPlanCommand:
    kind: ClassVar[TaskKind] = 'placement_plan'
    placement: Placement
    height: Optional[HeightSlice] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'placement', copy(self.placement))


@dataclass(frozen=True)
class PaintCommand:
    kind: ClassVar[TaskKind] = 'paint'
    selection: Region
    points: Tuple[Optional[Tuple[float, float, float]], ...]
    target: Union[str, Mix]
    radius: float = 1
    condition: Optional[Union[Condition, str]] = None
    height: Optional[HeightSlice] = None


@dataclass(frozen=True)
class NbtBatchCommand:
    kind: ClassVar[TaskKind] = 'nbt_batch'
    targets: NbtTargets
    path: Union[str, Tuple[Union[str, int], ...]]
    text: str
    height: Optional[HeightSlice] = None


@dataclass(frozen=True)
class ApplyCommand:
    kind: ClassVar[TaskKind] = 'apply'
    change: ChangeSet


@dataclass(frozen=True)
class HistoryCommand:
    kind: ClassVar[TaskKind] = 'history'
    index: int


@dataclass(frozen=True)
class SaveCommand:
    kind: ClassVar[TaskKind] = 'save'
    path: str
    force: bool = False


@dataclass(frozen=True)
class ObjectSearchCommand:
    kind: ClassVar[TaskKind] = 'object_search'
    text: str = ''
    category: Literal['all', 'entities', 'blocks', 'data'] = 'all'
    selection: Optional[Region] = None
    offset: int = 0


DocumentCommand = Union[OperationCommand, RecipeCommand, RepeatCommand, PlacementPlanCommand,
                        PaintCommand, NbtBatchCommand, ApplyCommand, HistoryCommand, SaveCommand, ObjectSearchCommand]
DOCUMENT_COMMANDS = {command.kind: command for command in (
    OperationCommand, RecipeCommand, RepeatCommand, PlacementPlanCommand, PaintCommand,
    NbtBatchCommand, ApplyCommand, HistoryCommand, SaveCommand, ObjectSearchCommand,
)}


@dataclass(frozen=True)
class DocumentToken:
    snapshot_id: str
    document_id: str
    revision: int
    state_id: str


@dataclass(frozen=True)
class DocumentRequest:
    token: DocumentToken
    command: DocumentCommand
    snapshot: Optional[EditSession] = None

    @property
    def kind(self) -> TaskKind:
        return self.command.kind


@dataclass(frozen=True)
class TaskCall:
    kind: TaskKind
    args: Dict[str, Any]


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    command: Union[TaskCall, DocumentRequest]


@dataclass(frozen=True)
class TaskProgress:
    task_id: str
    label: str
    done: int
    total: int


@dataclass(frozen=True)
class TaskSuccess:
    task_id: str
    payload: Any
    document: Optional[DocumentToken] = None


@dataclass(frozen=True)
class TaskFailure:
    task_id: str
    message: str


TaskResult = Union[TaskSuccess, TaskFailure]

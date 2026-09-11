# Python API

[Install](../README.md#install-and-launch) · [Workbench](workbench.md) ·
[Internal ownership](structura-edit-architecture.md)

## Sources and coordinates

```python
from structura_edit import EditSession, open_source

edit = EditSession.open("house.nbt")
selection = edit.select(((0, 0, 0), (16, 8, 16)))
change = edit.replace(selection, "minecraft:oak_planks", "minecraft:spruce_planks")
preview = edit.snapshot(change)
edit.apply(change)
edit.undo()
edit.redo()
edit.save("house-edited.nbt")

world = open_source("/path/to/saves/MyWorld", center=(0, 80, 0), radius=1)
region = open_source("build.litematic", region="Main")
```

`open_source` accepts schematics, world folders and `level.dat`; decoding and supported
formats belong to core. `source_data_version` is required for Sponge v1 lacking version
metadata. `palette_index` selects a Java palette; `region` a Litematic region.
Native Sponge metadata is retained for saves; Bedrock translation reports conversion losses.

Positions are local integer triples; add `edit.origin` for world coordinates. Bounds are
half-open: the example includes X/Z 0–15 and Y 0–7. `CellSet.from_positions(...)` represents
nonrectangular selections. Missing schematic cells remain missing unless filled; Erase
writes explicit air. Unknown world chunks do not become air.

## Changes and history

Fill/Replace/Erase/Move/shapes produce ChangeSet values for `apply`, `snapshot(change)`
or `transaction(label)`. A change belongs to one document revision; later edits raise
StaleChangeError for old changes. `transaction` edits a disposable branch and commits
one diff if successful; an exception leaves the original unchanged.

The default operation budget is 500,000 cells/objects as checked by each operation.
`stored_positions(selection)` iterates stored base/overlay entries using the smaller
of region volume and stored position count, including explicit air. `palette_counts`
uses the same selection semantics. Dense operations still enforce volume limits.

History stores committed steps in temporary SQLite; its cache is bounded by both cells
and estimated bytes. Cache eviction never removes Undo. Append records history before
changing data; a write error preserves state and the redo branch. A new edit after Undo
prunes unreachable redo entries; Save retains history. Worker acknowledgement additionally
protects old rows until the response is accepted (internal protocol, not a second history).
Draft recovery is separate and restores final edits without earlier Undo steps.

Public root exports are listed in `structura_edit.__all__`. Internal modules and private
cell/delta fields are implementation details; do not infer a stable external contract
from a convenient import. `py.typed` is present, but strict checking currently covers
only the worker boundary, not all public annotations.

## Clipboard and transforms

```python
from structura_edit import DestinationRule

clipboard = edit.copy(selection, include_blocks=True, include_entities=True)
change = edit.paste(clipboard, (16, 0, 0), include_air=False,
                    destination=DestinationRule("air"))
edit.apply(change)
```

`paste(..., take=True)` retains source identity, checks its revision/origin/dimension,
and removes source content only on Apply. Regular copies assign new UUIDs to entities
and passengers; players are excluded. Blocks include their NBT and extra record fields.
Cross-document copies do not inherit source dimension/chunk provenance. Versions must
be equal and known; clipboard transfer does not translate Minecraft versions or biomes.

`stack(selection, copies, step, ...)` places extra copies at `selection.lower + n*step`,
for n=1..copies. Step is a nonzero integer triple. All copies read one clipboard; later
destinations win overlap. One ChangeSet includes the whole series and any schematic growth.
Without Air the work budget counts real blocks/entities; with Air it counts each footprint.

DestinationRule defaults to all; `DestinationRule("air")` keeps existing blocks,
`DestinationRule("material", "minecraft:stone")` accepts only stone. Conditions read the
unchanged destination. Rules affect blocks, not entities. Filtered Take protects skipped
source cells and dependent overlapping moves. Missing world chunks/sections reject placement.

`clipboard.transformed(turns=..., axis="y", flip=...)` composes transforms from its
original data, preserving complete cycles and the anchor. Core handles supported spatial
block/entity properties; unsupported orientations fail. Arbitrary mod fields are retained,
not guessed. Move blocks is block-only; entity operations are explicit.

## Conditions, materials and planar tools

`Condition` describes material/property, non-air, height, NBT and combined predicates;
GUI From/Only controls use it directly. `Mix(items, seed=0, anchor="local")` uses positive
integer weights and deterministic sampling. World anchoring includes origin. A two-item
`gradient=(low_y, high_y)` changes the probability by height, not exact quotas.

`planar_selection`, `extrude`, `frame` and `paint_stroke` are root exports. Planar tools
use exposed default-state full cubes without block NBT; occupied extrusion targets fail.
Paint consumes sampled points within an existing selection and prepares a normal change.
Use the command's explicit bounds and limits; visual slicing does not restrict edits.

## Object search and NBT

```python
from structura_edit import collect_nbt_targets, replace_nbt_values

page = edit.find_objects("chest", kind="data", selection=selection, offset=0, limit=64)
targets = collect_nbt_targets(edit, "chest", kind="data", selection=selection)
plan = replace_nbt_values(edit, targets, "/Items/0/count", "7")
print(plan.summary)
edit.apply(plan.change)
```

A page has rows/total/offset. Rows carry local position, identity, kind and an entity key
where applicable. The query matches ID words, excludes empty space and does not mutate
history. `ObjectSearch` in `structura_edit.object_search` reuses an index/query across
pages; the convenience session method creates a fresh search. One index preserves order,
entities first; canonical order across independently constructed documents is not promised.

NBT batches freeze targets and revision across pages, retain scalar types and skip absent
or invalid fields with reasons. Collect is limited by object count and memory. A changed
revision, including Undo, requires fresh targets. `/` separates fields/indices, `~1`
escapes slash and `~0` tilde. Identity and outer positions cannot be batch-edited.

`structura_edit.object_edits` provides entity_items/transform_entities, block_data,
edit_block_data and edit_entity_data. Mutation helpers return ordinary ChangeSets.
Changing a block ID removes incompatible block-entity NBT; Undo restores it. Replacing
within a compatible family can preserve spatial properties; explicit target properties
win. This does not validate every Minecraft version or mod's semantics.

## Recipes and saving

The GUI Python panel runs ordinary local Python on a disposable branch. Preview never
commits parent edits; exceptions and cancellation discard that branch. Filesystem/network
side effects of explicitly executed code are outside the transaction.

File saves retain supported native metadata and core's atomic-file writer. Edited
Litematic saving and arbitrary cross-format conversion are separate capabilities.
For Java worlds, Apply is local; Save merges supported existing chunks/entities, preserves
history and creates backups. Undo after Save prepares the reverse pending patch.
Conflict detection, recovery and multi-file limitations are specified by
[core's writer contract](../../structura-core/docs/world-writing.md).

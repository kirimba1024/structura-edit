# Workbench guide

[Install and launch](../README.md#install-and-launch) · [Python API](api.md) ·
[Developer architecture](structura-edit-architecture.md)

## Open and inspect

Open accepts `.nbt`, `.snbt`, `.schem`, `.schematic`, `.litematic`, `.mcstructure`,
Java world folders and `level.dat`. `--region` selects a Litematic region;
`--palette-index` selects a Java palette. Missing Sponge v1 version metadata requires
an explicit source DataVersion (`--source-data-version`); version conversion is never guessed.
Legacy `.schematic` saves to NBT/SNBT rather than overwriting its original format.

Choose local Minecraft resources through View → Minecraft resources or `--assets`.
No Java code runs from the JAR and player skins are not downloaded. Without resources,
blocks use fallback colours. The inspector stays in a fixed side panel; scene controls
and results appear without resizing the viewport or moving keyboard focus.

## Navigation and selection

| Input in the viewport | Action |
|---|---|
| WASD / arrows | Continuous noclip flight; forward follows the view |
| E / Space, Q | Up, down |
| Shift | Faster flight; also previews a region from the selected block |
| Mouse / one finger after loading | Free look, no button required |
| Tab / Cursor–Look button | Switch between look and a free cursor |
| Hold RMB | Temporary look; release restores cursor mode |
| Alt | Temporary cursor access |
| Shift+backtick / Focus camera | Focus the scene and start look |
| Click | Select the pointed block/entity; look mode uses the crosshair |
| Shift+click | Commit the previewed cuboid, including both endpoints; entities toggle in the group |
| − / + | Halve / double flight speed |
| Wheel while looking | Change speed; trackpad scrolling does not change it |
| I / middle click | Pick the exact material state into To; no block data is copied |
| F | Frame the scene |
| M | Expand/close the map |
| Enter | Apply the ready preview |
| Escape | Cancel tool/preview or clear selection, return to look; a second Escape within 600 ms opens Exit |
| F5 / Load here | Reload the exact editing area around the camera |

Fields and dialogs handle their own keys. Focus loss, menus and app switching release
held movement/capture; returning restores the chosen look mode. Diagonal movement
has the same speed as straight movement. There is no collision, inertia or orbit mode.
Coordinates commit on Enter/focus loss, not on every typed digit.

Selection offers corner coordinates, size, material counts and operations. Connected
selects matching connected cells; **Planar select** picks a 4-connected exposed face.
Region counts use actual selected cells, excluding empty space. **Chunk columns**,
**Section grid** and schematic bounds are view toggles, not changes to data.

## Prepare, apply and undo

Fill, Replace, Erase, Move blocks and shapes prepare a preview. Changed blocks are
translucent; removals are marked red; unchanged surroundings stay opaque. Apply commits
one operation, Cancel discards it. Undo's label explicitly becomes **Cancel preview**,
**Cancel placement** or **Cancel stroke** during a temporary action; Redo is disabled.
Otherwise Undo/Redo operate on committed history. Empty previews create no history.

**From / Only** conditions combine AND/OR, world Y, NBT and strict property matching.
Negation never treats unloaded world cells as air. **Mix** uses weights, a seed and
local/world anchoring; a two-material height gradient is available. It is deterministic,
not an exact material quota. **Catalog / In build / Recent** share the material picker;
mod IDs can be typed directly. Catalog is a resource index, not a universal validator.

Shapes include Walls, Shell, Hollow, Overlay, Ellipsoid and Cylinder. Planar Extrude
adds positive depth; occupied destinations abort. Frame makes a square-neighbourhood
border. Planar tools initially accept default-state full cubes without block data.
Paint colours existing selected blocks within the radius of a sampled path, including
hidden surfaces inside that radius. Release prepares one preview; missing hits break
the stroke. Escape, focus loss or release outside the viewport cancels it.

The Python panel supplies a disposable branch and selection. Preview explicitly runs
ordinary local Python. A failed/cancelled recipe leaves document edits uncommitted;
filesystem and other external side effects cannot be rolled back.

## Clipboard and repeated placement

The selection strip exposes Move, Duplicate, Fill, Replace, Erase, Paste and Inspect;
More contains Copy, Repeat and Export. Import schematic uses the same placement path.
Move immediately lifts a ghost and hides the source visually; Cancel restores it.
The document changes only when placing. The ghost follows a face or the horizontal placement plane. Click pins it; drag X/Y/Z
handles or use exact coordinates and arrow nudges. Escape during a drag restores its
start; releasing/focus loss ends the drag without placing. WASD still flies.

**Place / Enter** prepares and commits one change. **Preview changes** shows the exact
result first; **Adjust** returns to the ghost. **Blocks / Entities** independently
control contents. Blocks include inventories; entities include passenger trees.
Players are excluded from clipboard capture. Copy assigns new UUIDs; Move/Take retains
identity and removes its source only with the final Apply. **Keep placing** is for copies.

Rotate ±90° and Mirror work on X/Y/Z and preserve the anchor. Transforms compose from
the original, so full cycles restore original data. Unsupported block orientations
fail explicitly; arbitrary mod coordinates/UUID references and entity roll are not guessed.
A schematic expands for destinations outside its bounds, including negative coordinates;
Apply/Undo include that resize and preserve the camera's world position.

**Copy air** includes omitted/air cells in the footprint. Without Air, work is budgeted
by real blocks. **Replace all / Keep existing / Only material** filter block destinations;
entities are placed independently. Partial Take protects skipped source cells even with
an overlapping destination. Empty results do not expand bounds. Missing world chunks
and sections remain unavailable, never air. Crossing a loaded world boundary may load
neighbouring existing chunks while preserving edits and history.

Repeat takes additional copies, direction and gap; zero gap places copies edge to edge.
The source remains, gaps are unaffected by Copy air, and the full series is one Undo.
A parameter change invalidates its preview. Clipboard survives opening another document.

## Objects and NBT

**Find objects…** searches loaded IDs/words, including unsaved changes and objects
hidden by a height slice. **Block data** means any block carrying NBT. **In selection**
uses the actual region. Inventory contents and CustomName are not object-search fields.
Each page contains up to 64 results. Show frames a result and reveals its height;
Select keeps the camera still; Inspect opens one block or a group of entities.
Separated block results are not silently replaced by their bounding box.

Entities can be moved, duplicated, rotated or deleted through Objects. Ordinary entity
copies and passengers get new UUIDs; player profiles must be excluded from destructive
or duplicate groups. Hanging anchors follow supported transforms. Region selection runs
in the worker; selecting the entire loaded entity set needs no NBT traversal.

Inspect a region through searchable Blocks/Block data/Entities tabs, or open an exact
object. The selection card shows precise counts and a bounded rotating preview.
**Structure** displays typed NBT in pages. **Find** searches unexpanded fields too;
**Edit value…** preserves number types and exact int64 values. **Inventories** finds
nested id/count records, including mods; **Edit count…** and **Open item…** address them.
Apply changes commits all inspected edits as one Undo; Cancel drops the drafts.
**NBT text** supports advanced structural edits. A limited search is labelled; complete
data stays available. This is data editing, not validation of every mod's semantics.

**Edit field in all results…** freezes the full result set across pages (up to 10,000
objects and the operation/memory budgets). Give a scalar path such as `/Items/0/count`
and a value, then Preview → Apply. Missing fields/invalid values are skipped with reasons;
identity and outer position are protected. `/` separates fields/indices; `~1` escapes
slash and `~0` tilde. New edits or Undo make targets stale. [API example](api.md#object-search-and-nbt).

## Maps and world editing

The compact map has six views. **Auto** selects the surface or a cave floor near the
camera's height. **Cave** replaces the old bottom projection. Surface and Slices remain
available; Slices starts views at the camera's block. Click a view to enlarge it, Map to restore the grid.
Drag/two-finger scroll pans, wheel/pinch zooms around the cursor, F recenters. Manual pan
in the large map suspends following; compact mode always follows. Double-click a settled
local projection moves the camera in that plane. Map gestures do not edit or fly underneath.
Close zoom loads the original block texture for the visible area. **Entities** cycles
Auto, Icons, Dots and Off. Auto uses dots at small scales and recognizable icons when
zoomed in. Markers stay a readable screen size; they do not grow into block-sized squares.

**Visible heights** offers all heights, hide above Y, or one layer. Y is world-space;
Use camera height copies the current Y. Geometry, picking and all projections use the
shown slice. It does not constrain editing to visible cells or create Undo.

Java Open starts near the saved player or spawn. World view distance selects dimension,
radius and vertical range. Default radius 6 covers 13×13 chunk columns across all saved
section heights, including caves. F5/Load here loads around the camera, preserving pending
edits/history, world camera position and valid selection. With a prepared overview,
flight refines cached geometry without reloading the editable area.
World settings and F5 do not reopen an old world while a schematic is active.

**Build / Update overview** prepares saved chunks as a persistent 3D/2D snapshot.
Opening a world reuses a valid snapshot or starts its first preparation. Updates to
world files, textures or the cache version invalidate the old snapshot on reopening.
World map pan/zoom uses that snapshot; Go to/double-click prepares a destination before
moving. Manual movement, another destination or Cancel cancels the pending teleport.
Auto detail refines prepared geometry for a stable camera cell; it does not load editable
blocks. Load here does that separately. Update overview* marks an older snapshot.
Nether's map defaults below Y=120; Map below Y changes display, not import limits.
Unknown chunks and known empty space remain distinct. [Implementation limits](world-view.md).

**Apply is local; Save world writes accumulated edits.** Existing supported chunks and
sections are required; no terrain is generated. Save merges against freshly read data,
rejects conflicts and preserves unrelated NBT/biomes. A conflict review can offer an
explicit Force choice. Before installation, core prepares backups and a manifest under
`<world>/.structura/backups/<save-id>`. Interrupted saves require recovery before another
write. **Restore backup** verifies originals/current files and backs up what it replaces.
Save preserves Undo; Undo after Save produces a reverse patch for the next Save.

Structura serializes its writes and rechecks hashes, but cannot lock Minecraft or make
multiple region files atomic. Inspect the conflict/recovery result; the pending patch
survives failures. Technical writer guarantees are owned by [core](../../structura-core/docs/world-writing.md).

## Save, export and local recovery

Saved/Unsaved/View-only is separate from task progress. Issues retains detailed errors
with Copy details. Save selects a working file once; Save as chooses another. Open/Close
offer Save/Discard/Cancel for unsaved edits and never silently commit a preview.

Export selection crops to zero and writes NBT/SNBT/Sponge with a loss review. Sponge is
rectangular, so sparse holes become air. Local fragments retain a sparse footprint,
name/tags/anchor and use normal placement. They do not execute recipes.

After 30 idle seconds with new changes, a local checkpoint records final edits/context.
Save local draft requests one now; Recover local draft does not write the source and
cannot restore earlier Undo history. Missing/changed schematic sources force Save as.
The last completed checkpoint is shown in the status tooltip. Data lives under
`~/.local/share/structura-edit` or `STRUCTURA_EDIT_DATA`; drafts keep two generations per
session. Older sessions and library fragments are not automatically deleted.

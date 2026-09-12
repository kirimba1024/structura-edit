# Changelog

## 0.1.0a2

- Require core 0.6.2 and render 0.8.2 so installed packages contain the world,
  transform, overview and render-packet APIs used by the editor.
- Keep exact geometry and polygonal world coverage while installing replacements
  in bounded batches; reuse textures, previews and geometry caches.
- Reduce map work during camera motion, reuse atlases during pan/zoom and reject
  stale maps after reloading a document with the same revision.
- Preserve exact map textures, entity icons and cave slices; keep overlays from
  resizing the 3D viewport.
- Keep placement controls fixed when adjacent explanatory text wraps.
- Reject a completed teleport if the camera moved or turned while its destination
  was being prepared, including a cached result arriving before the next GUI tick.
- Synchronize Windows recovery bundles through writable handles, retain UTF-8
  metadata, and allow cancellation to stop waiting for an unresponsive worker pipe.
- Reduce ChangeSet allocations and decoding cost while retaining atomic validation,
  NBT/entities, Save, Undo/Redo and stale-worker rejection.
- Add reproducible flight/map benchmarks and checks for installed packages.
  Active native navigation and stable 60/120 Hz acceptance remain pending.

## 0.1.0a1

- Introduce transactional schematic and bounded Java-world editing with a shared
  Python API and desktop workbench, previews, clipboard operations and recovery.

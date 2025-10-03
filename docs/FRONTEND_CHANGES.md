## Frontend Hierarchy & Panel Refactor (2025-10-01)

This document summarizes the structural UI changes introduced to support a three-level execution hierarchy and improved content viewing.

### Goals
1. Move phase/agent status hierarchy to the left panel (with multi-run instrument tabs).
2. Provide a 3-level tree: Phase -> Agent Role -> (Messages, Report).
3. Use the right panel exclusively to display either:
   - The detailed messages or report markdown for a leaf node, OR
   - A status summary for a selected Phase or Agent node (including child statuses and timing metadata).
4. Introduce a log filtering modal accessible from the instruments area to coordinate global filter preferences (future enhancement hook).

### Key Template Changes
- `_partials/left_panel.html`: Now renders instrument tabs, execution tree wrappers, and a `<dialog>` element for log filtering. A macro `render_item` was updated to optionally inject synthetic leaf nodes (`messages` / `report`) if the backend marks them via `synthetic_children` (future path) or the client-side JS synthesizes them for multi-run.
- `_partials/right_panel.html`: Accepts full `item` context and decides whether to render markdown content (leaf) or a status summary (non-leaf).
- `index.html`: Multi-run tabs moved from the right panel to the left. Right panel now starts with a placeholder. Added JS helpers `selectNode`, `loadRunTree`, and modified websocket handlers to populate new structures.

### Backend Adjustments
- `webapp/main.py`: `/content/{item_id}` and websocket `get_content` action now render `_partials/right_panel.html` with `item` in context, enabling status summary rendering.

### JavaScript Additions
- Selection logic (`selectNode`) fetches `/content/<item_id>` and injects the returned HTML into the new right panel.
- `loadRunTree` constructs the Phase -> Agent -> (Messages/Report) synthetic structure for each run when an init snapshot arrives.

### Modal / Log Filters
The log filter modal (`#log-filter-modal`) is introduced but only wires a stub `applyLogFilters` function. Future work: propagate selected filters to each run's log streaming UI and trigger reloads.

### Future Enhancements / TODO
- Add backend support to directly expose `messages` / `report` nodes in the execution tree to avoid client synthesis.
- Implement global filter propagation (severity, sources, query) to each run via a shared state object.
- Persist active selection per instrument when switching tabs.
- Keyboard navigation & accessibility improvements for the tree view.

---
For questions or extension guidance, see inline comments in the updated templates and `index.html`.

// Global-ish state containers (could later be encapsulated)
export const runPatchState = {}; // run_id -> { seq, syncing }
export const runContentState = {}; // run_id -> { seq, nodes: {itemId: renderedHtml} }
export const runLogState = {}; // run_id -> { seq, syncing }

export function getOrInit(map, key, init) {
  if (!map[key]) map[key] = init;
  return map[key];
}

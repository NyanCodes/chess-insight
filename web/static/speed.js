// Piece speed: the choices offered, the default, and how a remembered value is read back.
export const SPEEDS = [0, 120, 200, 300, 500];     // milliseconds; 0 means "off"
export const DEFAULT_SPEED_MS = 200;

// `saved` is whatever localStorage returned: null when nothing was stored yet. A missing or
// unknown value (including a speed an older version offered) must give the default, never
// "off" (Number(null) is 0).
export function parseSavedSpeed(saved) {
  if (saved === null || saved === undefined || String(saved).trim() === "") return DEFAULT_SPEED_MS;
  const value = Number(saved);
  return SPEEDS.includes(value) ? value : DEFAULT_SPEED_MS;
}

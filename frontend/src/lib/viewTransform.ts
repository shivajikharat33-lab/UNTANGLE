/** Zoom limits for the drawing viewer. 1 means 100 percent. */

export const MIN_ZOOM = 0.25;
export const MAX_ZOOM = 4;

export function clampZoom(value: number): number {
  const stepped = Math.round(value * 100) / 100;
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, stepped));
}

export function zoomBy(current: number, factor: number): number {
  return clampZoom(current * factor);
}

export function zoomPercent(zoom: number): string {
  return `${Math.round(zoom * 100)}%`;
}

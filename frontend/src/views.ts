/** Presentation style only affects the projection, never the recorded history. */
export const VIEWS = ["reader", "presenter", "inspector"] as const;
export type PresentationView = typeof VIEWS[number];

export function parseView(value: unknown): PresentationView | undefined {
  return typeof value === "string" && (VIEWS as readonly string[]).includes(value)
    ? value as PresentationView : undefined;
}

export function resolveView(
  requested: unknown, configured: unknown, stepCount: number,
): PresentationView {
  return parseView(requested) ?? parseView(configured) ?? (stepCount ? "inspector" : "reader");
}

export function displayIndex(view: PresentationView, idx: number, stepCount: number): number {
  return view === "reader" ? Math.max(0, stepCount - 1) : idx;
}

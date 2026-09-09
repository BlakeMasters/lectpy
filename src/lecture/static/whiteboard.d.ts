export interface Point {
  x: number;
  y: number;
  p: number;
}
export interface DrawingItem {
  id: string;
  tool: string;
  color: string;
  width: number;
  points: Point[];
  text?: string;
}
export interface Drawing {
  version: 1;
  width: number;
  height: number;
  background: string;
  items: DrawingItem[];
}
export interface BoardCommit {
  revision: number;
  drawing: Drawing;
  svg: string;
  alt: string;
  outputId?: string;
}
export class BoardModel {
  constructor(drawing?: Drawing);
  drawing: Drawing;
  readonly items: DrawingItem[];
  undoStack: unknown[];
  redoStack: unknown[];
  add(item: DrawingItem): void;
  remove(ids: Set<string>): void;
  clear(): void;
  undo(): void;
  redo(): void;
  snapshot(): Drawing;
}
export interface BoardState {
  model?: BoardModel;
  open?: boolean;
  commits?: BoardCommit[];
}
export const TOOLS: string[];
export function pointerSample(
  event: Pick<PointerEvent, "clientX" | "clientY" | "pressure" | "pointerType">,
  rect: Pick<DOMRect, "left" | "top" | "width" | "height">,
  width: number,
  height: number,
): Point;
export function acceptsPointer(
  event: Pick<PointerEvent, "pointerId" | "pointerType" | "button">,
  penOnly: boolean,
  activeId?: number | null,
): boolean;
export function pointerTool(
  event: Pick<PointerEvent, "pointerType" | "button" | "buttons">,
  tool: string,
): string;
export function hitTest(
  item: DrawingItem,
  point: Pick<Point, "x" | "y">,
  radius?: number,
): boolean;
export function validateDrawing(value: unknown): Drawing;
export function drawingSvg(drawing: Drawing): string;
export function mountWhiteboard(
  host: HTMLElement,
  props?: Record<string, unknown>,
  state?: BoardState,
): () => void;

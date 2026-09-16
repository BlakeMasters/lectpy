export interface StepKeyable {
  key: string;
  action: string;
  target?: string;
  label?: string;
  prevent_default?: boolean;
  host?: HTMLElement | null;
}
type StepEvent = { payload?: Record<string, unknown> };
export function keySpecMatches(event: KeyboardEvent, spec: unknown): boolean;
export function activeStepKeyables(
  root: ParentNode, step?: StepEvent, focused?: EventTarget | null, reader?: boolean,
): StepKeyable[];
export function dispatchPlaybackAction(
  root: ParentNode, action: string, target?: string, preferredHost?: HTMLElement | null,
): boolean;
export function handleStepKey(event: KeyboardEvent, options: {
  root: ParentNode;
  step?: StepEvent;
  reader: boolean;
  index: number;
  count: number;
  navigate: (index: number) => void;
}): void;

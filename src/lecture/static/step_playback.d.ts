export interface StepPlaybackProps {
  [key: string]: unknown;
}

export interface StepPlaybackMountOptions {
  active?: boolean;
}

export function mountStepPlayback(
  host: HTMLElement,
  props: StepPlaybackProps,
  options?: StepPlaybackMountOptions,
): () => void;

export function normalizeStepPlaybackProps(
  props: StepPlaybackProps,
): StepPlaybackProps;

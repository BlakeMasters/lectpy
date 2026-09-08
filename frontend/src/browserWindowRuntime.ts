/** Shared browser-reference state, kept outside the lazy visual renderer. */
import type { LectureEvent } from "./protocol";
import {
  BrowserWindowController,
  browserWindowSpec,
} from "../../src/lecture/static/browser_window.js";
import type { BrowserWindowProps } from "../../src/lecture/static/browser_window.js";

export const referenceWindowController = new BrowserWindowController();

const subscribers = new Set<() => void>();
const messages = new Map<string, string>();

export function subscribeBrowserWindowChanges(listener: () => void): () => void {
  subscribers.add(listener);
  return () => subscribers.delete(listener);
}

export function notifyBrowserWindowChange(): void {
  subscribers.forEach((listener) => listener());
}

export function browserWindowMessage(id: string, fallback: string): string {
  return messages.get(id) ?? fallback;
}

export function rememberBrowserWindowMessage(id: string, message: string): void {
  messages.set(id, message);
}

export function eventProps(event: LectureEvent): BrowserWindowProps {
  const value = event.payload?.["props"];
  return value && typeof value === "object" ? (value as BrowserWindowProps) : {};
}

export function applyBrowserWindowEvent(event: LectureEvent) {
  const props = eventProps(event);
  const spec = browserWindowSpec(props);
  const result = props.action === "close"
    ? referenceWindowController.close(spec.id)
    : referenceWindowController.open(props);
  rememberBrowserWindowMessage(spec.id, result.message);
  notifyBrowserWindowChange();
  return result;
}

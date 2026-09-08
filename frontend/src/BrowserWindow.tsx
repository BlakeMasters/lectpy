/** User-initiated external reference windows; no popup is opened during render. */
import { useEffect, useState } from "react";
import type { LectureEvent } from "./protocol";
import {
  BrowserWindowController,
  browserWindowName,
  browserWindowSpec,
} from "../../src/lecture/static/browser_window.js";
import type { BrowserWindowProps } from "../../src/lecture/static/browser_window.js";

const controller = new BrowserWindowController();
const subscribers = new Set<() => void>();
const notify = () => subscribers.forEach((listener) => listener());

function useWindowRevision(): number {
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const listener = () => setRevision((value) => value + 1);
    subscribers.add(listener);
    return () => {
      subscribers.delete(listener);
    };
  }, []);
  return revision;
}

function eventProps(event: LectureEvent): BrowserWindowProps {
  const value = event.payload?.["props"];
  return value && typeof value === "object" ? (value as BrowserWindowProps) : {};
}

export default function BrowserWindow({ event }: { event: LectureEvent }) {
  const props = eventProps(event);
  const action = props.action === "close" ? "close" : "open";
  const spec = browserWindowSpec(props);
  useWindowRevision();
  const [message, setMessage] = useState(
    action === "close" ? "Close request recorded." : "Ready to open from this control.",
  );

  useEffect(() => {
    if (action !== "close") return;
    const result = controller.close(spec.id);
    setMessage(result.message);
    notify();
  }, [action, spec.id]);

  const opened = Boolean(controller.get(spec.id));
  function open() {
    const result = controller.open(props);
    setMessage(result.message);
    notify();
  }
  function close() {
    const result = controller.close(spec.id);
    setMessage(result.message);
    notify();
  }

  if (action === "close") {
    return (
      <section className="lecture-browser-window" aria-label={`Close reference window ${spec.id}`}>
        <h3>Reference window: close request</h3>
        <p className="muted">Window <code>{spec.id}</code> is released when this step is reached.</p>
        <p role="status" aria-live="polite">{message}</p>
      </section>
    );
  }

  return (
    <section className="lecture-browser-window" aria-label={`Reference window: ${spec.title}`}>
      <h3>{spec.title}</h3>
      <p className="browser-window-url"><span>Reference: </span><code>{spec.url || "Blocked URL"}</code></p>
      <p className="muted">
        {spec.width} × {spec.height}
        {spec.left !== undefined || spec.top !== undefined
          ? ` · position ${spec.left ?? "auto"}, ${spec.top ?? "auto"}` : ""}
        {` · ${browserWindowName(spec.id)}`}
      </p>
      <div className="browser-window-actions">
        <button type="button" onClick={open} disabled={!spec.url}>
          {opened ? "Focus reference window" : "Open reference window"}
        </button>
        <button type="button" onClick={close} disabled={!opened}>Close reference window</button>
        {spec.url ? (
          <a href={spec.url} target="_blank" rel="noopener noreferrer">Open reference link</a>
        ) : null}
      </div>
      <p className="browser-window-status" role="status" aria-live="polite">{message}</p>
    </section>
  );
}

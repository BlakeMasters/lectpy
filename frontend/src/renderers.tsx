/** Built-in output renderers — trusted host UI in the shell's origin.
 *
 *  Lecture-supplied HTML is NEVER injected raw: `text`/`note` payloads carry
 *  exporter-sanitized `html` (see `sanitize.py`); live broker HTML gets a
 *  DOMPurify pass in v0.4 before reaching these components.
 */
import type { LectureEvent } from "./protocol";
import { isSafeUrl } from "./select";

type P = { event: LectureEvent };

function payload(event: LectureEvent): Record<string, unknown> {
  return event.payload ?? {};
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

export function TextBlock({ event }: P) {
  const p = payload(event);
  return <div className="out" dangerouslySetInnerHTML={{ __html: str(p["html"]) }} />;
}

export function NoteBlock({ event }: P) {
  const p = payload(event);
  return (
    <div className="out note" dangerouslySetInnerHTML={{ __html: str(p["html"]) }} />
  );
}

export function ImageBlock({ event }: P) {
  const p = payload(event);
  const src = str(p["src"]);
  if (!isSafeUrl(src, true)) {
    return (
      <p className="muted" role="note">
        Blocked image source (policy): {str(p["alt"]) || "(no alt text)"}
      </p>
    );
  }
  return (
    <figure>
      <img src={src} alt={str(p["alt"])} title={str(p["title"]) || undefined} />
      {str(p["title"]) ? <figcaption>{str(p["title"])}</figcaption> : null}
    </figure>
  );
}

export function VideoBlock({ event }: P) {
  const p = payload(event);
  const src = str(p["src"]);
  if (!isSafeUrl(src, true)) {
    return (
      <p className="muted" role="note">
        Blocked video source (policy).
      </p>
    );
  }
  return <video controls src={src} />;
}

export function LinkBlock({ event }: P) {
  const p = payload(event);
  const href = str(p["href"], "#");
  const label = str(p["label"]) || href;
  if (!isSafeUrl(href)) {
    return <p className="muted">Blocked link (policy): {label}</p>;
  }
  const external = /^(https?:)?\/\//.test(href);
  return (
    <p>
      <a href={href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
        {label}
      </a>
    </p>
  );
}

export function PlotBlock({ event }: P) {
  const p = payload(event);
  return (
    <details>
      <summary>Plot (static fallback — spec retained)</summary>
      <pre className="code">{JSON.stringify(p["spec"] ?? {}, null, 2)}</pre>
    </details>
  );
}

export function TerminalBlock({ event }: P) {
  const p = payload(event);
  const output = p["output"];
  if (typeof output === "string") {
    return <pre className="term">{output}</pre>;
  }
  const argv = Array.isArray(p["argv"])
    ? (p["argv"] as unknown[]).map(String).join(" ")
    : String(p["argv"] ?? "");
  return (
    <>
      <pre className="term">{"$ " + argv}</pre>
      <p className="muted">Recorded process block — attach a broker for a live PTY.</p>
    </>
  );
}

export function ComponentBlock({ event }: P) {
  const p = payload(event);
  return (
    <>
      <div className="muted" role="note">
        Interactive component <code>{str(p["component_type"])}</code> — recorded
        fallback in static mode.
      </div>
      <details>
        <summary>Declared props</summary>
        <pre className="code">{JSON.stringify(p["props"] ?? {}, null, 2)}</pre>
      </details>
    </>
  );
}

export function ErrorBlock({ event }: P) {
  const p = payload(event);
  return (
    <p role="alert">
      <strong>Error:</strong> {str(p["message"])}
    </p>
  );
}

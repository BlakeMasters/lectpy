/** Built-in output renderers — trusted host UI in the shell's origin.
 *
 *  Lecture-supplied HTML is NEVER injected raw: `text`/`note` payloads carry
 *  exporter-sanitized `html` (see `sanitize.py`); live broker HTML gets a
 *  DOMPurify pass in v0.4 before reaching these components.
 */
import { lazy, Suspense } from "react";
import type { LectureEvent } from "./protocol";
import { isSafeUrl } from "./select";
import { useResource } from "./resources";
import { Whiteboard } from "./Whiteboard";
import { texToMathML } from "../../src/lecture/static/equation.js";
import { umlDescription, umlSvg } from "../../src/lecture/static/uml.js";

type P = { event: LectureEvent };
const BrowserWindow = lazy(() => import("./BrowserWindow"));
const Automation = lazy(() => import("./Automation"));

function payload(event: LectureEvent): Record<string, unknown> {
  return event.payload ?? {};
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

export function TextBlock({ event }: P) {
  const p = payload(event);
  if (typeof p["html"] !== "string") return <pre className="out">{str(p["markdown"])}</pre>;
  return <div className="out" dangerouslySetInnerHTML={{ __html: str(p["html"]) }} />;
}

export function NoteBlock({ event }: P) {
  const p = payload(event);
  if (typeof p["html"] !== "string") return <pre className="out note">{str(p["markdown"])}</pre>;
  return (
    <div className="out note" dangerouslySetInnerHTML={{ __html: str(p["html"]) }} />
  );
}

export function ImageBlock({ event }: P) {
  const p = payload(event);
  const resource = useResource(str(p["src"]));
  const src = resource.url;
  if (resource.loading) return <p role="status">Loading image…</p>;
  if (resource.error) return <p role="alert">{resource.error}</p>;
  if (!isSafeUrl(src, true)) {
    return (
      <p className="muted" role="note">
        Blocked image source (policy): {str(p["alt"]) || "(no alt text)"}
      </p>
    );
  }
  return (
    <figure className="lecture-media">
      <img src={src} loading="lazy" alt={str(p["alt"])} title={str(p["title"]) || undefined} />
      {str(p["title"]) ? <figcaption>{str(p["title"])}</figcaption> : null}
    </figure>
  );
}

export function VideoBlock({ event }: P) {
  const p = payload(event);
  const resource = useResource(str(p["src"]));
  const src = resource.url;
  if (resource.loading) return <p role="status">Loading video…</p>;
  if (resource.error) return <p role="alert">{resource.error}</p>;
  if (!isSafeUrl(src, true) && !/^data:video\//i.test(src)) {
    return (
      <p className="muted" role="note">
        Blocked video source (policy).
      </p>
    );
  }
  return <figure className="lecture-media"><video controls preload="metadata" src={src}
    aria-label={str(p["title"]) || "Video"} />
    {str(p["title"]) && <figcaption>{str(p["title"])}</figcaption>}</figure>;
}

export function LinkBlock({ event }: P) {
  const p = payload(event);
  const resource = useResource(str(p["href"], "#"));
  const href = resource.url;
  const label = str(p["label"]) || href;
  if (resource.loading) return <p role="status">Loading {label}…</p>;
  if (resource.error) return <p role="alert">{resource.error}</p>;
  if (!isSafeUrl(href) && !href.startsWith("blob:")) {
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

export function EquationBlock({ event }: P) {
  const p = payload(event);
  const tex = str(p["tex"]);
  const alt = str(p["alt"]) || `Equation: ${tex}`;
  const title = str(p["title"]);
  const outputId = str(p["output_id"]) || undefined;
  const display = p["display"] !== false;
  return (
    <figure className="lecture-equation" data-output-id={outputId}>
      <div
        className="lecture-equation-math"
        aria-label={alt}
        dangerouslySetInnerHTML={{ __html: texToMathML(tex, { display, alt }) }}
      />
      {title ? <figcaption>{title}</figcaption> : null}
      <p className="equation-alt sr-only">{alt}</p>
    </figure>
  );
}

export function UmlBlock({ event }: P) {
  const p = payload(event);
  const kind = str(p["uml_kind"], "class");
  const spec = p["spec"] && typeof p["spec"] === "object"
    ? p["spec"] as Record<string, unknown>
    : {};
  const alt = str(p["alt"]) || umlDescription(kind, spec);
  const title = str(p["title"]);
  const outputId = str(p["output_id"]) || undefined;
  return (
    <figure className="lecture-uml" data-output-id={outputId}>
      <div
        className="lecture-uml-svg"
        role="img"
        aria-label={alt}
        dangerouslySetInnerHTML={{ __html: umlSvg(kind, spec) }}
      />
      {title ? <figcaption>{title}</figcaption> : null}
      <p className="uml-alt sr-only">{alt}</p>
    </figure>
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
  if (p["component_type"] === "playwright-controls") {
    return <Suspense fallback={<p role="status">Loading browser controls…</p>}><Automation event={event} /></Suspense>;
  }
  if (p["component_type"] === "whiteboard") return <Whiteboard event={event} />;
  if (p["component_type"] === "browser-window") {
    return (
      <Suspense fallback={<p role="status">Loading reference-window controls…</p>}>
        <BrowserWindow event={event} />
      </Suspense>
    );
  }
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

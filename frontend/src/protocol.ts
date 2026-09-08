/** lectpy protocol types v1 — mirrors schemas/event-v1.json,
 *  schemas/manifest-v1.json and schemas/bundle-v1.json.
 */

export const SCHEMA_VERSION = 1 as const;

export type EventKind =
  | "session_start" | "session_end" | "step" | "text" | "note"
  | "image" | "video" | "link" | "plot" | "inspect"
  | "clear" | "error" | "terminal" | "component" | "snapshot";

export interface SourceLocation { file: string; line: number; func?: string }

/** A trace step's nearest author call site (for example: ref → main:18). */
export interface TraceReference { file: string; line: number; func?: string }

export interface LectureEvent {
  session_id: string;
  execution_id: string;
  seq: number;
  wall_time?: number;
  kind: EventKind;
  payload?: Record<string, unknown>;
  source_location?: SourceLocation;
  artifact_refs?: string[];
  parent_event?: number;
  schema_version?: number;
}

export interface LectureManifest {
  format_version: 1;
  title: string;
  source_file: string;
  source_sha256: string;
  created?: number;
  runtime?: string;
  view?: "reader" | "presenter" | "inspector";
  policy_profile?: "static" | "local-trusted" | "local-restricted" | "classroom" | "public-untrusted";
  plugin_ids?: string[];
}

/** Author source snapshot for the shell's source pane (bundle v1 `source`). */
export interface LectureSource {
  file: string;
  sha256: string;
  text: string;
}

export interface LectureBundle {
  manifest: LectureManifest;
  events: LectureEvent[];
  checkpoint?: Record<string, unknown>;
  source?: LectureSource | null;
  resources?: Record<string, { path: string; mime: string; bytes: number }>;
}

/** Portable renderer contract (v0.2: React components implement it; the
 *  stable ABI is mount/unmount, never React internals). Untrusted lecture
 *  components use the sandboxed iframe contract (v0.4), never this registry.
 */
export interface RendererPlugin {
  mimeTypes: readonly string[];
  render(output: unknown, mount: HTMLElement): Promise<() => void>;
}

export interface ExecutionProvider {
  id: string;
  probe(): Promise<unknown>;
}

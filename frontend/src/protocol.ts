/** lectpy protocol types v1 — mirrors schemas/event-v1.json + manifest-v1.json.
 *  Full shell (renderer/inspector registries, xterm, editor adapter) in v0.2.
 */

export const SCHEMA_VERSION = 1 as const;

export type EventKind =
  | "session_start" | "session_end" | "step" | "text" | "note"
  | "image" | "video" | "link" | "plot" | "inspect"
  | "clear" | "error" | "terminal" | "component" | "snapshot";

export interface SourceLocation { file: string; line: number; func?: string }

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
  policy_profile?: "static" | "local-trusted" | "local-restricted" | "classroom" | "public-untrusted";
  plugin_ids?: string[];
}

export interface LectureBundle {
  manifest: LectureManifest;
  events: LectureEvent[];
  checkpoint?: Record<string, unknown>;
}

export interface RendererPlugin {
  mimeTypes: readonly string[];
  render(output: unknown, mount: HTMLElement): Promise<() => void>;
}

export interface ExecutionProvider {
  id: string;
  probe(): Promise<unknown>;
}

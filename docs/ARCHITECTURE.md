# Architecture — lectpy microkernel

## Layers

```
Lecture sources (.py/.md/.ts/assets)
  → Lecture compiler / author SDK (src/lecture/)
  → Lecture IR + manifest + ordered event log + CAS artifacts
  → Browser application (frontend/; v0.1 static replay, v0.2 full shell)
  → Capability broker lectured (src/lecture/broker/)
  → Execution providers (src/lecture/providers/)
```

## Microkernel boundary

The core understands only:

- document / lecture IDs, source locations
- execution sessions, output/event envelopes, artifact references
- capability declarations, plugin manifests, renderer media types
- command registration, state revisions

It does **not** understand Torch tensors, Vega, Deno, CUDA, terminals, Pyright,
or containerd. Those are plugins/providers behind `LecturePlugin` /
`ExecutionProvider` contracts (see `src/lecture/plugins.py`, `docs/ROADMAP.md`).

This is a **microkernel application architecture**, not a microservice
deployment requirement. Locally one broker process contains trusted providers
plus child processes; remote deployments may split providers later.

## Protocol (transport-neutral, v1)

```
SessionService   open(document, environment, policy) -> session | close(session)
ExecutionService start(session, ExecutionSpec) -> execution | input | interrupt | terminate
EventService     subscribe(session, after_seq) -> ordered Event stream
ArtifactService  put/get(hash) | open_object(handle, projection)
LanguageService  start(language, workspace, options) | json_rpc(...)
ComponentService dispatch(component_id, revision, event)
```

Local transport: loopback authenticated WebSocket / UDS / named pipe.
Remote transport: TLS WebSocket/HTTP over the same logical API.
Wire model never leaks PIDs or host paths to the client.

Event envelope (`schemas/event-v1.json`, `src/lecture/events.py`):

```
Event { session_id, execution_id, seq, wall_time, source_location?,
        kind, payload, artifact_refs[], parent_event?, schema_version }
```

- `seq` is monotonic per session (single writer). Reconnect = `after_seq=N`.
- Snapshots checkpoint a prefix of the log; replaying the same sequence onto a
  blank client must reconstruct identical presentation state (golden tests).

## Execution state ≠ document state

- **Authoring state** (source text, outline, annotations): CRDT (Yjs or Automerge)
  — planned v0.5. Yjs updates merge independent of delivery order.
- **Runtime state** (shell commands, file writes, CUDA kernels): single-writer
  monotonic event history. Never a CRDT — effects are not commutative.

Component sync uses host-mediated revisions (`component_id`, `instance_id`,
`revision_seen` → `revision`, `patch`, `binary_refs[]`), mirroring the useful
half of Jupyter widget comms without requiring component state to live in-kernel.

## Serialization (three levels)

1. **JSON** — schemas, commands, small payloads, debugging.
2. **CAS blobs** (`src/lecture/artifacts.py`) — files/images/audio/checkpoints/
   terminal recordings, addressed by `sha256:<hex>`, with provenance
   (source URL, retrieval date, content hash, license).
3. **Arrow IPC** — typed columnar transfer for arrays/tables (lazy, demand-driven;
   v0.1 defines the handle/preview convention, full Arrow paths in v0.3+).

Large values are never eagerly inlined: an `inspect` event carries
`{object, dtype, shape, preview}` plus a handle the inspector resolves lazily.

## Persistence

```
lecture_project/
  lecture_01.py  components/  assets/
  pyproject.toml  uv.lock  package.json  deno.lock  lecture.toml
  .lecture/ plugins.lock  environments/  checkpoints/  artifacts/
```

Checkpoint descriptor (`src/lecture/ir.py:Checkpoint`): source hash, IR version,
event seq, environment digest/lockfiles, kernel/runtime identity, plugin
IDs+versions, policy profile, artifact hashes, seeds, replayability flags.
Distinguishes **replayable checkpoint** vs **runtime-native checkpoint** vs
**recorded presentation snapshot** (files/sockets/GPU contexts are not
portably snapshottable).

## Frontend (target)

- TypeScript shell; React (or equivalent) internal; portable renderer contract =
  Custom Elements / mount-unmount API (never React internals as ABI).
- Untrusted lecture components → sandboxed opaque-origin iframes + typed
  `postMessage` bridge (origin checks, channel tokens, JSON-schema validation,
  allowlists, revision ordering, size/rate limits; no generic eval/run/filesystem).
- Trusted built-in/plugin UI may use Web Components in host DOM.
- Editor behind adapter (Monaco/CodeMirror); terminal = xterm.js in a privileged
  host-controlled realm/origin separate from lecture JS (xterm JS can otherwise
  observe terminal I/O).
- Markdown/HTML host rendering: sanitizer + CSP + Trusted Types; never raw
  `marked() → dangerouslySetInnerHTML`.

## Broker / security layering

All privileged actions flow through the capability gateway → session supervisor
→ artifact proxy → execution zones (WASM sandbox / OCI-gVisor / trusted host /
remote microVM). Plugin manifests *request* capabilities; policy/user *grants* a
subset. Deno/Node permission flags are defense-in-depth, never the outer
hostile-code boundary (both document bypassability). See `docs/SECURITY.md`.

## Reuse (own the narrow waist, reuse the rest)

Own: lecture semantics, event protocol, capability model, plugin ABI, author UX,
replay/checkpoint model. Reuse: Jupyter protocol, xterm.js, Monaco/CodeMirror,
Vite+esbuild, Deno+Node, Wasmtime, Yjs/Automerge (one), Arrow, Tauri, OCI
ecosystem, gVisor/microVM tiers.

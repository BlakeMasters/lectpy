# Roadmap — lectpy to superior interactive lecture platform

Estimates in engineer-weeks (engineering only; excludes prolonged institutional
security review / content migration). One protocol across local → Tauri → remote.

| Milestone | Deliverable | Effort | Status | Principal risk |
|---|---|---:|---|---|
| **v0.1 Protocol & compat core** | Lecture IR, event schemas, artifact IDs, edtrace-compat author layer, scoped context, tracer, CAS, static replay + tests | 3–5 | **in progress (this branch)** | Locking in wrong state model |
| **v0.2 Browser shell** | TS shell, virtualized source/trace view, keyboard nav + URL routes, inspector & renderer registries | 4–6 | **done (this branch)** | UI scope creep |
| **v0.3 Runtime broker** | Session supervisor, Jupyter kernels, one-shot processes, PTYs, cancellation, xterm integration | 6–8 | **done (this branch)** | Win PTY/process edge cases; leaks |
| **v0.4 JS/TS + live components** | Vite/esbuild pipeline, iframe sandbox, Deno/Node adapters, capability bridge | 5–7 | planned | XSS / escape / capability confusion |
| **v0.5 LSP + objects** | LSP router, virtual URIs/source maps, lazy inspectors, Arrow/binary paths | 4–6 | planned | source/runtime identity mapping |
| **v0.6 Persistence + collab** | Event log, snapshots, CAS, crash recovery, Yjs/Automerge source collab | 4–6 | planned | migration / long histories |
| **v0.7 Secure providers** | OCI provider, limits, net/file policy, optional gVisor remote profile | 7–10 | planned | host isolation / ops complexity |
| **v0.8 Packaging + hardening** | Tauri desktop, wheels/binaries, update/signing, static build, a11y + security review | 5–8 | planned | signing/update/security |
| **Total v1** | Core → deployable hardened v1 | 38–56 | — | security + x-platform execution |

Developer beta ≈ v0.1–v0.4 (≈22–32 e-w). Public multi-tenant service only after
v0.7 isolation milestone — never on "containers are probably enough".

## v0.1 definition of done (delivered)

- [x] Plan + architecture + security + authoring docs
- [x] `src/lecture/`: events, IR, context, SDK, sanitize, artifacts, policy,
      trace, providers/trace+process, broker (in-process), plugins registries,
      export_static, cli
- [x] `schemas/`: event-v1, manifest-v1 JSON schemas (+ bundle-v1 in v0.2)
- [x] `frontend/`: TS protocol types stub + static replay contract
- [x] `examples/`: lecture_01 (basics), lecture_02 (process/plot/component stubs)
- [x] `tests/`: protocol validation, golden replay, sanitizer adversarial,
      policy, CAS, tracer semantics, perf smoke (100k-line virtualization logic,
      20k-event append/slice smoke, output backpressure)
- [x] `lecture doctor` green; `pytest` green; static bundle opens from `file://`
      with keyboard nav + deep-linked `?step=N` (Edge-screenshot validated)

## v0.2 definition of done (delivered)

- [x] Vite + React + TS shell loading v1 `lecture.json` (`?bundle=` override)
- [x] Renderer / command / execution registries mirroring `plugins.py`
- [x] Pure selection logic (tail-owning final step, `clear` handling) shared
      semantically with the static viewer; 18 vitest tests green
- [x] Virtualized source pane (fixed-row windowing, click/Enter-to-seek,
      current-line tracking) + env inspector + nine trusted renderers
- [x] Keyboard stepping (←/→/Home/End), `?step=N` deep links + popstate,
      aria-live status, focus-visible outlines, reduced-motion support
- [x] `tsc --noEmit` clean, `vite build` clean, preview served +
      Edge-screenshot validated at first/last steps (visual testing caught and
      fixed: async-load screenshot timing, source auto-scroll vs
      virtualization chicken-and-egg, preview `--port` flag duplication)
- [x] Bundle `source` snapshot (`schemas/bundle-v1.json`) feeding the pane

## v0.3 definition of done (delivered)

- [x] `lectured` loopback daemon (`lecture broker`): token auth (persisted,
      0600), sessions, trace, cancellable jobs, PTY lifecycle, kernels,
      artifacts over REST; ordered event stream + PTY attach over WS
- [x] Real ConPTY/openpty backends (no pipe downgrade); process-group
      termination; output caps; wall-time kills; lifecycle-exempt budgets
- [x] Jupyter provider over the kernel protocol (execute_result/stream/error
      mapping, CAS-backed images, interrupt/shutdown) on real kernels
- [x] Shell live mode (`?live=1`): WS-streamed trace into the stage,
      xterm attached to broker PTYs, autoconnect demo flow, remote reap
- [x] 17 daemon API tests + 5 kernel tests + 6 client tests; 73 pytest green
- [x] Real-browser validation (Playwright + Edge) caught and fixed: CSP
      missing `ws:` in connect-src, pywinpty str-only write killing attach,
      stream-convergence count mismatch (now snapshot-marker based)

## v0.2+ entry criteria

- v0.2 starts when golden replay tests prove blank-client reconstruction.
- v0.3 starts when broker interfaces are frozen behind `broker/` ABCs.
- v0.7 blocks any public-untrusted deployment; `classroom` needs per-session
  containers at minimum.

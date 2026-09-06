# Roadmap — lectpy to superior interactive lecture platform

Estimates in engineer-weeks (engineering only; excludes prolonged institutional
security review / content migration). One protocol across local → Tauri → remote.

| Milestone | Deliverable | Effort | Status | Principal risk |
|---|---|---:|---|---|
| **v0.1 Protocol & compat core** | Lecture IR, event schemas, artifact IDs, edtrace-compat author layer, scoped context, tracer, CAS, static replay + tests | 3–5 | **in progress (this branch)** | Locking in wrong state model |
| **v0.2 Browser shell** | TS shell, virtualized source/trace view, keyboard nav + URL routes, inspector & renderer registries | 4–6 | planned | UI scope creep |
| **v0.3 Runtime broker** | Session supervisor, Jupyter kernels, one-shot processes, PTYs, cancellation, xterm integration | 6–8 | planned | Win PTY/process edge cases; leaks |
| **v0.4 JS/TS + live components** | Vite/esbuild pipeline, iframe sandbox, Deno/Node adapters, capability bridge | 5–7 | planned | XSS / escape / capability confusion |
| **v0.5 LSP + objects** | LSP router, virtual URIs/source maps, lazy inspectors, Arrow/binary paths | 4–6 | planned | source/runtime identity mapping |
| **v0.6 Persistence + collab** | Event log, snapshots, CAS, crash recovery, Yjs/Automerge source collab | 4–6 | planned | migration / long histories |
| **v0.7 Secure providers** | OCI provider, limits, net/file policy, optional gVisor remote profile | 7–10 | planned | host isolation / ops complexity |
| **v0.8 Packaging + hardening** | Tauri desktop, wheels/binaries, update/signing, static build, a11y + security review | 5–8 | planned | signing/update/security |
| **Total v1** | Core → deployable hardened v1 | 38–56 | — | security + x-platform execution |

Developer beta ≈ v0.1–v0.4 (≈22–32 e-w). Public multi-tenant service only after
v0.7 isolation milestone — never on "containers are probably enough".

## v0.1 definition of done (this milestone)

- [x] Plan + architecture + security + authoring docs
- [ ] `src/lecture/`: events, IR, context, SDK, sanitize, artifacts, policy,
      trace, providers/trace+process, broker (in-process), plugins registries,
      export_static, cli
- [ ] `schemas/`: event-v1, manifest-v1 JSON schemas
- [ ] `frontend/`: TS protocol types stub + static replay contract
- [ ] `examples/`: lecture_01 (basics), lecture_02 (process/plot/component stubs)
- [ ] `tests/`: protocol validation, golden replay, sanitizer adversarial,
      policy, CAS, tracer semantics, perf smoke (100k-line virtualization logic,
      1M-event seq handling, output backpressure)
- [ ] `lecture doctor` green on Win/macOS/Linux; `pytest` green; static bundle
      opens from `file://` with keyboard nav + deep-linked `?step=N`

## v0.2+ entry criteria

- v0.2 starts when golden replay tests prove blank-client reconstruction.
- v0.3 starts when broker interfaces are frozen behind `broker/` ABCs.
- v0.7 blocks any public-untrusted deployment; `classroom` needs per-session
  containers at minimum.

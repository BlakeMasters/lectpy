# Security — profiles, boundaries, checklists

Security is a **capability policy layered over isolation**, never runtime flags alone.

## Profiles (`src/lecture/policy.py`)

| Profile | Intended case | Native host exec | Active browser JS | Network |
|---|---|---|---|---|
| `static` | Published replay | None | Only prebuilt trusted renderers; sandboxed components | Denied unless asset policy permits |
| `local-trusted` | Instructor developing own lecture | Explicitly allowed | Custom components under dev policy | User-controlled |
| `local-restricted` | Opening downloaded material | Container/WASM default | iframe sandbox | Deny by default |
| `classroom` | Authenticated students | Per-session container; optional gVisor | iframe sandbox | allowlist/proxy |
| `public-untrusted` | Anonymous execution | gVisor or VM/microVM tier | strongest iframe isolation | deny/strict egress proxy |

Manifests *request*; policy/user *grants* a subset. Secrets live in broker/runtime
capabilities, never global browser state; components call narrow host
capabilities instead of receiving credentials.

## Boundaries (blocking tests before public release)

- **Browser/content:** malicious Markdown/HTML, SVG scripts, event-handler
  injection, `javascript:` URLs, iframe navigation, CSP bypass, `postMessage`
  spoofing, forged component IDs/revisions, oversized messages, cross-origin
  fetch, SW registration, clipboard/camera/mic, popup escape, Trusted Types.
- **Terminal:** lecture JS must not reach terminal DOM/model, keystrokes, or PTY
  tokens. Terminal renderer lives in privileged host-controlled origin.
- **Process:** shell-metachar injection, env leaks, PATH manipulation, cwd escape,
  inherited FDs, signals, orphans, fork bombs, Win Job Objects vs Unix pgroups,
  resize races, kill-on-disconnect.
- **Filesystem:** `..` traversal, absolute paths, symlinks/junctions, hard links,
  `/proc`, devices, tmp races, artifact path confusion. Path permissions alone
  are insufficient (symlink/FD limitations documented by Node).
- **Container:** non-root, dropped caps, no privileged, no host Docker socket
  (daemon control = host control), read-only root where feasible, explicit
  mounts, seccomp, PID/mem/CPU/nproc/storage quotas, no host networking.
- **Network:** deny egress by default for hostile code; block metadata endpoints
  + loopback/private management; authenticated port proxies; WS origin checks;
  DNS-rebinding + credential/signed-URL redaction.
- **Exhaustion:** wall/CPU/mem/nproc/nofile/stdout/event/artifact/WS/scrollback
  limits + backpressure (never unbounded buffering).
- **Supply chain:** locked deps, SBOM, verified runtime binaries, signed desktop
  updates, pinned images by digest, scans, opt-in network imports.
- **Deno/Node caveat:** Deno subprocess permission can recover broad host
  authority; Node states its permission model does not defend against malicious
  code. Both are defense-in-depth inside an OS/container boundary.

## Correctness / resilience checklist (execution fails unlike renderers)

kernel dies mid-execute; reconnect after outputs; broker crash/restart; stale
component revision; partial UTF-8; gigabyte outputs; post-cancel events; two
browsers one session; source change mid-execution; plugin schema upgrade;
snapshot/event-tail skew; env-lock mismatch; port opened before UI reconnect;
released object handles; remote partition (not clean death).

Protocol types use property-based/fuzz tests where feasible; golden histories
prove deterministic reconstruction.

## Static-profile rules (v0.1 enforced)

Static bundles contain no live sockets, no credentials, sanitized HTML only,
relative artifact links, and a recorded-fallback notice for interactive
components requiring a broker.

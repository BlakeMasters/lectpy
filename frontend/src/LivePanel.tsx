/** Live broker mode (?live=1): trace streaming + real PTY in the shell.
 *
 *  The terminal below is a genuine broker-owned ConPTY/openpty (never
 *  browser-spawned): keystrokes travel as WS input frames, screen bytes come
 *  back as output frames. Autoconnect (?live=1&token=..&entry=..) drives the
 *  whole flow hands-free for demos and screenshot validation.
 */
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef, useState } from "react";
import {
  closeSession,
  decodePtyBytes,
  fetchHealth,
  openPty,
  openSession,
  parseServerFrame,
  ptyAttachUrl,
  ptyInputFrame,
  runTrace,
  streamUrl,
  toLiveBundle,
  wsBase,
  type BrokerConfig,
} from "./broker";
import type { LectureBundle, LectureEvent } from "./protocol";
import type { LiveInitial } from "./liveParams";

export default function LivePanel({
  initial,
  onLiveBundle,
}: {
  initial: LiveInitial;
  onLiveBundle: (bundle: LectureBundle, label: string | null, cfg: BrokerConfig) => void;
}) {
  const [baseUrl, setBaseUrl] = useState(initial.baseUrl);
  const [token, setToken] = useState(initial.token);
  const [entry, setEntry] = useState(initial.entry);
  const [status, setStatus] = useState("idle");
  const [streamed, setStreamed] = useState(0);
  const [ptyId, setPtyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const termDiv = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const sessionRef = useRef<string | null>(null);
  const sessionCfg = useRef<BrokerConfig | null>(null);
  const ranRef = useRef(false);

  useEffect(() => {
    sessionStorage.setItem("lectpy.broker", baseUrl);
    sessionStorage.setItem("lectpy.token", token);
  }, [baseUrl, token]);

  // Tear down PTY + session with the panel (no orphaned runtimes).
  // Refs are read inside the cleanup so unmount sees the latest handles.
  useEffect(() => {
    return () => {
      try {
        wsRef.current?.close();
      } catch {
        /* already gone */
      }
      try {
        termRef.current?.dispose();
      } catch {
        /* already gone */
      }
      const sid = sessionRef.current;
      const cfg = sessionCfg.current;
      if (sid && cfg) {
        // Best-effort synchronous reap; the daemon also reaps on restart.
        try {
          void closeSession(cfg, sid);
        } catch {
          /* page is going away */
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connect(): Promise<BrokerConfig> {
    const cfg: BrokerConfig = { baseUrl, token };
    const health = await fetchHealth(cfg);
    if (!health.ok) throw new Error("broker unhealthy");
    if (health.ws_port == null) throw new Error("broker has no WS listener");
    return cfg;
  }

  async function runLiveTrace() {
    setError(null);
    setStatus("connecting…");
    try {
      const cfg = await connect();
      const health = await fetchHealth(cfg);
      const ws = wsBase(baseUrl, health.ws_port);
      setStatus("opening session…");
      const sid = await openSession(cfg, entry);
      sessionRef.current = sid;
      sessionCfg.current = cfg;

      // Attach the event stream BEFORE tracing so nothing is missed, then
      // build the stage bundle from streamed events. The broker closes each
      // trace with a `snapshot` marker; its arrival (not raw counts — the
      // stream also replays session_start) is the convergence signal, with
      // the synchronous POST response as the timeout fallback.
      const collected: LectureEvent[] = [];
      let sawSnapshot = false;
      await new Promise<void>((resolve, reject) => {
        const sock = new WebSocket(streamUrl(cfg, ws, sid, -1));
        const timer = window.setTimeout(() => reject(new Error("stream timeout")), 15000);
        sock.onmessage = (m) => {
          const f = parseServerFrame(String(m.data));
          if (f.type === "event") {
            collected.push(f.event);
            setStreamed(collected.length);
            if (f.event.kind === "snapshot") sawSnapshot = true;
          }
        };
        sock.onerror = () => reject(new Error("stream socket error"));
        sock.onopen = () => {
          void runTrace(cfg, sid, entry)
            .then((res) => {
              // Drain until the broker's snapshot marker or timeout.
              const t0 = Date.now();
              const tick = () => {
                const steps = collected.filter((e) => e.kind === "step").length;
                if (sawSnapshot || Date.now() - t0 > 8000) {
                  window.clearTimeout(timer);
                  try {
                    sock.close();
                  } catch {
                    /* already gone */
                  }
                  const useStreamed = sawSnapshot && steps === res.steps;
                  onLiveBundle(
                    toLiveBundle(`live: ${entry}`, useStreamed ? collected : res.events),
                    useStreamed ? `live · streamed ${collected.length}` : "live · post",
                    cfg,
                  );
                  setStatus(`traced ${res.steps} steps (${useStreamed ? "ws" : "post"})`);
                  resolve();
                } else {
                  window.setTimeout(tick, 100);
                }
              };
              tick();
            })
            .catch((e: unknown) => {
              window.clearTimeout(timer);
              reject(e instanceof Error ? e : new Error(String(e)));
            });
        };
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("failed");
    }
  }

  async function openTerminal() {
    setError(null);
    try {
      const cfg = await connect();
      const health = await fetchHealth(cfg);
      let sid = sessionRef.current;
      if (!sid) {
        sid = await openSession(cfg, entry);
        sessionRef.current = sid;
        sessionCfg.current = cfg;
      }
      const ws = wsBase(baseUrl, health.ws_port);
      const { pty_id: pid, backend } = await openPty(cfg, sid, 100, 30);
      setPtyId(`${pid} (${backend})`);
      const term = new Terminal({ cols: 100, rows: 30, scrollback: 2000 });
      termRef.current?.dispose();
      termRef.current = term;
      if (!termDiv.current) throw new Error("terminal mount missing");
      term.open(termDiv.current);
      term.focus();
      const decoder = new TextDecoder("utf-8");
      const sock = new WebSocket(ptyAttachUrl(cfg, ws, pid));
      wsRef.current = sock;
      sock.onmessage = (m) => {
        const f = parseServerFrame(String(m.data));
        if (f.type === "output") term.write(decodePtyBytes(f.data, decoder));
        if (f.type === "exit") term.writeln(`\r\n[pty exited: ${String(f.code)}]`);
      };
      sock.onerror = () => setError("pty socket error");
      term.onData((data) => {
        if (sock.readyState === WebSocket.OPEN) sock.send(ptyInputFrame(data));
      });
      sock.onopen = () => {
        if (initial.ptyCommand) sock.send(ptyInputFrame(initial.ptyCommand + "\r"));
      };
      setStatus(`pty ${pid} attached`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  // Hands-free demo / screenshot flow.
  useEffect(() => {
    if (initial.auto && token && !ranRef.current) {
      ranRef.current = true;
      void runLiveTrace().then(() => {
        void openTerminal();
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section aria-label="Live broker" className="livebar">
      <h2 className="pane-title">
        Live broker <span className="muted">sessions · stream · PTY (v0.3)</span>
      </h2>
      <div className="liverow">
        <label>
          Broker <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} size={24} />
        </label>
        <label>
          Token{" "}
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            size={20}
            autoComplete="off"
          />
        </label>
        <label>
          Entry <input value={entry} onChange={(e) => setEntry(e.target.value)} size={28} />
        </label>
        <button onClick={() => void runLiveTrace()}>Trace live</button>
        <button onClick={() => void openTerminal()}>Open terminal</button>
        <a href={window.location.pathname}>Exit live mode</a>
      </div>
      <p className="muted" role="status">
        {status}
        {streamed > 0 ? ` · ${streamed} streamed events` : ""}
        {ptyId ? ` · ${ptyId}` : ""}
      </p>
      {error ? <p role="alert">Live error: {error}</p> : null}
      <div ref={termDiv} className="term-live" aria-label="Live terminal" />
    </section>
  );
}

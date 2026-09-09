/** Small launcher stays in the shell; drawing code loads only when opened. */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import type { LectureEvent } from "./protocol";
import type { BoardState } from "../../src/lecture/static/whiteboard.js";

const BoardContext = createContext(new Map<string, BoardState>());
export function WhiteboardSession({ children }: { children: ReactNode }) {
  const states = useMemo(() => new Map<string, BoardState>(), []);
  return (
    <BoardContext.Provider value={states}>{children}</BoardContext.Provider>
  );
}
export function Whiteboard({ event }: { event: LectureEvent }) {
  const states = useContext(BoardContext);
  const key = `${event.execution_id}:${event.seq}`;
  const [state] = useState(() => {
    const existing = states.get(key) ?? {};
    states.set(key, existing);
    return existing;
  });
  const [loaded, setLoaded] = useState(!!state.open || Boolean(state.commits?.length));
  const [error, setError] = useState("");
  const host = useRef<HTMLDivElement>(null);
  const props = event.payload?.["props"] as Record<string, unknown> | undefined;
  const title =
    typeof props?.["title"] === "string" ? props.title : "whiteboard";
  useEffect(() => {
    if (!loaded) return;
    let active = true;
    let dispose: (() => void) | undefined;
    import("../../src/lecture/static/whiteboard.js")
      .then(({ mountWhiteboard }) => {
        if (active && host.current)
          dispose = mountWhiteboard(host.current, props, state);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      active = false;
      dispose?.();
    };
  }, [loaded, props, state]);
  return (
    <div className="whiteboard-host">
      {!loaded && (
        <button
          type="button"
          onClick={() => {
            state.open = true;
            setLoaded(true);
          }}
        >
          Open {title}
        </button>
      )}
      {error && <p role="alert">Whiteboard could not open: {error}</p>}
      <div ref={host} />
    </div>
  );
}

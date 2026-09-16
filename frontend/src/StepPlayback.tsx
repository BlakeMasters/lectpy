import { useEffect, useRef } from "react";
import { mountStepPlayback } from "../../src/lecture/static/step_playback.js";
import type { LectureEvent } from "./protocol";

export function StepPlayback({ event, active = false }: { event: LectureEvent; active?: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const activeRef = useRef<boolean | undefined>(undefined);
  const props = (event.payload?.["props"] ?? {}) as Record<string, unknown>;

  useEffect(() => {
    if (!host.current) return undefined;
    activeRef.current = active;
    return mountStepPlayback(host.current, props, { active });
  }, [props]);

  useEffect(() => {
    if (!host.current || activeRef.current === undefined || activeRef.current === active) return;
    activeRef.current = active;
    host.current.dispatchEvent(new CustomEvent("lectpy:step-playback-active", {
      detail: { active },
    }));
  }, [active]);

  return <div ref={host} data-output-id={String(props["output_id"] ?? "")} />;
}

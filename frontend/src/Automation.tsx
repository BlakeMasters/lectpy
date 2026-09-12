import { useEffect, useRef } from "react";
import type { LectureEvent } from "./protocol";
import { automationClient, mountAutomation } from "../../src/lecture/static/automation.js";
import type { ControlSpec } from "../../src/lecture/static/automation.js";

export default function Automation({event}: {event: LectureEvent}) {
  const host = useRef<HTMLDivElement>(null);
  const spec = event.payload?.["props"] as ControlSpec;
  useEffect(() => {
    if (host.current) return mountAutomation(host.current, spec, automationClient(event.execution_id));
  }, [event.execution_id, spec]);
  return <div ref={host} />;
}

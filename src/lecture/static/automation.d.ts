export interface ControlSpec {
  id: string;
  binding_id: string;
  target: string;
  actions: {label: string; script: string}[];
  on_enter: string;
  on_leave: string;
}
interface Event { payload?: Record<string, any> }
export function activeControlBindings(outputs: Event[], events: Event[]): ControlSpec[];
export function navigationCommands(before: ControlSpec[], after: ControlSpec[], forward: boolean): {spec: ControlSpec; action: string}[];
export class AutomationClient {
  constructor(executionId: string, base?: string, request?: typeof fetch);
  states: Record<string, any>;
  available: boolean;
  refresh(): Promise<void>;
  run(spec: ControlSpec, action: string, step: number): Promise<void>;
  navigate(before: ControlSpec[], after: ControlSpec[], from: number, to: number): void;
}
export function automationClient(executionId: string): AutomationClient;
export function mountAutomation(host: HTMLElement, spec: ControlSpec, client: AutomationClient): () => void;

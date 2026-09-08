export interface BrowserWindowProps {
  action?: "open" | "close";
  window_id?: string;
  url?: string;
  title?: string;
  width?: number;
  height?: number;
  left?: number | null;
  top?: number | null;
  resizable?: boolean;
  focus?: boolean;
}
export interface BrowserWindowSpec {
  id: string;
  url: string;
  title: string;
  width: number;
  height: number;
  left?: number;
  top?: number;
  resizable: boolean;
  focus: boolean;
}
export function browserWindowSpec(value?: BrowserWindowProps): BrowserWindowSpec;
export function browserWindowFeatures(spec: BrowserWindowSpec): string;
export function browserWindowName(id: string): string;
export class BrowserWindowController {
  constructor(hostWindow?: Window);
  get(id: string): Window | null | undefined;
  open(value: BrowserWindowProps): { ok: boolean; blocked: boolean; reused?: boolean; message: string };
  close(id: string): { ok: boolean; message: string };
  closeAll(): void;
}

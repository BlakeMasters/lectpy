import { describe, expect, it, vi } from "vitest";
import {
  BrowserWindowController,
  browserWindowFeatures,
  browserWindowSpec,
} from "../../src/lecture/static/browser_window.js";

describe("browser reference window controller", () => {
  it("normalizes geometry and builds bounded browser features", () => {
    const spec = browserWindowSpec({
      window_id: "papers", url: "https://arxiv.org/", title: "arXiv",
      width: 1024, height: 768, left: 80, top: 40, resizable: false, focus: false,
    });
    expect(spec).toMatchObject({ id: "papers", width: 1024, height: 768, left: 80, top: 40 });
    expect(browserWindowFeatures(spec)).toBe("popup=yes,width=1024,height=768,resizable=no,left=80,top=40");
    expect(browserWindowSpec({ url: "javascript:alert(1)", width: 1 }).url).toBe("");
    expect(browserWindowSpec({ url: "https://example.test/", width: 99999, height: 1 })).toMatchObject({
      width: 4096, height: 240,
    });
  });

  it("opens once per named reference, focuses reuse, and closes only owned handles", () => {
    const handle = { closed: false, focus: vi.fn(), close: vi.fn(() => { handle.closed = true; }) };
    const open = vi.fn(() => handle);
    const controller = new BrowserWindowController({ open } as unknown as Window);
    const props = { window_id: "papers", url: "https://arxiv.org/", width: 900, height: 700 };
    expect(controller.open(props)).toMatchObject({ ok: true, reused: false });
    expect(controller.open(props)).toMatchObject({ ok: true, reused: true });
    expect(open).toHaveBeenCalledTimes(1);
    expect(handle.focus).toHaveBeenCalledTimes(2);
    expect(controller.close("papers")).toMatchObject({ ok: true });
    expect(handle.close).toHaveBeenCalledTimes(1);
    expect(controller.close("papers")).toMatchObject({ ok: false });
  });

  it("reports popup blocking without leaving a phantom window", () => {
    const controller = new BrowserWindowController({ open: () => null } as unknown as Window);
    const result = controller.open({ url: "https://arxiv.org/", window_id: "papers" });
    expect(result).toMatchObject({ ok: false, blocked: true });
    expect(controller.close("papers")).toMatchObject({ ok: false });
  });
});

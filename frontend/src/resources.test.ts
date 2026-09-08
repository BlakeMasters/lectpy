import { afterEach, describe, expect, it, vi } from "vitest";
import { BlobResources, resourcePlan } from "./resources";

const hash = "a".repeat(64);
const ref = `sha256:${hash}`;
const broker = { baseUrl: "http://localhost:8766/", token: "test-token" };
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("asset resolution", () => {
  it("resolves paths against the fetched lecture, not the shell", () => {
    const env = { baseUrl: "https://example.com/courses/physics/lecture.json" };
    expect(resourcePlan("artifacts/x.svg", env).url).toBe("https://example.com/courses/physics/artifacts/x.svg");
    expect(resourcePlan("https://other.test/x.png", env).url).toBe("https://other.test/x.png");
  });
  it("prefers exported resources and sends auth only to canonical broker asset routes", () => {
    expect(resourcePlan(`artifact:${ref}`, { broker })).toEqual({
      url: `http://localhost:8766/v1/artifacts/${hash}`, token: "test-token" });
    expect(resourcePlan(`/v1/artifacts/${hash}`, { broker }).token).toBe("test-token");
    expect(resourcePlan("https://other.test/x.png", { broker }).token).toBeUndefined();
    expect(resourcePlan(`artifact:${ref}`, { broker, baseUrl: "https://example.com/nested/lecture.json",
      resources: { [ref]: { path: "artifacts/a.svg", mime: "image/svg+xml", bytes: 10 } } })).toEqual({
      url: "https://example.com/nested/artifacts/a.svg" });
    expect(resourcePlan(`artifact:${ref}`, {}).error).toMatch(/missing/);
  });
  it("coalesces active blob requests and releases memory after the last consumer", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(["svg"])));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const cache = new BlobResources();
    const a = cache.acquire("http://localhost/asset", "secret");
    const b = cache.acquire("http://localhost/asset", "secret");
    expect(await a.promise).toBe("blob:test");
    expect(await b.promise).toBe("blob:test");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer secret");
    a.release(); a.release();
    expect(revoke).not.toHaveBeenCalled();
    b.release();
    expect(revoke).toHaveBeenCalledWith("blob:test");
  });
  it("surfaces HTTP failures and aborts abandoned requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);
    const lease = new BlobResources().acquire("http://localhost/missing", "token");
    await expect(lease.promise).rejects.toThrow("404");
    lease.release();
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
  });
});

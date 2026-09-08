/** Bundle-relative URLs and authenticated live blobs, independent of live UI. */
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { LectureBundle } from "./protocol";

export interface ResourceEnvironment {
  baseUrl?: string;
  resources?: LectureBundle["resources"];
  broker?: { baseUrl: string; token: string };
}
export interface ResourcePlan { url: string; token?: string; error?: string }

export function resourcePlan(source: string, env: ResourceEnvironment): ResourcePlan {
  const canonical = /^artifact:(sha256:[0-9a-f]{64})$/.exec(source);
  const legacy = /^\/v1\/artifacts\/([0-9a-f]{64})$/.exec(source);
  const ref = canonical?.[1] ?? (legacy ? `sha256:${legacy[1]}` : undefined);
  if (ref) {
    const stored = env.resources?.[ref];
    if (stored) source = stored.path;
    else if (env.broker) {
      return { url: `${env.broker.baseUrl.replace(/\/$/, "")}/v1/artifacts/${ref.slice(7)}`,
        token: env.broker.token };
    } else return { url: "", error: "This bundle is missing the referenced asset." };
  }
  if (!source) return { url: "" };
  try {
    return { url: env.baseUrl ? new URL(source, env.baseUrl).href : source };
  } catch { return { url: "", error: "Invalid asset URL." }; }
}

interface Entry { promise: Promise<string>; count: number; controller: AbortController; url?: string }

/** Coalesce visible copies; promptly release binary memory when no view needs it. */
export class BlobResources {
  private entries = new Map<string, Entry>();
  acquire(url: string, token: string): { promise: Promise<string>; release: () => void } {
    const key = JSON.stringify([url, token]);
    let entry = this.entries.get(key);
    if (!entry) {
      const controller = new AbortController();
      const pending: Entry = { count: 0, controller, promise: Promise.resolve("") };
      pending.promise = fetch(url, { headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal }).then(async (response) => {
        if (!response.ok) throw new Error(`Asset fetch failed: ${response.status}`);
        const blob = await response.blob();
        if (controller.signal.aborted) throw new Error("Asset load cancelled");
        pending.url = URL.createObjectURL(blob);
        return pending.url;
      });
      entry = pending;
      this.entries.set(key, entry);
    }
    entry.count++;
    let released = false;
    return { promise: entry.promise, release: () => {
      if (released) return;
      released = true;
      if (--entry.count === 0) {
        entry.controller.abort();
        if (entry.url) URL.revokeObjectURL(entry.url);
        this.entries.delete(key);
      }
    } };
  }
}

const ResourceContext = createContext({ environment: {} as ResourceEnvironment,
  blobs: new BlobResources() });

export function ResourceProvider({ environment, children }: {
  environment: ResourceEnvironment; children: ReactNode;
}) {
  const blobs = useMemo(() => new BlobResources(), []);
  const value = useMemo(() => ({ environment, blobs }), [environment, blobs]);
  return <ResourceContext.Provider value={value}>{children}</ResourceContext.Provider>;
}

export function useResource(source: string): { url: string; error?: string; loading?: boolean } {
  const { environment, blobs } = useContext(ResourceContext);
  const plan = resourcePlan(source, environment);
  const key = JSON.stringify([plan.url, plan.token]);
  const [loaded, setLoaded] = useState<{ key: string; url: string; error?: string }>();
  useEffect(() => {
    if (plan.token === undefined || !plan.url) return;
    let active = true;
    const lease = blobs.acquire(plan.url, plan.token);
    lease.promise.then((url) => { if (active) setLoaded({ key, url }); },
      (error: unknown) => { if (active) setLoaded({ key, url: "",
        error: error instanceof Error ? error.message : String(error) }); });
    return () => { active = false; lease.release(); };
  }, [key, plan.url, plan.token, blobs]);
  if (plan.token === undefined) return plan;
  return loaded?.key === key ? loaded : { url: "", loading: true };
}

/** Microkernel registries for the shell — mirrors `src/lecture/plugins.py`.
 *
 *  The core knows media types, command ids and provider ids; it never knows
 *  Torch, Vega, Deno or CUDA specifics. Those live in plugins registered here.
 */
import type { ComponentType } from "react";
import type { LectureEvent } from "./protocol";

export interface RendererContribution {
  /** Event kinds this renderer handles (v0.2 dispatches on event kind;
   *  MIME-typed dispatch arrives with widget/component interop in v0.4). */
  kinds: readonly string[];
  component: ComponentType<{ event: LectureEvent }>;
  /** Trusted host UI (may live in the host DOM) vs sandboxed content. */
  trusted: boolean;
}

export interface CommandContribution {
  id: string;
  title: string;
  keybinding?: string;
  run: () => void;
}

export interface ExecutionProviderContribution {
  id: string;
  displayName: string;
}

export class RendererRegistry {
  private byKind = new Map<string, RendererContribution>();

  register(contrib: RendererContribution): void {
    for (const kind of contrib.kinds) {
      if (this.byKind.has(kind)) {
        throw new Error(`renderer already registered for ${kind}`);
      }
      this.byKind.set(kind, contrib);
    }
  }

  resolve(kind: string): RendererContribution | undefined {
    return this.byKind.get(kind);
  }

  kinds(): string[] {
    return [...this.byKind.keys()].sort();
  }
}

export class CommandRegistry {
  private commands = new Map<string, CommandContribution>();

  register(contrib: CommandContribution): void {
    if (this.commands.has(contrib.id)) {
      throw new Error(`command already registered: ${contrib.id}`);
    }
    this.commands.set(contrib.id, contrib);
  }

  get(id: string): CommandContribution | undefined {
    return this.commands.get(id);
  }

  all(): CommandContribution[] {
    return [...this.commands.values()].sort((a, b) =>
      a.id < b.id ? -1 : a.id > b.id ? 1 : 0,
    );
  }
}

export class ExecutionRegistry {
  private providers = new Map<string, ExecutionProviderContribution>();

  register(contrib: ExecutionProviderContribution): void {
    if (this.providers.has(contrib.id)) {
      throw new Error(`execution provider already registered: ${contrib.id}`);
    }
    this.providers.set(contrib.id, contrib);
  }

  get(id: string): ExecutionProviderContribution | undefined {
    return this.providers.get(id);
  }

  ids(): string[] {
    return [...this.providers.keys()].sort();
  }
}

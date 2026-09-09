import type { LectureEvent } from "./protocol";

export type SectionTone = "neutral" | "hero" | "evidence" | "code" | "recap";
export type SectionDensity = "compact" | "comfortable" | "roomy";
export type SectionWidth = "reading" | "wide" | "full";
export type SectionAlign = "start" | "center";

export interface SectionPresentation {
  name: string;
  tone: SectionTone;
  density: SectionDensity;
  width: SectionWidth;
  align: SectionAlign;
  className: string;
}

const TONES: readonly SectionTone[] = ["neutral", "hero", "evidence", "code", "recap"];
const DENSITIES: readonly SectionDensity[] = ["compact", "comfortable", "roomy"];
const WIDTHS: readonly SectionWidth[] = ["reading", "wide", "full"];
const ALIGNS: readonly SectionAlign[] = ["start", "center"];

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === "string" && allowed.includes(value as T) ? value as T : fallback;
}

/** Read presentation-only section hints without letting them affect execution. */
export function sectionPresentation(event: LectureEvent | undefined): SectionPresentation {
  const raw = event?.payload?.["presentation"];
  const value = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
  const name = typeof value["name"] === "string" ? value["name"].trim().slice(0, 80) : "";
  const tone = oneOf(value["tone"], TONES, "neutral");
  const density = oneOf(value["density"], DENSITIES, "comfortable");
  const width = oneOf(value["width"], WIDTHS, "reading");
  const align = oneOf(value["align"], ALIGNS, "start");
  return {
    name,
    tone,
    density,
    width,
    align,
    className: `section-tone-${tone} section-density-${density} section-width-${width} section-align-${align}`,
  };
}

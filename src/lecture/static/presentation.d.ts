export interface SectionPresentation {
  name: string;
  tone: "neutral" | "hero" | "evidence" | "code" | "recap";
  density: "compact" | "comfortable" | "roomy";
  width: "reading" | "wide" | "full";
  align: "start" | "center";
  font: "viewer" | "system" | "technical" | "reading";
  text_size: "normal" | "large";
  highlight: "viewer" | "amber" | "blue" | "mint" | "violet";
  focus: "line" | "wash" | "none";
  className: string;
}
export function sectionPresentation<T extends { payload?: Record<string, unknown> }>(event?: T): SectionPresentation;

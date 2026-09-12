/** Bounded presentation-only hints. Shared by both viewers, no DOM needed. */
export function sectionPresentation(event) {
  const raw = event?.payload?.presentation;
  const value = raw && typeof raw === "object" ? raw : {};
  const choices = {
    tone: ["neutral", "hero", "evidence", "code", "recap"],
    density: ["comfortable", "compact", "roomy"],
    width: ["reading", "wide", "full"],
    align: ["start", "center"],
    font: ["viewer", "system", "technical", "reading"],
    text_size: ["normal", "large"],
    highlight: ["viewer", "amber", "blue", "mint", "violet"],
    focus: ["wash", "line", "none"],
  };
  const result = {
    name: typeof value.name === "string" ? value.name.trim().slice(0, 80) : "",
  };
  const classes = [];
  for (const [key, allowed] of Object.entries(choices)) {
    result[key] = allowed.includes(value[key]) ? value[key] : allowed[0];
    classes.push(`section-${key.replaceAll("_", "-")}-${result[key]}`);
  }
  return { ...result, className: classes.join(" ") };
}

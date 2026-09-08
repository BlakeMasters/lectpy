/** Modular shell display tokens. No remote fonts or assets are required. */

export const DISPLAY_PRESETS = [
  {
    id: "system",
    label: "System",
    bodyFont: "system-ui, -apple-system, 'Segoe UI', sans-serif",
    codeFont: "ui-monospace, SFMono-Regular, Consolas, monospace",
    scale: 1,
    lineHeight: 1.55,
  },
  {
    id: "technical",
    label: "Technical",
    bodyFont: "'Segoe UI', system-ui, sans-serif",
    codeFont: "'Cascadia Code', 'SFMono-Regular', Consolas, monospace",
    scale: 0.96,
    lineHeight: 1.45,
  },
  {
    id: "reading",
    label: "Reading",
    bodyFont: "Georgia, 'Times New Roman', serif",
    codeFont: "ui-monospace, SFMono-Regular, Consolas, monospace",
    scale: 1.05,
    lineHeight: 1.7,
  },
] as const;

export type DisplayPresetId = typeof DISPLAY_PRESETS[number]["id"];
export type DisplayPreset = typeof DISPLAY_PRESETS[number];

export const HIGHLIGHT_COLORS = [
  { id: "amber", label: "Amber", value: "#d97706" },
  { id: "blue", label: "Blue", value: "#2563eb" },
  { id: "mint", label: "Mint", value: "#0f766e" },
  { id: "violet", label: "Violet", value: "#7c3aed" },
] as const;

export type HighlightColorId = typeof HIGHLIGHT_COLORS[number]["id"];

export function displayPreset(id: DisplayPresetId): DisplayPreset {
  return DISPLAY_PRESETS.find((preset) => preset.id === id) ?? DISPLAY_PRESETS[0];
}

export function highlightColor(id: HighlightColorId): string {
  return HIGHLIGHT_COLORS.find((color) => color.id === id)?.value ?? HIGHLIGHT_COLORS[0].value;
}

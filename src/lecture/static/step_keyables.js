/** Shared keyboard routing for the React shell and offline viewer. */
const STEP_KEYABLE_ACTIONS = new Set([
  "step.first", "step.previous", "step.next", "step.over", "step.last",
  "playback.play", "playback.pause", "playback.toggle", "playback.replay",
]);
const STEP_KEYABLE_MODIFIERS = {
  alt: "altKey", option: "altKey", ctrl: "ctrlKey", control: "ctrlKey",
  cmd: "metaKey", command: "metaKey", meta: "metaKey", shift: "shiftKey",
};

export function keySpecMatches(event, spec) {
  if (typeof spec !== "string" || !spec || spec.length > 64) return false;
  const parts = spec.split("+");
  const raw = parts.pop();
  const key = raw === "Space" || raw === "Spacebar" ? " " : raw;
  const actual = event.key;
  if (!key || (actual !== key && !(/^[a-z]$/i.test(key) && actual?.toLowerCase() === key.toLowerCase()))) return false;
  const modifiers = new Set();
  for (const part of parts) {
    if (!Object.prototype.hasOwnProperty.call(STEP_KEYABLE_MODIFIERS, part.toLowerCase())) return false;
    const name = STEP_KEYABLE_MODIFIERS[part.toLowerCase()];
    if (!name || modifiers.has(name)) return false;
    modifiers.add(name);
  }
  return ["altKey", "ctrlKey", "metaKey", "shiftKey"]
    .every((name) => Boolean(event[name]) === modifiers.has(name));
}

function stepBindings(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 12).filter((item) => item && typeof item === "object"
    && typeof item.key === "string" && item.key.length > 0 && item.key.length <= 64
    && STEP_KEYABLE_ACTIONS.has(item.action)
    && (item.target === undefined || typeof item.target === "string")
    && (item.prevent_default === undefined || typeof item.prevent_default === "boolean"));
}

export function activeStepKeyables(root, step, focused, reader = false) {
  const selector = reader ? "[data-step-keyables]" : ".lecture-output-current[data-step-keyables]";
  const cards = [...root.querySelectorAll(selector)];
  // A focused figure takes priority when a step or reader page has several outputs.
  const focusedCard = focused?.closest?.("[data-step-keyables]");
  if (cards.includes(focusedCard)) {
    cards.splice(cards.indexOf(focusedCard), 1);
    cards.unshift(focusedCard);
  }
  const bindings = cards.flatMap((card) => {
    try {
      const host = card.querySelector(".step-playback-host");
      return stepBindings(JSON.parse(card.getAttribute("data-step-keyables") || "[]"))
        .map((binding) => ({ ...binding, host }));
    } catch {
      return [];
    }
  });
  // Explicit output bindings override the surrounding trace-step scope.
  if (!reader) bindings.push(...stepBindings(step?.payload?.step_keyables));
  return bindings;
}

export function dispatchPlaybackAction(root, action, target = "", preferredHost) {
  const hosts = [...root.querySelectorAll(".step-playback-host")];
  const host = target
    ? hosts.find((candidate) => candidate.getAttribute("data-output-id") === target)
    : preferredHost || root.querySelector(".lecture-output-current .step-playback-host") || hosts[0];
  if (!host) return false;
  host.dispatchEvent(new CustomEvent("lectpy:step-playback-control", { detail: { action } }));
  return true;
}

export function handleStepKey(event, { root, step, reader, index, count, navigate }) {
  if (event.defaultPrevented || event.isComposing) return;
  const target = event.target;
  if (target?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role=slider],.lecture-table,.lecture-code pre')) return;
  const control = target?.closest?.('button,a,[role=button],audio,video');
  // Preserve native activation and other controls' own shortcuts.
  if (control && (!control.matches(".step-playback-button") || event.key === " " || event.key === "Enter")) return;
  const binding = activeStepKeyables(root, step, target, reader)
    .find((candidate) => (!reader || candidate.action.startsWith("playback.")) && keySpecMatches(event, candidate.key));
  if (binding) {
    if (binding.prevent_default !== false) event.preventDefault();
    if (event.repeat && ["playback.toggle", "playback.replay"].includes(binding.action)) return;
    if (binding.action.startsWith("playback.")) {
      dispatchPlaybackAction(root, binding.action, binding.target, binding.host);
    } else {
      const next = {
        "step.first": 0, "step.previous": index - 1,
        "step.next": index + 1, "step.over": index + 1, "step.last": count - 1,
      }[binding.action];
      navigate(next);
    }
    return;
  }
  if (reader || control || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: count - 1 }[event.key];
  if (typeof next === "number") {
    event.preventDefault();
    navigate(next);
  }
}

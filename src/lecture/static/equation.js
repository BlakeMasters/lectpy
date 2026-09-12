/** Small, dependency-free TeX subset renderer for static and React viewers.
 *
 * This is intentionally not a complete TeX engine. It covers the notation
 * commonly used in technical lectures and always keeps the original TeX and
 * author-provided alt text available to the host. Unknown commands become
 * readable text instead of executable markup.
 */
const SYMBOLS = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ϵ", varepsilon: "ε",
  zeta: "ζ", eta: "η", theta: "θ", vartheta: "ϑ", iota: "ι", kappa: "κ",
  lambda: "λ", mu: "μ", nu: "ν", xi: "ξ", pi: "π", varpi: "ϖ", rho: "ρ",
  sigma: "σ", varsigma: "ς", tau: "τ", upsilon: "υ", phi: "ϕ", varphi: "φ",
  chi: "χ", psi: "ψ", omega: "ω", Gamma: "Γ", Delta: "Δ", Theta: "Θ",
  Lambda: "Λ", Xi: "Ξ", Pi: "Π", Sigma: "Σ", Phi: "Φ", Psi: "Ψ", Omega: "Ω",
  nabla: "∇", partial: "∂", infty: "∞", sum: "∑", prod: "∏", int: "∫",
  oint: "∮", cdot: "⋅", times: "×", div: "÷", pm: "±", mp: "∓", le: "≤",
  leq: "≤", ge: "≥", geq: "≥", neq: "≠", ne: "≠", approx: "≈", equiv: "≡",
  in: "∈", notin: "∉", subset: "⊂", subseteq: "⊆", supset: "⊃", supseteq: "⊇",
  to: "→", rightarrow: "→", leftarrow: "←", leftrightarrow: "↔", mapsto: "↦",
  forall: "∀", exists: "∃", land: "∧", lor: "∨", neg: "¬", dots: "…",
  ldots: "…", cdots: "⋯", ell: "ℓ", Re: "ℜ", Im: "ℑ", emptyset: "∅",
};

const FUNCTIONS = new Set(["log", "ln", "exp", "sin", "cos", "tan", "min", "max", "lim"]);

function equationEscape(value) {
  return String(value).replace(/[<>&"']/g, (c) => ({
    "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;",
  })[c]);
}

function atom(value) {
  if (/^[0-9]$/.test(value)) return `<mn>${equationEscape(value)}</mn>`;
  if (/^[A-Za-z]$/.test(value)) return `<mi>${equationEscape(value)}</mi>`;
  if (value === " ") return "<mspace width=\"0.25em\"/>";
  return `<mo>${equationEscape(value)}</mo>`;
}

class TexParser {
  constructor(source) {
    this.source = source;
    this.index = 0;
    this.depth = 0;
    this.unsupported = [];
  }

  skipSpace() {
    while (/\s/.test(this.source[this.index] || "")) this.index += 1;
  }

  readCommand() {
    this.index += 1;
    if (this.index >= this.source.length) return "";
    if (/[A-Za-z]/.test(this.source[this.index])) {
      const start = this.index;
      while (/[A-Za-z]/.test(this.source[this.index] || "")) this.index += 1;
      return this.source.slice(start, this.index);
    }
    return this.source[this.index++];
  }

  readGroupText() {
    this.skipSpace();
    if (this.source[this.index] !== "{") return this.readScriptText();
    this.index += 1;
    const start = this.index;
    let depth = 1;
    while (this.index < this.source.length && depth) {
      const ch = this.source[this.index++];
      if (ch === "{") depth += 1;
      else if (ch === "}") depth -= 1;
    }
    return this.source.slice(start, depth ? this.index : this.index - 1);
  }

  readScriptText() {
    this.skipSpace();
    if (this.source[this.index] === "{") return this.readGroupText();
    if (this.source[this.index] === "\\") {
      const start = this.index;
      this.readCommand();
      return this.source.slice(start, this.index);
    }
    return this.source[this.index++] || "";
  }

  group() {
    this.skipSpace();
    if (this.source[this.index] === "{") {
      this.index += 1;
      const body = this.expression("}");
      if (this.source[this.index] === "}") this.index += 1;
      return `<mrow>${body}</mrow>`;
    }
    return this.atom(false); // Unbraced TeX arguments consume one token, not a number run.
  }

  script() {
    const source = this.readScriptText();
    if (source.startsWith("\\")) {
      const parser = new TexParser(source);
      return parser.expression("");
    }
    return this.simple(source);
  }

  simple(source) {
    if (!source) return "<mrow/>";
    if (/^(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$/.test(source)) return `<mn>${equationEscape(source)}</mn>`;
    if (/^[A-Za-z]+$/.test(source)) return `<mi>${equationEscape(source)}</mi>`;
    return `<mrow>${[...source].map(atom).join("")}</mrow>`;
  }

  decorate(base) {
    let sub = null;
    let sup = null;
    while (this.source[this.index] === "_" || this.source[this.index] === "^") {
      const marker = this.source[this.index++];
      const value = this.group();
      if (marker === "_") sub = value;
      else sup = value;
    }
    if (sub && sup) return `<msubsup>${base}${sub}${sup}</msubsup>`;
    if (sub) return `<msub>${base}${sub}</msub>`;
    if (sup) return `<msup>${base}${sup}</msup>`;
    return base;
  }

  command(name) {
    if (name === "frac" || name === "dfrac" || name === "tfrac") {
      return `<mfrac>${this.group()}${this.group()}</mfrac>`;
    }
    if (name === "sqrt") {
      this.skipSpace();
      let root = null;
      if (this.source[this.index] === "[") {
        this.index += 1;
        const start = this.index;
        while (this.index < this.source.length && this.source[this.index] !== "]") this.index += 1;
        root = this.simple(this.source.slice(start, this.index));
        if (this.source[this.index] === "]") this.index += 1;
      }
      const body = this.group();
      return root ? `<mroot>${body}${root}</mroot>` : `<msqrt>${body}</msqrt>`;
    }
    if (name === "text" || name === "operatorname") {
      return `<mtext>${equationEscape(this.readGroupText())}</mtext>`;
    }
    if (["mathrm", "mathit", "mathbf", "mathbb", "mathcal"].includes(name)) {
      const variant = { mathbb: "double-struck", mathcal: "script", mathbf: "bold", mathit: "italic" }[name] || "normal";
      return `<mstyle mathvariant="${variant}">${this.group()}</mstyle>`;
    }
    if (name === "left" || name === "right") {
      this.skipSpace();
      if (this.source[this.index] === "\\") return this.command(this.readCommand());
      if (this.source[this.index] === ".") { this.index += 1; return ""; }
      return this.source[this.index] ? atom(this.source[this.index++]) : "";
    }
    if (["{", "}", "|", "_", "%", "#", "&", "$"].includes(name)) return atom(name);
    if (name === "," || name === ";" || name === ":" || name === "!") {
      return name === "!" ? "<mspace width=\"-0.15em\"/>" : "<mspace width=\"0.2em\"/>";
    }
    if (name === "quad" || name === "qquad") {
      return `<mspace width="${name === "quad" ? 1 : 2}em"/>`;
    }
    if (Object.prototype.hasOwnProperty.call(SYMBOLS, name)) {
      const value = SYMBOLS[name];
      return /^[\u0370-\u03ffℓ]$/.test(value) ? `<mi>${value}</mi>` : `<mo>${value}</mo>`;
    }
    if (FUNCTIONS.has(name)) return `<mo>${equationEscape(name)}</mo>`;
    this.unsupported.push(name);
    return `<mtext>\\${equationEscape(name)}</mtext>`;
  }

  atom(numbers = true) {
    if (++this.depth > 64) throw new Error("Equation nesting limit exceeded");
    try {
      return this.readAtom(numbers);
    } finally {
      this.depth -= 1;
    }
  }

  readAtom(numbers) {
    this.skipSpace();
    const ch = this.source[this.index];
    if (!ch) return "";
    if (ch === "{") return this.group();
    if (ch === "\\") return this.command(this.readCommand());
    if (numbers && /[0-9.]/.test(ch)) {
      const number = this.source.slice(this.index).match(/^(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)/)?.[0];
      if (number) {
        this.index += number.length;
        return `<mn>${number}</mn>`;
      }
    }
    this.index += 1;
    return atom(ch);
  }

  expression(stop) {
    const nodes = [];
    while (this.index < this.source.length) {
      this.skipSpace();
      if (stop && this.source[this.index] === stop) break;
      if (this.source[this.index] === "^" || this.source[this.index] === "_") {
        const marker = this.source[this.index++];
        const base = nodes.pop() || "<mrow/>";
        const value = this.group();
        const next = this.source[this.index];
        if (next === "^" || next === "_") {
          this.source[this.index++];
          const second = this.group();
          const sub = marker === "_" ? value : second;
          const sup = marker === "^" ? value : second;
          nodes.push(`<msubsup>${base}${sub}${sup}</msubsup>`);
        } else {
          nodes.push(marker === "_" ? `<msub>${base}${value}</msub>` : `<msup>${base}${value}</msup>`);
        }
        continue;
      }
      nodes.push(this.atom());
    }
    return nodes.join("");
  }
}

/** Return safe MathML generated from a bounded TeX subset. */
export function texToMathML(source, { display = true, alt = "" } = {}) {
  const text = typeof source === "string" ? source.slice(0, 12000) : "";
  const parser = new TexParser(text);
  let body;
  try {
    body = parser.expression("") || `<mtext>${equationEscape(text)}</mtext>`;
  } catch {
    body = `<mtext>${equationEscape(text)}</mtext>`;
  }
  const label = alt || text || "Equation";
  return `<math xmlns="http://www.w3.org/1998/Math/MathML"${display ? ' display="block"' : ""} aria-label="${equationEscape(label)}"><mrow>${body}</mrow></math>`;
}

export function equationText(source) {
  return typeof source === "string" ? source.slice(0, 12000) : "";
}

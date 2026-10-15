// no-hardcoded-labels (TERMS-07): JSX text and string literals in the aria-label, title, placeholder
// and label props must not carry a default dictionary text (ITP, NCR, Variation ...); use t(key).
//
// The deny-list is read from config/terms/en-AU/*.json when linting starts and follows the Python
// scanner (apps/api/aip/modules/terms/lint.py): whole words; a text in capitals matches
// case-sensitively, any other text case-insensitively; texts with ICU arguments are skipped; where
// two texts overlap the longer one wins; the suggested key is the first key (sorted) for the text.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const DEFAULT_DICTIONARY = fileURLToPath(new URL("../../../config/terms/en-AU/", import.meta.url));
export const LABEL_PROPS = new Set(["aria-label", "title", "placeholder", "label"]);

const ABBREVIATION = /^[A-Z0-9&/-]*[A-Z][A-Z0-9&/-]*$/;
const cache = new Map();

function escape(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** `[{ text, key, regex }]`, longest text first. */
export function loadDenyList(dictionaryDir = DEFAULT_DICTIONARY) {
  const cached = cache.get(dictionaryDir);
  if (cached) return cached;
  const pairs = [];
  for (const name of readdirSync(dictionaryDir).filter((n) => n.endsWith(".json")).sort()) {
    const raw = JSON.parse(readFileSync(path.join(dictionaryDir, name), "utf8"));
    for (const [key, value] of Object.entries(raw)) {
      const message = typeof value === "string" ? value : value?.text;
      if (typeof message !== "string") continue;
      const text = message.split(/\s+/).filter(Boolean).join(" ");
      if (text && !text.includes("{")) pairs.push([key, text]);
    }
  }
  pairs.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  const byText = new Map();
  for (const [key, text] of pairs) if (!byText.has(text)) byText.set(text, key);
  const terms = [...byText].map(([text, key]) => {
    const body = text.split(" ").map(escape).join("\\s+");
    const flags = ABBREVIATION.test(text) ? "gu" : "giu";
    return { text, key, regex: new RegExp(`(?<![\\p{L}\\p{N}_])${body}(?![\\p{L}\\p{N}_])`, flags) };
  });
  terms.sort((a, b) => b.text.length - a.text.length || (a.text < b.text ? -1 : 1));
  cache.set(dictionaryDir, terms);
  return terms;
}

/** `[{ offset, term }]` for each non-overlapping match in `text`, in order. */
export function findTerms(text, terms) {
  const claimed = [];
  const hits = [];
  for (const term of terms) {
    for (const match of text.matchAll(term.regex)) {
      const start = match.index;
      const end = start + match[0].length;
      if (claimed.some(([s, e]) => start < e && s < end)) continue;
      claimed.push([start, end]);
      hits.push({ offset: start, term });
    }
  }
  return hits.sort((a, b) => a.offset - b.offset);
}

/** The string a label prop holds when it is a plain literal, else null. */
function propString(value) {
  if (!value) return null;
  if (value.type === "Literal") return typeof value.value === "string" ? value.value : null;
  if (value.type !== "JSXExpressionContainer") return null;
  const expression = value.expression;
  if (expression.type === "Literal" && typeof expression.value === "string") return expression.value;
  if (expression.type === "TemplateLiteral" && expression.expressions.length === 0) {
    return expression.quasis[0].value.cooked ?? null;
  }
  return null;
}

/** @type {import("eslint").Rule.RuleModule} */
export default {
  meta: {
    type: "problem",
    docs: { description: "Disallow default dictionary texts as literal UI labels (TERMS-07)" },
    schema: [
      {
        type: "object",
        properties: { dictionary: { type: "string" } },
        additionalProperties: false,
      },
    ],
    messages: {
      hardcoded: 'Hard-coded label "{{term}}": use t("{{key}}") (TERMS-07).',
    },
  },
  create(context) {
    const terms = loadDenyList(context.options[0]?.dictionary ?? DEFAULT_DICTIONARY);
    function check(node, text) {
      for (const { term } of findTerms(text, terms)) {
        context.report({ node, messageId: "hardcoded", data: { term: term.text, key: term.key } });
      }
    }
    return {
      JSXText(node) {
        check(node, node.value);
      },
      JSXAttribute(node) {
        if (node.name.type !== "JSXIdentifier" || !LABEL_PROPS.has(node.name.name)) return;
        const text = propString(node.value);
        if (text !== null) check(node.value, text);
      },
    };
  },
};

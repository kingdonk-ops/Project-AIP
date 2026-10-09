/** Accepts a post-login `next` target only when it is a same-origin relative path; otherwise `/`. */
export function safeNext(next: unknown): string {
  if (typeof next !== "string" || next.length === 0) return "/";
  // One leading slash; no `//` or `/\` (protocol-relative), no scheme, no backslashes or control characters.
  if (!next.startsWith("/") || next.startsWith("//")) return "/";
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f\\]/.test(next)) return "/";
  return next;
}

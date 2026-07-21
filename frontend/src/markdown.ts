import MarkdownIt from "markdown-it";

// `html: false` makes markdown-it escape literal `<...>` in the source instead of passing it
// through as executable HTML — notes/promo text comes from providers we don't control.
const md = new MarkdownIt({ html: false, linkify: true });

export function renderNoteMarkdown(text: string): string {
  return md.renderInline(text);
}

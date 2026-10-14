import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ts from "typescript";

const require = createRequire(import.meta.url);
const cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const output = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  cache.set(relative, exports);
  new Function("exports", "require", output)(exports, specifier => {
    if (specifier.startsWith("@/")) return load(specifier.slice(2));
    if (specifier === "react-markdown") return { default: ReactMarkdown };
    if (specifier === "remark-gfm") return { default: remarkGfm };
    return require(specifier);
  });
  return exports;
}
const { buildCitationPanel, prioritizeSourceGroups, sourceKey } = load("lib/chat/citation-panel");
const { rehypeCitationMarkers } = load("lib/chat/citation-markdown");
const { CitationMarker, CitationContent, SourceGroups } = load("components/chat/citation-content");
const { historyMessageToViewMessage } = load("lib/sessions/history");
const { ChatMessage } = load("components/chat/chat-message");
const id = n => `${n.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`;
const source = (n, overrides = {}) => ({ document_id: id(10), version_id: id(20), chunk_id: id(n),
  file_name: "guide.pdf", page: n - 1, chunk_index: 300 + n, ...overrides });
const message = (overrides = {}) => ({ key: "session-a:assistant-a", messageId: id(100), requestId: id(200),
  role: "assistant", content: "Nội dung [1] và [2] [1]", status: "COMPLETED", model: null,
  sources: [source(1), source(2)], citations: [], usage: null, error: null, ...overrides });
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));

test("click callbacks select exact source from the correct assistant even when ordinals repeat", () => {
  const selected = [];
  for (const current of [message(), message({ key: "session-b:assistant-b", sources: [source(9)] })]) {
    const button = CitationMarker({ message: current, ordinal: 1, marker: "[1]", onSelect: value => selected.push(value) });
    button.props.onClick();
  }
  assert.deepEqual(selected.map(s => s.chunk_id), [id(1), id(9)]);
  assert.deepEqual(selected.map(s => s.ordinal), [1, 1]);
});

test("parsed Markdown keeps citations in bold, lists, quotes and GFM tables, but code/links stay intact", () => {
  const text = "**bold [1]**\n\n- item [2]\n\n> quote [1]\n\n| column |\n| --- |\n| cell [2] |\n\n`[1]`\n\n```txt\n[2]\n```\n\n[link [1]](https://example.test)";
  const html = render(ReactMarkdown, { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeCitationMarkers], children: text });
  assert.equal((html.match(/data-citation-ordinal=/g) ?? []).length, 4);
  assert.match(html, /<strong>bold <button/);
  assert.match(html, /<li>item <button/);
  assert.match(html, /<blockquote>/);
  assert.match(html, /<table>/);
  assert.match(html, /<code>\[1\]<\/code>/);
  assert.match(html, /<pre><code class="language-txt">\[2\]/);
  assert.match(html, /<a href="https:\/\/example.test">link \[1\]<\/a>/);
});

test("production CitationContent renders labelled citation buttons and unavailable markers without fake links", () => {
  const html = render(CitationContent, { message: message({ content: "[1] [99] [0]" }) });
  assert.match(html, /aria-label="Xem nguồn \[1\]: guide.pdf"/);
  assert.match(html, /\[99\]: Không xác định được nguồn/);
  assert.match(html, /\[0\]: Không xác định được nguồn/);
  assert.match(html, /Nguồn của câu trả lời \(1\)/);
  assert(!html.includes("href="));
});

test("group by document/version/file and raw page; selected source comes first with correct PDF display page", () => {
  const current = message({ content: "[1] [2] [3] [4]", sources: [source(1), source(2),
    source(3, { page: 0 }), source(4, { version_id: id(21), page: 0 })] });
  const panel = buildCitationPanel(current);
  assert.equal(panel.groups.length, 2);
  assert.equal(panel.groups[0].pages.length, 2);
  assert.equal(panel.groups[0].pages[0].sources.length, 2);
  const target = panel.sources[1];
  const reordered = prioritizeSourceGroups(panel.groups, target.key);
  assert.equal(reordered[0].pages[0].sources[0].chunk_id, id(2));
  assert.equal(reordered[0].pages[0].label, "Trang 2");
  const html = render(SourceGroups, { groups: reordered, selectedKey: target.key });
  assert.match(html, /data-selected="true"/);
  assert.match(html, /Đang xem/);
  assert(html.includes(id(2)));
  assert.equal(panel.groups[0].pages[0].label, "Trang 1");
});

test("history survives DTO restoration with persisted citations and explicit missing ordinal mapping", () => {
  const citation = source(5, { page: 2 });
  const restored = historyMessageToViewMessage({ message_id: id(100), session_id: id(11), sequence: 2,
    role: "ASSISTANT", content: "Saved [3]", status: "COMPLETED", citations: [citation],
    model: null, usage: null, request_id: id(200), error_code: null });
  const panel = buildCitationPanel(restored);
  assert.equal(panel.sources[0].ordinal, null);
  assert.equal(panel.sources[0].chunk_id, id(5));
  assert.equal(panel.groups[0].pages[0].label, "Trang 3");
  const html = render(CitationContent, { message: restored });
  assert.match(html, /Thiếu thông tin nguồn cho trích dẫn này/);
  assert.match(html, /Nguồn của câu trả lời \(1\)/);
  assert(!html.includes("Xem nguồn [3]"));
  const drawer = render(SourceGroups, { groups: panel.groups, selectedKey: null });
  assert.match(drawer, /Trích dẫn đã lưu/);
  assert(drawer.includes(id(5)));
});

test("when ordered metadata is present after restoration citations resolve as usual", () => {
  const restored = message({ key: "history:assistant", sources: [source(8)], content: "[1]" });
  const html = render(CitationContent, { message: restored });
  assert.match(html, /Xem nguồn \[1\]: guide.pdf/);
  assert.equal(buildCitationPanel(restored).sources[0].chunk_id, id(8));
});

test("history and live sources deduplicate identities without stealing an ordinal from another message", () => {
  const current = message({ citations: [source(1), source(9)] });
  const panel = buildCitationPanel(current);
  assert.equal(panel.sources.length, 3);
  assert.equal(panel.sources.at(-1).ordinal, null);
  assert.equal(panel.sources.at(-1).key, sourceKey(source(9)));
  const missing = CitationMarker({ message: message({ sources: [] }), ordinal: 1, marker: "[1]", onSelect: () => assert.fail() });
  assert.equal(missing.type, "span");
  assert.equal(missing.props.onClick, undefined);
});

test("empty history fallback preserves original marker text and exposes no source URL", () => {
  const html = render(CitationContent, { message: message({ sources: [], content: "Text [1]", citations: [] }) });
  assert.match(html, /Text <span/);
  assert.match(html, />\[1\]<\/span>/);
  assert.match(html, /Nguồn của câu trả lời \(0\)/);
  assert(!html.includes("href="));
});

test("ChatMessage integrates citation content only for assistant bubbles", () => {
  const assistant = render(ChatMessage, { message: message({ content: "Answer [1]" }) });
  assert.match(assistant, /Xem nguồn \[1\]: guide.pdf/);
  const user = render(ChatMessage, { message: message({ role: "user", content: "Question [1]" }) });
  assert.match(user, /Question \[1\]/);
  assert(!user.includes("Xem nguồn"));
});

test("partial streaming marker stays textual then resolves on completion without changing content", () => {
  const partial = message({ content: "Delta [1", status: "STREAMING" });
  assert.match(render(CitationContent, { message: partial }), /Delta \[1/);
  const completed = { ...partial, content: partial.content + "]", status: "COMPLETED" };
  assert.match(render(CitationContent, { message: completed }), /Xem nguồn \[1\]: guide.pdf/);
  assert.equal(partial.content, "Delta [1");
  assert.equal(completed.content, "Delta [1]");
});

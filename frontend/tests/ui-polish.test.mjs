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
    // This handler-only harness calls the component directly; attachment state is covered in browser tests.
    if (relative === "components/chat/chat-composer" && specifier === "react") return { ...React, useRef: initial => ({ current: initial }), useEffect() {} };
    if (relative === "components/chat/chat-composer" && specifier === "@/hooks/use-chat-attachments") return {
      useChatAttachments: () => ({ attachments: [], choose() {}, remove() {}, capture: () => [], clearSubmitted: () => true }),
    };
    if (specifier.startsWith("@/")) return load(specifier.slice(2));
    if (specifier === "react-markdown") return { default: ReactMarkdown };
    if (specifier === "remark-gfm") return { default: remarkGfm };
    return require(specifier);
  });
  return exports;
}
const { ChatScrollController } = load("lib/chat/scroll");
const { copyText } = load("lib/chat/clipboard");
const { CitationContent } = load("components/chat/citation-content");
const { ChatComposer } = load("components/chat/chat-composer");
const { LoadingSkeleton } = load("components/layout/loading-skeleton");
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));

test("stream growth follows bottom but never moves reader away from older messages; jump resumes", () => {
  const scroll = new ChatScrollController();
  const viewport = { scrollTop: 0, scrollHeight: 1000, clientHeight: 300 };
  const detach = scroll.attach(viewport);
  assert.equal(viewport.scrollTop, 700);
  viewport.scrollHeight = 1200;
  scroll.contentChanged();
  assert.equal(viewport.scrollTop, 900);
  viewport.scrollTop = 100;
  scroll.onScroll();
  viewport.scrollHeight = 1500;
  scroll.contentChanged();
  assert.equal(viewport.scrollTop, 100);
  assert.equal(scroll.getSnapshot(), true);
  scroll.jump();
  assert.equal(viewport.scrollTop, 1200);
  assert.equal(scroll.getSnapshot(), false);
  detach();
  viewport.scrollHeight = 2000;
  scroll.contentChanged();
  assert.equal(viewport.scrollTop, 1200);
});

test("returning to bottom clears unread; viewport resize follows only when following", () => {
  const scroll = new ChatScrollController();
  const viewport = { scrollTop: 0, scrollHeight: 1000, clientHeight: 300 };
  scroll.attach(viewport);
  viewport.scrollTop = 0; scroll.onScroll(); scroll.contentChanged();
  viewport.scrollTop = 699; scroll.onScroll();
  assert.equal(scroll.getSnapshot(), false);
  viewport.clientHeight = 200; scroll.contentChanged();
  assert.equal(viewport.scrollTop, 800);
  viewport.scrollTop = 0; scroll.onScroll();
  viewport.clientHeight = 500; scroll.contentChanged();
  assert.equal(viewport.scrollTop, 0);
});

test("copy preserves exact whitespace and rejects unavailable or denied clipboard", async () => {
  const text = "  line\n\tcode\n\n";
  let actual;
  await copyText(text, { writeText: async value => { actual = value; } });
  assert.equal(actual, text);
  await assert.rejects(copyText(text));
  await assert.rejects(copyText(text, { writeText: async () => { throw new Error("denied"); } }));
});

test("production Markdown renders bounded code/table regions, copy and safe links without losing citations", () => {
  const html = render(CitationContent, { message: { key: "a", content: "# Title\n\n```js\n  const x = '[1]';\n```\n\n| A |\n| --- |\n| long |\n\n[website](https://example.test)\n\n<script>alert(1)</script>", sources: [], citations: [] } });
  assert.match(html, /<h3/);
  assert.match(html, /aria-label="Sao chép code"/);
  assert.match(html, /aria-label="Nội dung code"/);
  assert.match(html, /  const x = &#x27;\[1\]&#x27;;\n/);
  assert.match(html, /aria-label="Bảng trong câu trả lời"/);
  assert.match(html, /mở tab mới/);
  assert(!html.includes("<script>"));
  assert(!html.includes("Xem nguồn [1]"));
});

test("composer supports Enter, Shift+Enter, IME, empty guard and keyboard Stop while read-only", () => {
  let submitted = 0, stopped = 0, prevented = 0;
  const props = { value: "question", onChange: () => {}, onSubmit: () => submitted++, onStop: () => stopped++ };
  const form = ChatComposer(props);
  const field = form.props.children.props.children.find(child => child?.props?.onKeyDown);
  const key = (shiftKey, isComposing) => field.props.onKeyDown({ key: "Enter", shiftKey, nativeEvent: { isComposing }, preventDefault: () => prevented++ });
  key(true, false); key(false, true);
  assert.equal(submitted, 0);
  key(false, false);
  assert.equal(submitted, 1); assert.equal(prevented, 1);
  const generating = ChatComposer({ ...props, disabled: true, isGenerating: true });
  const generatingField = generating.props.children.props.children.find(child => child?.props?.onKeyDown);
  assert.equal(generatingField.props.readOnly, true);
  assert.equal(generatingField.props.disabled, undefined);
  const stop = generating.props.children.props.children.at(-1).props.children.at(-1);
  assert.equal(stop.props.disabled, false);
  stop.props.onClick({ preventDefault: () => prevented++ }); assert.equal(stopped, 1);
  assert.equal(prevented, 2, "Stop prevents a default submit when the control changes back to Send");
  ChatComposer({ ...props, value: "   " }).props.onSubmit({ preventDefault() {} });
  assert.equal(submitted, 1);
});

test("skeletons are hidden from assistive technology and respect reduced motion", () => {
  const html = render(LoadingSkeleton);
  assert.match(html, /aria-hidden="true"/);
  assert.match(html, /motion-reduce:animate-none/);
});

"use client"

import type { Element, RootContent } from "hast"
import { CopyButton } from "@/components/chat/copy-button"

export function codeText(node: RootContent): string {
  return node.type === "text" ? node.value : "children" in node ? node.children.map(codeText).join("") : ""
}

export function CodeBlock({ node }: { node: Element }) {
  const code = node.children.find(child => child.type === "element" && child.tagName === "code")
  const classes = code?.type === "element" ? code.properties.className : []
  const language = Array.isArray(classes) ? classes.find(value => String(value).startsWith("language-")) : null
  const text = codeText(node)
  return <div className="my-3 min-w-0 overflow-hidden rounded-lg border bg-muted">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-1">
      <span className="font-mono text-xs">{language ? String(language).slice(9) : "Code"}</span>
      <CopyButton text={text} label="Sao chép code" />
    </div>
    <pre tabIndex={0} aria-label="Nội dung code" className="max-w-full overflow-x-auto p-3 text-xs focus-visible:outline-2 focus-visible:outline-ring"><code>{text}</code></pre>
  </div>
}

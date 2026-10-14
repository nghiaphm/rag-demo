import type { Element, Root, RootContent, Text } from "hast";

/** Transform parsed Markdown text only; skip links, code, HTML and images. */
export function rehypeCitationMarkers() {
  return (tree: Root) => {
    function walk(parent: Root | Element) {
      if (parent.type === "element" && ["a", "code", "pre", "script", "style", "button"].includes(parent.tagName)) return;
      const children: RootContent[] = [];
      for (const child of parent.children) {
        if (child.type === "text") {
          let offset = 0;
          for (const match of child.value.matchAll(/\[(\d+)\]/g)) {
            if (match.index > offset) children.push({ type: "text", value: child.value.slice(offset, match.index) });
            children.push({ type: "element", tagName: "button",
              properties: { type: "button", dataCitationOrdinal: match[1] },
              children: [{ type: "text", value: match[0] } as Text] });
            offset = match.index + match[0].length;
          }
          if (offset < child.value.length) children.push({ type: "text", value: child.value.slice(offset) });
        } else {
          if (child.type === "element") walk(child);
          children.push(child);
        }
      }
      parent.children = children as typeof parent.children;
    }
    walk(tree);
  };
}

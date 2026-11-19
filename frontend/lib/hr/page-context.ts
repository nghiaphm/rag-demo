import type { Element, Root, RootContent, Text } from "hast";

import { HR_ANALYTICS_FIXTURE } from "@/fixtures/hr-analytics";
import { HR_GUIDE_SECTIONS, HR_PROMPT_TEMPLATES } from "@/fixtures/hr-guide";
import {
  HR_DOCUMENT_CATEGORIES,
  getHrCategoryLabel,
} from "@/lib/hr/document-categories";
import type { ChatUiContext } from "@/types/chat";
import type { HrPageContext, HrPageRoute } from "@/types/hr";

export interface HrNavigationSuggestion {
  route: HrPageRoute;
  title: string;
  description: string;
}

export interface HrRouteManifestEntry {
  route: HrPageRoute;
  title: string;
  navLabel: string;
  exact?: boolean;
  shortDescription: string;
  purpose: string;
  buildDefaultFeatures: () => readonly string[];
}

export interface HrPageContextDefinition {
  route: HrPageRoute;
  title: string;
  navLabel: string;
  exact?: boolean;
  shortDescription: string;
  purpose: string;
  availableFeatures: readonly string[];
  relatedPages: readonly HrNavigationSuggestion[];
}

function buildDashboardDefaultFeatures(): readonly string[] {
  const kpiSummary = HR_ANALYTICS_FIXTURE.kpis
    .map((item) => `${item.label} (${item.value})`)
    .join(", ");
  return [
    `Theo dõi ${HR_ANALYTICS_FIXTURE.kpis.length} chỉ số KPI nhân sự (${kpiSummary}).`,
    `Phân tích biểu đồ cơ cấu ${HR_ANALYTICS_FIXTURE.departments.length} phòng ban và ${HR_ANALYTICS_FIXTURE.contractStatuses.length} nhóm trạng thái hợp đồng (${HR_ANALYTICS_FIXTURE.asOfLabel}).`,
    "Theo dõi khối Kho tri thức RAG (Dữ liệu thực từ GET /documents): tổng tài liệu, tài liệu INDEXED, đang xử lý và tổng vector chunks.",
  ];
}

function buildDocumentsDefaultFeatures(): readonly string[] {
  const categories = ["Tất cả", ...HR_DOCUMENT_CATEGORIES.map((item) => item.label)].join(", ");
  return [
    `Lọc tài liệu theo nhóm phân loại tự động từ tên file (${categories}) và tìm kiếm nhanh theo từ khóa.`,
    "Làm mới danh sách, chọn tài liệu để xem trạng thái, số chunks, ngày cập nhật và đọc nội dung xem trước (TXT, MD, XLSX; PDF hỗ trợ ingest và hỏi đáp trích dẫn).",
    "Tải tài liệu mới (.pdf, .txt, .md, .markdown, .xlsx) trực tiếp vào kho tri thức RAG dùng chung và mở Trợ lý HR gắn ngữ cảnh tài liệu đang chọn.",
  ];
}

function buildGuideDefaultFeatures(): readonly string[] {
  const sectionTitles = HR_GUIDE_SECTIONS.map((section) => section.title).join(", ");
  return [
    `Tra cứu ${HR_GUIDE_SECTIONS.length} chuyên mục hướng dẫn thực hành (${sectionTitles}).`,
    `Chọn Thử câu hỏi này trên ${HR_PROMPT_TEMPLATES.length} mẫu câu hỏi nghiệp vụ để mở ngay Trợ lý HR với câu hỏi điền sẵn.`,
    "Khởi chạy Interactive Product Tour theo từng phân hệ (Tour Dashboard, Tour Tài liệu, Tour Trợ lý HR).",
  ];
}

/**
 * Single Source of Truth cho toàn bộ định tuyến, nhãn điều hướng và metadata ngữ cảnh cơ sở của HR Portal.
 * Khi bổ sung trang HR mới (ví dụ `/hr/analytics`), chỉ cần khai báo thêm 1 entry tại đây.
 */
export const HR_ROUTE_MANIFEST: Record<HrPageRoute, HrRouteManifestEntry> = {
  "/hr": {
    route: "/hr",
    title: "Tổng quan nhân sự",
    navLabel: "Tổng quan HR",
    exact: true,
    shortDescription:
      "Xem chỉ số KPI nhân sự, biểu đồ phòng ban/hợp đồng và thống kê Kho tri thức RAG theo thời gian thực.",
    purpose:
      "Tổng hợp bảng điều khiển KPI nhân sự, biểu đồ cơ cấu phòng ban và loại hợp đồng kết hợp trạng thái Kho tri thức RAG thực tế từ GET /documents.",
    buildDefaultFeatures: buildDashboardDefaultFeatures,
  },
  "/hr/documents": {
    route: "/hr/documents",
    title: "Tài liệu nhân sự",
    navLabel: "Tài liệu nhân sự",
    shortDescription:
      "Tìm kiếm, lọc nhóm chính sách/quy định/quy trình, xem trước nội dung và tải tài liệu mới vào kho RAG.",
    purpose:
      "Tra cứu, phân nhóm hiển thị tài liệu nhân sự, xem trước nội dung (TXT, MD, XLSX) và tải tài liệu mới lên kho tri thức RAG dùng chung với /documents.",
    buildDefaultFeatures: buildDocumentsDefaultFeatures,
  },
  "/hr/guide": {
    route: "/hr/guide",
    title: "Hướng dẫn sử dụng",
    navLabel: "Hướng dẫn sử dụng",
    shortDescription:
      "Xem hướng dẫn khai thác HR Portal, chạy Interactive Product Tour và thử bộ câu hỏi mẫu với Trợ lý HR.",
    purpose:
      "Cung cấp cẩm nang khai thác HR Portal, bộ khởi chạy Interactive Product Tour theo phân hệ và danh sách câu hỏi mẫu để thử trực tiếp với Trợ lý HR.",
    buildDefaultFeatures: buildGuideDefaultFeatures,
  },
};

export const ALLOWED_HR_ROUTES: readonly HrPageRoute[] = Object.freeze(
  Object.keys(HR_ROUTE_MANIFEST) as HrPageRoute[],
);

const SORTED_HR_ROUTES_BY_LENGTH: readonly HrPageRoute[] = Object.freeze(
  [...ALLOWED_HR_ROUTES].sort((left, right) => right.length - left.length),
);

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const HR_ROUTE_ALTERNATION = SORTED_HR_ROUTES_BY_LENGTH.map(escapeRegExp).join("|");

export function deriveRelatedHrPages(currentRoute: HrPageRoute): readonly HrNavigationSuggestion[] {
  return ALLOWED_HR_ROUTES.filter((route) => route !== currentRoute).map((route) => {
    const entry = HR_ROUTE_MANIFEST[route];
    return {
      route: entry.route,
      title: entry.title,
      description: entry.shortDescription,
    };
  });
}

export const HR_PAGE_CONTEXT_REGISTRY: Record<HrPageRoute, HrPageContextDefinition> =
  Object.freeze(
    Object.fromEntries(
      ALLOWED_HR_ROUTES.map((route) => {
        const entry = HR_ROUTE_MANIFEST[route];
        const definition: HrPageContextDefinition = {
          route: entry.route,
          title: entry.title,
          navLabel: entry.navLabel,
          exact: entry.exact,
          shortDescription: entry.shortDescription,
          purpose: entry.purpose,
          availableFeatures: entry.buildDefaultFeatures(),
          relatedPages: deriveRelatedHrPages(route),
        };
        return [route, definition];
      }),
    ) as Record<HrPageRoute, HrPageContextDefinition>,
  );

export function isSafeHrRoute(value: string): value is HrPageRoute {
  return (ALLOWED_HR_ROUTES as readonly string[]).includes(value);
}

export function matchesHrRoute(
  pathname: string,
  href: HrPageRoute,
  exact = Boolean(HR_ROUTE_MANIFEST[href]?.exact),
): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function resolveHrRouteFromPathname(pathname?: string | null): HrPageRoute {
  if (!pathname) return "/hr";
  for (const route of SORTED_HR_ROUTES_BY_LENGTH) {
    if (matchesHrRoute(pathname, route, HR_ROUTE_MANIFEST[route].exact)) {
      return route;
    }
  }
  return "/hr";
}

export function getHrRouteDisplayTitle(route: HrPageRoute): string {
  return HR_ROUTE_MANIFEST[route].title;
}

export function getHrRouteTitle(pathname?: string | null): string {
  return getHrRouteDisplayTitle(resolveHrRouteFromPathname(pathname));
}

export interface HrFeatureDomNodeLike {
  getAttribute(name: string): string | null;
}

export interface HrFeatureDomRootLike {
  querySelectorAll?(selector: string): Iterable<HrFeatureDomNodeLike>;
}

/**
 * Quét các vùng giao diện đang hiển thị thực tế trên DOM có gắn `data-hr-feature="..."`
 * để bổ sung ngữ cảnh sống (Live DOM Introspection) mà không cần hardcode trong registry.
 */
export function collectVisibleHrDomFeatures(
  domRoot?: HrFeatureDomRootLike | null,
): string[] {
  const root: HrFeatureDomRootLike | null =
    domRoot !== undefined
      ? domRoot
      : typeof document !== "undefined"
        ? (document as unknown as HrFeatureDomRootLike)
        : null;
  if (!root || typeof root.querySelectorAll !== "function") {
    return [];
  }

  const seen = new Set<string>();
  const collected: string[] = [];
  for (const node of root.querySelectorAll("[data-hr-feature]")) {
    const raw = node.getAttribute("data-hr-feature")?.trim();
    if (!raw || seen.has(raw)) continue;
    seen.add(raw);
    collected.push(raw);
  }
  return collected;
}

function mergeDistinctFeatures(...groups: readonly (readonly string[] | undefined)[]): string[] {
  const seen = new Set<string>();
  const merged: string[] = [];
  for (const group of groups) {
    if (!group) continue;
    for (const item of group) {
      const normalized = item.trim();
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      merged.push(normalized);
    }
  }
  return merged;
}

export function buildHrUiContext(
  pageContext: HrPageContext | null,
  pathname?: string | null,
  domRoot?: HrFeatureDomRootLike | null,
): ChatUiContext {
  const resolvedRoute =
    pageContext?.route && isSafeHrRoute(pageContext.route)
      ? pageContext.route
      : resolveHrRouteFromPathname(pathname);
  const definition = HR_PAGE_CONTEXT_REGISTRY[resolvedRoute];
  const domFeatures = collectVisibleHrDomFeatures(domRoot);
  const searchFeature =
    pageContext?.searchQuery && pageContext.searchQuery.trim()
      ? [`Từ khóa tìm kiếm đang áp dụng trên trang: "${pageContext.searchQuery.trim()}".`]
      : [];

  return {
    portal: "hr",
    route: definition.route,
    page_title: pageContext?.title?.trim() || definition.title,
    page_purpose: pageContext?.purpose?.trim() || definition.purpose,
    available_features: mergeDistinctFeatures(
      pageContext?.liveFeatures,
      searchFeature,
      domFeatures,
      definition.availableFeatures,
    ),
    related_pages: definition.relatedPages.map((page) => ({
      route: page.route,
      title: page.title,
      description: page.description,
    })),
    ...(pageContext?.selectedDocumentName
      ? { selected_document_name: pageContext.selectedDocumentName }
      : {}),
    ...(pageContext?.selectedCategory
      ? { selected_category: getHrCategoryLabel(pageContext.selectedCategory) }
      : {}),
  };
}

const HR_ROUTE_MENTION_PATTERN = new RegExp(
  `(?<![a-zA-Z0-9_/-])(${HR_ROUTE_ALTERNATION})(?![a-zA-Z0-9_/-])`,
  "g",
);

/**
 * Extract only whitelisted HR Portal navigation targets mentioned in assistant responses.
 * Rejects arbitrary URLs and ignores the active route so users choose valid next pages.
 */
export function extractHrNavigationSuggestions(
  content: string,
  currentRoute?: HrPageRoute | null,
): HrNavigationSuggestion[] {
  if (!content.trim()) return [];

  const seen = new Set<HrPageRoute>();
  const suggestions: HrNavigationSuggestion[] = [];

  for (const match of content.matchAll(HR_ROUTE_MENTION_PATTERN)) {
    const candidate = match[1];
    if (!candidate || !isSafeHrRoute(candidate)) continue;
    if (currentRoute && candidate === currentRoute) continue;
    if (seen.has(candidate)) continue;

    seen.add(candidate);
    const meta = HR_ROUTE_MANIFEST[candidate];
    suggestions.push({
      route: meta.route,
      title: meta.title,
      description: meta.shortDescription,
    });
  }

  return suggestions;
}

const HR_INLINE_ROUTE_PATTERN = new RegExp(
  `(^|[^a-zA-Z0-9_/:.-])(${HR_ROUTE_ALTERNATION})(?=$|[^a-zA-Z0-9_/-])`,
  "g",
);

function extractPlainText(node: Element): string | null {
  if (node.children.length !== 1) return null;
  const only = node.children[0];
  return only?.type === "text" ? only.value : null;
}

/**
 * Rehype plugin that turns whitelisted plain-text or inline-code HR routes (`/hr`, `/hr/documents`, `/hr/guide`)
 * inside assistant Markdown into clickable links with friendly page titles while leaving `<pre>`, existing `<a>`, buttons, and external URLs untouched.
 */
export function rehypeHrRouteLinks() {
  return (tree: Root) => {
    function walk(parent: Root | Element) {
      if (
        parent.type === "element" &&
        ["a", "pre", "script", "style", "button"].includes(parent.tagName)
      ) {
        return;
      }

      const nextChildren: RootContent[] = [];
      for (const child of parent.children) {
        if (child.type === "text") {
          let offset = 0;
          for (const match of child.value.matchAll(HR_INLINE_ROUTE_PATTERN)) {
            const prefix = match[1] ?? "";
            const route = match[2];
            const routeStart = match.index + prefix.length;
            if (!route || !isSafeHrRoute(route)) continue;

            if (routeStart > offset) {
              nextChildren.push({
                type: "text",
                value: child.value.slice(offset, routeStart),
              });
            }
            nextChildren.push({
              type: "element",
              tagName: "a",
              properties: { href: route },
              children: [{ type: "text", value: getHrRouteDisplayTitle(route) } as Text],
            });
            offset = routeStart + route.length;
          }
          if (offset < child.value.length) {
            nextChildren.push({
              type: "text",
              value: child.value.slice(offset),
            });
          }
          continue;
        }

        if (child.type === "element") {
          if (child.tagName === "code") {
            const raw = extractPlainText(child)?.trim();
            if (raw && isSafeHrRoute(raw)) {
              nextChildren.push({
                type: "element",
                tagName: "a",
                properties: { href: raw },
                children: [{ type: "text", value: getHrRouteDisplayTitle(raw) } as Text],
              });
              continue;
            }
          } else {
            walk(child);
          }
        }

        nextChildren.push(child);
      }

      parent.children = nextChildren as typeof parent.children;
    }

    walk(tree);
  };
}

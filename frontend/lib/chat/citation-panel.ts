import type { ChatViewMessage } from "@/lib/chat/controller";
import { mapMessageSources, type MappedSource } from "@/lib/chat/source-mapper";

export type CitationSource = Omit<MappedSource, "ordinal"> & { key: string; ordinal: number | null };
export interface SourceGroup {
  key: string;
  fileName: string;
  pages: { key: string; label: string; sources: CitationSource[] }[];
}

export function sourceKey(source: Pick<MappedSource, "document_id" | "version_id" | "chunk_id" | "page">) {
  return JSON.stringify([source.document_id, source.version_id, source.chunk_id, source.page ?? null]);
}

/** Keep the clicked target visible at the beginning of the drawer, without changing ordinals. */
export function prioritizeSourceGroups(groups: SourceGroup[], selectedKey: string | null): SourceGroup[] {
  const selected = (sources: CitationSource[]) => Number(sources.some(source => source.key === selectedKey));
  return groups.map(group => ({ ...group, pages: group.pages.map(page => ({
    ...page, sources: [...page.sources].sort((a, b) => Number(b.key === selectedKey) - Number(a.key === selectedKey)),
  })).sort((a, b) => selected(b.sources) - selected(a.sources)) }))
    .sort((a, b) => selected(b.pages.flatMap(page => page.sources)) - selected(a.pages.flatMap(page => page.sources)));
}

export function buildCitationPanel(message: ChatViewMessage) {
  const mapping = mapMessageSources(message);
  const entries = new Map<string, CitationSource>();
  for (const source of mapping.citations) {
    const key = sourceKey(source);
    entries.set(key, { ...source, key });
  }
  // History persists citation identities, not ordinal mapping. Display these
  // separately without assigning [1] based on their array position.
  if (message.role === "assistant") for (const citation of message.citations) {
    const page = citation.page ?? null;
    const key = sourceKey({ ...citation, page });
    if (entries.has(key)) continue;
    const file_name = citation.file_name?.trim() || null;
    entries.set(key, { document_id: citation.document_id, version_id: citation.version_id,
      chunk_id: citation.chunk_id, key, ordinal: null, file_name, page,
      pdf_page_number: file_name?.toLowerCase().endsWith(".pdf") && page !== null ? page + 1 : null });
  }
  const groups: SourceGroup[] = [];
  for (const source of entries.values()) {
    const key = JSON.stringify([source.document_id, source.version_id, source.file_name]);
    let group = groups.find(group => group.key === key);
    if (!group) {
      group = { key, fileName: source.file_name ?? "Tài liệu chưa có tên", pages: [] };
      groups.push(group);
    }
    const pageKey = String(source.page);
    let page = group.pages.find(page => page.key === pageKey);
    if (!page) {
      page = { key: pageKey, label: source.pdf_page_number !== null ? `Trang ${source.pdf_page_number}`
        : source.page === null ? "Chưa có thông tin trang" : `Vị trí nguồn: ${source.page}`, sources: [] };
      group.pages.push(page);
    }
    page.sources.push(source);
  }
  return { mapping, sources: [...entries.values()], groups,
    missingMetadata: mapping.references.some(ref => ref.status === "unavailable" && ref.reason === "missing_metadata") };
}

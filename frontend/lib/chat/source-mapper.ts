import type { ChatViewMessage } from "@/lib/chat/controller";
import type { Source } from "@/types/chat";

/** Derived UI data; not a REST/SSE DTO and never a download/preview URL. */
export interface MappedSource {
  ordinal: number;
  document_id: string;
  version_id: string;
  chunk_id: string;
  file_name: string | null;
  /** Original loader metadata, unchanged. */
  page: number | null;
  /** Only PDF's page convention is known; other loaders are not inferred. */
  pdf_page_number: number | null;
}

type UnavailableReason = "invalid_ordinal" | "missing_metadata" | "out_of_range" | "ineligible_source" | "not_assistant";
export type SourceResolution =
  | { status: "resolved"; ordinal: number; source: MappedSource }
  | { status: "unavailable"; ordinal: number; reason: UnavailableReason };

export type CitationReference = SourceResolution & {
  /** Exact text offsets for a later Markdown renderer; content is never rewritten. */
  marker: string;
  start: number;
  end: number;
};

export interface MessageSourceMap {
  messageKey: string;
  messageId: string | null;
  references: CitationReference[];
  /** First mention order, deduplicated by chunk_id like backend map_verified_citations. */
  citations: MappedSource[];
}

type SourceMessage = Pick<ChatViewMessage, "key" | "messageId" | "role" | "content" | "sources">;

// UUID eligibility follows Python UUID, rather than requiring only v1-v5 IDs.
function canonicalUuid(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const hex = value.replace(/^urn:uuid:/, "").replace(/[{}-]/g, "");
  if (!/^[0-9a-f]{32}$/i.test(hex)) return null;
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`.toLowerCase();
}

function eligibleSource(source: Source, ordinal: number): MappedSource | null {
  const document_id = canonicalUuid(source.document_id);
  const version_id = canonicalUuid(source.version_id);
  const chunk_id = canonicalUuid(source.chunk_id);
  if (!document_id || !version_id || !chunk_id) return null;
  const page = source.page ?? null;
  if (page !== null && (!Number.isSafeInteger(page) || page < 0)) return null;
  const file_name = source.file_name?.trim() ?? null;
  if (file_name === "") return null;
  return {
    ordinal, document_id, version_id, chunk_id, file_name, page,
    pdf_page_number: file_name?.toLowerCase().endsWith(".pdf") && page !== null ? page + 1 : null,
  };
}

/** Resolve only against this assistant's ordered metadata, never chunk_index or history citations. */
export function resolveCitationOrdinal(message: SourceMessage, ordinal: number): SourceResolution {
  const unavailable = (reason: UnavailableReason): SourceResolution => ({ status: "unavailable", ordinal, reason });
  if (message.role !== "assistant") return unavailable("not_assistant");
  if (!Number.isSafeInteger(ordinal) || ordinal < 1) return unavailable("invalid_ordinal");
  if (message.sources.length === 0) return unavailable("missing_metadata");
  if (ordinal > message.sources.length) return unavailable("out_of_range");
  const source = eligibleSource(message.sources[ordinal - 1], ordinal);
  return source ? { status: "resolved", ordinal, source } : unavailable("ineligible_source");
}

/** Scan markers with the backend's [digits] convention; Markdown interpretation belongs to F5-02. */
export function mapMessageSources(message: SourceMessage): MessageSourceMap {
  const result: MessageSourceMap = {
    messageKey: message.key, messageId: message.messageId, references: [], citations: [],
  };
  if (message.role !== "assistant") return result;
  const seen = new Set<string>();
  for (const match of message.content.matchAll(/\[(\d+)\]/g)) {
    const resolution = resolveCitationOrdinal(message, Number(match[1]));
    result.references.push({ ...resolution, marker: match[0], start: match.index, end: match.index + match[0].length });
    if (resolution.status === "resolved" && !seen.has(resolution.source.chunk_id)) {
      result.citations.push(resolution.source);
      seen.add(resolution.source.chunk_id);
    }
  }
  return result;
}

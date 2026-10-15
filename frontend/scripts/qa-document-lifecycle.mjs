// Opt-in /lifecycle mock only. Metadata in RAM; never writes raw files, embeds,
// indexes, imports the backend, or proxies requests. Not an ingestion emulator.
import { randomUUID } from "node:crypto";

export function createDocumentLifecycle(fixtures, delayMs) {
  const documents = structuredClone(fixtures);
  const deletes = new Map();
  let clock = Date.now();
  const now = () => new Date(++clock).toISOString();
  const wait = () => new Promise(resolve => setTimeout(resolve, delayMs * 4));
  return async ({ path, method, url, headers, body, json }) => {
    if (path !== "/documents" && !path.startsWith("/documents/")) return false;
    if (path === "/documents" && method === "GET") {
      const offset = Number(url.searchParams.get("offset") ?? 0), limit = Number(url.searchParams.get("limit") ?? 100);
      const visible = documents.filter(d => url.searchParams.get("include_deleted") === "true" || d.status !== "DELETED")
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at) || a.document_id.localeCompare(b.document_id));
      json(200, visible.slice(offset, offset + limit).map(document => {
        const info = { ...document }; delete info.versions; return info;
      })); return true;
    }
    const route = /^\/documents\/([^/]+)(\/re-index)?$/.exec(path);
    const upload = path === "/documents/upload" && method === "POST";
    let document = upload ? null : documents.find(d => d.document_id === route?.[1]);
    if (!upload && !document) { json(404, { detail: "QA document not found" }); return true; }
    if (method === "GET" && !route?.[2]) { json(200, document); return true; }
    if (method === "DELETE" && !route?.[2]) {
      const chunks = document.chunk_count;
      const attempt = (deletes.get(document.document_id) ?? 0) + 1;
      deletes.set(document.document_id, attempt);
      document.status = "DELETED"; document.active_version_id = null; document.chunk_count = 0;
      document.cleanup_pending = attempt === 1; document.deleted_at ??= now(); document.updated_at = now();
      await wait();
      json(document.cleanup_pending ? 202 : 200, { document_id: document.document_id, status: "DELETED",
        deleted_chunks: chunks, retained_files: document.versions.length, cleanup_pending: document.cleanup_pending,
        raw_file_policy: "retained", retrieval_eligible: false }); return true;
    }
    const reindex = method === "POST" && route?.[2] === "/re-index";
    if (!upload && !reindex && !(method === "PUT" && !route?.[2])) { json(404, { detail: "QA route not implemented" }); return true; }
    if (document && (document.status === "DELETED" || document.status === "PROCESSING" || (reindex && !document.active_version_id))) {
      json(409, { detail: "QA protected document" }); return true;
    }
    let filename, size;
    if (reindex) {
      const active = document.versions.find(v => v.version_id === document.active_version_id);
      filename = active.file_name; size = active.size_bytes;
    } else {
      const request = new Request("http://127.0.0.1/documents", { method: "POST", headers: { "Content-Type": headers["content-type"] ?? "" }, body });
      let form;
      try { form = await request.formData(); } catch { json(422, { detail: "QA invalid multipart" }); return true; }
      const file = form.get("file");
      if ([...form.keys()].length !== 1 || !(file instanceof File)) { json(422, { detail: "QA requires one file field" }); return true; }
      filename = file.name; size = file.size;
      if (!size || !/\.(pdf|md|markdown|txt|xlsx)$/i.test(filename)) { json(400, { detail: "QA invalid file" }); return true; }
    }
    if (!document) {
      document = { document_id: randomUUID(), file_name: filename, status: "UPLOADED", active_version_id: null,
        chunk_count: 0, version_count: 0, cleanup_pending: false, created_at: now(), updated_at: now(), deleted_at: null, versions: [] };
      documents.unshift(document);
    }
    const version = { version_id: randomUUID(), version: document.version_count + 1, file_name: filename,
      status: "PROCESSING", checksum_sha256: "qa-fixture-only", size_bytes: size, chunk_count: 0,
      embedding_model: null, created_at: now(), indexed_at: null };
    document.versions.unshift(version); document.version_count++;
    if (!document.active_version_id) document.status = "PROCESSING";
    document.updated_at = now();
    await wait();
    if (filename.startsWith("qa-fail")) {
      version.status = "FAILED";
      if (!document.active_version_id) document.status = "FAILED";
      document.updated_at = now();
      json(500, { detail: "QA fixture ingestion failure" }); return true;
    }
    version.status = "INDEXED"; version.chunk_count = 1; version.embedding_model = "qa/mock"; version.indexed_at = now();
    document.status = "INDEXED"; document.file_name = filename; document.active_version_id = version.version_id;
    document.chunk_count = 1; document.updated_at = now();
    json(201, { document_id: document.document_id, version_id: version.version_id, job_id: randomUUID(),
      file_name: filename, num_chunks: 1, status: "INDEXED", activated: true }); return true;
  };
}

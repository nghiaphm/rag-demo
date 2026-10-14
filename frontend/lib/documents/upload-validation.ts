export const DOCUMENT_UPLOAD_ACCEPT = ".pdf,.md,.markdown,.txt,.xlsx";
export const DOCUMENT_UPLOAD_EXTENSIONS = DOCUMENT_UPLOAD_ACCEPT.split(",");

/** Backend has no maximum byte limit. Do not invent a server size/MIME policy. */
export function validateUploadFile(file: Pick<File, "name" | "size"> | null): string | null {
  if (!file) return "Hãy chọn một file tài liệu.";
  if (!file.name || /[\\/\u0000]/.test(file.name) || /^[a-z]:/i.test(file.name)) return "Tên file không hợp lệ.";
  const dot = file.name.lastIndexOf(".");
  if (dot <= 0 || !DOCUMENT_UPLOAD_EXTENSIONS.includes(file.name.slice(dot).toLowerCase())) {
    return "Định dạng không được hỗ trợ. Chọn PDF, Markdown, TXT hoặc XLSX.";
  }
  if (!Number.isSafeInteger(file.size) || file.size <= 0) return "File rỗng hoặc kích thước file không hợp lệ.";
  return null;
}

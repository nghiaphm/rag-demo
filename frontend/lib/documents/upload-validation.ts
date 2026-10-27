export const DOCUMENT_UPLOAD_ACCEPT = ".pdf,.md,.markdown,.txt,.xlsx";
export const DOCUMENT_UPLOAD_EXTENSIONS = DOCUMENT_UPLOAD_ACCEPT.split(",");

/** XLSX limits mirror app/excel.py; other upload formats keep their existing policy. */
export function validateUploadFile(file: (Pick<File, "name" | "size"> & { type?: string }) | null): string | null {
  if (!file) return "Hãy chọn một file tài liệu.";
  if (!file.name || /[\\/\u0000]/.test(file.name) || /^[a-z]:/i.test(file.name)) return "Tên file không hợp lệ.";
  const dot = file.name.lastIndexOf(".");
  if (dot <= 0 || !DOCUMENT_UPLOAD_EXTENSIONS.includes(file.name.slice(dot).toLowerCase())) {
    return "Định dạng không được hỗ trợ. Chọn PDF, Markdown, TXT hoặc XLSX.";
  }
  if (!Number.isSafeInteger(file.size) || file.size <= 0) return "File rỗng hoặc kích thước file không hợp lệ.";
  if (file.name.slice(dot).toLowerCase() === ".xlsx") {
    if (file.size > 10 * 1024 * 1024) return "File XLSX không được quá 10 MiB.";
    if (!["", "application/octet-stream", "application/zip", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"].includes((file.type ?? "").split(";", 1)[0].toLowerCase())) return "MIME không phù hợp với file XLSX.";
  }
  return null;
}

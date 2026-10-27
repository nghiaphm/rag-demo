/** Preview only a bounded prefix; upload validation/size policy stays unchanged. */
export const TEXT_PREVIEW_MAX_BYTES = 256 * 1024

export async function readTextPreview(file: Blob): Promise<{ text: string; truncated: boolean }> {
  let bytes: Uint8Array
  try {
    bytes = new Uint8Array(await file.slice(0, TEXT_PREVIEW_MAX_BYTES).arrayBuffer())
  } catch {
    throw new Error("Không thể đọc file trên thiết bị. Hãy đóng và mở lại bản xem trước.")
  }
  const truncated = file.size > TEXT_PREVIEW_MAX_BYTES
  const encoding = bytes[0] === 0xff && bytes[1] === 0xfe ? "utf-16le"
    : bytes[0] === 0xfe && bytes[1] === 0xff ? "utf-16be" : "utf-8"
  try {
    // Streaming decode omits a partial character at the bounded prefix's end.
    const text = new TextDecoder(encoding, { fatal: true }).decode(bytes, { stream: truncated })
    if (text.includes("\u0000")) throw new Error("Binary content")
    return { text, truncated }
  } catch {
    throw new Error("Không đọc được encoding của file. Bản xem trước hỗ trợ UTF-8 hoặc UTF-16 có BOM; hãy chuyển file sang UTF-8.")
  }
}

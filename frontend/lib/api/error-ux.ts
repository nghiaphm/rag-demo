/** Never use arbitrary Error.message, HTTP detail/input/ctx or SSE message as UI copy. */
export function safeApiErrorMessage(error: unknown, fallback = "Không thể hoàn tất yêu cầu."): string {
  if (typeof error !== "object" || error === null) return fallback;
  const value = error as Record<string, unknown>;
  const statuses: Record<number, string> = {
    400: "Yêu cầu không hợp lệ. Kiểm tra dữ liệu trước khi gửi lại.",
    404: "Không tìm thấy dữ liệu. Hãy tải lại danh sách hoặc chọn mục khác.",
    409: "Dữ liệu đang có xung đột trạng thái. Chờ yêu cầu hiện tại hoàn tất rồi kiểm tra lại.",
    410: "Dữ liệu đã bị xóa. Hãy chọn mục khác.",
    422: "Dữ liệu gửi lên không hợp lệ. Kiểm tra nội dung hoặc file trước khi gửi lại.",
    429: "Quá nhiều yêu cầu. Hãy chờ rồi thử lại chủ động.",
    502: "Dịch vụ chưa thể hoàn tất xử lý. Kiểm tra trạng thái đã lưu trước khi gửi lại.",
    503: "Dịch vụ tạm thời chưa sẵn sàng. Kiểm tra trạng thái kết nối rồi thử lại chủ động.",
  };
  if (typeof value.status === "number" && statuses[value.status]) return statuses[value.status];
  if (value.kind === "timeout") return "Đã hết thời gian chờ. Kiểm tra trạng thái đã lưu trước khi gửi lại.";
  if (value.kind === "network" || value.kind === "transport") return "Kết nối bị gián đoạn. Kiểm tra mạng và trạng thái đã lưu trước khi gửi lại.";
  if (value.kind === "aborted") return "Đã dừng chờ phản hồi. Xử lý trên dịch vụ có thể vẫn tiếp tục.";
  if (["invalid_response", "protocol", "incomplete", "consumer"].includes(String(value.kind))) return "Phản hồi chưa đầy đủ hoặc không hợp lệ. Tải lại dữ liệu để kiểm tra trước khi gửi lại.";
  return fallback;
}

export function safeStreamErrorMessage(code: string): string {
  const messages: Record<string, string> = {
    RAG_STREAM_EMPTY: "Dịch vụ không trả nội dung. Kiểm tra trạng thái phiên trước khi gửi câu hỏi mới.",
    RAG_STREAM_TIMEOUT: "Luồng trả lời đã hết thời gian. Nội dung nhận được được giữ lại; kiểm tra lịch sử trước khi gửi lại.",
    RAG_STREAM_ERROR: "Luồng tạo câu trả lời thất bại. Nội dung nhận được được giữ lại; kiểm tra lịch sử trước khi gửi lại.",
    RAG_STREAM_CANCELLED: "Luồng trả lời đã dừng. Nội dung nhận được được giữ lại.",
    STREAM_PERSISTENCE_ERROR: "Chưa xác nhận được việc lưu câu trả lời. Kiểm tra lịch sử trước khi gửi lại.",
  };
  return Object.hasOwn(messages, code) ? messages[code] : "Luồng trả lời không hoàn tất. Nội dung nhận được được giữ lại; kiểm tra lịch sử trước khi gửi lại.";
}

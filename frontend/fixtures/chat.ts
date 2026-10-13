export type ChatFixtureMessage = {
  id: string
  role: "user" | "assistant"
  content: string
}

export const chatConversationFixture: readonly ChatFixtureMessage[] = [
  {
    id: "fixture-user-1",
    role: "user",
    content: "Tóm tắt các bước chính để chuẩn bị một tài liệu cho hệ thống RAG.",
  },
  {
    id: "fixture-assistant-1",
    role: "assistant",
    content: `Để chuẩn bị tài liệu cho hệ thống RAG, bạn có thể đi theo ba bước:

1. **Kiểm tra nội dung**: loại bỏ dữ liệu trùng lặp và bảo đảm văn bản đọc được.
2. **Bổ sung metadata**: ghi rõ tên tài liệu, phiên bản và phạm vi sử dụng.
3. **Theo dõi ingestion**: chỉ dùng tài liệu sau khi phiên bản đã được xử lý thành công.

> Đây là nội dung Markdown từ fixture. Nguồn trích dẫn sẽ được nối ở phase riêng.`,
  },
]

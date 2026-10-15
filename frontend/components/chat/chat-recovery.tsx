import type { ChatState } from "@/lib/chat/controller"
import { isHistoricalNonterminal } from "@/lib/chat/recovery"

export function ChatRecovery({ state, initialSessionId }: { state: ChatState; initialSessionId: string | null }) {
  if (!state.sessionId) return null
  const href = `/chat/${encodeURIComponent(state.sessionId)}`
  const historical = state.messages.some(isHistoricalNonterminal)
  return <>
    {!initialSessionId && <div className="mb-4 rounded-lg border p-3 text-sm leading-6">
      <p>Phiên đã được tạo. URL sẽ cập nhật sau khi câu trả lời kết thúc và lịch sử được xác minh.
        Trước lúc đó, tải lại trang /chat sẽ không tự mở lại phiên này.</p>
      <a href={href} target="_blank" rel="noopener noreferrer" className="underline focus-visible:outline-2 focus-visible:outline-ring">
        Mở lịch sử trong tab mới (có thể lưu liên kết phiên)
      </a>
      <p className="text-muted-foreground">Không tự gửi lại câu hỏi hoặc khôi phục luồng khi mở lịch sử.</p>
    </div>}
    {historical && <div role="status" className="mb-4 rounded-lg border p-3 text-sm leading-6">
      <p>Lịch sử có tin nhắn PENDING/STREAMING. Đây là trạng thái đã đọc từ backend;
        trang này không kết nối với luồng trả lời của những tin nhắn đó.
        Backend có thể vẫn đang xử lý. Không tự tiếp tục hoặc gửi lại câu hỏi.</p>
      {!state.isGenerating && <a href={href} className="underline focus-visible:outline-2 focus-visible:outline-ring">Tải lại lịch sử</a>}
    </div>}
  </>
}

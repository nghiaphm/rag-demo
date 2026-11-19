"""Structured UI context normalization and prompt composition for context-aware HR chat."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class UiRelatedPage:
    """Whitelisted related page that the assistant may suggest for user navigation."""

    route: str
    title: str
    description: str | None = None


@dataclass(frozen=True)
class UiPageContext:
    """Validated current-page metadata passed optionally from the frontend portal."""

    portal: str
    route: str
    page_title: str
    page_purpose: str
    available_features: tuple[str, ...] = ()
    related_pages: tuple[UiRelatedPage, ...] = ()
    selected_document_name: str | None = None
    selected_category: str | None = None


def _clean_line(value: str, max_chars: int) -> str:
    collapsed = " ".join(part for part in value.replace("\r", " ").replace("\n", " ").split() if part)
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "…"


def format_ui_context_block(
    ui_context: UiPageContext,
    *,
    max_features: int = 8,
    max_related: int = 4,
) -> str:
    """Format sanitized frontend page context as structured, non-authoritative UI metadata."""
    lines = [
        "[Ngữ cảnh trang hiện tại (UI Context)]",
        f"- Cổng: { _clean_line(ui_context.portal, 32) }",
        f"- Đường dẫn hiện tại: { _clean_line(ui_context.route, 120) }",
        f"- Tên trang: { _clean_line(ui_context.page_title, 120) }",
        f"- Mục đích trang: { _clean_line(ui_context.page_purpose, 360) }",
    ]
    if ui_context.selected_document_name:
        lines.append(f"- Tài liệu đang chọn: { _clean_line(ui_context.selected_document_name, 160) }")
    if ui_context.selected_category:
        lines.append(f"- Nhóm phân loại đang lọc: { _clean_line(ui_context.selected_category, 64) }")

    features = [
        _clean_line(item, 180)
        for item in ui_context.available_features[:max_features]
        if _clean_line(item, 180)
    ]
    if features:
        lines.append("- Các chức năng hiện có trên trang:")
        lines.extend(f"  * {feature}" for feature in features)

    related = list(ui_context.related_pages[:max_related])
    if related:
        lines.append("- Các trang liên quan hợp lệ (chỉ gợi ý trong danh sách này):")
        for page in related:
            route = _clean_line(page.route, 120)
            title = _clean_line(page.title, 120)
            if page.description:
                desc = _clean_line(page.description, 160)
                lines.append(f"  * {title} (`{route}`): {desc}")
            else:
                lines.append(f"  * {title} (`{route}`)")
    return "\n".join(lines)


_UI_POLICY_INSTRUCTION = (
    "\n\nHƯỚNG DẪN KẾT HỢP NGỮ CẢNH GIAO DIỆN (UI Context):\n"
    "1) Phân biệt đúng ý định câu hỏi:\n"
    "- Nếu người dùng hỏi về trang hiện tại, tính năng đang có, cách thao tác trên hệ thống hoặc nên chuyển sang trang nào: "
    "dùng thông tin xác thực trong phần `[Ngữ cảnh trang hiện tại (UI Context)]` ở dưới, kết hợp thêm thông tin từ `Context` tài liệu RAG nếu có nội dung phù hợp.\n"
    "  Với câu hỏi hướng dẫn thao tác/giao diện, tổ chức câu trả lời theo đúng 5 mục Markdown rõ ràng:\n"
    "  ### 1. Giới thiệu trang hiện tại\n"
    "  ### 2. Các chức năng chính\n"
    "  ### 3. Hướng dẫn thao tác từng bước\n"
    "  ### 4. Các trang liên quan\n"
    "  (Khi nhắc đến trang HR ở mục Hướng dẫn thao tác từng bước hoặc mục Các trang liên quan, hãy nhúng trực tiếp liên kết Markdown với nhãn là tên trang thân thiện như `[Tài liệu nhân sự](/hr/documents)`, `[Tổng quan nhân sự](/hr)`, `[Hướng dẫn sử dụng](/hr/guide)`; không dùng đường dẫn thô `/hr/...` làm nhãn hiển thị, không viết lặp kiểu `Tài liệu nhân sự: [Tài liệu nhân sự](/hr/documents)`, và không tự bịa URL khác.)\n"
    "  ### 5. Nguồn tài liệu tham khảo\n"
    "  (Nếu có dùng thông tin từ `Context` tài liệu RAG, ghi và gắn đúng citation `[1]`, `[2]`; nếu chỉ trả lời từ UI Context và không có tài liệu RAG phù hợp, ghi rõ chưa có tài liệu RAG bổ sung được trích dẫn và không bịa số `[n]`.)\n"
    "  Không từ chối bằng \"Không tìm thấy thông tin trong tài liệu\" đối với phần thao tác giao diện đã có trong UI Context; đồng thời tuyệt đối không tự bịa nút bấm, API hay chức năng không được liệt kê trong UI Context.\n"
    "- Nếu người dùng hỏi về chính sách, quy định, quy trình nhân sự hoặc thống kê tài liệu thông thường: "
    "trả lời tự nhiên như trợ lý RAG chuẩn từ `Context` tài liệu (kèm `[1]`, `[2]`) hoặc tool; không ép sang mẫu 5 mục hướng dẫn giao diện."
)


def compose_ui_aware_system_instruction(
    base_instruction: str,
    ui_context: UiPageContext | None,
    *,
    max_features: int = 8,
    max_related: int = 4,
) -> str:
    """Compose base instruction with bounded UI context guidance."""
    if ui_context is None:
        return base_instruction
    block = format_ui_context_block(
        ui_context,
        max_features=max_features,
        max_related=max_related,
    )
    return f"{base_instruction}{_UI_POLICY_INSTRUCTION}\n\n{block}"


def fit_ui_system_instruction(
    base_instruction: str,
    ui_context: UiPageContext | None,
    count_tokens: Callable[[str], int],
    max_tokens: int,
) -> str:
    """Return UI-aware system instruction only while staying strictly within system_max_tokens."""
    if ui_context is None:
        return base_instruction

    for feature_limit, related_limit in ((8, 4), (4, 3), (2, 2), (0, 2)):
        candidate = compose_ui_aware_system_instruction(
            base_instruction,
            ui_context,
            max_features=feature_limit,
            max_related=related_limit,
        )
        if count_tokens(candidate) <= max_tokens:
            return candidate
    return base_instruction


def build_selector_ui_note(ui_context: UiPageContext | None) -> str:
    """Compact selector hint so UI navigation/how-to queries stay on the RAG + UI path."""
    if ui_context is None:
        return ""
    return (
        f" Note: user is currently viewing HR Portal page '{_clean_line(ui_context.page_title, 80)}' "
        f"({_clean_line(ui_context.route, 80)}). Questions about how to use this UI/page "
        "do NOT require document inventory tools unless the user explicitly asks to count or list files."
    )

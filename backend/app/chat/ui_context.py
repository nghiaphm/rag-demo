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
class UiDashboardKpi:
    """Single KPI card rendered on the HR Dashboard."""

    label: str
    value: str
    delta_label: str | None = None
    trend: str | None = None
    helper_text: str | None = None


@dataclass(frozen=True)
class UiDashboardDepartment:
    """Department headcount & open hiring roles rendered on the HR Dashboard."""

    department: str
    count: int
    open_roles: int = 0


@dataclass(frozen=True)
class UiDashboardContractStatus:
    """Contract / employee status distribution item rendered on the HR Dashboard."""

    label: str
    count: int


@dataclass(frozen=True)
class UiDashboardKnowledgeBase:
    """Live RAG Knowledge Base document stats shown on the HR Dashboard."""

    total_documents: int
    indexed_documents: int
    processing_documents: int
    failed_documents: int
    total_chunks: int


@dataclass(frozen=True)
class UiDashboardSnapshot:
    """Structured HR Dashboard data snapshot used for deterministic statistical analysis."""

    as_of_label: str
    total_employees: int
    kpis: tuple[UiDashboardKpi, ...] = ()
    departments: tuple[UiDashboardDepartment, ...] = ()
    contract_statuses: tuple[UiDashboardContractStatus, ...] = ()
    knowledge_base: UiDashboardKnowledgeBase | None = None


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
    dashboard_snapshot: UiDashboardSnapshot | None = None


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


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 100.0, 1)


def format_dashboard_snapshot_context(ui_context: UiPageContext | None) -> str:
    """Render deterministic Python-computed HR Dashboard statistics for grounded LLM analysis.

    Returns an empty string when no dashboard_snapshot is attached. Numbers and percentages are
    computed here in Python so the model never relies on mental arithmetic.
    """
    if ui_context is None or ui_context.dashboard_snapshot is None:
        return ""
    snap = ui_context.dashboard_snapshot
    lines: list[str] = [
        "[Dữ liệu thống kê Dashboard HR hiện tại (UI Snapshot trên trang /hr — KHÔNG gán số trích dẫn [n])]",
        f"- Nguồn & kỳ dữ liệu: {_clean_line(snap.as_of_label, 160)}",
        f"- Tổng nhân sự hiển thị: {snap.total_employees}",
    ]

    if snap.kpis:
        lines.append("- Các chỉ số KPI chính:")
        for kpi in snap.kpis:
            parts = [f"{_clean_line(kpi.label, 120)}: {_clean_line(kpi.value, 64)}"]
            if kpi.delta_label:
                parts.append(f"biến động: {_clean_line(kpi.delta_label, 160)}")
            if kpi.trend:
                parts.append(f"xu hướng: {_clean_line(kpi.trend, 16)}")
            if kpi.helper_text:
                parts.append(f"ghi chú: {_clean_line(kpi.helper_text, 180)}")
            lines.append("  * " + " | ".join(parts))

    if snap.departments:
        sorted_depts = sorted(snap.departments, key=lambda d: (-d.count, d.department))
        dept_total = sum(d.count for d in sorted_depts)
        total_open_roles = sum(d.open_roles for d in sorted_depts)
        overall_hiring_rate = _pct(total_open_roles, dept_total)
        lines.append(
            f"- Phân bổ nhân sự theo {len(sorted_depts)} phòng ban "
            f"(tổng={dept_total}, tổng vị trí đang tuyển={total_open_roles}, "
            f"tỉ lệ nhu cầu tuyển/quy mô={overall_hiring_rate:.1f}%):"
        )
        for dept in sorted_depts:
            share = _pct(dept.count, dept_total)
            open_ratio = _pct(dept.open_roles, dept.count)
            lines.append(
                f"  * {_clean_line(dept.department, 120)}: {dept.count} nhân sự "
                f"({share:.1f}%), đang tuyển {dept.open_roles} vị trí "
                f"(tỉ lệ tuyển/quy mô phòng: {open_ratio:.1f}%)"
            )
        largest = sorted_depts[0]
        smallest = sorted_depts[-1]
        top_hiring = max(sorted_depts, key=lambda d: (d.open_roles, _pct(d.open_roles, d.count)))
        top_hiring_rate = max(sorted_depts, key=lambda d: (_pct(d.open_roles, d.count), d.open_roles))
        lines.append(
            f"  * Tóm tắt phòng ban: lớn nhất={_clean_line(largest.department, 80)} "
            f"({largest.count}, {_pct(largest.count, dept_total):.1f}%); "
            f"nhỏ nhất={_clean_line(smallest.department, 80)} "
            f"({smallest.count}, {_pct(smallest.count, dept_total):.1f}%); "
            f"tuyển nhiều nhất={_clean_line(top_hiring.department, 80)} ({top_hiring.open_roles} vị trí); "
            f"áp lực tuyển theo tỉ lệ cao nhất={_clean_line(top_hiring_rate.department, 80)} "
            f"({_pct(top_hiring_rate.open_roles, top_hiring_rate.count):.1f}%)."
        )

    if snap.contract_statuses:
        sorted_contracts = sorted(snap.contract_statuses, key=lambda c: (-c.count, c.label))
        contract_total = sum(c.count for c in sorted_contracts)
        lines.append(
            f"- Cơ cấu {len(sorted_contracts)} nhóm loại hợp đồng / trạng thái (tổng={contract_total}):"
        )
        for item in sorted_contracts:
            share = _pct(item.count, contract_total)
            lines.append(
                f"  * {_clean_line(item.label, 120)}: {item.count} nhân sự ({share:.1f}%)"
            )

    if snap.knowledge_base is not None:
        kb = snap.knowledge_base
        ready_pct = _pct(kb.indexed_documents, kb.total_documents)
        lines.append(
            "- Kho tri thức RAG thực tế (từ GET /documents): "
            f"tổng={kb.total_documents} tài liệu, "
            f"sẵn sàng (INDEXED)={kb.indexed_documents} ({ready_pct:.1f}%), "
            f"đang xử lý={kb.processing_documents}, "
            f"lỗi (FAILED)={kb.failed_documents}, "
            f"tổng vector chunks={kb.total_chunks}."
        )

    return "\n".join(lines)


_UI_POLICY_INSTRUCTION = (
    "\n\nHƯỚNG DẪN NGỮ CẢNH GIAO DIỆN (UI Context):\n"
    "1) Câu hỏi hướng dẫn thao tác/tính năng trang hiện tại hoặc điều hướng: "
    "dùng `[Ngữ cảnh trang hiện tại (UI Context)]` (kết hợp `Context` RAG nếu có), "
    "KHÔNG từ chối vì thiếu tài liệu, KHÔNG bịa chức năng ngoài UI Context; trả lời theo 5 mục Markdown:\n"
    "### 1. Giới thiệu trang hiện tại\n"
    "### 2. Các chức năng chính\n"
    "### 3. Hướng dẫn thao tác từng bước\n"
    "### 4. Các trang liên quan\n"
    "(Nhúng link thân thiện `[Tài liệu nhân sự](/hr/documents)`, `[Tổng quan nhân sự](/hr)`, `[Hướng dẫn sử dụng](/hr/guide)`; không dùng path thô làm nhãn, không bịa URL.)\n"
    "### 5. Nguồn tài liệu tham khảo\n"
    "(Gắn `[1]`, `[2]` nếu dùng tài liệu RAG; nếu chỉ dùng UI Context thì ghi rõ chưa có tài liệu RAG và không bịa `[n]`.)\n"
    "2) Câu hỏi chính sách/quy định/quy trình nhân sự: trả lời tự nhiên từ `Context` tài liệu kèm `[1]`, `[2]`, không ép sang mẫu 5 mục giao diện."
)

_DASHBOARD_ANALYTICS_INSTRUCTION = (
    "\n3) Câu hỏi phân tích/thống kê nhân sự, trang Nhân sự hoặc Dashboard HR "
    "(có `[Dữ liệu thống kê Dashboard HR hiện tại]` trong ngữ cảnh): "
    "dùng đúng số liệu và `%` đã tính sẵn, không bịa số, không từ chối vì thiếu tài liệu, không gắn `[n]` cho số liệu Dashboard "
    "(ghi rõ nguồn Dashboard `[Tổng quan nhân sự](/hr)` và minh bạch nếu là dữ liệu mô phỏng); trình bày báo cáo Markdown 5 mục:\n"
    "### 1. Tóm tắt điều hành\n"
    "### 2. Phân tích chỉ số KPI chính\n"
    "### 3. Bảng phân bổ cơ cấu nhân sự (bảng Markdown Phòng ban: Số lượng | Tỷ trọng % | Đang tuyển; bảng Loại hợp đồng: Số lượng | Tỷ trọng %)\n"
    "### 4. Điểm nổi bật & Cảnh báo\n"
    "### 5. Đề xuất hành động"
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
    policy = (
        f"{_UI_POLICY_INSTRUCTION}{_DASHBOARD_ANALYTICS_INSTRUCTION}"
        if ui_context.dashboard_snapshot is not None
        else _UI_POLICY_INSTRUCTION
    )
    return f"{base_instruction}{policy}\n\n{block}"


def fit_ui_system_instruction(
    base_instruction: str,
    ui_context: UiPageContext | None,
    count_tokens: Callable[[str], int],
    max_tokens: int,
) -> str:
    """Return UI-aware system instruction only while staying strictly within system_max_tokens."""
    if ui_context is None:
        return base_instruction

    for feature_limit, related_limit in ((8, 4), (4, 3), (2, 2), (0, 2), (0, 0)):
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
    """Compact selector hint so UI navigation and HR Dashboard analytics stay on the RAG + UI path."""
    if ui_context is None:
        return ""
    dashboard_hint = (
        " Questions asking to analyze or summarize HR Dashboard workforce/KPI/department/contract statistics "
        "also stay on the RAG + UI path (do NOT call count_documents or list_documents unless explicitly asked about uploaded files)."
        if ui_context.dashboard_snapshot is not None
        else ""
    )
    return (
        f" Note: user is currently viewing HR Portal page '{_clean_line(ui_context.page_title, 80)}' "
        f"({_clean_line(ui_context.route, 80)}). Questions about how to use this UI/page "
        "do NOT require document inventory tools unless the user explicitly asks to count or list files."
        f"{dashboard_hint}"
    )

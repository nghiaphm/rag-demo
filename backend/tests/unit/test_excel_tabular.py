"""Unit tests cho Giai đoạn 2 (T2.1): chuẩn hóa bảng Excel, suy luận kiểu và xuất Parquet."""

from __future__ import annotations

from datetime import date, datetime
import io
import unittest
from zipfile import ZipFile

from openpyxl import Workbook
import pyarrow.parquet as pq

from app.documents.excel.tabular import (
    extract_workbook_tables,
    normalize_column_name,
    normalize_table_name,
)
from app.documents.excel.validation import WorkbookError


def _save_workbook(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


class ExcelTabularUnitTests(unittest.TestCase):
    def test_table_and_column_identifier_normalization_and_deduplication(self) -> None:
        used_tables: set[str] = set()
        t1 = normalize_table_name("Đánh Giá Nhân Sự 2026!", used_tables)
        t2 = normalize_table_name("Danh-Gia-Nhan-Su-2026", used_tables)
        t3 = normalize_table_name("2026 KPI Phòng Ban", used_tables)
        t4 = normalize_table_name("???", used_tables)

        self.assertEqual(t1, "danh_gia_nhan_su_2026")
        self.assertEqual(t2, "danh_gia_nhan_su_2026_2")
        self.assertEqual(t3, "t_2026_kpi_phong_ban")
        self.assertEqual(t4, "sheet")

        used_cols: set[str] = set()
        c1, orig1 = normalize_column_name("Mã Nhân Viên", 1, used_cols)
        c2, orig2 = normalize_column_name("", 2, used_cols)
        c3, orig3 = normalize_column_name("Ma Nhan Vien", 3, used_cols)
        c4, orig4 = normalize_column_name("12 Tháng", 4, used_cols)

        self.assertEqual((c1, orig1), ("ma_nhan_vien", "Mã Nhân Viên"))
        self.assertEqual((c2, orig2), ("col_2", "col_2"))
        self.assertEqual((c3, orig3), ("ma_nhan_vien_2", "Ma Nhan Vien"))
        self.assertEqual((c4, orig4), ("c_12_thang", "12 Tháng"))

    def test_header_offset_detection_and_empty_sheet_skipping(self) -> None:
        wb = Workbook()
        # Sheet 1: chỉ có tiêu đề đơn lẻ, không có dữ liệu -> phải được bỏ qua
        ws_empty = wb.active
        ws_empty.title = "ChiCoTieuDe"
        ws_empty.append(["BÁO CÁO TỔNG HỢP NĂM 2026"])

        # Sheet 2: dòng 1 trống, dòng 2 tiêu đề đơn, dòng 3 mới là header thật
        ws_data = wb.create_sheet("Bảng Lương")
        ws_data.append([None, None, None])
        ws_data.append(["BẢNG LƯƠNG THÁNG 11", None, None])
        ws_data.append(["Mã NV", "", "Họ và Tên"])
        ws_data.append(["NV01", "Ghi chú A", "Nguyễn Văn A"])
        ws_data.append(["NV02", "Ghi chú B", "Trần Thị B"])

        tables = extract_workbook_tables(_save_workbook(wb))
        self.assertEqual(len(tables), 1)
        tbl = tables[0]
        self.assertEqual(tbl.table_name, "bang_luong")
        self.assertEqual(tbl.sheet_name, "Bảng Lương")
        self.assertEqual(tbl.row_count, 2)
        self.assertEqual([c.name for c in tbl.columns], ["ma_nv", "col_2", "ho_va_ten"])
        self.assertEqual([c.original_name for c in tbl.columns], ["Mã NV", "col_2", "Họ và Tên"])

    def test_type_inference_preserves_leading_zeros_large_ints_vn_numbers_and_dates(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "DuLieu"
        ws.append([
            "MaCode",
            "SoNguyen",
            "SoThuc",
            "SoLon",
            "LuongVN",
            "LuongVNHonHop",
            "DangLamViec",
            "NgayVao",
            "ThoiDiemTao",
            "HonHop",
        ])
        ws.append([
            "00123",
            42,
            3.5,
            "99999999999999999999999",
            "1.250.000,5",
            "1.250.000,5",
            True,
            date(2026, 5, 19),
            datetime(2026, 5, 19, 14, 30, 0),
            "100",
        ])
        ws.append([
            "00456",
            108,
            7.25,
            "12345678901234567890123",
            "2.500.000,75",
            "2,500,000.75",
            False,
            date(2026, 6, 1),
            datetime(2026, 6, 1, 9, 15, 0),
            "Khác",
        ])

        tables = extract_workbook_tables(_save_workbook(wb))
        self.assertEqual(len(tables), 1)
        tbl = tables[0]
        type_map = {col.name: col.type for col in tbl.columns}

        self.assertEqual(type_map["macode"], "VARCHAR")
        self.assertEqual(type_map["songuyen"], "INT64")
        self.assertEqual(type_map["sothuc"], "DOUBLE")
        self.assertEqual(type_map["solon"], "VARCHAR")
        self.assertEqual(type_map["luongvn"], "DOUBLE")
        self.assertEqual(type_map["luongvnhonhop"], "VARCHAR")
        self.assertEqual(type_map["danglamviec"], "BOOLEAN")
        self.assertEqual(type_map["ngayvao"], "DATE")
        self.assertEqual(type_map["thoidiemtao"], "TIMESTAMP")
        self.assertEqual(type_map["honhop"], "VARCHAR")

        pa_table = pq.read_table(io.BytesIO(tbl.parquet_bytes))
        pydict = pa_table.to_pydict()
        self.assertEqual(pydict["macode"], ["00123", "00456"])
        self.assertEqual(pydict["songuyen"], [42, 108])
        self.assertEqual(pydict["luongvn"], [1250000.5, 2500000.75])
        self.assertEqual(pydict["luongvnhonhop"], ["1.250.000,5", "2,500,000.75"])
        self.assertEqual(pydict["danglamviec"], [True, False])
        self.assertEqual(pydict["ngayvao"], [date(2026, 5, 19), date(2026, 6, 1)])

    def test_formula_without_cached_value_becomes_null_and_flags_has_formula_values(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "CongThuc"
        ws.append(["A", "B", "Tong"])
        ws.append([10, 20, "=A2+B2"])
        ws.append([30, 40, "=A3+B3"])

        tables = extract_workbook_tables(_save_workbook(wb))
        self.assertEqual(len(tables), 1)
        tbl = tables[0]
        self.assertTrue(tbl.has_formula_values)

        col_map = {col.name: col for col in tbl.columns}
        self.assertFalse(col_map["a"].has_formula_values)
        self.assertTrue(col_map["tong"].has_formula_values)
        self.assertTrue(col_map["tong"].nullable)

        pa_table = pq.read_table(io.BytesIO(tbl.parquet_bytes))
        self.assertEqual(pa_table.to_pydict()["tong"], [None, None])

    def test_sample_rows_limit_and_cell_truncation_and_determinism(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "Nhân Sự"
        ws.append(["Mã NV", "Ghi chú dài"])
        long_text = "A" * 150
        for idx in range(5):
            ws.append([f"NV{idx}", long_text])
        raw_bytes = _save_workbook(wb)

        t_zero = extract_workbook_tables(raw_bytes, sample_rows_limit=0)[0]
        self.assertEqual(t_zero.sample_rows, ())

        t_run1 = extract_workbook_tables(raw_bytes, sample_rows_limit=3)[0]
        t_run2 = extract_workbook_tables(raw_bytes, sample_rows_limit=3)[0]
        self.assertEqual(len(t_run1.sample_rows), 3)
        self.assertEqual(len(t_run1.sample_rows[0]["ghi_chu_dai"]), 100)
        self.assertEqual(t_run1.table_name, t_run2.table_name)
        self.assertEqual(t_run1.columns, t_run2.columns)
        self.assertEqual(t_run1.sample_rows, t_run2.sample_rows)
        self.assertEqual(t_run1.parquet_bytes, t_run2.parquet_bytes)

    def test_read_workbook_safety_limits_are_enforced(self) -> None:
        with self.assertRaises(WorkbookError):
            extract_workbook_tables(b"")

        # Giả lập workbook có chứa file vbaProject.bin (macro) -> phải bị chặn
        wb = Workbook()
        ws = wb.active
        ws.append(["A", "B"])
        ws.append(["1", "2"])
        clean_bytes = _save_workbook(wb)

        macro_buf = io.BytesIO()
        with ZipFile(io.BytesIO(clean_bytes), "r") as src, ZipFile(macro_buf, "w") as dst:
            for item in src.infolist():
                dst.writestr(item, src.read(item.filename))
            dst.writestr("xl/vbaProject.bin", b"fake-macro")

        with self.assertRaises(WorkbookError):
            extract_workbook_tables(macro_buf.getvalue())


if __name__ == "__main__":
    unittest.main()

import sys
import types
from pathlib import Path

from openpyxl import Workbook

from agents.auditor import AuditorAgent
from tools import document_parser as dp


def test_financial_post_processing_extracts_priority_sections():
    text = "\n".join(
        [
            "Revenue from operations 12,345",
            "EBITDA margin 18.2%",
            "Total borrowings 4,200",
            "Cash and cash equivalents 1,100",
        ]
    )

    out = dp._post_process_financial_text(text)

    assert "### Financial Signals (Revenue, EBITDA, Debt, Cash)" in out
    assert "#### Revenue" in out
    assert "#### EBITDA" in out
    assert "#### Debt" in out
    assert "#### Cash" in out


def test_parse_pdf_uses_ocr_fallback_for_low_text_pages(monkeypatch, tmp_path: Path):
    class FakePage:
        def get_text(self, mode: str):
            if mode == "text":
                return ""
            if mode == "blocks":
                return []
            return ""

    class FakeDoc:
        def __iter__(self):
            return iter([FakePage()])

        def close(self):
            return None

    fake_fitz = types.SimpleNamespace(
        open=lambda _: FakeDoc(),
        Matrix=lambda x, y: (x, y),
    )

    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    tesseract_called = {"count": 0}
    rapid_called = {"count": 0}

    def fake_tesseract(_page):
        tesseract_called["count"] += 1
        return ""

    def fake_rapidocr(_page):
        rapid_called["count"] += 1
        return "Revenue from operations 999"

    monkeypatch.setattr(dp, "_ocr_page_with_tesseract", fake_tesseract)
    monkeypatch.setattr(dp, "_ocr_page_with_rapidocr", fake_rapidocr)

    fake_pdf = tmp_path / "scanned.pdf"
    fake_pdf.write_bytes(b"%PDF")

    out = dp.parse_document(str(fake_pdf), "pdf")

    assert tesseract_called["count"] == 1
    assert rapid_called["count"] == 1
    assert out is not None
    assert "Revenue from operations 999" in out
    assert "#### Revenue" in out


def test_parse_excel_emits_sheet_text_and_financial_signals(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "P&L"
    ws.append(["Metric", "FY25"])
    ws.append(["Revenue from operations", 120000])
    ws.append(["EBITDA", 24000])
    ws.append(["Total borrowings", 18000])
    ws.append(["Cash and cash equivalents", 5000])

    xlsx_path = tmp_path / "financials.xlsx"
    wb.save(str(xlsx_path))

    out = dp.parse_document(str(xlsx_path), "xlsx")

    assert out is not None
    assert "## Sheet: P&L" in out
    assert "Revenue from operations" in out
    assert "#### Revenue" in out
    assert "#### EBITDA" in out
    assert "#### Debt" in out
    assert "#### Cash" in out


def test_extract_structured_financials_from_ifrs_inr_workbook(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "IFRS-PnL,BS-INR"
    ws.append(
        [
            "Synthetic IFRS financials - INR Mn",
            "FY21",
            "FY22",
            "FY23",
            "FY24",
            "FY25",
        ]
    )
    ws.append(["Total Revenue", 1000, 1100, 1210, 1331, 1464.1])
    ws.append(["Depreciation", 12, 13, 14, 15, 16])
    ws.append(["Depreciation", 3, 3, 4, 4, 5])
    ws.append(["Operating Income", 240, 275, 305, 336, 372])
    ws.append(["Cash and Cash Equivalents", 100, 110, 120, 130, 140])
    ws.append(["Investments", 200, 210, 220, 230, 240])
    ws.append(["Bank Deposits", 15, 15, 16, 16, 17])
    ws.append(["Short-term Borrowings", 10, 9, 8, 7, 6])
    ws.append(["Net Profit After Taxes", 180, 205, 228, 251, 278])
    ws.append(["Basic and Diluted EPS", 18, 20.5, 22.8, 25.1, 27.8])
    ws.append(["Weighted average no of shares used in computing Basic and Diluted EPS", 10_000_000, 10_000_000, 10_000_000, 10_000_000, 10_000_000])
    ws.append(["Information Technology and Consultancy Services"])

    xlsx_path = tmp_path / "ifrs_inr_metrics.xlsx"
    wb.save(str(xlsx_path))

    extracted = dp.extract_structured_financials(str(xlsx_path), "xlsx")

    assert extracted is not None
    data = extracted["extracted_data"]
    assert data["reporting_unit"] == "millions"
    assert data["historical_revenues"] == [
        1_000_000_000,
        1_100_000_000,
        1_210_000_000,
        1_331_000_000,
        1_464_100_000,
    ]
    assert data["shares_outstanding"] == 10_000_000
    assert data["cash_and_equivalents"] == 397_000_000
    assert round(data["historical_ebitda_margins"][-1], 4) == round((372 + 16 + 5) / 1464.1, 4)
    assert data["industry_sector"] == "IT Services"


def test_auditor_auto_approves_structured_spreadsheet_mode():
    result = AuditorAgent.audit(
        system_prompt="unused",
        preparer_output={
            "extraction_mode": "structured_spreadsheet",
            "extracted_data": {"historical_revenues": [1, 2, 3]},
            "audit_trail": [
                {
                    "field": "historical_revenues",
                    "value": [1, 2, 3],
                    "confidence": 0.95,
                    "source_citation": "IFRS-PnL,BS-INR row 2",
                }
            ],
            "reconciliation_log": "Structured spreadsheet extraction.",
        },
        company_name="Synthetic IT Services Ltd",
    )

    assert result["overall_status"] == "approved"
    assert result["field_verdicts"][0]["status"] == "approved"

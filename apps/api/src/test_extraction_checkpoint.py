from agents.modeling import FinancialModelingAgent


def _base_llm_data():
    return {
        "historical_revenues": [1_000_000_000, 1_200_000_000, 1_350_000_000, 1_500_000_000],
        "historical_ebitda_margins": [0.12, 0.13, 0.14, 0.145],
        "total_borrowings": 400_000_000,
        "lease_liabilities": 50_000_000,
        "ccps_liability": 0,
        "cash_and_equivalents": 150_000_000,
        "net_debt": 300_000_000,
        "shares_outstanding": 100_000_000,
    }


def _base_audit_trail():
    return [
        {
            "field": "historical_revenues",
            "confidence": 0.85,
            "source_citation": "Annual report note 3",
        },
        {
            "field": "historical_ebitda_margins",
            "confidence": 0.82,
            "source_citation": "Annual report note 4",
        },
        {
            "field": "total_borrowings",
            "confidence": 0.8,
            "source_citation": "Balance sheet",
        },
        {
            "field": "cash_and_equivalents",
            "confidence": 0.8,
            "source_citation": "Cash flow statement",
        },
    ]


def test_extraction_checkpoint_passes_for_consistent_extraction():
    checkpoint = FinancialModelingAgent._build_extraction_checkpoint(
        llm_data=_base_llm_data(),
        audit_trail=_base_audit_trail(),
        auditor_status="approved",
        triangulation_result={"overall_verdict": "pass"},
        has_uploaded_documents=True,
        fallback_mode=False,
        company_context={"is_private_company": False},
    )

    assert checkpoint["status"] == "passed"
    assert checkpoint["blocking_issues"] == []


def test_extraction_checkpoint_fails_when_required_fields_missing():
    llm_data = {
        "historical_revenues": [1_000_000_000],
        "historical_ebitda_margins": [0.1],
    }
    checkpoint = FinancialModelingAgent._build_extraction_checkpoint(
        llm_data=llm_data,
        audit_trail=[],
        auditor_status="approved",
        triangulation_result={"overall_verdict": "pass"},
        has_uploaded_documents=True,
        fallback_mode=False,
        company_context={"is_private_company": False},
    )

    assert checkpoint["status"] == "failed"
    assert any("historical_revenues" in issue for issue in checkpoint["blocking_issues"])
    assert any("historical_ebitda_margins" in issue for issue in checkpoint["blocking_issues"])


def test_extraction_checkpoint_fails_for_net_debt_mismatch():
    llm_data = _base_llm_data()
    llm_data["net_debt"] = 900_000_000

    checkpoint = FinancialModelingAgent._build_extraction_checkpoint(
        llm_data=llm_data,
        audit_trail=_base_audit_trail(),
        auditor_status="approved",
        triangulation_result={"overall_verdict": "pass"},
        has_uploaded_documents=True,
        fallback_mode=False,
        company_context={"is_private_company": False},
    )

    assert checkpoint["status"] == "failed"
    assert any("net_debt_reconciliation" in issue for issue in checkpoint["blocking_issues"])

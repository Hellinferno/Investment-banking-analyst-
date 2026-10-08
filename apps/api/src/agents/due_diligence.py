"""External due diligence discovery; no risk verdicts inferred from search results."""
from agents.base import BaseAgent
from tools.research_evidence import ResearchParameters, build_report, collect_evidence
from tools.research_export import export_research
from tools.serpapi_client import SearchError


class DueDiligenceAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict):
        super().__init__("due_diligence", "dd_report", deal_id, input_payload)

    def run(self) -> str:
        try:
            params = ResearchParameters.model_validate(self.input_payload.get("parameters", {}))
            deal = self._get_deal_info()
            self.act("serpapi", "Searching public filings and reported developments for analyst review.")
            evidence = collect_evidence(deal.get("company_name", ""), deal.get("industry", ""), params, diligence=True)
            self.update_payload("research_evidence", evidence)
            report = build_report(evidence, synthesize=params.synthesize, diligence=True)
            report["warnings"].append("Reported allegations are unverified. This is a review checklist, not a legal or risk determination.")
            self.update_payload("research_report", report)
            for path, kind in export_research(deal.get("company_name", "Company"), self.run_id, evidence, report, diligence=True):
                self._register_output(path, kind, "due_diligence")
            if not evidence["sources"]:
                self.fail("No usable diligence sources. No risk assessment was made.")
            else:
                self.complete(confidence=None)
        except SearchError as exc:
            self.fail(str(exc))
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Diligence export or processing failed for run %s", self.run_id)
            self.fail("Diligence discovery could not finish. Check backend configuration and server logs.")
        return self.run_id

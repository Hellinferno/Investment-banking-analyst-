"""SerpApi company research with persistent evidence and reviewable exports."""
from agents.base import BaseAgent
from tools.research_evidence import ResearchParameters, build_report, collect_evidence
from tools.research_export import export_research
from tools.serpapi_client import SearchError


class ResearchAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict):
        super().__init__("research", input_payload.get("task_name", "industry_brief"), deal_id, input_payload)

    def run(self) -> str:
        try:
            params = ResearchParameters.model_validate(self.input_payload.get("parameters", {}))
            deal = self._get_deal_info()
            self.act("serpapi", "Searching public company metadata; uploaded documents are not sent to search.")
            evidence = collect_evidence(deal.get("company_name", ""), deal.get("industry", ""), params)
            self.update_payload("research_evidence", evidence)
            report = build_report(evidence, synthesize=params.synthesize)
            if self.task_name == "buyer_universe":
                report["title"] = "Buyer and transaction discovery"
                report["warnings"].append("Search mentions do not establish buyer interest or an intent to acquire.")
            self.update_payload("research_report", report)
            self.observe(f"Collected {len(evidence['sources'])} sources. Coverage: {evidence['status']}.")
            for path, kind in export_research(deal.get("company_name", "Company"), self.run_id, evidence, report):
                self._register_output(path, kind, "research")
            if not evidence["sources"]:
                self.fail("No usable search evidence. Inspect search coverage and retry; no conclusions were generated.")
            else:
                self.complete(confidence=None)
        except SearchError as exc:
            self.fail(str(exc))
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Research export or processing failed for run %s", self.run_id)
            self.fail("Research could not finish. Check backend configuration and server logs.")
        return self.run_id

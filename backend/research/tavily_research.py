"""Tavily-backed research pipeline."""

from __future__ import annotations
import logging
import os
import re
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


logger = logging.getLogger(__name__)


class TavilyResearch:
    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        client: Any | None = None,
        api_key: str | None = None,
    ):
        self.config = config or {}
        self._client = client
        self.api_key = api_key if api_key is not None else os.getenv("TAVILY_API_KEY")

    def search(self, query: str, **overrides) -> Dict[str, Any]:
        params = {
            "search_depth": self.config.get("search_depth", "basic"),
            "max_results": self.config.get("max_results", 8),
            "timeout": self.config.get("search_timeout_seconds", 30),
            "topic": self.config.get("topic"),
            "include_domains": self.config.get("include_domains"),
            "exclude_domains": self.config.get("exclude_domains"),
            "country": self.config.get("country"),
            "include_answer": self.config.get("include_answer", False),
            "include_raw_content": self.config.get("include_raw_content", False),
            "include_usage": self.config.get("include_usage", True),
        }
        params.update({key: value for key, value in overrides.items() if value is not None})
        params = {key: value for key, value in params.items() if value is not None}
        return self._get_client().search(query=query, **params)

    def extract(self, urls: str | List[str], **overrides) -> Dict[str, Any]:
        params = {
            "extract_depth": self.config.get("extract_depth", "basic"),
            "format": self.config.get("extract_format", "markdown"),
            "timeout": self.config.get("extract_timeout_seconds", 30),
            "include_images": self.config.get("include_images", False),
            "include_favicon": self.config.get("include_favicon", False),
            "include_usage": self.config.get("include_usage", True),
            "chunks_per_source": self.config.get("chunks_per_source", 3),
        }
        params.update({key: value for key, value in overrides.items() if value is not None})
        params = {key: value for key, value in params.items() if value is not None}
        return self._get_client().extract(urls=urls, **params)

    def build_structured_evidence(
        self,
        task: str,
        research_prompt: str = "",
        role_names: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        objectives = self._objectives()
        queries = self._queries(task, research_prompt, objectives)
        source_records: Dict[str, Dict[str, Any]] = {}
        failed_sources: List[str] = []
        logger.info("tavily.generated_search_queries=%s", list(queries.values()))

        for objective in objectives:
            logger.info("tavily.objective=%s", objective["name"])
            query = queries.get(objective["name"])
            if not query:
                continue
            logger.info("tavily.query objective=%s query=%s", objective["name"], query)
            try:
                response = self.search(query)
            except Exception as error:
                failed_sources.append(f"{query}: {self._error_text(error)}")
                logger.warning(
                    "tavily.query_failed objective=%s query=%s error=%s",
                    objective["name"],
                    query,
                    self._error_text(error),
                )
                continue
            results = response.get("results", []) or []
            logger.info(
                "tavily.result_count objective=%s query=%s count=%s",
                objective["name"],
                query,
                len(results),
            )
            if not results:
                failed_sources.append(f"{query}: no Tavily results returned")
            for result in results:
                url = str(result.get("url") or "").strip()
                if not self._is_valid_url(url):
                    failed_sources.append(f"{url or query}: invalid result URL")
                    continue
                source_records.setdefault(
                    url,
                    {
                        "url": url,
                        "title": str(result.get("title") or url).strip(),
                        "snippet": str(result.get("content") or "").strip(),
                        "objective": objective["name"],
                        "score": result.get("score"),
                    },
                )

        max_sources = self._int_config("max_total_sources", 10)
        extract_urls = list(source_records)[:max_sources]
        logger.info("tavily.extract_url_count=%s", len(extract_urls))
        extracted = {}
        if extract_urls:
            try:
                extract_response = self.extract(
                    extract_urls,
                    query=task,
                )
                for item in extract_response.get("results", []) or []:
                    url = str(item.get("url") or "").strip()
                    if url:
                        extracted[url] = item
                logger.info("tavily.extract_result_count=%s", len(extracted))
                for item in extract_response.get("failed_results", []) or []:
                    url = str(item.get("url") or "").strip()
                    reason = str(item.get("error") or item.get("reason") or "").strip()
                    failed_sources.append(
                        f"{url or '(unknown URL)'}: {reason or 'Tavily extract failed'}"
                    )
            except Exception as error:
                failed_sources.append(f"Tavily extract: {self._error_text(error)}")
                logger.warning("tavily.extract_failed error=%s", self._error_text(error))

        structured_objectives = []
        sources = []
        for objective in objectives:
            evidence = []
            for url, record in source_records.items():
                if record["objective"] != objective["name"]:
                    continue
                content = self._content_for(record, extracted.get(url))
                if not content:
                    failed_sources.append(f"{url}: no Tavily content available")
                    continue
                evidence.append(
                    {
                        "objective": objective["name"],
                        "claim": self._claim(objective["name"], task, record),
                        "source_title": record["title"],
                        "source_url": url,
                        "summary": self._summary(content),
                        "confidence": self._confidence(record),
                    }
                )
                sources.append(url)
                if len(evidence) >= self._int_config("max_sources_per_objective", 2):
                    break

            status = "complete" if evidence else "incomplete"
            structured_objectives.append(
                {
                    "name": objective["name"],
                    "status": status,
                    "evidence": evidence,
                }
            )

        missing = [
            f"{item['name']}: no valid Tavily evidence collected."
            for item in structured_objectives
            if item["status"] == "incomplete"
        ]
        complete_count = sum(1 for item in structured_objectives if item["status"] == "complete")
        quality = "strong" if complete_count >= 4 else "moderate" if complete_count >= 2 else "weak"
        role_text = ", ".join(role_names or [])
        summary = (
            f"Tavily research collected evidence for {complete_count} of "
            f"{len(structured_objectives)} objectives for: {task}."
        )
        if not sources:
            summary = (
                f"Tavily research evidence is missing for: {task}. "
                "No valid source pages were collected."
            )
        if role_text:
            summary = f"{summary} Evidence is structured for downstream roles: {role_text}."

        failed_sources = self._unique(failed_sources)
        sources = self._unique(sources)
        logger.info("tavily.failed_sources=%s", failed_sources)
        logger.info("tavily.final_sources=%s", sources)

        return {
            "research_summary": summary,
            "objectives": structured_objectives,
            "missing_information": missing,
            "research_quality": quality,
            "recommended_next_searches": [
                queries[item["name"]]
                for item in structured_objectives
                if item["status"] == "incomplete" and item["name"] in queries
            ],
            "search_queries": [query for query in queries.values() if query],
            "failed_sources": failed_sources,
            "sources": sources,
        }

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is not configured.")
        if TavilyClient is None:
            raise RuntimeError(
                "tavily-python is not installed in the backend runtime."
            )
        self._client = TavilyClient(api_key=self.api_key)
        return self._client

    def _objectives(self) -> List[Dict[str, str]]:
        configured = self.config.get("objectives")
        if isinstance(configured, list) and configured:
            objectives = []
            for item in configured:
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                    query_terms = str(item.get("query_terms") or name).strip()
                else:
                    name = str(item or "").strip()
                    query_terms = name
                if name:
                    objectives.append({"name": name, "query_terms": query_terms})
            if objectives:
                return objectives
        return [
            {"name": "Demand", "query_terms": "market demand customer demand"},
            {"name": "Competitors", "query_terms": "competitors alternatives"},
            {"name": "Pricing", "query_terms": "pricing fees costs revenue model"},
            {"name": "Regulations", "query_terms": "regulations compliance legal requirements"},
            {"name": "Customer pain points", "query_terms": "customer pain points user behavior"},
            {"name": "Technical feasibility", "query_terms": "technical feasibility implementation risk"},
            {"name": "Risks", "query_terms": "business risks operational risks"},
        ]

    def _queries(
        self,
        task: str,
        research_prompt: str,
        objectives: List[Dict[str, str]],
    ) -> Dict[str, str]:
        base = self._compact_query(task)
        prompt_terms = self._prompt_terms(research_prompt)
        max_queries = self._search_query_limit()
        queries = {}
        for objective in objectives[:max_queries]:
            suffix = " ".join(
                part
                for part in [objective.get("query_terms", ""), prompt_terms]
                if part
            )
            queries[objective["name"]] = self._compact_query(f"{base} {suffix}")
        return queries

    def _search_query_limit(self) -> int:
        max_queries = self._int_config("max_search_queries", 6)
        if max_queries == 1 and not self.config.get("allow_single_search_query", False):
            logger.warning(
                "tavily.max_search_queries=1 ignored because "
                "allow_single_search_query is not enabled"
            )
            return 6
        return max_queries

    @staticmethod
    def _compact_query(value: str) -> str:
        text = " ".join(str(value or "").split())
        return text[:350]

    @staticmethod
    def _prompt_terms(value: str) -> str:
        text = str(value or "")
        lines = [
            line.strip("-: ")
            for line in text.splitlines()
            if any(
                marker in line.lower()
                for marker in ("research", "competitor", "pricing", "regulation", "risk")
            )
        ]
        return " ".join(lines[:3])[:180]

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        path = parsed.path.lower()
        query = parsed.query.lower()
        if path.startswith("/search") and "q=" in query:
            return False
        return True

    @staticmethod
    def _content_for(record: Dict[str, Any], extracted: Dict[str, Any] | None) -> str:
        if extracted:
            content = str(extracted.get("raw_content") or "").strip()
            if content:
                return content
        return str(record.get("snippet") or "").strip()

    @staticmethod
    def _claim(objective: str, task: str, record: Dict[str, Any]) -> str:
        title = record.get("title") or record.get("url")
        return f"{title} provides {objective.lower()} evidence relevant to {task}."

    @staticmethod
    def _summary(content: str, max_chars: int = 500) -> str:
        text = re.sub(r"\s+", " ", str(content or "")).strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."

    @staticmethod
    def _confidence(record: Dict[str, Any]) -> str:
        score = record.get("score")
        try:
            value = float(score)
        except (TypeError, ValueError):
            return "medium"
        if value >= 0.75:
            return "high"
        if value >= 0.45:
            return "medium"
        return "low"

    def _int_config(self, key: str, default: int) -> int:
        try:
            return max(1, int(self.config.get(key, default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _error_text(error: Exception) -> str:
        return str(error) or error.__class__.__name__

    @staticmethod
    def _unique(items: Iterable[str]) -> List[str]:
        seen = set()
        unique = []
        for item in items:
            text = str(item or "").strip()
            if text and text not in seen:
                seen.add(text)
                unique.append(text)
        return unique

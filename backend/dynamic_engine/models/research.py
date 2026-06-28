"""Structured research models."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List
from urllib.parse import urlparse


_VALID_CONFIDENCE = {"high", "medium", "low"}
_VALID_OBJECTIVE_STATUS = {"complete", "partial", "incomplete"}
_VALID_QUALITY = {"strong", "moderate", "weak"}


@dataclass
class StructuredResearch:
    status: str = "success"
    fallback_used: bool = False
    fallback_reason: str | None = None
    task: str = ""
    research_summary: str = ""
    objectives: List[Dict[str, Any]] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    research_quality: str = "weak"
    recommended_next_searches: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)
    shared_evidence: List[str] = field(default_factory=list)
    findings_by_agent: Dict[str, List[str]] = field(default_factory=dict)
    failed_sources: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    raw_brief: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "task": self.task,
            "research_summary": self.research_summary,
            "objectives": self.objectives,
            "missing_information": self.missing_information,
            "research_quality": self.research_quality,
            "recommended_next_searches": self.recommended_next_searches,
            "search_queries": self.search_queries,
            "shared_evidence": self.shared_evidence,
            "findings_by_agent": self.findings_by_agent,
            "failed_sources": self.failed_sources,
            "open_questions": self.open_questions,
            "sources": self.sources,
            "raw_brief": self.raw_brief,
        }

    @classmethod
    def from_brief(
        cls,
        task: str,
        raw_brief: str,
        findings: List[Dict[str, Any]],
        status: str = "success",
        fallback_reason: str | None = None,
    ) -> "StructuredResearch":
        fallback_used = status == "fallback"
        raw_text = str(raw_brief or "")
        findings_by_agent = cls._findings_by_agent(findings)
        payload = cls._extract_json_object(raw_text)

        if isinstance(payload, dict):
            return cls._from_structured_payload(
                task=task,
                raw_brief=raw_text,
                findings_by_agent=findings_by_agent,
                payload=payload,
                status=status,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )

        return cls._from_legacy_brief(
            task=task,
            raw_brief=raw_text,
            findings_by_agent=findings_by_agent,
            status=status,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    @classmethod
    def _from_structured_payload(
        cls,
        task: str,
        raw_brief: str,
        findings_by_agent: Dict[str, List[str]],
        payload: Dict[str, Any],
        status: str,
        fallback_used: bool,
        fallback_reason: str | None,
    ) -> "StructuredResearch":
        failed_sources = cls._normalize_failed_sources(payload.get("failed_sources", []))
        missing_information = cls._normalize_string_list(
            payload.get("missing_information", [])
        )
        objectives, objective_sources, shared_evidence, objective_missing, rejected = (
            cls._normalize_objectives(payload.get("objectives", []))
        )
        failed_sources = cls._unique([*failed_sources, *rejected])
        missing_information = cls._unique([*missing_information, *objective_missing])

        payload_sources, rejected_sources = cls._normalize_sources(payload.get("sources", []))
        sources = cls._unique([*objective_sources, *payload_sources])
        failed_sources = cls._unique([*failed_sources, *rejected_sources])

        open_questions = cls._normalize_string_list(payload.get("open_questions", []))
        if not open_questions:
            open_questions = list(missing_information)

        research_quality = cls._normalized_quality(payload.get("research_quality"))
        derived_quality = cls._derive_quality(objectives, sources, fallback_used)
        if cls._quality_rank(derived_quality) < cls._quality_rank(research_quality):
            research_quality = derived_quality

        return cls(
            status=status,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            task=task,
            research_summary=str(payload.get("research_summary") or "").strip(),
            objectives=objectives,
            missing_information=missing_information,
            research_quality=research_quality,
            recommended_next_searches=cls._normalize_string_list(
                payload.get("recommended_next_searches", [])
            ),
            search_queries=cls._normalize_string_list(payload.get("search_queries", [])),
            shared_evidence=shared_evidence,
            findings_by_agent=findings_by_agent,
            failed_sources=failed_sources,
            open_questions=open_questions,
            sources=sources,
            raw_brief=raw_brief,
        )

    @classmethod
    def _from_legacy_brief(
        cls,
        task: str,
        raw_brief: str,
        findings_by_agent: Dict[str, List[str]],
        status: str,
        fallback_used: bool,
        fallback_reason: str | None,
    ) -> "StructuredResearch":
        failed_sources = cls._split_section(raw_brief, "Failed Sources")
        sources, rejected_sources = cls._normalize_sources(
            cls._split_section(raw_brief, "Sources")
        )
        failed_sources = cls._unique([*failed_sources, *rejected_sources])
        missing_information = cls._split_section(raw_brief, "Missing Information")
        open_questions = cls._split_section(raw_brief, "Open Questions")
        if not open_questions:
            open_questions = list(missing_information)

        quality = cls._normalized_quality(
            cls._section_text(raw_brief, "Research Quality")
        )
        derived_quality = cls._derive_quality([], sources, fallback_used)
        if cls._quality_rank(derived_quality) < cls._quality_rank(quality):
            quality = derived_quality

        return cls(
            status=status,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            task=task,
            research_summary=cls._section_text(raw_brief, "Research Summary"),
            missing_information=missing_information,
            research_quality=quality,
            search_queries=cls._split_section(raw_brief, "Search Queries Used"),
            shared_evidence=cls._split_section(raw_brief, "Shared Evidence"),
            findings_by_agent=findings_by_agent,
            failed_sources=failed_sources,
            open_questions=open_questions,
            sources=sources,
            raw_brief=raw_brief,
        )

    @staticmethod
    def _findings_by_agent(findings: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        findings_by_agent: Dict[str, List[str]] = {}
        for finding in findings:
            agent = str(finding.get("agent") or "Unknown")
            content = str(finding.get("content") or "")
            findings_by_agent.setdefault(agent, []).append(content)
        return findings_by_agent

    @staticmethod
    def _extract_json_object(raw: str) -> Dict[str, Any] | None:
        text = str(raw or "").strip()
        if not text:
            return None

        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        elif not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None
            text = match.group(0)

        try:
            data = json.loads(text)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    @classmethod
    def _normalize_objectives(
        cls,
        objectives: Any,
    ) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str], List[str]]:
        normalized = []
        sources = []
        shared_evidence = []
        missing = []
        rejected = []

        if not isinstance(objectives, list):
            return normalized, sources, shared_evidence, missing, rejected

        for item in objectives:
            if not isinstance(item, dict):
                continue

            name = str(item.get("name") or item.get("objective") or "").strip()
            if not name:
                continue

            evidence_items = []
            for evidence in item.get("evidence", []) or []:
                normalized_evidence, failure = cls._normalize_evidence(evidence, name)
                if normalized_evidence:
                    evidence_items.append(normalized_evidence)
                    source_url = normalized_evidence["source_url"]
                    sources.append(source_url)
                    shared_evidence.append(
                        cls._evidence_summary(name, normalized_evidence)
                    )
                elif failure:
                    rejected.append(failure)

            raw_status = str(item.get("status") or "").strip().lower()
            if raw_status not in _VALID_OBJECTIVE_STATUS:
                raw_status = "complete" if evidence_items else "incomplete"
            if not evidence_items and raw_status != "incomplete":
                raw_status = "incomplete"
                missing.append(f"{name}: no valid source evidence collected.")
            elif raw_status == "incomplete":
                missing.append(f"{name}: objective not fully evidenced.")

            normalized.append(
                {
                    "name": name,
                    "status": raw_status,
                    "evidence": evidence_items,
                }
            )

        return (
            normalized,
            cls._unique(sources),
            cls._unique(shared_evidence),
            cls._unique(missing),
            cls._unique(rejected),
        )

    @classmethod
    def _normalize_evidence(
        cls,
        evidence: Any,
        objective_name: str,
    ) -> tuple[Dict[str, Any] | None, str]:
        if not isinstance(evidence, dict):
            return None, ""

        source_url = str(evidence.get("source_url") or evidence.get("url") or "").strip()
        if not cls._is_valid_source_url(source_url):
            return None, cls._failure_text(source_url, "invalid or search/error URL")

        title = str(evidence.get("source_title") or evidence.get("title") or "").strip()
        summary = str(evidence.get("summary") or evidence.get("extracted_summary") or "").strip()
        claim = str(evidence.get("claim") or "").strip()
        if cls._looks_like_error_content(" ".join([title, summary, claim])):
            return None, cls._failure_text(source_url, "error or blocked page content")
        if not (claim and summary):
            return None, cls._failure_text(source_url, "missing claim or summary")

        confidence = str(evidence.get("confidence") or "medium").strip().lower()
        if confidence not in _VALID_CONFIDENCE:
            confidence = "medium"

        return (
            {
                "objective": str(evidence.get("objective") or objective_name).strip(),
                "claim": claim,
                "source_title": title or source_url,
                "source_url": source_url,
                "summary": summary,
                "confidence": confidence,
            },
            "",
        )

    @classmethod
    def _normalize_sources(cls, sources: Any) -> tuple[List[str], List[str]]:
        valid = []
        rejected = []
        for item in cls._normalize_string_list(sources):
            if cls._is_valid_source_url(item):
                valid.append(item)
            else:
                rejected.append(cls._failure_text(item, "invalid source URL"))
        return cls._unique(valid), cls._unique(rejected)

    @staticmethod
    def _normalize_string_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = re.split(r"\n|;", value)
        elif isinstance(value, list):
            items = value
        else:
            items = [value]

        normalized = []
        for item in items:
            text = str(item or "").strip()
            text = re.sub(r"^\s*[-*]\s*", "", text)
            if text and text.lower().strip(".") not in {"none", "n/a", "null"}:
                normalized.append(text)
        return StructuredResearch._unique(normalized)

    @staticmethod
    def _normalize_failed_sources(value: Any) -> List[str]:
        if isinstance(value, list):
            normalized = []
            for item in value:
                if isinstance(item, dict):
                    url = str(item.get("url") or item.get("source_url") or "").strip()
                    reason = str(item.get("reason") or item.get("failure_reason") or "").strip()
                    normalized.append(
                        f"{url}: {reason}".strip(": ") if url or reason else ""
                    )
                else:
                    normalized.append(str(item or "").strip())
            return StructuredResearch._normalize_string_list(normalized)
        return StructuredResearch._normalize_string_list(value)

    @staticmethod
    def _is_valid_source_url(url: str) -> bool:
        text = str(url or "").strip()
        lower = text.lower()
        if not text or lower.startswith("about:") or "<empty>" in lower:
            return False
        if "static-pages/418" in lower or "unexpected error" in lower:
            return False

        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False

        host = parsed.hostname or ""
        host = host.lower()
        path = parsed.path.lower()
        query = parsed.query.lower()
        if path.startswith("/search") and "q=" in query:
            return False

        return True

    @staticmethod
    def _looks_like_error_content(text: str) -> bool:
        lower = str(text or "").lower()
        markers = (
            "<empty>",
            "unexpected error",
            "please try again",
            "access denied",
            "blocked",
            "captcha",
            "anti-bot",
            "http 418",
            "error page",
            "no meaningful content",
            "about:blank",
        )
        return any(marker in lower for marker in markers)

    @staticmethod
    def _failure_text(url: str, reason: str) -> str:
        url = str(url or "").strip() or "(no URL)"
        return f"{url}: {reason}"

    @staticmethod
    def _evidence_summary(objective_name: str, evidence: Dict[str, Any]) -> str:
        title = evidence.get("source_title") or evidence.get("source_url")
        return f"{objective_name}: {evidence.get('claim')} ({title})"

    @staticmethod
    def _normalized_quality(value: Any) -> str:
        quality = str(value or "").strip().lower()
        return quality if quality in _VALID_QUALITY else "weak"

    @staticmethod
    def _derive_quality(
        objectives: List[Dict[str, Any]],
        sources: List[str],
        fallback_used: bool,
    ) -> str:
        if fallback_used:
            return "weak"
        complete = sum(1 for item in objectives if item.get("status") == "complete")
        if complete >= 4 and len(sources) >= 4:
            return "strong"
        if complete >= 2 and len(sources) >= 2:
            return "moderate"
        return "weak"

    @staticmethod
    def _quality_rank(value: str) -> int:
        return {"weak": 1, "moderate": 2, "strong": 3}.get(value, 1)

    @classmethod
    def _split_section(cls, text: str, heading: str) -> List[str]:
        section = cls._section_text(text, heading)
        if not section:
            return []
        lines = re.split(r"\n|;", section)
        if len(lines) == 1:
            lines = re.split(r"\s+-\s+", section)
        return cls._normalize_string_list(lines)

    @staticmethod
    def _section_text(text: str, heading: str) -> str:
        headings = (
            "Research Summary",
            "Search Queries Used",
            "Shared Evidence",
            "Failed Sources",
            "Missing Information",
            "Research Quality",
            "Open Questions",
            "Sources",
            "Original Task",
        )
        stop_pattern = "|".join(re.escape(item) for item in headings)
        match = re.search(
            rf"(?ims)^\s*{re.escape(heading)}\s*:?\s*(.*?)(?=^\s*(?:{stop_pattern})\s*:|\Z)",
            str(text or ""),
        )
        if not match:
            return ""
        return " ".join(match.group(1).split())

    @staticmethod
    def _unique(items: List[str]) -> List[str]:
        seen = set()
        unique = []
        for item in items:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            unique.append(text)
        return unique

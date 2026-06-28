import re
from dataclasses import dataclass


CASUAL_CHAT = "casual_chat"
BUSINESS_IDEA = "business_idea"
REFINEMENT = "refinement"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentResult:
    intent: str
    confidence: float
    reason: str


_CASUAL_PATTERNS = (
    r"^(hi|hello|hey|yo|hiya|howdy)[!. ]*$",
    r"^(hi|hello|hey|yo|hiya|howdy)[,!. ]+(how are you|how are you doing|how's it going)[?!. ]*$",
    r"^(good morning|good afternoon|good evening)[!. ]*$",
    r"^(how are you|how are you doing|how's it going)[?!. ]*$",
    r"^(thanks|thank you|thx|appreciate it)[!. ]*$",
    r"^(who are you|what can you do)[?!. ]*$",
)

_BUSINESS_PATTERNS = (
    r"\bi want to build\b",
    r"\bhelp me validate\b",
    r"\bvalidate this (startup|idea|business|product)\b",
    r"\bturn this idea into\b",
    r"\bturn .* into an? mvp\b",
    r"\bmy (company|startup|business|team) (has|needs|wants)\b",
    r"\b(build|create|launch|develop) (a |an |the )?.*(app|platform|tool|service|business|product)\b",
    r"\bcan this (product|startup|business|idea) work\b",
    r"\bstartup\b",
    r"\bmvp\b",
    r"\bbusiness idea\b",
    r"\bproduct idea\b",
)

_REFINEMENT_PATTERNS = (
    r"\b(refine|revise|update|change|adjust|improve|iterate|expand|shorten|simplify)\b",
    r"\b(add|remove|replace|defer|prioritize|focus on)\b",
    r"\b(previous|existing|current|that|this) (plan|blueprint|report|idea|mvp)\b",
)


def classify_intent(message: str, has_existing_chat: bool = False) -> IntentResult:
    text = " ".join(str(message or "").strip().lower().split())
    if not text:
        return IntentResult(UNKNOWN, 0.0, "empty_message")

    if any(re.search(pattern, text, re.IGNORECASE) for pattern in _CASUAL_PATTERNS):
        return IntentResult(CASUAL_CHAT, 0.95, "casual_pattern")

    if has_existing_chat and any(
        re.search(pattern, text, re.IGNORECASE) for pattern in _REFINEMENT_PATTERNS
    ):
        return IntentResult(REFINEMENT, 0.85, "refinement_pattern")

    if any(re.search(pattern, text, re.IGNORECASE) for pattern in _BUSINESS_PATTERNS):
        return IntentResult(BUSINESS_IDEA, 0.9, "business_pattern")

    word_count = len(text.split())
    if has_existing_chat and word_count >= 4:
        return IntentResult(REFINEMENT, 0.6, "existing_chat_context")

    if word_count >= 10 and any(
        marker in text
        for marker in (
            "customer",
            "market",
            "revenue",
            "pricing",
            "users",
            "platform",
            "app",
            "service",
            "problem",
        )
    ):
        return IntentResult(BUSINESS_IDEA, 0.65, "business_context_terms")

    return IntentResult(UNKNOWN, 0.35, "ambiguous")


def casual_chat_reply(message: str) -> str:
    text = str(message or "").strip().lower()
    if "what can you do" in text or "who are you" in text:
        return (
            "I'm Genesis, your startup blueprint workspace. I can help brainstorm "
            "ideas, evaluate products, refine an existing plan, or turn a business "
            "concept into an MVP direction."
        )
    if "thank" in text or text in {"thanks", "thx"}:
        return "You're welcome. I'm ready when you want to keep shaping the idea."
    return (
        "I'm doing well. Ready to help you brainstorm ideas, evaluate products, "
        "or continue a previous discussion."
    )


def unknown_intent_reply() -> str:
    return (
        "I can help with startup ideas, MVP planning, product validation, or refining "
        "an existing blueprint. What would you like to work on?"
    )

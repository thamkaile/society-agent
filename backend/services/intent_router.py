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
    r"\bi have an? idea\b",
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

_BUSINESS_NOUNS = (
    "agency",
    "app",
    "business",
    "company",
    "consultancy",
    "consulting",
    "consultant",
    "firm",
    "platform",
    "product",
    "saas",
    "service",
    "shop",
    "store",
    "studio",
    "tool",
)

_BUSINESS_CONTEXT_MARKERS = (
    "b2b",
    "b2c",
    "client",
    "clients",
    "company",
    "competitor",
    "competitors",
    "customer",
    "customers",
    "industry",
    "license",
    "licenses",
    "logistics",
    "market",
    "problem",
    "revenue",
    "sector",
    "startup",
    "supplier",
    "users",
)

_LOCATION_PATTERN = r"\b(?:in|for|across|around|near)\s+[a-z][a-z .'-]{2,}\b"

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

    if _looks_like_structured_business_input(text):
        return IntentResult(BUSINESS_IDEA, 0.88, "structured_business_input")

    if _has_business_intention_with_context(text):
        return IntentResult(BUSINESS_IDEA, 0.82, "business_intention_context")

    word_count = len(text.split())
    if has_existing_chat and word_count >= 4:
        return IntentResult(REFINEMENT, 0.6, "existing_chat_context")

    if word_count >= 10 and any(
        marker in text
        for marker in (*_BUSINESS_CONTEXT_MARKERS, "pricing")
    ):
        return IntentResult(BUSINESS_IDEA, 0.65, "business_context_terms")

    return IntentResult(UNKNOWN, 0.35, "ambiguous")


def _looks_like_structured_business_input(text: str) -> bool:
    required_fields = (
        "product:",
        "target customer:",
        "problem:",
    )
    if not all(field in text for field in required_fields):
        return False

    def _field_has_value(label: str) -> bool:
        match = re.search(rf"{re.escape(label)}\s*([^\n\r]+)", text, re.IGNORECASE)
        if not match:
            return False
        value = match.group(1).strip(" .,:;-")
        return len(value) >= 3

    return all(_field_has_value(field) for field in required_fields)


def _has_business_intention_with_context(text: str) -> bool:
    intent_match = re.search(
        r"\b(?:i|we)\s+(?:want|would like|plan|intend|need|hope)\s+to\s+"
        r"(?:start|open|launch|build|create|develop|set up)\b"
        r"|\b(?:i'?m|we'?re)\s+(?:thinking of|planning to|looking to|trying to)\s+"
        r"(?:start|open|launch|build|create|develop|set up)\b"
        r"|\bcan\s+(?:i|we)\s+(?:start|open|launch|build|create|develop|set up)\b",
        text,
        re.IGNORECASE,
    )
    if not intent_match:
        return False

    has_business_noun = any(re.search(rf"\b{re.escape(noun)}\b", text) for noun in _BUSINESS_NOUNS)
    has_context_marker = any(
        re.search(rf"\b{re.escape(marker)}\b", text)
        for marker in _BUSINESS_CONTEXT_MARKERS
    )
    has_location = bool(re.search(_LOCATION_PATTERN, text, re.IGNORECASE))
    return has_business_noun and (has_context_marker or has_location or len(text.split()) >= 7)


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

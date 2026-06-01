import re

SPEAKER_RE = re.compile(r"^\s*(INTERVIEWER|CANDIDATE)\s*:\s*(.*)$")
BEHAVIORAL_PATTERNS = [
    re.compile(r"\btell me about a time\b", re.IGNORECASE),
    re.compile(r"\bgive me an example\b", re.IGNORECASE),
    re.compile(r"\bdescribe a situation\b", re.IGNORECASE),
    re.compile(r"\bwalk me through a time\b", re.IGNORECASE),
    re.compile(r"\bwhen have you\b", re.IGNORECASE),
    re.compile(r"\bwhat's a time\b", re.IGNORECASE),
]
NON_QUESTION_PATTERNS = [
    re.compile(r"\bhow('?s| is) your day\b", re.IGNORECASE),
    re.compile(r"\bnice to meet you\b", re.IGNORECASE),
    re.compile(r"\bcan you hear me\b", re.IGNORECASE),
    re.compile(r"\bcan you see my screen\b", re.IGNORECASE),
    re.compile(r"\bany trouble with (the )?(video|audio|link)\b", re.IGNORECASE),
    re.compile(r"\bthanks for joining\b", re.IGNORECASE),
    re.compile(r"\bshall we get started\b", re.IGNORECASE),
]
FOLLOW_UP_PATTERNS = [
    re.compile(r"^\s*can you\b", re.IGNORECASE),
    re.compile(r"^\s*could you\b", re.IGNORECASE),
    re.compile(r"^\s*would you\b", re.IGNORECASE),
    re.compile(r"^\s*you mentioned\b", re.IGNORECASE),
    re.compile(r"^\s*on [a-z0-9_-]+", re.IGNORECASE),
    re.compile(r"^\s*when you said\b", re.IGNORECASE),
    re.compile(r"^\s*tell me more\b", re.IGNORECASE),
    re.compile(r"^\s*go deeper\b", re.IGNORECASE),
    re.compile(r"^\s*what happened next\b", re.IGNORECASE),
    re.compile(r"^\s*what broke\b", re.IGNORECASE),
    re.compile(r"^\s*what was your role\b", re.IGNORECASE),
    re.compile(r"^\s*how exactly\b", re.IGNORECASE),
    re.compile(r"^\s*be more specific\b", re.IGNORECASE),
    re.compile(r"^\s*walk me through\b", re.IGNORECASE),
]
CLARIFYING_PATTERNS = [
    re.compile(r"\bclarify\b", re.IGNORECASE),
    re.compile(r"\bmore specific\b", re.IGNORECASE),
    re.compile(r"\bwhat exactly\b", re.IGNORECASE),
    re.compile(r"\bcan you expand\b", re.IGNORECASE),
    re.compile(r"\bhelp me understand\b", re.IGNORECASE),
    re.compile(r"\bwhat do you mean\b", re.IGNORECASE),
]
DEEPENING_PATTERNS = [
    re.compile(r"\bwhat broke\b", re.IGNORECASE),
    re.compile(r"\bwhat happened next\b", re.IGNORECASE),
    re.compile(r"\bwhy\b", re.IGNORECASE),
    re.compile(r"\btrade-?off\b", re.IGNORECASE),
    re.compile(r"\bedge case\b", re.IGNORECASE),
    re.compile(r"\bon [a-z0-9_-]+", re.IGNORECASE),
    re.compile(r"\byou mentioned\b", re.IGNORECASE),
]

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawlite.workspace.loader import WorkspaceLoader
from clawlite.workspace.user_profile import WorkspaceUserProfile


@dataclass(slots=True)
class EnforcementResult:
    text: str
    persist_allowed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class IdentityEnforcer:
    _IDENTITY_NAME_RE = re.compile(r"^\s*[-*]\s*Name:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    _PROVIDER_CLAUSE_RE = re.compile(
        r"^\s*as\s+(?:an?\s+)?(?:ai\s+)?(?:language\s+model|assistant)(?:[^,.\n]{0,120})?,\s*",
        re.IGNORECASE,
    )
    _PROVIDER_SENTENCE_RE = re.compile(
        r"^\s*(?:i\s+am|i'm|sou\s+um)\s+(?:an?\s+)?(?:ai\s+)?(?:language\s+model|assistant|modelo\s+de\s+linguagem|assistente)(?:[^.!?\n]{0,120})?[.!?]?\s*",
        re.IGNORECASE,
    )
    _PROVIDER_BRAND_RE = re.compile(
        r"\b(?:openai|anthropic|google|gemini|claude|groq|meta|mistral|xai|grok)\s+(?:assistant|model)\b",
        re.IGNORECASE,
    )
    _PROVIDER_GENERATED_RE = re.compile(
        r"\b(?:generated|created|provided)\s+by\s+(?:openai|anthropic|google|gemini|claude|groq|meta|mistral|xai|grok)\b",
        re.IGNORECASE,
    )
    _LANGUAGE_GUARD_RE = re.compile(r"always respond in the same language|mesma linguagem", re.IGNORECASE)
    _PT_HINT_RE = re.compile(r"\b(você|voce|para|com|isso|sobre|agora|arquivo|resposta)\b", re.IGNORECASE)
    _EN_HINT_RE = re.compile(r"\b(the|this|that|with|about|file|response|now|please)\b", re.IGNORECASE)
    _CONCISE_HINT_RE = re.compile(r"\bconcise|conciso|curtas|curto\b", re.IGNORECASE)

    def __init__(self, workspace_path: str | Path | None = None, *, workspace_loader: WorkspaceLoader | None = None) -> None:
        if workspace_loader is not None:
            self.workspace_loader = workspace_loader
        else:
            self.workspace_loader = WorkspaceLoader(workspace_path=workspace_path)

    @staticmethod
    def _compact(text: str) -> str:
        return " ".join(str(text or "").split()).strip()

    @classmethod
    def _guess_language(cls, text: str) -> str:
        clean = cls._compact(text).lower()
        if not clean:
            return ""
        pt_hits = len(cls._PT_HINT_RE.findall(clean))
        en_hits = len(cls._EN_HINT_RE.findall(clean))
        if pt_hits >= en_hits + 2:
            return "pt"
        if en_hits >= pt_hits + 2:
            return "en"
        return ""

    def _identity_name(self, identity_text: str) -> str:
        match = self._IDENTITY_NAME_RE.search(str(identity_text or ""))
        if match is None:
            return "ClawLite"
        name = self._compact(match.group(1))
        return name or "ClawLite"

    def _sanitize_provider_contamination(self, text: str, *, identity_name: str) -> str:
        clean = str(text or "")
        clean = self._PROVIDER_CLAUSE_RE.sub("", clean)
        clean = self._PROVIDER_SENTENCE_RE.sub("", clean)
        clean = self._PROVIDER_BRAND_RE.sub(identity_name, clean)
        clean = re.sub(r"\s+([,.;:!?])", r"\1", clean)
        clean = re.sub(r"([.?!])(?=[^\s.?!])", r"\1 ", clean)
        return self._compact(clean.strip(" \t\r\n,;:-"))

    def enforce(
        self,
        *,
        user_text: str,
        output_text: str,
        user_profile: WorkspaceUserProfile | None = None,
    ) -> EnforcementResult:
        docs = self.workspace_loader.read(["IDENTITY.md", "SOUL.md", "USER.md"])
        identity_name = self._identity_name(docs.get("IDENTITY.md", ""))
        soul_text = docs.get("SOUL.md", "")
        profile = user_profile or self.workspace_loader.user_profile()

        original = self._compact(output_text)
        sanitized = self._sanitize_provider_contamination(original, identity_name=identity_name)
        if not sanitized:
            sanitized = identity_name

        warnings: list[str] = []
        violations: list[str] = []

        if sanitized != original:
            warnings.append("provider_contamination_rewritten")

        residual_brand = self._PROVIDER_BRAND_RE.search(sanitized)
        residual_generated = self._PROVIDER_GENERATED_RE.search(sanitized)
        if residual_brand is not None or residual_generated is not None:
            violations.append("provider_contamination_residual")

        if self._LANGUAGE_GUARD_RE.search(soul_text):
            user_language = self._guess_language(user_text)
            output_language = self._guess_language(sanitized)
            if user_language and output_language and user_language != output_language:
                warnings.append(f"language_mismatch:{user_language}->{output_language}")

        profile_hint = " ".join([*profile.preferences, *profile.working_style])
        if self._CONCISE_HINT_RE.search(profile_hint) and len(sanitized) > 2400:
            warnings.append("response_too_verbose_for_user_profile")

        return EnforcementResult(
            text=sanitized,
            persist_allowed=not violations,
            violations=violations,
            warnings=warnings,
            metadata={
                "identity_name": identity_name,
                "user_profile_timezone": profile.timezone,
                "user_profile_preferred_name": profile.preferred_name or profile.name,
                "rewritten": sanitized != original,
            },
        )

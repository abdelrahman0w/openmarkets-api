import re
from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError

from src.exceptions import SummarizerBusyError
from src.exceptions import SummarizerError
from src.settings import settings
from src.utils import Singleton


INSTRUCTION = (
    "You summarize the disclosures of the Egyptian Exchange (EGX) for investors. "
    "Summarize the attached document, read it with the url context tool, "
    "the announcement's own text is only its context. "
    "Use only the document and the announcement, never what you know besides. "
    "Keep every number, amount, percentage, date, and name exactly as written, "
    "never estimate one. Write the English fields in English, "
    "and the Arabic ones in Modern Standard Arabic. "
    "The summary is two or three sentences. "
    "The key points are at most four short ones, none when there are none."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "The summary, in English."},
        "summary_ar": {"type": "string", "description": "The summary, in Arabic."},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The key facts, in English.",
        },
        "key_points_ar": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The key facts, in Arabic.",
        },
    },
    "required": ["summary", "summary_ar", "key_points", "key_points_ar"],
}


BUSY = {429, 500, 502, 503, 504}
RETRY_DELAY = re.compile(
    r'retry in (\d+(?:\.\d+)?)\s*s|"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"',
    re.IGNORECASE,
)
DAILY_QUOTA = re.compile(r"per[\s_-]*day", re.IGNORECASE)


def _retry_after(response: httpx.Response) -> float | None:
    if match := RETRY_DELAY.search(response.text):
        return float(match.group(1) or match.group(2))
    try:
        return float(response.headers["retry-after"])
    except KeyError, ValueError:
        return None


class NewsSummaryDraft(BaseModel):
    summary: str
    summary_ar: str
    key_points: list[str] = Field(default_factory=list, max_length=6)
    key_points_ar: list[str] = Field(default_factory=list, max_length=6)
    read_attachments: bool = False


def _steps(
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    steps = body.get("steps")
    if not isinstance(steps, list):
        raise SummarizerError(
            f"Gemini answered without steps, it had {sorted(body)}",
        )

    return [step for step in steps if isinstance(step, dict)]


def _output_text(
    steps: list[dict[str, Any]],
) -> str:
    return "".join(
        part["text"]
        for step in steps
        if step.get("type") == "model_output"
        for part in step.get("content") or []
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )


def _statuses(value: object) -> list[str]:
    if isinstance(value, dict):
        return [
            status
            for key, item in value.items()
            for status in (
                [str(item)]
                if key == "status" and not isinstance(item, (dict, list))
                else _statuses(item)
            )
        ]
    if isinstance(value, list):
        return [status for item in value for status in _statuses(item)]

    return []


def _retrievals(steps: list[dict[str, Any]]) -> list[str]:
    return [
        status
        for step in steps
        if step.get("type") == "url_context_result"
        for status in _statuses(step)
    ]


class GeminiService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
    ) -> None:
        self._client = client
        self.model = model

    async def summarize_news(
        self,
        announcement: str,
        *,
        attachments: Sequence[str] = (),
    ) -> NewsSummaryDraft:
        prompt = announcement
        if attachments:
            prompt += "\n\nThe attached document:\n" + "\n".join(attachments)

        body: dict[str, Any] = {
            "model": self.model,
            "system_instruction": INSTRUCTION,
            "input": prompt,
            "store": False,
            "generation_config": {
                "temperature": 0.2,
                "thinking_level": "low",
            },
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": SCHEMA,
            },
        }
        if attachments:
            body["tools"] = [{"type": "url_context"}]

        steps = _steps(await self._interact(body))
        text = _output_text(steps)
        try:
            draft = NewsSummaryDraft.model_validate_json(text)
        except ValidationError as exc:
            raise SummarizerError(
                f"Gemini's summary did not match its schema: {text[:200]!r}",
            ) from exc

        if not attachments:
            return draft

        retrievals = _retrievals(steps)
        if not any("success" in status.lower() for status in retrievals):
            kinds = sorted({str(step.get("type")) for step in steps})

            raise SummarizerError(
                "Gemini could not read the attachment, "
                f"it reported {retrievals or 'no retrieval'}, its steps were {kinds}",
            )

        return draft.model_copy(
            update={
                "read_attachments": True,
            },
        )

    async def _interact(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post("/interactions", json=body)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SummarizerBusyError("Gemini took too long to answer") from exc
        except httpx.HTTPStatusError as exc:
            status, text = exc.response.status_code, exc.response.text[:300]
            if status in BUSY:
                raise SummarizerBusyError(
                    f"Gemini answered {status}: {text}",
                    retry_after_seconds=_retry_after(exc.response),
                    daily=status == 429 and bool(DAILY_QUOTA.search(exc.response.text)),
                ) from exc

            raise SummarizerError(f"Gemini answered {status}: {text}") from exc
        except httpx.RequestError as exc:
            raise SummarizerBusyError("Gemini could not be reached") from exc

        try:
            answer = response.json()
        except ValueError as exc:
            raise SummarizerError(
                "Gemini answered with something other than json",
            ) from exc
        if not isinstance(answer, dict):
            raise SummarizerError(
                "Gemini answered with something other than an object",
            )

        return answer

    async def close(self) -> None:
        await self._client.aclose()


class GeminiConnection(Singleton[GeminiService | None]):
    @classmethod
    def create(cls) -> GeminiService | None:
        gemini = settings.gemini
        if gemini.api_key is None:
            return None

        return GeminiService(
            httpx.AsyncClient(
                base_url=gemini.base_url,
                headers={
                    "x-goog-api-key": gemini.api_key.get_secret_value(),
                    "Api-Revision": gemini.api_revision,
                },
                timeout=httpx.Timeout(gemini.timeout_seconds, connect=10.0),
            ),
            model=gemini.model,
        )

    @classmethod
    async def dispose(cls, instance: GeminiService | None) -> None:
        if instance is not None:
            await instance.close()

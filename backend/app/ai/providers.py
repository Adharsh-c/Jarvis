from __future__ import annotations

from typing import Any

import httpx

from ..config import settings

SYSTEM_INSTRUCTION = """
You are JARVIS, the user's personal AI software-development orchestrator.

Your responsibilities:
- Understand product ideas and convert them into actionable software plans.
- Coordinate a virtual software team: Research, Product, Architecture, UI/UX,
  Frontend, Backend, QA, Security, DevOps and Documentation.
- Help create production-quality code, architecture, tests and documentation.
- Clearly separate suggestions from actions that were actually executed.
- Never claim that a file was created, a command was executed, software was
  installed, a repository was pushed, or a deployment happened unless JARVIS
  tools actually performed that action.
- Sensitive actions such as software installation, external access, git push,
  administrator commands, or production deployment require human approval.
- Keep responses practical and structured. When code is requested, provide
  complete code when reasonably possible.

JARVIS is a controlled development system, not an unrestricted remote-control
agent. Respect the user's approval workflow and workspace boundaries.

You are running locally through Ollama. Do not claim that you performed live
web research or verified current external information unless a dedicated JARVIS
web tool actually supplied that information.
""".strip()


def _ollama_reply(message: str, context: str, response_format: dict[str, Any] | str | None = None) -> dict[str, Any]:
    if not settings.ollama_enabled:
        raise RuntimeError("Ollama is disabled. Set OLLAMA_ENABLED=true in backend/.env")

    prompt = message if not context else f"Context:\n{context}\n\nUser request:\n{message}"
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": max(2048, settings.ollama_num_ctx)},
    }
    if response_format is not None:
        payload["format"] = response_format

    try:
        with httpx.Client(timeout=settings.ai_request_timeout_seconds) as client:
            response = client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot connect to Ollama at {settings.ollama_base_url}. "
            f"Start Ollama and make sure model '{settings.ollama_model}' is installed."
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise RuntimeError(f"Ollama API error ({exc.response.status_code}): {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama connection error: {type(exc).__name__}: {exc}") from exc

    text = ((data.get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response")

    return {
        "reply": text,
        "model": settings.ollama_model,
        "provider": "ollama",
        "grounded": False,
    }


def provider_status() -> list[dict[str, Any]]:
    return [
        {
            "provider": "ollama",
            "configured": bool(settings.ollama_enabled),
            "model": settings.ollama_model,
            "local": True,
            "supports_search": False,
        }
    ]


def generate_reply(
    message: str,
    context: str = "",
    use_search: bool | None = None,
    provider: str | None = None,
    response_format: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    selected = (provider or settings.ai_provider or "ollama").strip().lower()
    if selected in {"", "auto"}:
        selected = "ollama"
    if selected != "ollama":
        raise RuntimeError("JARVIS V9 is configured for Ollama only. Remove other provider settings and use provider='ollama'.")
    if use_search:
        # Do not silently ignore a user's request for live research. The current
        # Ollama-only build has no configured web-search connector.
        search_note = (
            "LIVE SEARCH STATUS: No live web-search tool is configured in this "
            "Ollama-only installation. Do not claim that current web research "
            "was performed. Label external/current claims as unverified and "
            "offer a research plan or ask the user to enable a search connector."
        )
        context = "\\n\\n".join(part for part in (context, search_note) if part)
    return _ollama_reply(message, context, response_format=response_format)


def generate_research(industry: str, audience: str, region: str, provider: str | None = None) -> dict[str, Any]:
    prompt = f"""
Create an offline market-opportunity hypothesis report for:
Industry: {industry}
Target audience: {audience}
Region: {region}

Important: this report is generated only from the local model's knowledge/context.
Do not present market statistics, competitor details, prices, trends, or other
current facts as verified. Clearly label hypotheses and recommend questions that
should be validated with current external research.

Return:
1. Executive summary
2. Likely problems and demand hypotheses
3. Possible competitor categories
4. Potential gaps/opportunities
5. MVP ideas
6. Risks and validation questions
7. What should be verified with live research
""".strip()
    result = generate_reply(prompt, use_search=False, provider=provider or "ollama")
    return {
        "summary": result["reply"],
        "model": result["model"],
        "provider": result["provider"],
        "grounded": False,
    }

"""
app/routers/explain.py
POST /explain  — streams an AI-generated assessment.

Cache behaviour:
  - Cache HIT  → streams the stored text as a single chunk (instant).
  - Cache MISS → streams live from Groq, then saves result to DB.
  - force=True → skips cache, always generates fresh, overwrites stored entry.

Cache is automatically invalidated when a city's parameters are edited
via PATCH /api/v1/cities/{pcode} (see cities.py).
"""
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from groq import Groq

from app.db.database import SessionLocal
from app.db.models import AiAssessmentCache
from app.services.ai_cache import get_cached, save_cached

router = APIRouter(tags=["Explain"])

# ── Prompt builder ────────────────────────────────────────────────────────

_SEVERITY_LABEL = ["", "Minor", "Moderate", "Major", "Catastrophic"]


def _build_prompt(req: dict) -> str:
    risk_pct    = f"{req.get('riskScore', 0) * 100:.0f}%" if req.get('riskScore') is not None else "N/A"
    poverty_pct = f"{req.get('povertyPct', 0) * 100:.1f}%" if req.get('povertyPct') is not None else "N/A"
    week_cost   = f"PHP {req.get('totalWeekCost', 0):,.2f}"
    location    = ", ".join(filter(None, [req.get('cityName'), req.get('province'), req.get('region')]))

    sev = req.get('severity')
    sev_label = _SEVERITY_LABEL[sev] if sev and 1 <= sev <= 4 else ""
    sim_line  = (
        f"Active Scenario: {req.get('hazard')} - Severity {sev}/4 ({sev_label})"
        if req.get('simActive') and req.get('hazard')
        else "Baseline (no active scenario)"
    )

    demand = req.get('demand', {})

    return f"""You are a senior disaster-preparedness analyst for the Philippine government. \
Write a professional assessment report section (4 short paragraphs, 280 words max total) \
based ONLY on the data provided below.

Rules:
- Plain text ONLY. No markdown, no bullet points, no headers, no numbered lists.
- Use only basic ASCII characters. No smart quotes, no em dashes, no curly apostrophes.
- Use straight single quotes (') and hyphens (-) instead of dashes.
- Separate paragraphs with a single blank line.
- NEVER invent or cite figures not explicitly given below.
- NEVER name specific agencies or organizations. Use "local authorities" or "relief coordinators".
- NEVER fabricate infrastructure details not stated in the data.
- Stick to planning-level guidance.

=== LOCATION ===
{location}
Population: {req.get('population', 0):,}  |  Households: {req.get('households', 0):,}
Poverty rate: {poverty_pct}  |  Coastal: {"Yes" if req.get('isCoastal') else "No"}
Flood Zone: {req.get('floodZone') or 'N/A'}  |  Earthquake Zone: {req.get('eqZone') or 'N/A'}
Risk Score: {risk_pct}

=== SCENARIO ===
{sim_line}

=== PEAK DEMAND ESTIMATES ===
Rice: {demand.get('rice', 0):,.0f} kg
Water: {demand.get('water', 0):,.0f} L
Medical Kits: {demand.get('meds', 0):,.0f} units
Hygiene Kits: {demand.get('kits', 0):,.0f} units

=== 7-DAY FORECAST ===
Total estimated cost: {week_cost}

Paragraph 1 - Risk overview: Summarize the vulnerability profile. Reference coastal status, \
flood/earthquake zone, and poverty rate.

Paragraph 2 - Resource demand justification: Explain why demand estimates are at these \
quantities. Connect to population, households, hazard type, and poverty rate.

Paragraph 3 - Immediate pre-positioning actions: Give 2-3 concrete, time-bound logistics \
actions within 72 hours. No specific quantities or agency names.

Paragraph 4 - Longer-term preparedness gaps: Identify 1-2 structural vulnerabilities and \
a mitigation measure for each."""


def _sanitize(text: str) -> str:
    replacements = {
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2014": "-", "\u2013": "-",
        "\u2026": "...", "\u00a0": " ",
        "\u20b1": "PHP ",
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    return text.encode("ascii", "ignore").decode("ascii").strip()


# ── Endpoint ──────────────────────────────────────────────────────────────

@router.post("/explain")
async def explain_endpoint(body: dict):
    """
    Accepts the full ExplainInput from the frontend (sent by useCompletion).
    Extra fields sent by the AI SDK (e.g. 'prompt') are ignored since we
    accept a raw dict.
    """
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        def _err():
            yield f'3:{json.dumps("LLM_API_KEY is not configured.")}\n'
            yield f'd:{json.dumps({"finishReason": "error"})}\n'
        return StreamingResponse(
            _err(),
            media_type="text/plain; charset=utf-8",
            headers={"x-vercel-ai-data-stream": "v1"},
        )

    pcode    = body.get("pcode")
    hazard   = body.get("hazard") or ""
    severity = int(body.get("severity") or 0)
    force    = bool(body.get("force", False))

    # ── Check DB cache before opening the stream ──────────────────────────
    cached_text: str | None = None
    generated_at = datetime.now(timezone.utc).isoformat()

    if pcode and not force:
        db = SessionLocal()
        try:
            cached: AiAssessmentCache | None = get_cached(db, pcode, hazard, severity)
            if cached:
                cached_text = cached.text
                generated_at = cached.generated_at.isoformat()
        finally:
            db.close()

    client = Groq(api_key=api_key)

    # ── Generator ─────────────────────────────────────────────────────────
    def generate():
        # Cache HIT — stream stored text as one chunk (feels instant to client)
        if cached_text is not None:
            yield f"0:{json.dumps(cached_text)}\n"
            yield f'd:{json.dumps({"finishReason": "stop"})}\n'
            return

        # Cache MISS — stream live from Groq, then persist to DB
        db = SessionLocal()
        try:
            parts: list[str] = []

            stream = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=600,
                temperature=0.35,
                top_p=0.9,
                stream=True,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a disaster-preparedness analyst. "
                            "Always respond in plain ASCII text only. "
                            "Never use smart quotes, em dashes, bullet points, or markdown."
                        ),
                    },
                    {"role": "user", "content": _build_prompt(body)},
                ],
            )

            for chunk in stream:
                text = chunk.choices[0].delta.content or ""
                if text:
                    parts.append(text)
                    yield f"0:{json.dumps(text)}\n"

            # Save sanitized full text to DB
            if pcode and parts:
                full_text = _sanitize("".join(parts))
                save_cached(db, pcode, hazard, severity, full_text)

        except Exception as exc:
            yield f"3:{json.dumps(f'Generation error: {exc}')}\n"
        finally:
            db.close()
            yield f'd:{json.dumps({"finishReason": "stop"})}\n'

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "x-vercel-ai-data-stream": "v1",
            "X-Generated-At": generated_at,
        },
    )
"""
app/routers/chat.py
POST /chat  — streaming chat endpoint for PhiliReady Assistant.

Streams responses in the Vercel AI SDK v4 data-stream format so the
frontend useChat() hook works without any custom parsing.

Stream line format:
  text chunk  → 0:"<escaped text>"\n
  finish      → d:{"finishReason":"stop"}\n
"""
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel

router = APIRouter(tags=["Chat"])

# ── System prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are PhiliReady Assistant, an AI embedded in the PhiliReady \
platform — a micro-demand forecasting tool for relief goods across all Philippine \
cities and municipalities. You support DRRMO officers and LGU coordinators.

You are knowledgeable about:
- SPHERE Humanitarian Standards (2018): rice 1.5 kg/HH/day, water 15 L/HH/day, \
  medicine kits 0.08 units/HH/day, hygiene kits 0.07 units/HH/day
- Philippine disaster types: typhoon, flood, earthquake, volcanic eruption
- Risk scoring: composite of population, poverty rate, coastal status, flood zone, \
  earthquake zone — clamped to [0.05, 0.99]
- Philippine agencies and standards: NDRRMC, PAGASA, PHIVOLCS, MGB, PSA, DSWD, DOH
- The PhiliReady platform: 7-day demand forecasting, city risk scores, simulation \
  mode (hazard + severity 1-4), what-if forecaster, price management, AI assessments
- Severity scale: 1 Minor, 2 Moderate, 3 Major, 4 Catastrophic
- Displacement rates by severity: ~10%, ~20%, ~35%, ~55% of households
- Zone modifiers: low 0.7x, medium 1.0x, high 1.3x
- Coastal modifier: 1.2x for typhoon and flood only
- National average household size: 4.1 (PSA 2020 Census)

Behavior rules:
- Be concise and practical — these are field officers making time-sensitive decisions.
- NEVER use markdown formatting of any kind. No **bold**, no *italic*, no `code`. \
  Only numbers, lists are allowed.
- When citing SPHERE rates or formulas, be precise.
- If asked about a specific city's live data, tell the user to click the city on \
  the map to open its detail panel.
- ONLY answer questions related to disaster preparedness, relief logistics, \
  humanitarian standards, and the PhiliReady platform. If the user asks about \
  anything else, respond with: "I can only assist with disaster preparedness, \
  relief logistics, and the PhiliReady platform." Do not answer off-topic \
  questions under any circumstances."""


# ── Schema ────────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


# ── Endpoint ──────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="LLM_API_KEY is not configured.")

    client = Groq(api_key=api_key)

    def generate():
        try:
            stream = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *[{"role": m.role, "content": m.content} for m in request.messages],
                ],
                stream=True,
                max_tokens=600,
                temperature=0.4,
            )
            for chunk in stream:
                text = chunk.choices[0].delta.content or ""
                if text:
                    yield f"0:{json.dumps(text)}\n"
        except Exception as exc:
            yield f"3:{json.dumps(f'Assistant error: {exc}')}\n"
        finally:
            yield f'd:{json.dumps({"finishReason": "stop"})}\n'

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"x-vercel-ai-data-stream": "v1"},
    )
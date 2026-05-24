"""RAG pipeline with MoE routing for cross-jurisdictional regulatory queries."""
import asyncio
import json
from typing import Optional

import anthropic

from config import settings
from services import vector_store

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_EXPERTS = {
    "asean": {
        "name": "ASEAN Regulatory Expert",
        "countries": ["Thailand", "Vietnam", "Indonesia", "Philippines", "Malaysia", "Singapore",
                      "Brunei", "Cambodia", "Laos", "Myanmar"],
        "system": (
            "You are an expert in ASEAN digital trade regulations, specialising in Thailand, "
            "Vietnam, Indonesia, Philippines, Malaysia, and Singapore. "
            "Ground every claim exclusively in the provided source excerpts."
        ),
    },
    "east_asia": {
        "name": "East Asia Trade Expert",
        "countries": ["Japan", "South Korea", "China", "Taiwan", "Hong Kong"],
        "system": (
            "You are an expert in East Asian digital trade regulations, specialising in Japan, "
            "South Korea, China, and Taiwan. "
            "Ground every claim exclusively in the provided source excerpts."
        ),
    },
    "ip": {
        "name": "Digital IP & Copyright Expert",
        "system": (
            "You are an expert in digital intellectual property, copyright, and platform liability "
            "regulations across Asia-Pacific jurisdictions. "
            "Ground every claim exclusively in the provided source excerpts."
        ),
    },
    "harmonisation": {
        "name": "Harmonisation Expert",
        "system": (
            "You are an expert in regional trade agreement harmonisation, including RCEP, CPTPP, "
            "and bilateral FTA digital trade chapters. "
            "Ground every claim exclusively in the provided source excerpts."
        ),
    },
    "general": {
        "name": "Digital Trade Regulatory Analyst",
        "system": (
            "You are a digital trade regulatory analyst covering Asia-Pacific jurisdictions. "
            "Ground every claim exclusively in the provided source excerpts."
        ),
    },
}

_ROUTER_PROMPT = """Classify this regulatory query to determine the best expert and search strategy.

Query: {query}

Respond with JSON only:
{{
  "expert": "<asean|east_asia|ip|harmonisation|general>",
  "search_terms": ["<term1>", "<term2>"],
  "category_filter": "<data_privacy|e_commerce|intellectual_property|customs|general_trade|dispute_resolution|definitions|null>"
}}"""

_ANSWER_PROMPT = """Answer the question using ONLY the source excerpts below. Rules:
1. Cite every key claim with [Citation: <citation_string>]
2. If sources are insufficient, say so explicitly — do not speculate
3. Compare jurisdictions systematically when multiple are relevant
4. Never fabricate regulatory text

Sources:
{sources}

Question: {query}"""


async def _route_query(query: str) -> tuple[str, list[str], Optional[str]]:
    response = await _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": _ROUTER_PROMPT.format(query=query)}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

    try:
        result = json.loads(raw)
        category = result.get("category_filter")
        if category == "null":
            category = None
        return result.get("expert", "general"), result.get("search_terms", [query]), category
    except json.JSONDecodeError:
        return "general", [query], None


async def answer_query(query: str, session_id: Optional[str] = None) -> dict:
    expert_key, search_terms, category_filter = await _route_query(query)
    expert = _EXPERTS.get(expert_key, _EXPERTS["general"])

    where = {"category": {"$eq": category_filter}} if category_filter else None

    seen: set[str] = set()
    results: list[dict] = []

    for term in search_terms:
        hits = await asyncio.to_thread(vector_store.search, term, 6, where)
        for h in hits:
            if h["id"] not in seen and h["score"] > 0.25:
                results.append(h)
                seen.add(h["id"])

    # Retry without category filter if too few results
    if len(results) < 3 and category_filter:
        for term in search_terms:
            hits = await asyncio.to_thread(vector_store.search, term, 6, None)
            for h in hits:
                if h["id"] not in seen and h["score"] > 0.25:
                    results.append(h)
                    seen.add(h["id"])

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:8]

    if not top:
        return {
            "message": (
                "No relevant provisions found in the knowledge base for this query. "
                "Please ensure relevant documents have been uploaded and their extractions accepted."
            ),
            "citations": [],
            "expert_used": expert["name"],
        }

    sources_text = ""
    citations = []
    for i, r in enumerate(top):
        meta = r["metadata"]
        citation = meta.get("citation", f"Source {i + 1}")
        sources_text += f"\n[{i + 1}] {citation}\n{r['text']}\n"
        citations.append({
            "id": r["id"],
            "citation": citation,
            "text": r["text"],
            "score": round(r["score"], 3),
            "article_ref": meta.get("article_ref", ""),
            "category": meta.get("category", ""),
        })

    response = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=expert["system"] + "\n\nCRITICAL: Only use information from the provided sources. Never fabricate provisions.",
        messages=[{
            "role": "user",
            "content": _ANSWER_PROMPT.format(sources=sources_text, query=query),
        }],
    )

    return {
        "message": response.content[0].text,
        "citations": citations,
        "expert_used": expert["name"],
    }

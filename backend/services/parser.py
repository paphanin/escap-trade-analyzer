"""VLM-based document parsing and provision extraction."""
import asyncio
import base64
import json
from pathlib import Path

import anthropic
import pymupdf

from config import settings

# max_retries=6 gives exponential backoff up to ~64s on 429 rate-limit errors
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=6)

_PARSE_SYSTEM = """You are a legal document parser for digital trade regulations.
The document may be in any language including Lao, Thai, Khmer, Burmese, Japanese, Chinese, Korean, or other scripts.

Parse the provided page image and output structured Markdown that preserves:
- ALL text exactly as it appears in the original language and script — never translate
- All article numbers, sub-clause references, and section hierarchy
- Tables as Markdown tables
- Multi-column layouts in reading order
- Numbered and lettered lists with their full content

Mark genuinely illegible text as [UNCLEAR]. Output only the structured content, no commentary."""

_EXTRACT_SYSTEM = """You are a legal information extraction system for digital trade regulations.
The document may be in any language. Preserve all source text verbatim in its original language and script.

Extract every article, section, and sub-clause as a separate item. Each item MUST include:
- The complete body text of the article/clause, not just the heading
- All sub-items and paragraphs that belong to that article
- If an article has sub-clauses (a), (b), (c)..., include all of them together in one item

For each item output a JSON object with these exact keys:
- article_ref: the article/section number exactly as written (e.g. "Article 14", "ມາດຕາ 14", "第14条")
- text: the COMPLETE verbatim text of the full article including all its sub-clauses and paragraphs — minimum 2 sentences unless the article is genuinely a single short sentence
- lang: 2-letter ISO language code of the source text (e.g. "lo" for Lao, "th" for Thai, "en" for English, "ja" for Japanese)
- category: one of [data_privacy, e_commerce, intellectual_property, customs, general_trade, dispute_resolution, definitions]
- confidence: float 0.0–1.0 (1.0 = clear complete text; 0.5 = partially legible; 0.3 = reconstructed)
- page_number: integer

Output ONLY a valid JSON array. No commentary, no markdown fencing.
Do not truncate article text. Do not paraphrase. Do not translate."""


def _render_page(file_path: str, page_num: int) -> bytes:
    doc = pymupdf.open(file_path)
    page = doc[page_num]
    mat = pymupdf.Matrix(1.5, 1.5)
    pix = page.get_pixmap(matrix=mat)
    result = pix.tobytes("png")
    doc.close()
    return result


def _get_page_image_sync(file_path: str, page_number: int) -> bytes:
    doc = pymupdf.open(file_path)
    page = doc[page_number - 1]
    mat = pymupdf.Matrix(1.5, 1.5)
    pix = page.get_pixmap(matrix=mat)
    result = pix.tobytes("png")
    doc.close()
    return result


async def get_page_image(file_path: Path, page_number: int) -> bytes:
    return await asyncio.to_thread(_get_page_image_sync, str(file_path), page_number)


def _extract_text_from_page(file_path: str, page_num: int) -> str:
    """Fast free text extraction — sufficient for well-formed text PDFs."""
    doc = pymupdf.open(file_path)
    text = doc[page_num].get_text("text")
    doc.close()
    return text


async def parse_document(file_path: Path, filename: str) -> tuple[str, int]:
    """Parse all pages concurrently. Uses free text extraction when available;
    falls back to Vision API for scanned/complex pages."""

    def _page_count(fp: str) -> int:
        doc = pymupdf.open(fp)
        n = len(doc)
        doc.close()
        return n

    page_count = await asyncio.to_thread(_page_count, str(file_path))
    page_count = min(page_count, settings.max_pages_per_doc)

    # Semaphore keeps concurrent Vision API calls within Anthropic rate limits
    sem = asyncio.Semaphore(settings.parse_concurrency)

    async def _parse_one(page_num: int) -> tuple[int, str]:
        text = await asyncio.to_thread(_extract_text_from_page, str(file_path), page_num)
        if len(text.strip()) >= settings.vision_fallback_threshold:
            return page_num, f"<!-- PAGE: {page_num + 1} -->\n{text.strip()}"

        async with sem:
            img_bytes = await asyncio.to_thread(_render_page, str(file_path), page_num)
            img_b64 = base64.standard_b64encode(img_bytes).decode()
            response = await _client.messages.create(
                model=settings.parse_model,
                max_tokens=2048,
                system=_PARSE_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                        {"type": "text", "text": f"Parse page {page_num + 1} of document '{filename}'. Extract all content preserving structure."},
                    ],
                }],
            )
        return page_num, f"<!-- PAGE: {page_num + 1} -->\n{response.content[0].text}"

    results = await asyncio.gather(*[_parse_one(n) for n in range(page_count)])
    # Restore original page order after concurrent execution
    ordered = [content for _, content in sorted(results, key=lambda x: x[0])]
    return "\n\n---\n\n".join(ordered), page_count


async def extract_provisions(parsed_content: str, filename: str) -> list[dict]:
    """Extract regulatory provisions concurrently across page batches."""
    pages = parsed_content.split("<!-- PAGE:")
    batches = [pages[i:i + 4] for i in range(0, len(pages), 4)]

    sem = asyncio.Semaphore(settings.extract_concurrency)

    async def _extract_batch(batch: list[str]) -> list[dict]:
        chunk = "<!-- PAGE:".join(batch).strip()
        if not chunk:
            return []
        async with sem:
            response = await _client.messages.create(
                model=settings.extract_model,
                max_tokens=8192,
                system=_EXTRACT_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": f"Document: {filename}\n\nContent:\n{chunk}\n\nExtract all regulatory provisions as a JSON array.",
                }],
            )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        try:
            provisions = json.loads(raw)
            if isinstance(provisions, list):
                for p in provisions:
                    p["citation"] = f"{filename} § {p.get('article_ref', 'Unknown')} (p.{p.get('page_number', '?')})"
                return provisions
        except json.JSONDecodeError:
            pass
        return []

    batch_results = await asyncio.gather(*[_extract_batch(b) for b in batches])
    return [p for batch in batch_results for p in batch]

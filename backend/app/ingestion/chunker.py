"""Semantic chunking respecting markdown sections, with token budget."""
from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

from app.ingestion.ocr import OcrResult

_enc = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    chunk_id: str
    page: int
    text: str
    token_count: int


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_pages(
    ocr: OcrResult,
    target_tokens: int = 800,
    max_tokens: int = 1500,
    overlap_tokens: int = 80,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    counter = 0
    for page_obj in ocr.pages:
        page = page_obj.page
        paragraphs = _split_paragraphs(page_obj.text)
        buf: list[str] = []
        buf_tok = 0
        for para in paragraphs:
            ptok = len(_enc.encode(para))
            if buf_tok + ptok > max_tokens and buf:
                _emit(chunks, page, buf, counter)
                counter += 1
                # overlap: keep tail of buffer
                tail = _tail_for_overlap(buf, overlap_tokens)
                buf = list(tail)
                buf_tok = sum(len(_enc.encode(s)) for s in buf)
            buf.append(para)
            buf_tok += ptok
            if buf_tok >= target_tokens:
                _emit(chunks, page, buf, counter)
                counter += 1
                tail = _tail_for_overlap(buf, overlap_tokens)
                buf = list(tail)
                buf_tok = sum(len(_enc.encode(s)) for s in buf)
        if buf:
            _emit(chunks, page, buf, counter)
            counter += 1
    return chunks


def _tail_for_overlap(buf: list[str], overlap_tokens: int) -> list[str]:
    out: list[str] = []
    used = 0
    for s in reversed(buf):
        t = len(_enc.encode(s))
        if used + t > overlap_tokens:
            break
        out.insert(0, s)
        used += t
    return out


def _emit(chunks: list[Chunk], page: int, buf: list[str], counter: int) -> None:
    text = "\n\n".join(buf).strip()
    if not text:
        return
    chunks.append(
        Chunk(
            chunk_id=f"c{counter:05d}",
            page=page,
            text=text,
            token_count=len(_enc.encode(text)),
        )
    )

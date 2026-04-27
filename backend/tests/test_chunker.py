from app.ingestion.chunker import chunk_pages
from app.ingestion.ocr import OcrPage, OcrResult


def test_chunker_produces_chunks_with_overlap():
    text = ("Paragraphe " + "lorem ipsum " * 30 + "\n\n") * 5
    ocr = OcrResult(pages=[OcrPage(page=1, text=text)], full_text=text)
    chunks = chunk_pages(ocr, target_tokens=200, max_tokens=400, overlap_tokens=20)
    assert len(chunks) >= 2
    assert all(c.token_count > 0 for c in chunks)
    assert all(c.text for c in chunks)


def test_chunker_keeps_page_attribution():
    p1 = "Page 1 contenu " * 50
    p2 = "Page 2 contenu " * 50
    ocr = OcrResult(
        pages=[OcrPage(page=1, text=p1), OcrPage(page=2, text=p2)],
        full_text=p1 + "\n\n" + p2,
    )
    chunks = chunk_pages(ocr, target_tokens=100, max_tokens=200)
    pages = {c.page for c in chunks}
    assert pages == {1, 2}

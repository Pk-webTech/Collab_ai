def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """
    Splits text into overlapping character-based chunks, breaking on
    paragraph/sentence boundaries where possible so chunks read naturally.
    Good enough for Phase 3; can be swapped for a token-aware splitter later
    without touching anything downstream (chunks are just stored strings).
    """
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)

        if end < n:
            # Prefer breaking at a paragraph, then sentence, then word boundary.
            break_at = text.rfind("\n\n", start, end)
            if break_at == -1 or break_at <= start:
                break_at = text.rfind(". ", start, end)
            if break_at == -1 or break_at <= start:
                break_at = text.rfind(" ", start, end)
            if break_at != -1 and break_at > start:
                end = break_at + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= n:
            break
        start = max(end - overlap, start + 1)

    return chunks

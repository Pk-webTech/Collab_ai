def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """
    Splits text into overlapping character-based chunks, breaking on
    paragraph/sentence boundaries where possible so chunks read naturally.

    The separator search is deliberately restricted to the tail of each
    window. `rfind` returns the LAST separator in the window, but if the
    only separator sits near the window's start -- e.g. a PDF with a short
    header followed by one long unbroken block -- the break point lands
    behind where the previous chunk ended. `end` then collapses backwards,
    `start` advances by a single character, and the splitter emits hundreds
    of near-identical chunks sliding one character at a time. Requiring the
    break to fall past `min_break` keeps every chunk close to `chunk_size`,
    and the `min_start` floor guarantees forward progress even if a future
    edit reintroduces a bad break point.
    """
    text = text.strip()
    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    # Overlap must leave room to advance, or the loop cannot terminate.
    overlap = max(0, min(overlap, chunk_size // 2))

    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)

        if end < n:
            # Only accept a break in the last 40% of the window.
            min_break = start + int(chunk_size * 0.6)
            for separator in ("\n\n", ". ", "\n", " "):
                break_at = text.rfind(separator, min_break, end)
                if break_at != -1:
                    end = break_at + len(separator)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= n:
            break

        # Never move backwards, and always advance by at least one character.
        min_start = start + chunk_size - overlap
        start = max(end - overlap, min_start, start + 1)

    return chunks
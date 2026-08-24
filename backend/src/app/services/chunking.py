"""Split extracted document text into retrieval chunks."""


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[str]:
    """Create overlapping word-based text chunks."""
    words = text.split()
    chunks: list[str] = []
    step = chunk_size - overlap

    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + chunk_size])

        if chunk:
            chunks.append(chunk)

    return chunks

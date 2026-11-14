from collections.abc import Sequence


def fixed_size_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller than chunk_size")
    cleaned = text.strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(cleaned):
            break
        start = end - overlap
    return chunks


def recursive_character_chunks(
    text: str,
    chunk_size: int,
    overlap: int,
    separators: Sequence[str] = ("\n\n", "\n", " ", ""),
) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller than chunk_size")
    cleaned = text.strip()
    if not cleaned:
        return []

    def split_segment(segment: str, separator_index: int) -> list[str]:
        segment = segment.strip()
        if len(segment) <= chunk_size:
            return [segment] if segment else []
        if separator_index >= len(separators):
            return fixed_size_chunks(segment, chunk_size, overlap)
        separator = separators[separator_index]
        if not separator:
            pieces = list(segment)
        else:
            pieces = segment.split(separator)
            pieces = [piece + separator for piece in pieces[:-1]] + pieces[-1:]
        if all(len(piece) <= chunk_size for piece in pieces):
            return pieces
        result: list[str] = []
        for piece in pieces:
            if len(piece) > chunk_size:
                result.extend(split_segment(piece, separator_index + 1))
            elif piece.strip():
                result.append(piece.strip())
        return result

    pieces = split_segment(cleaned, 0)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{piece}" if not current else f"{current}{piece}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current.strip():
            chunks.append(current.strip())
        tail = current[-overlap:] if overlap else ""
        current = f"{tail}{piece}"
        if len(current) > chunk_size:
            chunks.extend(fixed_size_chunks(current, chunk_size, overlap))
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return chunks

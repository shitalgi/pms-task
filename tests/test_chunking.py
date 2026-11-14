import pytest

from app.services.chunking import fixed_size_chunks, recursive_character_chunks


@pytest.mark.parametrize("chunker", [fixed_size_chunks, recursive_character_chunks])
def test_chunkers_cover_text_and_respect_size(chunker) -> None:
    text = "First paragraph.\n\nSecond paragraph has enough words to split into parts."
    chunks = chunker(text, chunk_size=24, overlap=5)

    assert chunks
    assert all(0 < len(chunk) <= 24 for chunk in chunks)
    assert any("First" in chunk for chunk in chunks)
    assert any("paragraph" in chunk for chunk in chunks)
    assert any("Second" in chunk for chunk in chunks)
    assert any("parts" in chunk for chunk in chunks)


def test_chunkers_return_empty_for_blank_text() -> None:
    assert fixed_size_chunks("  \n ", 20, 2) == []
    assert recursive_character_chunks("", 20, 2) == []


def test_chunkers_reject_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        fixed_size_chunks("hello", 10, 10)
    with pytest.raises(ValueError):
        recursive_character_chunks("hello", 10, -1)

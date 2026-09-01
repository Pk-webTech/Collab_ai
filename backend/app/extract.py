import io


class UnsupportedFileType(Exception):
    pass


def extract_text(filename: str, data: bytes) -> str:
    lower = filename.lower()

    if lower.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore")

    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    raise UnsupportedFileType(f"Unsupported file type: {filename}")

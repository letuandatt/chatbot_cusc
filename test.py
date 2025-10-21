from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import MarkdownHeaderTextSplitter
from pathlib import Path
import re
import os

def extract_mahieu_from_filename(filename: str) -> str:
    """
    Trích mã hiệu từ tên file.
    Hỗ trợ các dạng: QT07, TT07.01, TT07.01.I, TT07.10, v.v.
    """
    match = re.match(r'^(TT\d{2}(?:\.\d{2})?(?:\.[A-Za-z0-9]+)?|QT\d{2})', filename)
    return match.group(1) if match else None

def load_documents(file_path: str):
    loader = TextLoader(file_path)
    raw_docs = loader.load()

    enriched = []
    for d in raw_docs:
        src_path = Path(d.metadata.get("source") or file_path)
        file_name = src_path.stem
        ma_hieu = extract_mahieu_from_filename(file_name)

        enriched.append(
            Document(
                page_content=d.page_content,
                metadata={
                    "source": str(src_path),
                    "ten_van_ban": file_name,
                    "ma_hieu": ma_hieu
                }
            )
        )

    print(f"Loaded {len(enriched)} documents.")
    return enriched

def split_documents(documents):
    headers_to_split = [("#", "section"), ("##", "subsection"), ("###", "subsubsection")]
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split,
        return_each_line=False,
        strip_headers=False
    )

    all_chunks = []
    for doc in documents:
        # splitter.split_text có thể trả list of Document-like objects or plain strings
        md_chunks = splitter.split_text(doc.page_content)

        # Nếu trả strings -> wrap; nếu trả Document-like với metadata -> merge
        chunks_for_doc = []
        for i, c in enumerate(md_chunks):
            if isinstance(c, Document):
                chunk_text = c.page_content
                chunk_meta = getattr(c, "metadata", {}) or {}
            elif hasattr(c, "page_content") and hasattr(c, "metadata"):
                chunk_text = c.page_content
                chunk_meta = c.metadata or {}
            else:
                # plain string
                chunk_text = str(c)
                chunk_meta = {}

            # merge metadata: chunk_meta overrides doc.metadata if conflict
            merged_meta = {**doc.metadata, **chunk_meta}
            # keep origin file identity to detect contamination later
            merged_meta.setdefault("origin_file", doc.metadata.get("ten_van_ban"))

            chunk_doc = Document(page_content=chunk_text, metadata=merged_meta)
            chunks_for_doc.append(chunk_doc)

        print(f"→ {doc.metadata['ten_van_ban']} -> {len(chunks_for_doc)} chunks")
        all_chunks.extend(chunks_for_doc)

    print(f"Total chunks: {len(all_chunks)}")
    return all_chunks

def inspect_metadata(chunks, top_n=10):
    print("\n--- Inspect first chunks metadata ---")
    for i, c in enumerate(chunks[:top_n]):
        print(f"[{i}] source={c.metadata.get('source')} | ten_van_ban={c.metadata.get('ten_van_ban')} | ma_hieu={c.metadata.get('ma_hieu')}")

    # check distinct ma_hieu per origin file
    mapping = {}
    for c in chunks:
        origin = c.metadata.get("ten_van_ban")
        mh = c.metadata.get("ma_hieu")
        mapping.setdefault(origin, set()).add(mh)

    print("\n--- ma_hieu sets by file ---")
    for origin, s in mapping.items():
        print(f"{origin}: {s}")

    # detect if any chunk has ma_hieu that doesn't match origin file (suspicious)
    suspicious = []
    for c in chunks:
        if c.metadata.get("ten_van_ban") and c.metadata.get("ma_hieu") not in (None, ''):
            if not str(c.metadata.get("ten_van_ban")).startswith(str(c.metadata.get("ma_hieu"))):
                # loose check: file name should start with ma_hieu in your naming convention
                suspicious.append((c.metadata.get("ten_van_ban"), c.metadata.get("ma_hieu")))
    if suspicious:
        print("\n--- Suspicious chunks (file name doesn't start with ma_hieu) ---")
        for s in suspicious[:50]:
            print(s)
    else:
        print("\nNo obvious contamination found by simple check.")


if __name__ == "__main__":
    # thay đường dẫn phù hợp
    fp = "data/after_parse/TT07.01.I - Kinh doanh phan mem v2.0.md"
    if not os.path.exists(fp):
        raise SystemExit(f"File not found: {fp}")

    docs = load_documents(fp)
    chunks = split_documents(docs)
    inspect_metadata(chunks, top_n=20)

    for chunk in chunks[:10]:
        print(chunk)
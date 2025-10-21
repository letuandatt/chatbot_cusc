from langchain_community.document_loaders import DirectoryLoader
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import MarkdownHeaderTextSplitter
from dotenv import load_dotenv
from pathlib import Path

import os
import re

load_dotenv()

def create_data(CHROMA_PATH="vectorstores/chroma_db_2", google_api_key=os.getenv("GOOGLE_API_KEY")):
    data = "data/after_parse"

    def main():
        generate_data_store()

    def generate_data_store():
        documents = load_documents()
        chunks = split_documents(documents)
        inspect_metadata(chunks)  # ✅ Kiểm tra metadata sau khi split
        save_chunks(chunks)

    def extract_mahieu_from_filename(filename: str) -> str:
        match = re.match(r'^(TT\d{2}(?:\.\d{2})?(?:\.\w+)?|QT\d{2})', filename)
        return match.group(1) if match else None

    def load_documents():
        loader = DirectoryLoader(data, glob="*.md")
        documents = loader.load()

        enrich_documents = []
        for document in documents:
            text = document.page_content
            file_path = Path(document.metadata["source"])
            file_name = file_path.stem
            ma_hieu = extract_mahieu_from_filename(file_name)

            enrich_documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": str(file_path),
                        "ten_van_ban": file_name,
                        "ma_hieu": ma_hieu,
                    }
                )
            )

        print(f"Loaded {len(enrich_documents)} documents.")
        return enrich_documents

    def split_documents(documents):
        embedding_model = load_embedding()
        header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "section"), ("##", "subsection"), ("###", "subsubsection")],
            return_each_line=False,
            strip_headers=False
        )
        semantic_splitter = SemanticChunker(embeddings=embedding_model)

        all_chunks = []

        for document in documents:
            header_chunks = header_splitter.split_text(document.page_content)

            base_metadata = document.metadata.copy()

            total_chunks_for_doc = []
            for header_chunk in header_chunks:

                # 1. Tạo metadata mới bằng cách kết hợp
                chunk_metadata = base_metadata.copy()
                if isinstance(header_chunk, Document):
                    chunk_metadata.update(header_chunk.metadata)
                    text_chunk = header_chunk.page_content
                else:
                    text_chunk = str(header_chunk)

                # 2. Split ngữ nghĩa
                semantic_chunks = semantic_splitter.split_text(text_chunk)

                # 3. Gán metadata đã được kết hợp
                for sc in semantic_chunks:
                    total_chunks_for_doc.append(Document(page_content=sc, metadata=chunk_metadata))

            print(f"🪶 {document.metadata['ten_van_ban']} → Split thành {len(total_chunks_for_doc)} chunks.")
            all_chunks.extend(total_chunks_for_doc)

        print(f"📚 Tổng cộng {len(all_chunks)} chunks sau khi split toàn bộ.")
        return all_chunks

    def inspect_metadata(chunks, top_n=10):
        print("\n--- Inspect first chunks metadata ---")
        for i, c in enumerate(chunks[:top_n]):
            print(f"[{i}] source={c.metadata.get('source')} | ten_van_ban={c.metadata.get('ten_van_ban')} | ma_hieu={c.metadata.get('ma_hieu')}")

        mapping = {}
        for c in chunks:
            origin = c.metadata.get("ten_van_ban")
            mh = c.metadata.get("ma_hieu")
            mapping.setdefault(origin, set()).add(mh)

        print("\n--- ma_hieu sets by file ---")
        for origin, s in mapping.items():
            print(f"{origin}: {s}")

        suspicious = []
        for c in chunks:
            if c.metadata.get("ten_van_ban") and c.metadata.get("ma_hieu") not in (None, ''):
                if not str(c.metadata.get("ten_van_ban")).startswith(str(c.metadata.get("ma_hieu"))):
                    suspicious.append((c.metadata.get("ten_van_ban"), c.metadata.get("ma_hieu")))

        if suspicious:
            print("\n--- Suspicious chunks (file name doesn't start with ma_hieu) ---")
            for s in suspicious[:50]:
                print(s)
        else:
            print("\nNo obvious contamination found by simple check.")

    def load_embedding():
        embedding_model = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=google_api_key
        )
        return embedding_model

    def save_chunks(chunks):
        embedding_model = load_embedding()
        Chroma.from_documents(
            documents=chunks,
            persist_directory=CHROMA_PATH,
            embedding=embedding_model,
            collection_name="docs_cusc"
        )
        print(f"Saved {len(chunks)} chunks to {CHROMA_PATH}")

    main()

from langchain_community.document_loaders import DirectoryLoader
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from dotenv import load_dotenv
from pathlib import Path

import os
import re


load_dotenv()

def create_data(CHROMA_PATH="vectorstores/chroma_db", google_api_key=os.getenv("GOOGLE_API_KEY")):
    data = "data/after_parse"

    def main():
        generate_data_store()

    def generate_data_store():
        documents = load_documents()
        chunks = split_documents(documents)
        save_chunks(chunks)

    def extract_mahieu_from_filename(filename: str) -> str:
        """
        Trích mã hiệu từ tên file.
        Hỗ trợ các dạng: QT07, TT07.01, TT07.01.I, TT07.10, v.v.
        """
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

        sc_splitter = SemanticChunker(
            embeddings=embedding_model
        )

        all_chunks = []

        for document in documents:
            # Split text
            md_chunks = sc_splitter.split_text(document.page_content)
            print(md_chunks)
            print(f"🪶 {document.metadata['ten_van_ban']} → Split thành {len(md_chunks)} chunks.")

            chunks = []
            for chunk in md_chunks:
                chunks.append(Document(page_content=chunk, metadata=document.metadata))

            all_chunks.extend(chunks)

        print(f"📚 Tổng cộng {len(all_chunks)} chunks sau khi split toàn bộ.")

        return all_chunks

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

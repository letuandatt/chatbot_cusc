from langchain_community.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain_experimental.text_splitter import SemanticChunker
from dotenv import load_dotenv

import os
import shutil

load_dotenv()

def create_data(CHROMA_PATH="vectorstores/chroma_db", google_api_key=os.getenv("GOOGLE_API_KEY")):
    data = "data/after_parse"

    def main():
        generate_data_store()

    def generate_data_store():
        documents = load_documents()
        chunks = split_documents(documents)
        save_chunks(chunks)

    def load_documents():
        loader = DirectoryLoader(data, glob="*.md")
        documents = loader.load()
        return documents

    def split_documents(documents):
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,
            chunk_overlap=100,
            length_function=len,
            add_start_index=True
        )

        chunks = text_splitter.split_documents(documents)
        print(f"Split {len(documents)} documents into {len(chunks)} chunks.")

        document = chunks[10]
        print(document.page_content)
        print(document.metadata)

        return chunks

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
            embedding=embedding_model
        )
        print(f"Saved {len(chunks)} chunks to {CHROMA_PATH}")

    main()

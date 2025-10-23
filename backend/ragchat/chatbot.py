"""Core chatbot logic shared by API endpoints."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import (
    CSVLoader,
    Docx2txtLoader,
    JSONLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredHTMLLoader,
    UnstructuredMarkdownLoader,
    UnstructuredXMLLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv()


class ChatbotEngine:
    """Encapsulates the RAG pipeline and exposes chat/upload helpers."""

    def __init__(
        self,
        docs_path: str | os.PathLike[str] = "docs",
        index_path: str | os.PathLike[str] = "faiss_index",
        llm_name: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo"),
    ) -> None:
        self.docs_path = Path(docs_path)
        self.index_path = Path(index_path)
        self.llm_name = llm_name
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY must be provided in the environment.")

        self.model = ChatOpenAI(api_key=self.api_key, model=self.llm_name)
        self.embedding = OpenAIEmbeddings(openai_api_key=self.api_key)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )

        self._vector_store: FAISS | None = None
        self._load_or_create_index()

    # ------------------------------------------------------------------
    # Index bootstrap helpers
    # ------------------------------------------------------------------
    def _load_or_create_index(self) -> None:
        if self.index_path.exists():
            self._vector_store = FAISS.load_local(
                str(self.index_path),
                self.embedding,
                allow_dangerous_deserialization=True,
            )
        else:
            documents = self._load_all_documents(self.docs_path)
            if documents:
                split_docs = self.text_splitter.split_documents(documents)
                self._vector_store = FAISS.from_documents(split_docs, self.embedding)
                self.index_path.mkdir(parents=True, exist_ok=True)
                self._vector_store.save_local(str(self.index_path))
            else:
                self._vector_store = None

    # ------------------------------------------------------------------
    # Document ingestion
    # ------------------------------------------------------------------
    def ingest_files(self, paths: Iterable[Path]) -> List[str]:
        """Load files from disk, update the FAISS index and return their sources."""

        loaded_documents: list[Document] = []
        ingested_sources: set[str] = set()
        for path in paths:
            documents = self._load_documents_from_path(path)
            if not documents:
                continue
            split_docs = self.text_splitter.split_documents(documents)
            loaded_documents.extend(split_docs)
            ingested_sources.update(
                {doc.metadata.get("source", str(path)) for doc in documents}
            )

        if not loaded_documents:
            return []

        if self._vector_store is None:
            self._vector_store = FAISS.from_documents(loaded_documents, self.embedding)
        else:
            self._vector_store.add_documents(loaded_documents)

        self.index_path.mkdir(parents=True, exist_ok=True)
        self._vector_store.save_local(str(self.index_path))
        return sorted(ingested_sources)

    # ------------------------------------------------------------------
    # Chat interaction
    # ------------------------------------------------------------------
    def chat(self, message: str) -> tuple[str, str, list[str]]:
        """Return the assistant answer, detected intent and supporting documents."""

        if self._vector_store is None:
            retrieved_docs: list[Document] = []
        else:
            retriever = self._vector_store.as_retriever()
            retrieved_docs = retriever.invoke(message)

        context = "\n\n".join(doc.page_content for doc in retrieved_docs)
        has_docs = len(context.strip()) > 100
        intent = self._classify_intent(message)

        if intent == "playbook_writing":
            response = self._call_playbook_generator(message, context)
        elif intent == "question" and has_docs:
            response = self._call_rag_response(message, context)
        else:
            response = self._call_direct_response(message)

        used_sources = [doc.metadata.get("source", "Unknown source") for doc in retrieved_docs]
        return response.content, intent, used_sources

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------
    def _classify_intent(self, message: str) -> str:
        prompt = (
            "Tu es un classifieur d’intention.\n\n"
            "Voici un message utilisateur :\n"
            f'"{message}"\n\n'
            "Catégorise-le dans une des classes suivantes :\n"
            "- playbook_writing\n- question\n- autre\n\n"
            "Réponds uniquement par l’un des trois mots : playbook_writing, question, autre."
        )
        label = self.model.invoke(prompt).content.strip().lower()
        if label not in {"playbook_writing", "question", "autre"}:
            return "question"
        return label

    def _call_rag_response(self, message: str, context: str) -> AIMessage:
        prompt = (
            "Voici des extraits de documents :\n"
            f"{context}\n\n"
            "En te basant uniquement sur ces extraits, réponds à cette question :\n"
            f"{message}"
        )
        return self.model.invoke(prompt)

    def _call_direct_response(self, message: str) -> AIMessage:
        return self.model.invoke(message)

    def _call_playbook_generator(self, message: str, context: str) -> AIMessage:
        prompt = (
            "Voici des extraits de documents :\n"
            f"{context}\n"
            "Tu es un assistant expert en cybersécurité chargé de créer un playbook automatisé.\n\n"
            "En te basant uniquement sur ces extraits et de la demande suivante de l'utilisateur,\n"
            "génère un playbook clair en te basant sur les instructions pour créer un playbook qui sont"
            " dans le fichier \"instructions_to_create_a_playbook.txt\".\n\n"
            "Demande de l'utilisateur :\n"
            f'"""{message}"""\n\n'
            "Il faut que tu répondes en écrivant juste le playbook"
        )
        return self.model.invoke(prompt)

    # ------------------------------------------------------------------
    # File loader helpers
    # ------------------------------------------------------------------
    def _load_all_documents(self, folder_path: Path) -> list[Document]:
        documents: list[Document] = []
        if not folder_path.exists():
            return documents
        for file in folder_path.iterdir():
            if file.is_file():
                documents.extend(self._load_documents_from_path(file))
        return documents

    def _load_documents_from_path(self, path: Path) -> list[Document]:
        loader: CSVLoader | Docx2txtLoader | JSONLoader | PyPDFLoader | TextLoader | UnstructuredHTMLLoader | UnstructuredMarkdownLoader | UnstructuredXMLLoader
        documents: list[Document] = []
        if not path.exists():
            return documents
        try:
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                loader = PyPDFLoader(str(path))
                documents = loader.load()
            elif suffix == ".txt":
                loader = TextLoader(str(path))
                documents = loader.load()
            elif suffix == ".docx":
                loader = Docx2txtLoader(str(path))
                documents = loader.load()
            elif suffix == ".md":
                try:
                    loader = UnstructuredMarkdownLoader(str(path))
                    documents = loader.load()
                except Exception:
                    loader = TextLoader(str(path))
                    documents = loader.load()
            elif suffix in {".html", ".htm"}:
                loader = UnstructuredHTMLLoader(str(path))
                documents = loader.load()
            elif suffix == ".xml":
                loader = UnstructuredXMLLoader(str(path))
                documents = loader.load()
            elif suffix == ".json":
                loader = JSONLoader(str(path), jq_schema=".", text_content=False)
                documents = loader.load()
                for doc in documents:
                    doc.page_content = str(doc.page_content)
            elif suffix == ".csv":
                loader = CSVLoader(file_path=str(path))
                documents = loader.load()
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"⚠️ Erreur en chargeant {path.name} : {exc}")
            return []

        for doc in documents:
            doc.metadata.setdefault("source", str(path))
        return documents


# Global singleton to avoid rebuilding the FAISS index repeatedly.
_ENGINE: ChatbotEngine | None = None


def get_engine() -> ChatbotEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ChatbotEngine()
    return _ENGINE

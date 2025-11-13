"""Core chatbot logic shared by API endpoints."""
from __future__ import annotations

import logging
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

from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv()

logger = logging.getLogger(__name__)


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
        self.embedding = OpenAIEmbeddings(api_key=self.api_key)

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )

        self._vector_store: FAISS | None = None
        logger.info(
            "Initialisation du moteur de chatbot avec les dossiers docs=%s, index=%s et modèle=%s",
            self.docs_path,
            self.index_path,
            self.llm_name,
        )
        self._load_or_create_index()

    # ------------------------------------------------------------------
    # Index bootstrap helpers
    # ------------------------------------------------------------------
    def _load_or_create_index(self) -> None:
        if self.index_path.exists():
            logger.info("Chargement de l'index FAISS existant depuis %s", self.index_path)
            self._vector_store = FAISS.load_local(
                str(self.index_path),
                self.embedding,
                allow_dangerous_deserialization=True,
            )
        else:
            logger.info(
                "Aucun index existant trouvé. Chargement des documents pour créer un nouvel index."
            )
            documents = self._load_all_documents(self.docs_path)
            if documents:
                split_docs = self.text_splitter.split_documents(documents)
                self._vector_store = FAISS.from_documents(split_docs, self.embedding)
                self.index_path.mkdir(parents=True, exist_ok=True)
                self._vector_store.save_local(str(self.index_path))
                logger.info(
                    "Index FAISS initialisé avec %s documents et sauvegardé dans %s",
                    len(split_docs),
                    self.index_path,
                )
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
            logger.info("Ingestion du fichier %s", path)
            documents = self._load_documents_from_path(path)
            if not documents:
                logger.warning("Aucun document chargé depuis %s", path)
                continue
            split_docs = self.text_splitter.split_documents(documents)
            loaded_documents.extend(split_docs)
            ingested_sources.update(
                {doc.metadata.get("source", str(path)) for doc in documents}
            )

        if not loaded_documents:
            logger.warning("Aucun document ingéré. L'index n'a pas été mis à jour.")
            return []

        if self._vector_store is None:
            self._vector_store = FAISS.from_documents(loaded_documents, self.embedding)
            logger.info(
                "Création d'un nouvel index FAISS avec %s fragments de documents", len(loaded_documents)
            )
        else:
            self._vector_store.add_documents(loaded_documents)
            logger.info(
                "Ajout de %s fragments de documents à l'index FAISS existant",
                len(loaded_documents),
            )

        self.index_path.mkdir(parents=True, exist_ok=True)
        self._vector_store.save_local(str(self.index_path))
        logger.info(
            "Index FAISS sauvegardé dans %s. Sources ingérées : %s",
            self.index_path,
            sorted(ingested_sources),
        )
        return sorted(ingested_sources)

    # ------------------------------------------------------------------
    # Chat interaction
    # ------------------------------------------------------------------
    def chat(self, message: str) -> tuple[str, str, list[str]]:
        """Return the assistant answer, detected intent and supporting documents."""

        logger.info("Réception d'un message utilisateur : %s", message)

        if self._vector_store is None:
            retrieved_docs: list[Document] = []
        else:
            retriever = self._vector_store.as_retriever()
            retrieved_docs = retriever.invoke(message)

        logger.info(
            "Documents récupérés : %s",
            [doc.metadata.get("source", "Unknown source") for doc in retrieved_docs],
        )

        context = "\n\n".join(doc.page_content for doc in retrieved_docs)
        has_docs = len(context.strip()) > 100
        intent = self._classify_intent(message)
        logger.info("Intention détectée : %s", intent)

        if intent == "Rag" and has_docs:
            response = self._call_rag_response(message, context)
        else:
            response = self._call_direct_response(message)

        used_sources = [doc.metadata.get("source", "Unknown source") for doc in retrieved_docs]
        logger.info("Réponse générée : %s", response.content)
        logger.info("Sources utilisées : %s", used_sources)
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
            "Rag, NotRag\n\n"
            "Réponds uniquement par l’un des deux mots : Rag, NotRag."
        )
        logger.info("Envoi au LLM pour classification : %s", prompt)
        label = self.model.invoke(prompt).content.strip()
        logger.info("Réponse du LLM pour la classification : %s", label)
        normalized = label.replace(" ", "").lower()
        if normalized == "rag":
            return "Rag"
        return "NotRag"

    def _call_rag_response(self, message: str, context: str) -> AIMessage:
        prompt = (
            "Voici des extraits de documents :\n"
            f"{context}\n\n"
            "En te basant uniquement sur ces extraits, réponds à cette question :\n"
            f"{message}"
        )
        logger.info("Envoi au LLM (RAG) avec le prompt : %s", prompt)
        response = self.model.invoke(prompt)
        logger.info("Réponse du LLM (RAG) : %s", response.content)
        return response

    def _call_direct_response(self, message: str) -> AIMessage:
        logger.info("Envoi au LLM (direct) du message : %s", message)
        response = self.model.invoke(message)
        logger.info("Réponse du LLM (direct) : %s", response.content)
        return response

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
        loader: (
            CSVLoader
            | Docx2txtLoader
            | JSONLoader
            | PyPDFLoader
            | TextLoader
            | UnstructuredHTMLLoader
            | UnstructuredMarkdownLoader
            | UnstructuredXMLLoader
        )
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

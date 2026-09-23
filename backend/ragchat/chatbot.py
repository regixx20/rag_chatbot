"""Core RAG pipeline shared by the API endpoints and the CLI.

Knowledge is split in two kinds of FAISS indexes stored on disk:
- a read-only "demo" index built from the files in ``demo_docs/`` (always available,
  rebuilt automatically when the files or the embedding model change);
- one index per visitor session, holding the documents that visitor uploaded.

A question is answered in four steps: condense it with the conversation history,
retrieve the most relevant chunks from both indexes, drop the ones under a relevance
threshold, then ask the LLM to answer from those numbered extracts only.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEMO_DOCS_DIR = Path(os.getenv("RAG_DEMO_DOCS_DIR", BACKEND_DIR / "demo_docs"))
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", BACKEND_DIR / "rag_data"))

CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
TOP_K = int(os.getenv("RAG_TOP_K", "4"))
# Cosine similarity between the question and a chunk (1 = identical meaning).
# Chunks below this score are ignored instead of being fed to the LLM.
MIN_RELEVANCE = float(os.getenv("RAG_MIN_RELEVANCE", "0.3"))
HISTORY_MESSAGES = int(os.getenv("RAG_HISTORY_MESSAGES", "8"))
HISTORY_CHARS = 1500

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".xml", ".json", ".csv"}
DEMO_INDEX = "demo"


@dataclass
class Source:
    """A retrieved chunk, as shown to the user."""

    number: int
    document: str
    page: int | None
    excerpt: str
    score: float
    is_demo: bool

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "document": self.document,
            "page": self.page,
            "excerpt": self.excerpt,
            "score": round(self.score, 3),
            "is_demo": self.is_demo,
        }


@dataclass
class PreparedAnswer:
    """Everything needed to call the LLM, computed before the (possibly streamed) call."""

    messages: list[BaseMessage]
    intent: str
    sources: list[Source]
    standalone_question: str


# ----------------------------------------------------------------------
# File loading
# ----------------------------------------------------------------------
def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _html_to_text(markup: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def load_file(path: Path, display_name: str | None = None) -> list[Document]:
    """Extract the text of a file. PDF pages keep their page number in metadata."""

    name = display_name or path.name
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        documents = PyPDFLoader(str(path)).load()
        for doc in documents:
            doc.metadata = {"page": int(doc.metadata.get("page", 0)) + 1}
    elif suffix == ".docx":
        documents = Docx2txtLoader(str(path)).load()
    elif suffix in {".html", ".htm"}:
        documents = [Document(page_content=_html_to_text(_read_text(path)))]
    elif suffix == ".json":
        content = json.loads(_read_text(path))
        documents = [Document(page_content=json.dumps(content, ensure_ascii=False, indent=2))]
    elif suffix == ".csv":
        rows = csv.DictReader(_read_text(path).splitlines())
        lines = [", ".join(f"{key}: {value}" for key, value in row.items()) for row in rows]
        documents = [Document(page_content="\n".join(lines))]
    elif suffix in {".txt", ".md", ".xml"}:
        documents = [Document(page_content=_read_text(path))]
    else:
        raise ValueError(f"Format non pris en charge : {suffix}")

    documents = [doc for doc in documents if doc.page_content.strip()]
    for doc in documents:
        doc.metadata["source"] = name
    return documents


# ----------------------------------------------------------------------
# On-disk FAISS indexes
# ----------------------------------------------------------------------
class IndexStore:
    """FAISS indexes persisted on disk, cached in memory and reloaded when changed on disk
    (several gunicorn workers may write to the same index)."""

    def __init__(self, root: Path, embeddings: OpenAIEmbeddings) -> None:
        self.root = root
        self.embeddings = embeddings
        self._cache: dict[str, tuple[float, FAISS]] = {}
        self._lock = threading.RLock()

    def _dir(self, key: str) -> Path:
        return self.root / key

    def _mtime(self, key: str) -> float | None:
        index_file = self._dir(key) / "index.faiss"
        return index_file.stat().st_mtime if index_file.exists() else None

    def get(self, key: str) -> FAISS | None:
        with self._lock:
            mtime = self._mtime(key)
            if mtime is None:
                self._cache.pop(key, None)
                return None
            cached = self._cache.get(key)
            if cached and cached[0] == mtime:
                return cached[1]
            store = FAISS.load_local(
                str(self._dir(key)), self.embeddings, allow_dangerous_deserialization=True
            )
            self._cache[key] = (mtime, store)
            return store

    def _save(self, key: str, store: FAISS) -> None:
        directory = self._dir(key)
        directory.mkdir(parents=True, exist_ok=True)
        store.save_local(str(directory))
        self._cache[key] = (self._mtime(key) or 0.0, store)

    def add(self, key: str, chunks: list[Document], ids: list[str]) -> None:
        with self._lock:
            store = self.get(key)
            if store is None:
                store = FAISS.from_documents(chunks, self.embeddings, ids=ids)
            else:
                store.add_documents(chunks, ids=ids)
            self._save(key, store)

    def delete(self, key: str, ids: list[str]) -> None:
        """Remove chunks without re-embedding anything."""
        with self._lock:
            store = self.get(key)
            if store is None:
                return
            existing = [chunk_id for chunk_id in ids if chunk_id in store.index_to_docstore_id.values()]
            if existing:
                store.delete(existing)
            if store.index.ntotal == 0:
                self.drop(key)
            else:
                self._save(key, store)

    def drop(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            shutil.rmtree(self._dir(key), ignore_errors=True)

    def read_meta(self, key: str) -> str | None:
        meta = self._dir(key) / "fingerprint.txt"
        return meta.read_text(encoding="utf-8") if meta.exists() else None

    def write_meta(self, key: str, value: str) -> None:
        self._dir(key).mkdir(parents=True, exist_ok=True)
        (self._dir(key) / "fingerprint.txt").write_text(value, encoding="utf-8")


# ----------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------
class ChatbotEngine:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY must be provided in the environment.")

        # Explicit timeout: without it a stuck OpenAI call keeps the request open for minutes
        self.model = ChatOpenAI(api_key=api_key, model=CHAT_MODEL, timeout=45, max_retries=1)
        self.condense_model = ChatOpenAI(
            api_key=api_key, model=CHAT_MODEL, timeout=20, max_retries=1, temperature=0
        )
        self.embeddings = OpenAIEmbeddings(api_key=api_key, model=EMBEDDING_MODEL)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        self.indexes = IndexStore(DATA_DIR / "indexes", self.embeddings)
        self._demo_lock = threading.Lock()
        logger.info("Moteur RAG prêt (chat=%s, embeddings=%s)", CHAT_MODEL, EMBEDDING_MODEL)

    # -- Demo corpus ----------------------------------------------------
    def demo_files(self) -> list[Path]:
        if not DEMO_DOCS_DIR.exists():
            return []
        return sorted(
            path
            for path in DEMO_DOCS_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    def _demo_fingerprint(self) -> str:
        digest = hashlib.sha256(EMBEDDING_MODEL.encode())
        for path in self.demo_files():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def ensure_demo_index(self) -> None:
        """(Re)build the demo index when missing or outdated. Cheap no-op otherwise."""
        with self._demo_lock:
            fingerprint = self._demo_fingerprint()
            if self.indexes.read_meta(DEMO_INDEX) == fingerprint and self.indexes.get(DEMO_INDEX):
                return
            self.indexes.drop(DEMO_INDEX)
            chunks: list[Document] = []
            for path in self.demo_files():
                chunks.extend(self.splitter.split_documents(load_file(path)))
            if chunks:
                for chunk in chunks:
                    chunk.metadata["is_demo"] = True
                ids = [f"demo:{i}" for i in range(len(chunks))]
                self.indexes.add(DEMO_INDEX, chunks, ids)
                self.indexes.write_meta(DEMO_INDEX, fingerprint)
            logger.info("Index de démo construit : %s fragments", len(chunks))

    # -- Session documents ----------------------------------------------
    @staticmethod
    def session_key(session_id: str) -> str:
        return f"session-{session_id}"

    def ingest(self, session_id: str, document_id: int, path: Path, display_name: str) -> int:
        """Index a visitor's file. Returns the number of chunks (0 if no text was found)."""
        chunks = self.splitter.split_documents(load_file(path, display_name))
        if not chunks:
            return 0
        for chunk in chunks:
            chunk.metadata["document_id"] = document_id
        ids = [f"{document_id}:{i}" for i in range(len(chunks))]
        self.indexes.add(self.session_key(session_id), chunks, ids)
        logger.info("Document %s indexé (%s fragments)", display_name, len(chunks))
        return len(chunks)

    def remove(self, session_id: str, document_id: int, chunk_count: int) -> None:
        ids = [f"{document_id}:{i}" for i in range(chunk_count)]
        self.indexes.delete(self.session_key(session_id), ids)

    def drop_session(self, session_id: str) -> None:
        self.indexes.drop(self.session_key(session_id))

    # -- Retrieval --------------------------------------------------------
    def retrieve(self, session_id: str, query: str) -> list[Source]:
        self.ensure_demo_index()
        candidates: list[tuple[Document, float]] = []
        for key in (self.session_key(session_id), DEMO_INDEX):
            store = self.indexes.get(key)
            if store is not None:
                # FAISS returns squared L2 distances; OpenAI embeddings are unit vectors,
                # so cosine similarity = 1 - d² / 2
                candidates.extend(
                    (doc, 1 - float(distance) / 2)
                    for doc, distance in store.similarity_search_with_score(query, k=TOP_K)
                )

        relevant = sorted(
            (item for item in candidates if item[1] >= MIN_RELEVANCE),
            key=lambda item: item[1],
            reverse=True,
        )[:TOP_K]
        logger.info(
            "Recherche '%s' : %s candidats, %s retenus (scores %s)",
            query,
            len(candidates),
            len(relevant),
            [round(score, 2) for _, score in relevant],
        )
        return [
            Source(
                number=i + 1,
                document=doc.metadata.get("source", "Document"),
                page=doc.metadata.get("page"),
                excerpt=doc.page_content.strip(),
                score=score,
                is_demo=bool(doc.metadata.get("is_demo")),
            )
            for i, (doc, score) in enumerate(relevant)
        ]

    # -- Prompting ------------------------------------------------------------
    @staticmethod
    def _history_messages(history: Iterable[dict[str, str]]) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        for entry in list(history)[-HISTORY_MESSAGES:]:
            content = (entry.get("content") or "").strip()[:HISTORY_CHARS]
            if not content:
                continue
            role = entry.get("role")
            messages.append(HumanMessage(content) if role == "user" else AIMessage(content))
        return messages

    def condense_question(self, message: str, history: list[BaseMessage]) -> str:
        """Rewrite a follow-up question ("and for minors?") into a self-contained one,
        so the vector search gets the full intent."""
        if not history:
            return message
        transcript = "\n".join(
            f"{'Utilisateur' if isinstance(m, HumanMessage) else 'Assistant'} : {m.content}"
            for m in history[-4:]
        )
        prompt = [
            SystemMessage(
                "Reformule la dernière question de l'utilisateur en une question autonome, "
                "compréhensible sans l'historique, dans la même langue. "
                "Réponds uniquement par la question reformulée."
            ),
            HumanMessage(f"Historique :\n{transcript}\n\nDernière question : {message}"),
        ]
        try:
            rewritten = str(self.condense_model.invoke(prompt).content).strip()
            logger.info("Question reformulée : %s -> %s", message, rewritten)
            return rewritten or message
        except Exception:
            logger.exception("Échec de la reformulation, question d'origine utilisée")
            return message

    def prepare(
        self,
        message: str,
        mode: str = "rag",
        history: Iterable[dict[str, str]] | None = None,
        session_id: str = "cli",
    ) -> PreparedAnswer:
        mode = mode.lower()
        if mode not in {"rag", "direct"}:
            raise ValueError(f"Mode de chat invalide : {mode}")

        history_messages = self._history_messages(history or [])
        language_rule = "Réponds toujours dans la langue de la question de l'utilisateur."

        if mode == "direct":
            system = SystemMessage(
                "Tu es un assistant utile, précis et concis. Utilise le Markdown si cela "
                f"améliore la lisibilité. {language_rule}"
            )
            return PreparedAnswer(
                [system, *history_messages, HumanMessage(message)], "Direct", [], message
            )

        standalone = self.condense_question(message, history_messages)
        sources = self.retrieve(session_id, standalone)

        if not sources:
            system = SystemMessage(
                "Aucun passage pertinent n'a été trouvé dans les documents de l'utilisateur "
                "pour cette question. Explique-le brièvement et poliment, sans inventer de "
                "réponse, et suggère d'ajouter un document qui contient l'information ou de "
                f"désactiver le mode RAG pour une réponse générale. {language_rule}"
            )
            return PreparedAnswer([system, HumanMessage(message)], "NoContext", [], standalone)

        extracts = "\n\n".join(
            f"[{s.number}] {s.document}{f', page {s.page}' if s.page else ''}\n{s.excerpt}"
            for s in sources
        )
        system = SystemMessage(
            "Tu réponds à partir des extraits de documents fournis ci-dessous, et uniquement "
            "à partir d'eux. Cite tes sources avec leur numéro entre crochets, par exemple [1]. "
            "Si les extraits ne permettent pas de répondre, dis-le clairement au lieu "
            f"d'inventer. Utilise le Markdown si utile. {language_rule}\n\n"
            f"Extraits :\n{extracts}"
        )
        return PreparedAnswer(
            [system, *history_messages, HumanMessage(message)], "Rag", sources, standalone
        )

    # -- Answering --------------------------------------------------------------
    def answer(self, prepared: PreparedAnswer) -> str:
        return str(self.model.invoke(prepared.messages).content)

    def stream(self, prepared: PreparedAnswer) -> Iterator[str]:
        for chunk in self.model.stream(prepared.messages):
            if chunk.content:
                yield str(chunk.content)

    def chat(self, message: str, mode: str = "rag", history=None, session_id: str = "cli"):
        """Non-streamed helper: returns (answer, intent, sources)."""
        prepared = self.prepare(message, mode, history, session_id)
        return self.answer(prepared), prepared.intent, prepared.sources


_ENGINE: ChatbotEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_engine() -> ChatbotEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = ChatbotEngine()
        return _ENGINE

"""Core RAG pipeline shared by the API endpoints and the CLI.

Knowledge is split in two kinds of FAISS indexes stored on disk:
- a read-only "demo" index built from the files in ``demo_docs/`` (always available,
  rebuilt automatically when the files or the embedding model change);
- one index per visitor session, holding the documents that visitor uploaded.

A question is answered in four steps: condense it with the conversation history,
retrieve the most relevant chunks from both indexes, drop the ones under a relevance
threshold, then ask Claude to answer from those numbered extracts only.

Generation runs on Claude (Anthropic API); embeddings stay on OpenAI, since Anthropic
does not provide an embeddings endpoint.
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
import anthropic
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEMO_DOCS_DIR = Path(os.getenv("RAG_DEMO_DOCS_DIR", BACKEND_DIR / "demo_docs"))
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", BACKEND_DIR / "rag_data"))

CHAT_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")
# Effort drives thinking depth and token spend; "low"/"medium" hold quality well on
# RAG answers, where the heavy lifting is done by retrieval.
ANSWER_EFFORT = os.getenv("CLAUDE_ANSWER_EFFORT", "medium")
ANSWER_MAX_TOKENS = int(os.getenv("CLAUDE_ANSWER_MAX_TOKENS", "4000"))

# $ per million tokens (input, output), to enforce the daily budget from real usage.
# Unknown models are billed at the most expensive rate, so the budget stays safe.
MODEL_PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
DEFAULT_PRICE = (10.0, 50.0)
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
    """Everything needed to call Claude, computed before the (possibly streamed) call."""

    system: str
    messages: list[dict]
    intent: str
    sources: list[Source]
    standalone_question: str
    cost_usd: float = 0.0  # spent while preparing (question rewriting)


@dataclass
class StreamResult:
    """Filled once the stream is over."""

    cost_usd: float = 0.0
    stop_reason: str | None = None


def usage_cost(model: str, usage) -> float:
    input_price, output_price = MODEL_PRICES.get(model, DEFAULT_PRICE)
    input_tokens = (
        (usage.input_tokens or 0)
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.1
    )
    return (input_tokens * input_price + (usage.output_tokens or 0) * output_price) / 1_000_000


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
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise RuntimeError("OPENAI_API_KEY must be provided in the environment (embeddings).")
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY must be provided in the environment.")

        # Explicit timeout: without it a stuck call keeps the request open for minutes
        self.claude = anthropic.Anthropic(timeout=60.0, max_retries=2)
        self.embeddings = OpenAIEmbeddings(api_key=openai_key, model=EMBEDDING_MODEL)
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

    # -- Claude calls -----------------------------------------------------------
    @staticmethod
    def _request_options(effort: str) -> dict:
        options: dict = {"output_config": {"effort": effort}}
        # On a safety decline, let the API re-run the request on its recommended
        # fallback model instead of returning a refusal (Claude Opus 5 / Fable).
        if CHAT_MODEL.startswith(("claude-opus-5", "claude-fable")):
            options["betas"] = ["server-side-fallback-2026-07-01"]
            options["fallbacks"] = "default"
        return options

    def _complete(self, system: str, messages: list[dict], effort: str, max_tokens: int):
        """Streamed under the hood (no HTTP timeout risk), returns the final message."""
        with self.claude.beta.messages.stream(
            model=CHAT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            **self._request_options(effort),
        ) as stream:
            return stream.get_final_message()

    @staticmethod
    def _text_of(message) -> str:
        if message.stop_reason == "refusal":
            return ""
        return "".join(block.text for block in message.content if block.type == "text").strip()

    # -- Prompting ------------------------------------------------------------
    @staticmethod
    def _history_messages(history: Iterable[dict[str, str]]) -> list[dict]:
        messages: list[dict] = []
        for entry in list(history)[-HISTORY_MESSAGES:]:
            content = (entry.get("content") or "").strip()[:HISTORY_CHARS]
            if content:
                role = "user" if entry.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": content})
        # The conversation sent to Claude must start with a user turn
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        return messages

    def condense_question(self, message: str, history: list[dict]) -> tuple[str, float]:
        """Rewrite a follow-up question ("and for minors?") into a self-contained one,
        so the vector search gets the full intent. Returns (question, cost)."""
        if not history:
            return message, 0.0
        transcript = "\n".join(
            f"{'Utilisateur' if m['role'] == 'user' else 'Assistant'} : {m['content']}"
            for m in history[-4:]
        )
        try:
            response = self._complete(
                system=(
                    "Tu reformules la dernière question d'une conversation en une question autonome, "
                    "compréhensible sans l'historique, dans la même langue que la question. "
                    "Réponds uniquement par la question reformulée, sans guillemets ni commentaire."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": f"Historique :\n{transcript}\n\nDernière question : {message}",
                    }
                ],
                effort="low",
                max_tokens=1024,
            )
            rewritten = self._text_of(response)
            logger.info("Question reformulée : %s -> %s", message, rewritten)
            return rewritten or message, usage_cost(CHAT_MODEL, response.usage)
        except anthropic.APIError:
            logger.exception("Échec de la reformulation, question d'origine utilisée")
            return message, 0.0

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
        conversation = [*history_messages, {"role": "user", "content": message}]
        style = (
            "Réponds dans la langue de la question de l'utilisateur. "
            "Va droit au but : quelques phrases ou une courte liste suffisent dans la plupart des cas. "
            "Utilise le Markdown (gras, listes) seulement quand il améliore la lisibilité."
        )

        if mode == "direct":
            system = f"Tu es l'assistant d'un chatbot de démonstration, utile et précis. {style}"
            return PreparedAnswer(system, conversation, "Direct", [], message)

        standalone, cost = self.condense_question(message, history_messages)
        sources = self.retrieve(session_id, standalone)

        if not sources:
            system = (
                "Aucun passage pertinent n'a été trouvé dans les documents de l'utilisateur pour "
                "cette question. Explique-le en une ou deux phrases, sans répondre à la question avec "
                "tes connaissances générales, et suggère d'ajouter un document qui contient "
                f"l'information ou de passer en mode « Modèle seul ». {style}"
            )
            return PreparedAnswer(
                system, [{"role": "user", "content": message}], "NoContext", [], standalone, cost
            )

        def as_xml(source: Source) -> str:
            page = f' page="{source.page}"' if source.page else ""
            return (
                f'<extrait numero="{source.number}" document="{source.document}"{page}>\n'
                f"{source.excerpt}\n</extrait>"
            )

        extracts = "\n\n".join(as_xml(source) for source in sources)
        system = (
            "Tu réponds aux questions à partir des extraits de documents ci-dessous, et uniquement "
            "à partir d'eux : n'ajoute pas d'informations venant d'ailleurs.\n"
            "- Cite chaque affirmation avec le numéro de l'extrait entre crochets, par exemple [1] ou [2][3].\n"
            "- Si les extraits ne répondent qu'en partie, réponds sur cette partie et dis ce qui manque.\n"
            "- S'ils ne permettent pas de répondre, dis-le clairement au lieu d'inventer.\n"
            "- Les extraits peuvent être dans une autre langue que la question : traduis au besoin.\n"
            f"{style}\n\n"
            f"<extraits>\n{extracts}\n</extraits>"
        )
        return PreparedAnswer(system, conversation, "Rag", sources, standalone, cost)

    # -- Answering --------------------------------------------------------------
    REFUSAL_TEXT = "Je ne peux pas répondre à cette demande."
    TRUNCATED_TEXT = "\n\n*(Réponse tronquée : la limite de longueur a été atteinte.)*"

    def stream(self, prepared: PreparedAnswer, result: StreamResult | None = None) -> Iterator[str]:
        """Yield the answer text as it is generated. `result` receives the cost and
        stop reason once the stream is over."""
        result = result or StreamResult()
        with self.claude.beta.messages.stream(
            model=CHAT_MODEL,
            max_tokens=ANSWER_MAX_TOKENS,
            system=prepared.system,
            messages=prepared.messages,
            **self._request_options(ANSWER_EFFORT),
        ) as stream:
            yielded = False
            for text in stream.text_stream:
                yielded = yielded or bool(text)
                yield text
            final = stream.get_final_message()

        result.stop_reason = final.stop_reason
        result.cost_usd = prepared.cost_usd + usage_cost(CHAT_MODEL, final.usage)
        if final.stop_reason == "refusal" and not yielded:
            yield self.REFUSAL_TEXT
        elif final.stop_reason == "max_tokens":
            yield self.TRUNCATED_TEXT
        logger.info(
            "Réponse générée (%s, arrêt=%s, coût=%.4f $)", prepared.intent, final.stop_reason, result.cost_usd
        )

    def answer(self, prepared: PreparedAnswer, result: StreamResult | None = None) -> str:
        return "".join(self.stream(prepared, result))

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

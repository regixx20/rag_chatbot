"""Core RAG pipeline shared by the API endpoints and the CLI.

Knowledge is split in two kinds of FAISS indexes stored on disk:
- a read-only "demo" index built from the files in ``demo_docs/`` (always available,
  rebuilt automatically when the files or the embedding model change);
- one index per visitor session, holding the documents that visitor uploaded.

A question is answered in four steps: condense it with the conversation history,
retrieve the most relevant chunks from both indexes, drop the ones under a relevance
threshold, then ask the model to answer from those numbered extracts only.

Both generation and embeddings run on the Gemini API free tier (one key, no cost).
When a model's free quota is exhausted, the request falls back to lighter models.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import shutil
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
import numpy as np
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
import httpx
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEMO_DOCS_DIR = Path(os.getenv("RAG_DEMO_DOCS_DIR", BACKEND_DIR / "demo_docs"))
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", BACKEND_DIR / "rag_data"))

# Tried in order: when a model is out of free-tier quota (429), overloaded (503) or too
# slow, the next one answers instead. Ordered by measured free-tier latency (flash-lite
# answers in ~1 s while the bigger Flash models are often saturated). Comma-separated.
CHAT_MODELS = [
    model.strip()
    for model in os.getenv(
        "GEMINI_MODELS",
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.6-flash,gemini-3.5-flash,gemini-3.7-flash,gemini-3.8-flash",
    ).split(",")
    if model.strip()
]
# Query rewriting is a small task: light models answer faster and have their own quota
REWRITE_MODELS = [
    model.strip()
    for model in os.getenv(
        "GEMINI_REWRITE_MODELS", "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-3.6-flash"
    ).split(",")
    if model.strip()
]
ANSWER_THINKING = os.getenv("GEMINI_ANSWER_THINKING", "LOW")
# Free-tier latency varies a lot from one minute to the next: rather than waiting on a
# saturated model, give each one a short deadline for its first token, then move on.
# (The API rejects deadlines under 10 s.)
ANSWER_TIMEOUT_S = float(os.getenv("GEMINI_ANSWER_TIMEOUT", "20"))
REWRITE_TIMEOUT_S = float(os.getenv("GEMINI_REWRITE_TIMEOUT", "10"))
# Number of models asked in parallel; the first to answer wins (each has its own quota)
RACE_WIDTH = int(os.getenv("GEMINI_RACE_WIDTH", "2"))
# Whatever happens, stop trying new models after this long and tell the user
FALLBACK_BUDGET_S = float(os.getenv("GEMINI_FALLBACK_BUDGET", "45"))
ANSWER_MAX_TOKENS = int(os.getenv("GEMINI_ANSWER_MAX_TOKENS", "4000"))
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIMENSIONS = int(os.getenv("GEMINI_EMBEDDING_DIMENSIONS", "768"))
TOP_K = int(os.getenv("RAG_TOP_K", "6"))
# Cosine similarity between the question and a chunk (1 = identical meaning).
# Chunks below this score are ignored instead of being fed to the LLM.
# Calibrated on gemini-embedding-2: relevant chunks score 0.65-0.8, off-topic ones < 0.58.
MIN_RELEVANCE = float(os.getenv("RAG_MIN_RELEVANCE", "0.6"))
HISTORY_MESSAGES = int(os.getenv("RAG_HISTORY_MESSAGES", "8"))
HISTORY_CHARS = 1500

CHUNK_SIZE = 1500
# Free tier: 100 embedded texts per minute. A visitor document is capped so its
# indexing fits in about a minute (~90 chunks of 1500 characters, ~40 pages).
MAX_CHUNKS_PER_DOCUMENT = int(os.getenv("RAG_MAX_CHUNKS_PER_DOCUMENT", "90"))

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
    """Everything needed to call the model, computed before the (possibly streamed) call."""

    system: str
    messages: list[dict]
    intent: str
    sources: list[Source]
    standalone_question: str
    cost_usd: float = 0.0  # spent while preparing (question rewriting)


@dataclass
class StreamResult:
    """Filled once the stream is over."""

    cost_usd: float = 0.0  # always 0 on the free tier, kept for the usage records
    stop_reason: str | None = None
    model: str | None = None


class DocumentTooLarge(ValueError):
    """The document would need more embedding requests than the free tier allows."""


class QuotaExhausted(RuntimeError):
    """Every configured model is out of free-tier quota for now."""

    MESSAGE = "Les modèles gratuits sont momentanément saturés. Réessayez dans une minute."


# A model that times out or drops the connection is treated like an overloaded one
httpx_errors = (httpx.TimeoutException, httpx.TransportError)


_RACE_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini-race")


def _close_loser(future, winner) -> None:
    """Close the stream of a model that answered after the race was won."""
    if future.cancelled() or future.exception() is not None:
        return
    result = future.result()
    if result is not winner:
        close = getattr(result[2], "close", None)
        if close:
            close()


def _retry_delay(error: Exception, default: float) -> float:
    """Delay suggested by the API ("Please retry in 39.2s"), capped to one minute."""
    match = re.search(r"retry in ([\d.]+)s", str(error))
    return min(float(match.group(1)) + 1, 65.0) if match else default


def _should_fall_back(error: Exception) -> bool:
    """Quota exhausted (429), model unavailable (404) or overloaded (500/503):
    worth trying the next model. Other errors (bad request, bad key) are not."""
    if isinstance(error, genai_errors.ClientError):
        return error.code in (404, 429)
    return isinstance(error, genai_errors.ServerError)


# ----------------------------------------------------------------------
# Embeddings
# ----------------------------------------------------------------------
class GeminiEmbeddings(Embeddings):
    """LangChain embeddings backed by the Gemini API.

    gemini-embedding-2 merges a plain list of strings into ONE vector, so each text
    is sent as its own Content. The task is given as a text prefix (this model has no
    task_type), and vectors are L2-normalised: the FAISS scoring assumes unit vectors.
    """

    BATCH_SIZE = 50
    MAX_ATTEMPTS = 4

    def __init__(self, client: genai.Client) -> None:
        self.client = client

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[start : start + self.BATCH_SIZE]
            contents = [types.Content(parts=[types.Part(text=text)]) for text in batch]
            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    response = self.client.models.embed_content(
                        model=EMBEDDING_MODEL,
                        contents=contents,
                        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
                    )
                    break
                except genai_errors.APIError as error:
                    # Free tier: each text counts as one request (100 per minute), and
                    # models get overloaded at peak times: wait as told, then retry
                    if not _should_fall_back(error) or attempt == self.MAX_ATTEMPTS - 1:
                        raise
                    delay = _retry_delay(error, default=2 ** attempt * 5)
                    logger.warning("Quota d'embeddings atteint, nouvel essai dans %.0f s", delay)
                    time.sleep(delay)
            for embedding in response.embeddings:
                vector = np.asarray(embedding.values, dtype="float32")
                vectors.append((vector / (np.linalg.norm(vector) or 1.0)).tolist())
        if len(vectors) != len(texts):
            raise RuntimeError("Le nombre de vecteurs ne correspond pas au nombre de textes.")
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([f"title: none | text: {text}" for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([f"task: search result | query: {text}"])[0]


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

    def __init__(self, root: Path, embeddings: Embeddings) -> None:
        self.root = root
        self.embeddings = embeddings
        self._cache: dict[str, tuple[int, FAISS]] = {}
        self._lock = threading.RLock()

    def _dir(self, key: str) -> Path:
        return self.root / key

    # FAISS's C++ file I/O cannot open non-ASCII paths on Windows (e.g. C:\Users\Régix),
    # so indexes are serialised in memory and written with Python instead.
    INDEX_FILE = "index.bin"

    def _mtime(self, key: str) -> int | None:
        index_file = self._dir(key) / self.INDEX_FILE
        return index_file.stat().st_mtime_ns if index_file.exists() else None

    def get(self, key: str) -> FAISS | None:
        with self._lock:
            mtime = self._mtime(key)
            if mtime is None:
                self._cache.pop(key, None)
                return None
            cached = self._cache.get(key)
            if cached and cached[0] == mtime:
                return cached[1]
            store = FAISS.deserialize_from_bytes(
                (self._dir(key) / self.INDEX_FILE).read_bytes(),
                self.embeddings,
                allow_dangerous_deserialization=True,  # only files written by this server
            )
            self._cache[key] = (mtime, store)
            return store

    def _save(self, key: str, store: FAISS) -> None:
        directory = self._dir(key)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / self.INDEX_FILE).write_bytes(store.serialize_to_bytes())
        self._cache[key] = (self._mtime(key) or 0, store)

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
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY must be provided in the environment.")

        # Explicit timeout (ms): without it a stuck call keeps the request open for minutes
        # One HTTP attempt per model: on overload the next model is tried right away,
        # instead of the SDK retrying the same saturated model for a long time
        self.gemini = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=30_000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )
        self.embeddings = GeminiEmbeddings(self.gemini)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=200)
        self.indexes = IndexStore(DATA_DIR / "indexes", self.embeddings)
        # The demo index is committed next to the demo files: a server that wakes up
        # loads it instead of re-embedding the whole corpus (free-tier quota)
        self.demo_indexes = IndexStore(DEMO_DOCS_DIR, self.embeddings)
        self._demo_lock = threading.Lock()
        logger.info("Moteur RAG prêt (chat=%s, embeddings=%s)", CHAT_MODELS, EMBEDDING_MODEL)

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
        digest = hashlib.sha256(f"{EMBEDDING_MODEL}:{EMBEDDING_DIMENSIONS}:{CHUNK_SIZE}".encode())
        for path in self.demo_files():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def ensure_demo_index(self) -> None:
        """(Re)build the demo index when missing or outdated. Cheap no-op otherwise."""
        with self._demo_lock:
            fingerprint = self._demo_fingerprint()
            if self.demo_indexes.read_meta(DEMO_INDEX) == fingerprint and self.demo_indexes.get(DEMO_INDEX):
                return
            self.demo_indexes.drop(DEMO_INDEX)
            chunks: list[Document] = []
            for path in self.demo_files():
                chunks.extend(self.splitter.split_documents(load_file(path)))
            if chunks:
                for chunk in chunks:
                    chunk.metadata["is_demo"] = True
                ids = [f"demo:{i}" for i in range(len(chunks))]
                self.demo_indexes.add(DEMO_INDEX, chunks, ids)
                self.demo_indexes.write_meta(DEMO_INDEX, fingerprint)
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
        if len(chunks) > MAX_CHUNKS_PER_DOCUMENT:
            raise DocumentTooLarge(
                f"Document trop long pour la démo gratuite (environ {MAX_CHUNKS_PER_DOCUMENT * CHUNK_SIZE // 3500} "
                "pages maximum). Essayez avec un extrait plus court."
            )
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
    def retrieve(self, session_id: str, queries: list[str]) -> list[Source]:
        """Search every query in the visitor's documents and the demo corpus, keep each
        chunk's best score, drop what is under the relevance threshold."""
        self.ensure_demo_index()
        stores = [
            store
            for store in (self.indexes.get(self.session_key(session_id)), self.demo_indexes.get(DEMO_INDEX))
            if store is not None
        ]
        best: dict[str, tuple[Document, float]] = {}
        for query in queries:
            for store in stores:
                # FAISS returns squared L2 distances; embeddings are unit vectors,
                # so cosine similarity = 1 - d² / 2
                for doc, distance in store.similarity_search_with_score(query, k=TOP_K + 2):
                    score = 1 - float(distance) / 2
                    key = hashlib.sha1(
                        f"{doc.metadata.get('source')}|{doc.metadata.get('page')}|{doc.page_content}".encode()
                    ).hexdigest()
                    if key not in best or score > best[key][1]:
                        best[key] = (doc, score)

        relevant = sorted(
            (item for item in best.values() if item[1] >= MIN_RELEVANCE),
            key=lambda item: item[1],
            reverse=True,
        )[:TOP_K]
        logger.info(
            "Recherche %s : %s candidats, %s retenus (scores %s)",
            queries,
            len(best),
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

    # -- Gemini calls -----------------------------------------------------------
    @staticmethod
    def _config(system: str, thinking: str, max_tokens: int, timeout_s: float) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=thinking),
            http_options=types.HttpOptions(
                timeout=int(timeout_s * 1000), retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )

    @staticmethod
    def _contents(messages: list[dict]) -> list[types.Content]:
        return [
            types.Content(
                role="user" if message["role"] == "user" else "model",
                parts=[types.Part(text=message["content"])],
            )
            for message in messages
        ]

    def _open_stream(
        self,
        system: str,
        messages: list[dict],
        thinking: str,
        max_tokens: int,
        models: list[str],
        timeout_s: float = ANSWER_TIMEOUT_S,
    ):
        """Start a stream on the first model able to answer.

        Models are raced RACE_WIDTH at a time: each free-tier model has its own quota and
        load, so asking two at once and keeping the first to produce a token avoids
        waiting for a saturated one to time out. Returns (model, first_chunk, iterator),
        so any fallback happens before a single token reaches the user."""

        def start(model: str):
            iterator = iter(
                self.gemini.models.generate_content_stream(
                    model=model,
                    contents=self._contents(messages),
                    config=self._config(system, thinking, max_tokens, timeout_s),
                )
            )
            return model, next(iterator, None), iterator

        last_error: Exception | None = None
        started = time.monotonic()
        remaining = list(models)
        while remaining and time.monotonic() - started <= FALLBACK_BUDGET_S:
            batch, remaining = remaining[:RACE_WIDTH], remaining[RACE_WIDTH:]
            futures = [_RACE_POOL.submit(start, model) for model in batch]
            winner = None
            for future in as_completed(futures):
                try:
                    winner = future.result()
                    break
                except (genai_errors.APIError, *httpx_errors) as error:
                    if isinstance(error, genai_errors.APIError) and not _should_fall_back(error):
                        raise
                    reason = getattr(error, "code", None) or type(error).__name__
                    logger.warning("Modèle indisponible (%s), on continue", reason)
                    last_error = error
            # Losers keep running in the background: close their stream once they answer
            for future in futures:
                future.add_done_callback(lambda f, w=winner: _close_loser(f, w))
            if winner is not None:
                return winner
        raise QuotaExhausted(QuotaExhausted.MESSAGE) from last_error

    def _complete(
        self,
        system: str,
        messages: list[dict],
        thinking: str,
        max_tokens: int,
        models: list[str],
        timeout_s: float = ANSWER_TIMEOUT_S,
    ) -> str:
        _, first, iterator = self._open_stream(system, messages, thinking, max_tokens, models, timeout_s)
        chunks = [first, *iterator] if first is not None else []
        return "".join(chunk.text or "" for chunk in chunks).strip()

    # -- Prompting ------------------------------------------------------------
    @staticmethod
    def _history_messages(history: Iterable[dict[str, str]]) -> list[dict]:
        messages: list[dict] = []
        for entry in list(history)[-HISTORY_MESSAGES:]:
            content = (entry.get("content") or "").strip()[:HISTORY_CHARS]
            if content:
                role = "user" if entry.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": content})
        # The conversation sent to the model must start with a user turn
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        return messages

    def search_queries(self, message: str, history: list[dict]) -> list[str]:
        """Turn the question into self-contained search queries: one in the user's language,
        one in English. Follow-ups ("and for minors?") get the context of the conversation,
        and an English query finds passages of English documents asked about in French."""
        transcript = "\n".join(
            f"{'Utilisateur' if m['role'] == 'user' else 'Assistant'} : {m['content'][:500]}"
            for m in history[-4:]
        )
        prompt = (f"Historique :\n{transcript}\n\n" if transcript else "") + f"Question : {message}"
        try:
            text = self._complete(
                system=(
                    "Tu prépares une recherche dans des documents. Réécris la question en requête de "
                    "recherche autonome, compréhensible sans l'historique et avec les mots-clés utiles. "
                    "Réponds avec exactement deux lignes, sans numérotation ni commentaire : "
                    "ligne 1, la requête dans la langue de la question ; ligne 2, la même requête en anglais."
                ),
                messages=[{"role": "user", "content": prompt}],
                thinking="MINIMAL",
                max_tokens=300,
                models=REWRITE_MODELS,
                timeout_s=REWRITE_TIMEOUT_S,
            )
        except (genai_errors.APIError, QuotaExhausted, *httpx_errors) as error:
            # Expected on a saturated free tier: search with the raw question instead
            logger.warning("Reformulation indisponible (%s), question d'origine utilisée", error)
            return [message]

        queries = [re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", line).strip() for line in text.splitlines()]
        queries = list(dict.fromkeys(q for q in queries if q))[:2]
        logger.info("Requêtes de recherche : %s -> %s", message, queries)
        return queries or [message]

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

        queries = self.search_queries(message, history_messages)
        standalone, cost = queries[0], 0.0
        sources = self.retrieve(session_id, queries)

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
        """Yield the answer text as it is generated. `result` receives the model used
        and the finish reason once the stream is over."""
        result = result or StreamResult()
        model, first, iterator = self._open_stream(
            prepared.system, prepared.messages, ANSWER_THINKING, ANSWER_MAX_TOKENS, CHAT_MODELS
        )
        result.model = model
        yielded = False
        finish_reason = None
        for chunk in ([first, *iterator] if first is not None else []):
            if chunk.candidates and chunk.candidates[0].finish_reason:
                finish_reason = chunk.candidates[0].finish_reason.name
            if chunk.text:
                yielded = True
                yield chunk.text

        result.stop_reason = finish_reason
        if finish_reason == "MAX_TOKENS":
            yield self.TRUNCATED_TEXT
        elif not yielded:
            # Blocked by safety filters (SAFETY, PROHIBITED_CONTENT…) or empty answer
            yield self.REFUSAL_TEXT
        logger.info("Réponse générée (%s, modèle=%s, fin=%s)", prepared.intent, model, finish_reason)

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

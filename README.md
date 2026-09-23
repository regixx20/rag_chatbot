# RAG Chatbot

Chatbot qui répond à partir de vos documents (Retrieval-Augmented Generation), en citant ses sources avec le numéro de page.

**Stack** : React (Vite) · Django REST Framework · LangChain · FAISS · OpenAI

## Fonctionnement

```
Question ──► Reformulation avec l'historique ──► Recherche vectorielle (FAISS)
                                                        │
                        Filtrage par seuil de pertinence ◄┘
                                     │
          Prompt avec extraits numérotés [1] [2]… ──► LLM (réponse en streaming)
```

1. **Ingestion** : le texte du fichier est extrait (numéros de page conservés pour les PDF), découpé en fragments de 1000 caractères, puis vectorisé avec `text-embedding-3-small`.
2. **Reformulation** : une question de suivi (« et pour les mineurs ? ») est réécrite en question autonome avant la recherche.
3. **Recherche** : les fragments les plus proches sont récupérés ; ceux dont la similarité cosinus est sous le seuil sont écartés, pour ne pas donner de contexte hors sujet au modèle.
4. **Génération** : le modèle répond uniquement à partir des extraits, cite ses sources `[n]`, et le dit clairement quand l'information n'y figure pas.

Un document de démonstration (`backend/demo_docs/`) est indexé automatiquement au démarrage. Les documents ajoutés par un visiteur sont isolés dans sa session et supprimés après 24 h.

## Lancer en local

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # ou source .venv/bin/activate
pip install -r requirements.txt
echo OPENAI_API_KEY=sk-... > .env
python manage.py migrate
python manage.py runserver

# Frontend
cd frontend
npm install
npm run dev
```

## Configuration (variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `OPENAI_API_KEY` | — | Clé OpenAI (obligatoire) |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Modèle de génération |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Modèle d'embeddings |
| `RAG_TOP_K` | `4` | Nombre d'extraits envoyés au modèle |
| `RAG_MIN_RELEVANCE` | `0.3` | Similarité cosinus minimale d'un extrait |
| `RAG_DATA_DIR` | `backend/rag_data` | Dossier des index FAISS |
| `VITE_API_BASE_URL` | URL Render en production | URL de l'API pour le frontend |

## API

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/health/` | État du serveur |
| `GET` / `POST` | `/api/documents/` | Lister / ajouter des documents (en-tête `X-Session-Id`) |
| `DELETE` | `/api/documents/<id>/` | Supprimer un document |
| `POST` | `/api/chat/stream/` | Réponse en streaming (NDJSON : `meta`, `token`, `done`) |
| `POST` | `/api/chat/` | Réponse complète en JSON |

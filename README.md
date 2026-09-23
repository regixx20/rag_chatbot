# RAG Chatbot

Chatbot qui répond à partir de vos documents (Retrieval-Augmented Generation), en citant ses sources avec le numéro de page.

**Stack** : React (Vite) · Django REST Framework · Gemini API · FAISS

## Fonctionnement

```
Question ──► Reformulation avec l'historique ──► Recherche vectorielle (FAISS)
                                                        │
                        Filtrage par seuil de pertinence ◄┘
                                     │
          Prompt avec extraits numérotés [1] [2]… ──► Gemini (réponse en streaming)
```

1. **Ingestion** : le texte du fichier est extrait (numéros de page conservés pour les PDF), découpé en fragments de 1500 caractères, puis vectorisé avec `gemini-embedding-2`.
2. **Reformulation** : la question est réécrite en requête autonome (une question de suivi comme « et pour les mineurs ? » récupère son contexte), dans sa langue et en anglais, pour trouver aussi les passages de documents dans une autre langue.
3. **Recherche** : les fragments les plus proches sont récupérés ; ceux dont la similarité cosinus est sous le seuil sont écartés, pour ne pas donner de contexte hors sujet au modèle.
4. **Génération** : le modèle répond uniquement à partir des extraits, cite ses sources `[n]`, et le dit clairement quand l'information n'y figure pas.

Un document de démonstration (`backend/demo_docs/`) est indexé automatiquement au démarrage. Les documents ajoutés par un visiteur sont isolés dans sa session et supprimés après 24 h.

## Lancer en local

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # ou source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis renseignez GEMINI_API_KEY (gratuite)
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
| `GEMINI_API_KEY` | — | Clé Gemini, gratuite (obligatoire) |
| `GEMINI_MODELS` | `gemini-3.5-flash-lite,gemini-3.6-flash,gemini-3.1-flash-lite` | Modèles essayés dans l'ordre (quota épuisé, surcharge ou lenteur) |
| `GEMINI_ANSWER_THINKING` | `LOW` | Niveau de réflexion des réponses |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-2` | Modèle d'embeddings (768 dimensions) |
| `RAG_TOP_K` | `6` | Nombre d'extraits envoyés au modèle |
| `RAG_MIN_RELEVANCE` | `0.6` | Similarité cosinus minimale d'un extrait (calibrée sur gemini-embedding-2) |
| `RAG_DATA_DIR` | `backend/rag_data` | Dossier des index FAISS |
| `VITE_API_BASE_URL` | URL Render en production | URL de l'API pour le frontend |

## Protection des clés et limites d'usage

La clé ne quitte jamais le serveur : le frontend n'appelle que l'API Django. L'offre gratuite de Gemini ne facture jamais ; pour rester sous ses quotas et répartir l'accès entre visiteurs, l'API applique :

| Variable | Défaut | Limite |
|---|---|---|
| `RAG_MAX_QUESTIONS_GLOBAL_PER_DAY` | `300` | Questions par jour pour tout le site |
| `RAG_MAX_QUESTIONS_PER_HOUR` | `20` | Questions par visiteur et par heure |
| `RAG_MAX_QUESTIONS_PER_DAY` | `60` | Questions par visiteur et par jour |
| `RAG_MAX_DOCUMENTS_PER_SESSION` | `5` | Documents par session |

Au-delà, l'API répond `429` avec un message explicite.

## API

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/health/` | État du serveur |
| `GET` / `POST` | `/api/documents/` | Lister / ajouter des documents (en-tête `X-Session-Id`) |
| `DELETE` | `/api/documents/<id>/` | Supprimer un document |
| `POST` | `/api/chat/stream/` | Réponse en streaming (NDJSON : `meta`, `token`, `done`) |
| `POST` | `/api/chat/` | Réponse complète en JSON |

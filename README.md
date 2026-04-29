# Sonar-Echo

Plateforme multi-tenant de **RAG Graph avec dimension temporelle native**.

- **Admin** : crée des bases de connaissance (KB), upload des documents lourds (PDF + scans, type CR de conseil municipal), visualise le graphe entités/relations, gère les utilisateurs et leurs droits par KB, modère les propositions de documents.
- **User** : chatte avec une KB (style ChatGPT, historique, citations datées), propose des documents (workflow d'approbation), donne du feedback, crée des **Gems** (system prompts).
- **Les deux** : créent des automatisations (cron + Gem + canal email). Pilotable via REST API et **MCP**.

## Stack

| Couche    | Tech |
|-----------|------|
| Frontend  | HTML/CSS/JS vanilla (ES modules), Cytoscape.js pour la viz, nginx |
| Backend   | Python 3.12 + FastAPI 0.115 + SQLAlchemy 2 (async) |
| Workers   | Arq (Redis) — ingestion + cron automations |
| User DB   | Postgres 16 (+ extension `vector` pour pgvector) |
| Graphe    | Neo4j 5 (community + plugin GDS pour Leiden) |
| Vecteurs  | Qdrant (1 collection, KB en payload filter) |
| Stockage  | MinIO (S3-compatible) — basculable vers S3 en prod |
| LLM       | OpenAI GPT-4o (extraction / génération) + GPT-4o-mini (routing / intent) |
| OCR       | Mistral OCR (FR scans) + Tesseract en fallback dev |
| MCP       | Serveur JSON-RPC monté sur `/mcp` |

## Architecture & déploiement

**Un seul** `docker-compose.yml` — le comportement bascule via la variable `APP_ENV` :

| Service    | Image            | Port hôte (par défaut) | Note |
|------------|------------------|------------------------|------|
| `frontend` | nginx:alpine     | `3000`                 | sert l'app et proxie `/api/*` et `/mcp` vers le backend |
| `backend`  | build local      | `8000`                 | FastAPI ; entrypoint branche dev (`uvicorn --reload`) vs prod (`--workers N`) |
| `worker`   | même image       | —                      | Arq workers (ingestion + cron) |
| `postgres` | postgres:16      | `5433` → 5432          | métadonnées + pgvector |
| `neo4j`    | neo4j:5 + GDS    | `7474`, `7687`         | graphe temporel |
| `qdrant`   | qdrant/qdrant    | `6333`                 | vecteurs |
| `redis`    | redis:7          | `6379`                 | queue Arq |
| `minio`    | minio/minio      | `9000`, `9001`         | stockage objets (S3-compatible) |
| `mailhog`  | mailhog/mailhog  | `1025`, `8025`         | **profile `dev` uniquement** ; UI sur `:8025` |

L'**entrypoint** `backend/entrypoint.sh` :
- exécute `alembic upgrade head` à chaque démarrage,
- puis lance `uvicorn --reload` si `APP_ENV=dev`, ou `uvicorn --workers $UVICORN_WORKERS` si `APP_ENV=prod`.

Tous les ports hôtes sont surchargeables via `.env` (`BACKEND_PORT`, `FRONTEND_PORT`, etc.).

---

## Setup — DEV (machine locale)

```bash
# 1. Cloner + configurer
git clone <repo> sonar-echo
cd sonar-echo
cp .env.example .env

# 2. Renseigner dans .env :
#    - POSTGRES_PASSWORD, NEO4J_PASSWORD, MINIO_SECRET_KEY  (peu importe en local)
#    - JWT_SECRET_KEY  (mettre une chaîne aléatoire ≥ 32 chars)
#    - OPENAI_API_KEY  (sinon : LLM remplacé par fallback déterministe — chat dégradé)
#    - MISTRAL_API_KEY (sinon : OCR via Tesseract local — qualité inférieure)
#    APP_ENV=dev (déjà la valeur par défaut)

# 3. Démarrer (le profile "dev" inclut MailHog pour tester les emails d'automations)
docker compose --profile dev up -d --build

# 4. Bootstrapper le premier admin
docker compose exec backend python -m app.scripts.seed \
    --email admin@example.com \
    --password change_me_too \
    --org "Demo Org"
```

**Accès** :
- UI :          http://localhost:3000
- API & docs :  http://localhost:8000/docs
- Neo4j browser : http://localhost:7474 (user `neo4j`, mot de passe = `NEO4J_PASSWORD`)
- MailHog UI  : http://localhost:8025 (uniquement profile `dev`)
- MinIO console : http://localhost:9001

**Hot-reload** : la source `backend/app/` est montée dans le conteneur — toute modification déclenche un reload uvicorn (~1 s).
Le frontend est servi tel quel par nginx (montage read-only) — un simple refresh navigateur suffit.

---

## Setup — PROD (un VPS, ou docker host géré)

```bash
# 1. Sur le serveur
git clone <repo> /opt/sonar-echo
cd /opt/sonar-echo
cp .env.example .env
```

Configurer **.env** pour la prod :

```ini
APP_ENV=prod
UVICORN_WORKERS=4

# Tous les secrets DOIVENT être changés
POSTGRES_PASSWORD=<long-aléatoire>
NEO4J_PASSWORD=<long-aléatoire>
MINIO_SECRET_KEY=<long-aléatoire>
JWT_SECRET_KEY=<≥ 64 chars aléatoires>

# Clés payantes
OPENAI_API_KEY=sk-...
MISTRAL_API_KEY=...

# Vrai SMTP (sinon les emails partiront dans le vide — pas de mailhog en prod)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<...>
SMTP_TLS=true
SMTP_FROM=noreply@ton-domaine.fr

# URL publique (utile pour les webhooks et les liens dans les emails)
PUBLIC_BASE_URL=https://sonar.ton-domaine.fr
FRONTEND_ORIGIN=https://sonar.ton-domaine.fr
```

```bash
# 2. Démarrer (PAS de --profile dev — mailhog ne sera pas démarré)
docker compose up -d --build

# 3. Premier admin
docker-compose exec backend python -m app.scripts.seed \
    --email admin@ton-domaine.fr \
    --password "$(openssl rand -base64 24)" \
    --org "Mon Organisation"

# 4. Reverse-proxy externe (recommandé)
#    Mettre Caddy / nginx / Traefik devant pour TLS + domaine + WebSocket(SSE).
#    Cibler http://localhost:3000 (le service frontend gère déjà le proxy /api et /mcp).
```

**Mises à jour** :

```bash
git pull
docker compose up -d --build backend worker  # rebuild & restart sans toucher aux DBs
docker compose exec backend alembic upgrade head  # explicite, mais l'entrypoint le fait aussi
```

**Sauvegardes** : volumes Docker `pgdata`, `neo4jdata`, `qdrantdata`, `miniodata` — backup régulier (pg_dump pour Postgres, snapshots pour Neo4j/Qdrant/MinIO).

---

## Endpoints clés

| Méthode | Path | Rôle min | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | — | login (JWT) |
| POST | `/api/v1/auth/register` | global admin | invite utilisateur |
| GET/POST | `/api/v1/kbs` | reader / — | liste / création KB |
| POST | `/api/v1/kbs/{id}/members` | admin KB | ajout membre par email |
| POST | `/api/v1/kbs/{id}/documents` | proposer | upload (multipart, `?supersedes=` versioning) |
| POST | `/api/v1/kbs/{id}/documents/{did}/approve` | editor | approbation |
| DELETE | `/api/v1/kbs/{id}/documents/{did}?hard=true` | editor / admin | soft / hard delete (cascade 3 stores) |
| POST | `/api/v1/kbs/{id}/search` | reader | **search 4D JSON** sans génération |
| GET | `/api/v1/kbs/{id}/entities/{eid}/timeline` | reader | timeline d'une entité |
| GET | `/api/v1/kbs/{id}/communities` | reader | communautés Leiden |
| POST | `/api/v1/kbs/{id}/communities/rebuild` | admin KB | relance Leiden |
| GET | `/api/v1/kbs/{id}/graph` | reader | nodes + edges pour viz |
| POST | `/api/v1/chat/conversations` | — | crée conversation |
| POST | `/api/v1/chat/conversations/{id}/messages` | — | **SSE stream** réponse |
| POST | `/api/v1/chat/messages/{id}/feedback` | — | feedback −1 / 0 / 1 |
| `*` | `/api/v1/gems` | — | CRUD Gems (system prompts) |
| `*` | `/api/v1/automations` | — | CRUD automations + `/trigger` |
| DELETE | `/api/v1/users/{id}/erase` | global admin | RGPD droit à l'effacement |
| POST | `/mcp` | — | JSON-RPC (initialize, tools/list, tools/call) |

## Modèle temporel (Neo4j)

- `(:Entity)-[:MENTIONED_IN {observation_date, confidence, chunk_id}]->(:Document)` — observation ponctuelle
- `(:Entity)-[:RELATED_TO {type, valid_from, valid_to, tx_from, tx_to, source_doc_id, confidence}]->(:Entity)` — **bitemporal** (monde vs enregistrement)
- `(:Document)-[:SUPERSEDES]->(:Document)` — amendements / corrections
- `(:Entity)-[:HAD_ATTRIBUTE]->(:AttributeVersion)` — historique d'attributs mutables

## Retrieval unifié 4 dimensions

Une requête → 4 vues retournées en parallèle :

1. **Chunks** (Qdrant) avec citations `{doc_id, doc_title, page, source_date, chunk_id, entity_ids}`
2. **Entités** (Neo4j fulltext + promotion par chunks)
3. **Timeline** (events `RELATED_TO` filtrés temporellement)
4. **Communautés** (résumés Leiden, recherche par cosine sur `summary_embedding`)

Disponible via `POST /api/v1/kbs/{id}/search` (JSON pur) et via le chat (SSE qui retourne aussi les 4 sections en plus du texte généré).

## Frontend

App single-page vanilla JS (ES modules, hash routing, store réactif, SSE par fetch). Pages :

- `#/login` — connexion
- `#/chat` — chat ChatGPT-like avec sidebar conversations + streaming SSE + feedback
- `#/kbs` — liste des bases
- `#/kbs/{id}/{tab}` — onglets `documents`, `graph` (Cytoscape), `communities`, `members`
- `#/kbs/{id}/entities/{eid}` — timeline complète d'une entité
- `#/search` — recherche 4D pure JSON
- `#/gems` — CRUD Gems
- `#/automations` — CRUD automations + déclenchement immédiat
- `#/proposals` — modération (admin/editor) des documents proposés
- `#/admin` — invitations + RGPD (admin global uniquement)

## Tests

```bash
docker compose exec backend pip install -e ".[dev]"
docker compose exec backend pytest -q
```

## MCP

Le serveur MCP est monté sur `POST /mcp` (JSON-RPC). Auth = JWT Bearer (même token que l'API). Outils :
`list_kbs`, `search_kb`, `get_entity_timeline`, `list_communities`, `get_community`,
`list_automations`, `trigger_automation`.

Pour le brancher à Claude Desktop ou un autre client MCP : pointer sur `https://<host>/mcp` avec le JWT.

## Roadmap

- Cross-encoder bge-reranker en option (qualité retrieval)
- Resolution queue UI (review humaine de `entity_resolution_candidates`)
- Canaux Slack / webhook (l'interface `NotificationChannel` est déjà en place)
- WebSocket pour notifier la fin d'ingestion en live

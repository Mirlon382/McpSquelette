![McpSquelette](./doc/Logo_McpSquelette_idle.webp)

# McpSquelette 🦴

**"Just the tools."**

An McpSquelette server is a [FastMCP](https://github.com/jlowin/fastmcp) v4 application where the
only thing you write is **your data models and your tool functions**. Everything a server needs to
survive contact with the outside world is already there: configuration, logging, rate limiting, an
error contract, host/origin protection, a container image and Kubernetes manifests.

You do not need to know the Model Context Protocol to use it. If you can write a Python function
that takes arguments and returns a value, you can publish a tool.

> **English** · [En français](#en-français)

---

## What is already done for you

| Concern | Where it lives | What you get |
| --- | --- | --- |
| Configuration | `settings.py`, `.env.example` | Every knob in one typed class, read from the environment or `.env` |
| Logging | `logging.py`, `server.py` | One-line format, level from `LOG_LEVEL`, request/tool logging via middleware |
| Rate limiting | `server.py` | Sliding window per client address, 100 req/min by default |
| Error contract | `errors/` | One exception type whose message actually reaches the caller, with codes |
| Host protection | `server.py` | `Host` / `Origin` checks against `ALLOWED_HOSTS` and `ALLOWED_ORIGINS` |
| Model-facing instructions | `server.py` | Handshake instructions plus your docstrings as tool descriptions |
| Container | `Dockerfile` | Multi-stage, non-root, healthcheck (needs `--format docker` under podman), pinned `uv`, reproducible `--locked` build |
| Kubernetes | `k8s/manifest.yaml` | Service + Deployment + Ingress with the env vars that matter |
| Lifespan | `lifespan.py`, `utils/http.py` | One outbound HTTP client and one state store, opened at startup and closed at shutdown |
| Transports | `server.py`, `MCP_TRANSPORT` | Streamable HTTP for a deployed server, stdio for a client that launches the process |
| Scaffolding | `scripts/new_tool.py` | A new tool written across its four files, registered, with a test |
| Quality gates | `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml` | `ruff` lint + format, `pytest` suite that speaks the real protocol, both gated on every push |
| Agent guide | `skills/mcpsquelette/SKILL.md` | A skill that tells a coding agent how to add a tool correctly |

## Quickstart

Prerequisites: **Python 3.12+** and **[uv](https://docs.astral.sh/uv/)**. uv can install the
Python version for you, so the only thing you really need is uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # once, if `uv` is not installed
```

Get the skeleton and install it:

```bash
git clone https://github.com/Mirlon382/McpSquelette.git my-mcp-server
cd my-mcp-server
uv sync
```

Start it:

```bash
uv run mcpserver
```

```
INFO | uvicorn.error | Uvicorn running on http://0.0.0.0:8000
```

The server answers on **http://localhost:8000/mcp** (Streamable HTTP transport). To have a client
launch it instead of calling a URL, run it over stdio: `MCP_TRANSPORT=stdio uv run mcpserver`.

### "It's alive 🧟"

```bash
npx @modelcontextprotocol/inspector
```

Open the inspector, choose **Streamable HTTP**, enter `http://localhost:8000/mcp`, connect, and you
will see `wikipedia_summary`, `notes_add` and `notes_list` with their input schemas. Call
`wikipedia_summary` with `Ada Lovelace` and it answers with the article's summary.

## Your first tool

The skeleton ships two worked examples, because they are the two shapes almost every server needs:
`wikipedia_summary` reads an external API through the shared client, and `notes_add` / `notes_list`
write to and read from state that lives in the lifespan. Read them, then delete them.

Add your own by scaffolding it. From the repository root:

```bash
uv run python scripts/new_tool.py weather_now --summary "Return the current weather for one city."
```

That writes every file a tool touches, already wired: the models, the tool function, a protocol test
that stays skipped until you finish it, and the import plus registration in
`src/mcpserver/tools/__init__.py`. The generated tool raises a visible "not implemented"
`AppToolError` until you replace the body, and `ruff` and `pytest` stay green meanwhile.

By hand, it is three files:

**1. The models** — `src/mcpserver/models/<yourservice>.py`

```python
ArticleTitle = Annotated[
    str,
    Field(
        description="Exact English Wikipedia article title, not a search phrase.",
        examples=["Ada Lovelace"],
    ),
]


class ArticleSummary(BaseModel):
    """What `wikipedia_summary` returns."""

    title: str = Field(description="The article title as Wikipedia resolved it.")
    extract: str = Field(description="Plain-text summary of the article.")
```

**2. The tool** — `src/mcpserver/tools/<yourservice>/tools.py`

```python
async def wikipedia_summary(title: ArticleTitle, http: Http = Depends(get_http)) -> ArticleSummary:
    """Read the plain-text summary of one English Wikipedia article."""
    ...
```

**3. The registration** — `src/mcpserver/tools/__init__.py`

```python
mcp.tool(wikipedia_summary, annotations=READ_ONLY)
```

Three rules make the difference between a tool an LLM uses well and one it ignores:

- **The docstring is the tool description.** It is what the model reads to decide whether to call
  you. Say what the tool does, when to use it, and what it returns.
- **Every `Field(description=...)` is part of the schema.** Write them for a reader who has never
  seen your code.
- **Anything the tool needs arrives through `Depends`, never a module global.** The HTTP client and
  the state store are opened once by the lifespan. `utils/http.py` explains why the obvious version
  is wrong: a dependency that returns a bare `httpx.AsyncClient` makes FastMCP open it per call and
  fail on the second one.

## How the request flows

```
client → Host/Origin check → ErrorHandling → RateLimit → Timing → Logging → your tool
```

Middleware order matters and is deliberate (`server.py`):

- **ErrorHandling** first, so it sees the whole chain. `mask_error_details=True` means an
  `AppToolError` message reaches the caller verbatim, while any other exception — a bug — is
  replaced by a generic message and logged in full server-side.
- **RateLimit** next, keyed on the caller's address (`utils/client_host.py`), honouring
  `X-Forwarded-For` only from `TRUSTED_PROXY_HOSTS`.
- **Timing** and **Logging** last, so they record what actually ran.

## Errors your users will read

```python
from ...errors import AppToolError, ErrorCode

raise AppToolError(
    ErrorCode.NOT_FOUND,
    "No English Wikipedia article is titled `title='Klipper docs'`. Check the spelling and use "
    "the article name itself, not a question.",
)
```

The message reaches the caller prefixed with its code, `[INVALID_INPUT] …`; with
`retryable=True` it becomes `[BACKEND_UNAVAILABLE, retryable] …` so a client knows a retry is safe.
Every message must say **what failed, why, and what to do next** — it is the only thing the caller
gets.

| Code | Meaning |
| --- | --- |
| `INVALID_INPUT` | The arguments are wrong or impossible |
| `INVALID_QUERY` | The query is well-formed but not allowed |
| `NOT_FOUND` | The thing asked for does not exist |
| `PARSE_ERROR` | An upstream answer could not be read |
| `BACKEND_UNAVAILABLE` | A dependency is down (usually retryable) |
| `UPSTREAM_ERROR` | A dependency answered with an error |
| `INTERNAL_ERROR` | Our fault, not the caller's — logged in full, reported generically |

## Connecting a client

Two transports, one set of tools.

**stdio** — the client launches the process and talks over pipes. This is what Claude Desktop,
Claude Code, Cursor and most editors do:

```json
{
  "mcpServers": {
    "mcpsquelette": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/my-mcp-server", "mcpserver"],
      "env": { "MCP_TRANSPORT": "stdio" }
    }
  }
}
```

**HTTP** — a long-running server answering `POST /mcp` on port `8000`. Clients that speak Streamable
HTTP take a URL:

```json
{
  "mcpServers": {
    "mcpsquelette": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

`MCP_TRANSPORT` picks one; the default is `http` so the quickstart works without a client. Check the
shape your client expects: the stdio `command`/`args` form and the remote `url` form are not
interchangeable, and some hosts need a bridge for remote servers.

## Configuration

Everything is read from the environment, or from `.env` in the working directory. Copy the example
first: `cp .env.example .env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MCP_NAME` | `McpSquelette` | Server name sent in the handshake, shown by most clients |
| `MCP_TRANSPORT` | `http` | `http` serves Streamable HTTP; `stdio` talks over pipes for a client that launches the process |
| `MCP_HOST` | `0.0.0.0` | Interface to bind (`0.0.0.0` is what a container needs) |
| `MCP_PORT` | `8000` | Port to listen on |
| `ALLOWED_HOSTS` | `["*"]` | Hostnames accepted in the `Host` header. `["*"]` disables the check |
| `ALLOWED_ORIGINS` | `[]` | Browser origins allowed to call `POST /mcp`. Empty rejects all cross-origin browsers |
| `TRUSTED_PROXY_HOSTS` | `["127.0.0.1"]` | Peers whose `X-Forwarded-For` is believed. Widen to your reverse proxy only |
| `HTTP_TIMEOUT_SECONDS` | `10` | Timeout of the single outbound client the lifespan opens |
| `HTTP_USER_AGENT` | `McpSquelette/0.1 (…)` | User-Agent that client sends; many public APIs reject the Python default |
| `RATE_LIMIT_MAX_REQUESTS` | `100` | Requests allowed per window, per client address |
| `RATE_LIMIT_WINDOW_MINUTES` | `1` | Window length in minutes |
| `LOG_LEVEL` | `INFO` | Root level; FastMCP's middlewares log under `fastmcp.*` |

**Lists are JSON strings**, not comma-separated: `ALLOWED_HOSTS='["mcp.example.com"]'`. That is also
the exact form the Kubernetes manifest uses.

## Deploy

**Container — podman (rootless, recommended)**

```bash
podman build --format docker -t my-mcp-server .
podman run --rm -p 8000:8000 -e ALLOWED_HOSTS='["localhost"]' my-mcp-server
```

`--format docker` matters: podman's default OCI format **drops `HEALTHCHECK`** and warns, so the
container would run with no health status at all. With the docker format the probe survives:
`podman inspect --format '{{.State.Health.Status}}' <container>` answers `starting`, then `healthy`
about twenty seconds in.

**Container — docker**

```bash
docker build -t my-mcp-server .
docker run --rm -p 8000:8000 -e ALLOWED_HOSTS='["localhost"]' my-mcp-server
```

The image builds with `uv sync --locked`, so `uv.lock` must be current (`uv lock` after changing
dependencies). It runs as a non-root user, and its healthcheck opens a TCP connection rather than
making an HTTP request — the MCP endpoint answers `400` without a session handshake, so an HTTP
probe would fail on a healthy server.

**Kubernetes**

`k8s/manifest.yaml` contains the Service, the Deployment and the Ingress. Edit the namespace, the
image and the hostname, then:

```bash
kubectl apply -f k8s/manifest.yaml
```

Two values are not optional once you are behind an Ingress:

- `ALLOWED_HOSTS` must contain the hostname the Ingress routes, or host protection returns `421` to
  every request.
- `TRUSTED_PROXY_HOSTS` must include the Ingress controller (the manifest uses `["*"]`, safe only
  because the pod is reachable exclusively through the Ingress). Without it, uvicorn sees every
  request coming from the Ingress and rate-limits all your users as one caller.

The image built above is local to your machine: a cluster cannot pull it. Push it to a registry
(`podman push my-mcp-server docker://registry.example.com/my-mcp-server:latest`) and point the
manifest at that reference, or load it into the node directly.

## Project layout

```
.
├── .env.example                  # every variable, documented — copy to .env
├── .github/workflows/ci.yml      # ruff + pytest on 3.12 and 3.13, plus a container healthcheck
├── Dockerfile                    # multi-stage, non-root, healthcheck
├── k8s/manifest.yaml             # Service + Deployment + Ingress
├── pyproject.toml                # deps, console script, ruff + pytest config
├── scripts/
│   ├── new_tool.py               # scaffold a tool across the four files it touches
│   └── rename.py                 # rename the package, the script, the CMD and the tests
├── skills/mcpsquelette/SKILL.md  # the agent skill (`.claude/skills/` links to it)
├── src/mcpserver/
│   ├── server.py                 # entrypoint: settings, lifespan, middlewares, transports
│   ├── lifespan.py               # the HTTP client and the note store, opened once
│   ├── settings.py               # every configurable value
│   ├── logging.py                # log format and level
│   ├── notes_store.py            # the write example's state
│   ├── errors/                   # AppToolError + ErrorCode
│   ├── models/                   # your Pydantic schemas, one file per service
│   ├── tools/
│   │   ├── __init__.py           # the single registration point
│   │   ├── wikipedia/            # read example: API call, Depends, error mapping
│   │   └── notes/                # write example: state, WRITE annotations
│   └── utils/
│       ├── client_host.py        # rate-limit key resolution
│       └── http.py               # the shared client, as a tool dependency
└── tests/                        # run the real app over the real protocol
```

To rename the project, let the script do it — it knows the five places the name lives (package
directory, `pyproject.toml` `name`, the console script, the `Dockerfile` CMD, the test imports):

```bash
uv run python scripts/rename.py --package acmeserver --name "Acme Server"
uv lock && uv sync && uv run pytest -q
```

## Development

```bash
uv run pytest -q                  # protocol-level, no network
uv run ruff check . && uv run ruff format --check .
uv run pre-commit install         # lint and format on every commit
uv run python scripts/new_tool.py my_tool   # scaffold, register and test in one go
```

The tests speak to the app through `fastmcp.Client(mcp)`, so they prove the tool is *registered*
and its schema is right — not merely that the function works when called directly. For a tool that
calls an API, `tests/conftest.py` gives you the seam: `build_test_server(httpx.MockTransport(handler))`
returns the same application with the network replaced, so every branch of your error mapping is
testable offline. Add a test for each tool you publish; the scaffolder starts it for you.

## For AI agents

`skills/mcpsquelette/SKILL.md` is a [Skill](https://docs.claude.com/en/docs/claude-code/skills)
written for coding agents, and `.claude/skills/mcpsquelette` is a symlink to it so Claude Code finds
it without being told. It states where a tool goes, which conventions this skeleton enforces (raise
`AppToolError`, return a model, register in one place), the two traps of `Depends`, and how to
verify the result. Any agent that reads `SKILL.md` — Claude Code, Hermes, Codex — can add a tool to a
copy of this repo without inventing the structure.

## Limits and security

- **No authentication.** McpSquelette serves whoever can reach the port. Put it behind a gateway,
  a VPN or your platform's auth proxy before exposing it.
- **`ALLOWED_HOSTS` defaults to `["*"]`** and logs a warning. Set the real hostname.
- **Rate limiting is in memory, per process.** Two replicas allow twice the requests, and a restart
  resets the counters. Use the platform's rate limiter for a hard guarantee.
- **The example note store is in memory too.** It is a demonstration of where state belongs (the
  lifespan), not storage: it is lost on restart and shared by every caller.
- **`stdio` has no network surface at all.** Host and origin protection only apply to the HTTP
  transport.
- **`mask_error_details=True` is the point**: only `AppToolError` text is public. Never put a token,
  an internal URL or a stack trace in a tool's error message.
- **One process, one tool set.** Tools are registered at startup; there is no hot reload of the
  schema in production.

---

# En français

**« Juste les outils. »**

Un serveur McpSquelette est une application [FastMCP](https://github.com/jlowin/fastmcp) v4 où la
seule chose que vous écrivez est **vos modèles de données et vos fonctions d'outils**. Tout ce dont
un serveur a besoin pour affronter l'extérieur est déjà en place : configuration, journalisation,
limitation de débit, contrat d'erreur, protection `Host`/`Origin`, image conteneur et manifestes
Kubernetes.

Vous n'avez pas besoin de connaître le Model Context Protocol. Si vous savez écrire une fonction
Python qui prend des arguments et renvoie une valeur, vous savez publier un outil.

## Ce qui est déjà fait pour vous

| Sujet | Fichier | Ce que vous obtenez |
| --- | --- | --- |
| Configuration | `settings.py`, `.env.example` | Toutes les valeurs dans une classe typée, lues depuis l'environnement ou `.env` |
| Journalisation | `logging.py`, `server.py` | Format sur une ligne, niveau via `LOG_LEVEL`, traces des requêtes par middleware |
| Limitation de débit | `server.py` | Fenêtre glissante par adresse client, 100 req/min par défaut |
| Contrat d'erreur | `errors/` | Une seule exception dont le message atteint réellement l'appelant, avec un code |
| Protection d'hôte | `server.py` | Contrôle `Host` / `Origin` via `ALLOWED_HOSTS` et `ALLOWED_ORIGINS` |
| Instructions au modèle | `server.py` | Instructions de handshake + vos docstrings comme descriptions d'outils |
| Conteneur | `Dockerfile` | Multi-étapes, non-root, healthcheck (exige `--format docker` avec podman), `uv` épinglé, build `--locked` reproductible |
| Kubernetes | `k8s/manifest.yaml` | Service + Deployment + Ingress avec les variables qui comptent |
| Cycle de vie | `lifespan.py`, `utils/http.py` | Un client HTTP sortant et un magasin d'état, ouverts au démarrage et fermés à l'arrêt |
| Transports | `server.py`, `MCP_TRANSPORT` | Streamable HTTP pour un serveur déployé, stdio pour un client qui lance le processus |
| Échafaudage | `scripts/new_tool.py` | Un nouvel outil écrit dans ses quatre fichiers, enregistré, avec son test |
| Qualité | `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml` | `ruff` (lint + format), suite `pytest` au niveau du protocole, vérifiés à chaque push |
| Guide pour agents | `skills/mcpsquelette/SKILL.md` | Un Skill qui explique à un agent comment ajouter un outil correctement |

## Démarrage rapide

Prérequis : **Python 3.12+** et **[uv](https://docs.astral.sh/uv/)** — uv sait installer la bonne
version de Python, donc uv suffit :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # une fois, si `uv` n'est pas installé
```

Récupérer le squelette et l'installer :

```bash
git clone https://github.com/Mirlon382/McpSquelette.git mon-serveur-mcp
cd mon-serveur-mcp
uv sync
```

Le lancer :

```bash
uv run mcpserver
```

Le serveur répond sur **http://localhost:8000/mcp** (transport Streamable HTTP). Pour qu'un client
le lance lui-même au lieu d'appeler une URL, passez-le en stdio : `MCP_TRANSPORT=stdio uv run mcpserver`.

### « It's alive 🧟 »

```bash
npx @modelcontextprotocol/inspector
```

Dans l'inspecteur : transport **Streamable HTTP**, URL `http://localhost:8000/mcp`, puis connect.
Les outils `wikipedia_summary`, `notes_add` et `notes_list` apparaissent avec leurs schémas d'entrée.
Appelez `wikipedia_summary` avec `Ada Lovelace` : il répond par le résumé de l'article.

## Votre premier outil

Le squelette livre deux exemples complets, parce que ce sont les deux formes dont presque tout
serveur a besoin : `wikipedia_summary` lit une API à travers le client partagé, et `notes_add` /
`notes_list` écrivent et relisent un état qui vit dans le lifespan. Lisez-les, puis supprimez-les.

Ajoutez le vôtre en l'échafaudant, depuis la racine du dépôt :

```bash
uv run python scripts/new_tool.py weather_now --summary "Return the current weather for one city."
```

Le script écrit tous les fichiers qu'un outil touche, déjà câblés : les modèles, la fonction, un test
au niveau du protocole qui reste en `skip` jusqu'à ce que vous le terminiez, et l'import plus
l'enregistrement dans `src/mcpserver/tools/__init__.py`. L'outil généré lève un `AppToolError`
« not implemented » bien visible tant que le corps n'est pas écrit, et `ruff` comme `pytest`
restent verts entre-temps.

À la main, c'est trois fichiers :

**1. Les modèles** — `src/mcpserver/models/<votre_service>.py`

```python
ArticleTitle = Annotated[
    str,
    Field(description="Titre exact d'un article Wikipédia en anglais, pas une recherche.", examples=["Ada Lovelace"]),
]


class ArticleSummary(BaseModel):
    """Ce que renvoie `wikipedia_summary`."""

    title: str = Field(description="Le titre tel que Wikipédia l'a résolu.")
    extract: str = Field(description="Résumé en texte brut de l'article.")
```

**2. L'outil** — `src/mcpserver/tools/<votre_service>/tools.py`

```python
async def wikipedia_summary(title: ArticleTitle, http: Http = Depends(get_http)) -> ArticleSummary:
    """Lire le résumé en texte brut d'un article Wikipédia en anglais."""
    ...
```

**3. L'enregistrement** — `src/mcpserver/tools/__init__.py`

```python
mcp.tool(wikipedia_summary, annotations=READ_ONLY)
```

Trois règles séparent un outil qu'un LLM utilise bien d'un outil qu'il ignore :

- **La docstring est la description de l'outil.** C'est ce que lit le modèle pour décider de vous
  appeler. Dites ce que fait l'outil, quand l'utiliser, ce qu'il renvoie.
- **Chaque `Field(description=...)` fait partie du schéma.** Écrivez-les pour quelqu'un qui n'a
  jamais vu votre code.
- **Tout ce dont l'outil a besoin arrive par `Depends`, jamais par une variable globale.** Le client
  HTTP et le magasin d'état sont ouverts une fois par le lifespan. `utils/http.py` explique pourquoi
  la version évidente est fausse : une dépendance qui renvoie un `httpx.AsyncClient` nu fait ouvrir
  le client à chaque appel par FastMCP, et le deuxième appel échoue.

## Le trajet d'une requête

```
client → contrôle Host/Origin → ErrorHandling → RateLimit → Timing → Logging → votre outil
```

L'ordre est délibéré (`server.py`) : **ErrorHandling** d'abord, pour voir toute la chaîne ;
**RateLimit** ensuite, indexé sur l'adresse de l'appelant (`utils/client_host.py`), en ne croyant
`X-Forwarded-For` que pour `TRUSTED_PROXY_HOSTS` ; **Timing** et **Logging** en dernier, pour
enregistrer ce qui a réellement tourné.

## Les erreurs que vos utilisateurs liront

```python
from ...errors import AppToolError, ErrorCode

raise AppToolError(
    ErrorCode.NOT_FOUND,
    "Aucun article Wikipédia en anglais ne s'appelle `title='doc Klipper'`. Vérifiez l'orthographe "
    "et passez le nom de l'article, pas une question.",
)
```

Le message arrive préfixé par son code : `[INVALID_INPUT] …` ; avec `retryable=True`, il devient
`[BACKEND_UNAVAILABLE, retryable] …` et le client sait qu'une nouvelle tentative est sans risque.
Chaque message doit dire **ce qui a échoué, pourquoi, et quoi faire** : c'est tout ce que reçoit
l'appelant.

| Code | Signification |
| --- | --- |
| `INVALID_INPUT` | Les arguments sont faux ou impossibles |
| `INVALID_QUERY` | La requête est bien formée mais interdite |
| `NOT_FOUND` | Ce qui est demandé n'existe pas |
| `PARSE_ERROR` | Une réponse amont est illisible |
| `BACKEND_UNAVAILABLE` | Une dépendance est indisponible (souvent réessayable) |
| `UPSTREAM_ERROR` | Une dépendance a répondu par une erreur |
| `INTERNAL_ERROR` | Notre faute, pas celle de l'appelant — tracée en entier, signalée génériquement |

## Connecter un client

Deux transports, un seul jeu d'outils.

**stdio** — le client lance le processus et parle par les pipes. C'est ce que font Claude Desktop,
Claude Code, Cursor et la plupart des éditeurs :

```json
{
  "mcpServers": {
    "mcpsquelette": {
      "command": "uv",
      "args": ["run", "--directory", "/chemin/absolu/vers/mon-serveur-mcp", "mcpserver"],
      "env": { "MCP_TRANSPORT": "stdio" }
    }
  }
}
```

**HTTP** — un serveur qui tourne et répond sur `POST /mcp`, port `8000`. Les clients Streamable HTTP
prennent une URL :

```json
{
  "mcpServers": {
    "mcpsquelette": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

`MCP_TRANSPORT` choisit ; le défaut est `http` pour que le démarrage rapide fonctionne sans client.
Vérifiez la forme attendue par votre client : la forme stdio `command`/`args` et la forme distante
`url` ne sont pas interchangeables, et certains hôtes exigent un pont pour les serveurs distants.

## Configuration

Tout est lu depuis l'environnement, ou depuis `.env` dans le répertoire de travail. Commencez par
`cp .env.example .env`.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `MCP_NAME` | `McpSquelette` | Nom du serveur envoyé au handshake |
| `MCP_TRANSPORT` | `http` | `http` sert en Streamable HTTP ; `stdio` parle par les pipes, pour un client qui lance le processus |
| `MCP_HOST` | `0.0.0.0` | Interface d'écoute (`0.0.0.0` est nécessaire en conteneur) |
| `MCP_PORT` | `8000` | Port d'écoute |
| `ALLOWED_HOSTS` | `["*"]` | Noms d'hôte acceptés dans l'en-tête `Host`. `["*"]` désactive le contrôle |
| `ALLOWED_ORIGINS` | `[]` | Origines navigateur autorisées sur `POST /mcp`. Vide refuse tout navigateur cross-origin |
| `TRUSTED_PROXY_HOSTS` | `["127.0.0.1"]` | Pairs dont `X-Forwarded-For` est cru. À élargir à votre reverse proxy uniquement |
| `HTTP_TIMEOUT_SECONDS` | `10` | Délai du client sortant unique ouvert par le lifespan |
| `HTTP_USER_AGENT` | `McpSquelette/0.1 (…)` | User-Agent envoyé par ce client ; beaucoup d'API publiques refusent celui de Python |
| `RATE_LIMIT_MAX_REQUESTS` | `100` | Requêtes autorisées par fenêtre, par adresse client |
| `RATE_LIMIT_WINDOW_MINUTES` | `1` | Durée de la fenêtre, en minutes |
| `LOG_LEVEL` | `INFO` | Niveau racine ; les middlewares FastMCP journalisent sous `fastmcp.*` |

**Les listes sont du JSON**, pas des virgules : `ALLOWED_HOSTS='["mcp.example.com"]'`. C'est aussi la
forme exacte utilisée par le manifeste Kubernetes.

## Déployer

**Conteneur — podman (rootless, recommandé)**

```bash
podman build --format docker -t mon-serveur-mcp .
podman run --rm -p 8000:8000 -e ALLOWED_HOSTS='["localhost"]' mon-serveur-mcp
```

`--format docker` n'est pas décoratif : le format OCI, celui de podman par défaut, **supprime
`HEALTHCHECK`** (avec un avertissement) et le conteneur tourne alors sans état de santé. Avec le
format docker la sonde est conservée : `podman inspect --format '{{.State.Health.Status}}'
<conteneur>` répond `starting`, puis `healthy` au bout d'une vingtaine de secondes.

**Conteneur — docker**

```bash
docker build -t mon-serveur-mcp .
docker run --rm -p 8000:8000 -e ALLOWED_HOSTS='["localhost"]' mon-serveur-mcp
```

L'image se construit avec `uv sync --locked` : `uv.lock` doit être à jour (`uv lock` après tout
changement de dépendance). Elle tourne en utilisateur non-root, et son healthcheck ouvre une
connexion TCP plutôt que de faire une requête HTTP — le point d'entrée MCP répond `400` sans
handshake de session, donc une sonde HTTP échouerait sur un serveur en bonne santé.

**Kubernetes**

`k8s/manifest.yaml` contient le Service, le Deployment et l'Ingress. Modifiez le namespace, l'image
et le nom d'hôte, puis :

```bash
kubectl apply -f k8s/manifest.yaml
```

Deux valeurs ne sont pas optionnelles derrière un Ingress :

- `ALLOWED_HOSTS` doit contenir le nom d'hôte routé, sinon la protection d'hôte renvoie `421` à
  toutes les requêtes.
- `TRUSTED_PROXY_HOSTS` doit inclure le contrôleur d'Ingress (le manifeste met `["*"]`, acceptable
  seulement parce que le pod n'est joignable que par l'Ingress). Sans cela, uvicorn voit toutes les
  requêtes venir de l'Ingress et limite tous vos utilisateurs comme un seul appelant.

L'image construite plus haut est locale : un cluster ne peut pas la récupérer. Poussez-la vers un
registre (`podman push mon-serveur-mcp docker://registry.example.com/mon-serveur-mcp:latest`) et
pointez le manifeste vers cette référence, ou chargez-la directement sur le nœud.

## Arborescence

```
.
├── .env.example                  # toutes les variables, documentées — à copier en .env
├── .github/workflows/ci.yml      # ruff + pytest sur 3.12 et 3.13, plus le healthcheck du conteneur
├── Dockerfile                    # multi-étapes, non-root, healthcheck
├── k8s/manifest.yaml             # Service + Deployment + Ingress
├── pyproject.toml                # dépendances, script console, config ruff + pytest
├── scripts/
│   ├── new_tool.py               # échafaude un outil dans ses quatre fichiers
│   └── rename.py                 # renomme le paquet, le script, le CMD et les tests
├── skills/mcpsquelette/SKILL.md  # le Skill pour agents (`.claude/skills/` pointe dessus)
├── src/mcpserver/
│   ├── server.py                 # point d'entrée : settings, lifespan, middlewares, transports
│   ├── lifespan.py               # le client HTTP et le magasin de notes, ouverts une fois
│   ├── settings.py               # chaque valeur configurable
│   ├── logging.py                # format et niveau de journalisation
│   ├── notes_store.py            # l'état de l'exemple d'écriture
│   ├── errors/                   # AppToolError + ErrorCode
│   ├── models/                   # vos schémas Pydantic, un fichier par service
│   ├── tools/
│   │   ├── __init__.py           # l'unique point d'enregistrement
│   │   ├── wikipedia/            # exemple en lecture : appel API, Depends, contrat d'erreur
│   │   └── notes/                # exemple en écriture : état, annotations WRITE
│   └── utils/
│       ├── client_host.py        # clé de limitation de débit
│       └── http.py               # le client partagé, en dépendance
└── tests/                        # exécutent la vraie app sur le vrai protocole
```

Pour renommer le projet, laissez le script le faire — il connaît les cinq endroits où le nom vit
(répertoire du paquet, `name` de `pyproject.toml`, script console, CMD du `Dockerfile`, imports des
tests) :

```bash
uv run python scripts/rename.py --package acmeserver --name "Acme Server"
uv lock && uv sync && uv run pytest -q
```

## Développement

```bash
uv run pytest -q                  # au niveau du protocole, sans réseau
uv run ruff check . && uv run ruff format --check .
uv run pre-commit install         # lint et format à chaque commit
uv run python scripts/new_tool.py mon_outil   # échafaude, enregistre et teste d'un coup
```

Les tests parlent à l'application via `fastmcp.Client(mcp)` : ils prouvent que l'outil est
*enregistré* et que son schéma est correct, pas seulement que la fonction marche appelée
directement. Pour un outil qui appelle une API, `tests/conftest.py` fournit la couture :
`build_test_server(httpx.MockTransport(handler))` renvoie la même application avec le réseau
remplacé, donc chaque branche de votre contrat d'erreur se teste hors ligne. Ajoutez un test pour
chaque outil publié ; l'échafaudage le commence.

## Pour les agents IA

`skills/mcpsquelette/SKILL.md` est un [Skill](https://docs.claude.com/en/docs/claude-code/skills)
destiné aux agents de code, et `.claude/skills/mcpsquelette` y pointe pour que Claude Code le trouve
sans qu'on le lui indique. Il précise où va un outil, les conventions que ce squelette impose (lever
`AppToolError`, renvoyer un modèle, enregistrer à un seul endroit), les deux pièges de `Depends`, et
comment vérifier le résultat. Tout agent qui lit `SKILL.md` — Claude Code, Hermes, Codex — peut
ajouter un outil à une copie de ce dépôt sans inventer la structure.

## Limites et sécurité

- **Aucune authentification.** McpSquelette sert quiconque atteint le port. Placez-le derrière une
  passerelle, un VPN ou le proxy d'authentification de votre plateforme avant de l'exposer.
- **`ALLOWED_HOSTS` vaut `["*"]` par défaut** et journalise un avertissement. Mettez le vrai nom
  d'hôte.
- **La limitation de débit est en mémoire, par processus.** Deux réplicas autorisent deux fois plus
  de requêtes, et un redémarrage remet les compteurs à zéro. Pour une garantie ferme, utilisez le
  limiteur de votre plateforme.
- **Le magasin de notes d'exemple est en mémoire lui aussi.** C'est une démonstration de l'endroit
  où va l'état (le lifespan), pas du stockage : perdu au redémarrage, partagé par tous les appelants.
- **`stdio` n'expose aucune surface réseau.** La protection `Host`/`Origin` ne concerne que le
  transport HTTP.
- **`mask_error_details=True` est voulu** : seul le texte des `AppToolError` est public. Ne mettez
  jamais de jeton, d'URL interne ou de trace dans le message d'erreur d'un outil.
- **Un processus, un jeu d'outils.** Les outils sont enregistrés au démarrage ; pas de rechargement
  à chaud du schéma en production.

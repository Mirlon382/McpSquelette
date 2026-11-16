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
| Quality gates | `pyproject.toml`, `.pre-commit-config.yaml` | `ruff` lint + format, `pytest` suite that speaks the real protocol |
| Agent guide | `skill.md` | A skill that tells a coding agent how to add a tool correctly |

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

The server answers on **http://localhost:8000/mcp** (Streamable HTTP transport).

### "It's alive 🧟"

```bash
npx @modelcontextprotocol/inspector
```

Open the inspector, choose **Streamable HTTP**, enter `http://localhost:8000/mcp`, connect, and you
will see `tool1` with its input schema. Call it with `world` and it answers
`Votre choix : world`.

## Your first tool, in three files

The example tool that ships in the skeleton is the whole pattern. Copy it, rename it, keep the shape.

**1. The models** — `src/mcpserver/models/myserver.py`

```python
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class Tool1Choice(StrEnum):
    """The closed set of values `tool1` accepts, so a bad value fails here rather than downstream."""

    HELLO = "hello"
    WORLD = "world"
    EXCLAM = "!"


Tool1Input = Annotated[
    Tool1Choice,
    Field(description="Which word to echo back: 'hello', 'world' or '!'.", examples=["hello"]),
]


class OutputPhrase(BaseModel):
    """What `tool1` returns."""

    returned_phrase: str = Field(description="The sentence built from the chosen word.")
```

**2. The tool** — `src/mcpserver/tools/myservice/tools.py`

```python
from ...models.myserver import OutputPhrase, Tool1Input


async def tool1(word: Tool1Input) -> OutputPhrase:
    """Echo the chosen word back in a sentence."""
    return OutputPhrase(returned_phrase=f"Votre choix : {word}")
```

**3. The registration** — `src/mcpserver/tools/__init__.py`

```python
from .myservice.tools import tool1

mcp.tool(tool1, annotations=READ_ONLY)
```

That is all. Restart the server, `tool1` is listed, callable, validated against
`Tool1Input`, and its answer validated against `OutputPhrase`.

Two rules make the difference between a tool an LLM uses well and one it ignores:

- **The docstring is the tool description.** It is what the model reads to decide whether to call
  you. Say what the tool does, when to use it, and what it returns.
- **Every `Field(description=...)` is part of the schema.** Write them for a reader who has never
  seen your code.

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
    ErrorCode.INVALID_INPUT,
    "`word` must be one of hello, world or !. Call `tool1` with 'hello' to test it.",
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

The endpoint is `POST /mcp` on port `8000`; the transport is Streamable HTTP. Any MCP client that
supports HTTP works. A `mcpServers` entry (Claude Desktop, Cursor, and most others):

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

Clients that only speak **stdio** cannot reach this server directly: point them at an HTTP-capable
client, or run the server behind a gateway that speaks both.

## Configuration

Everything is read from the environment, or from `.env` in the working directory. Copy the example
first: `cp .env.example .env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MCP_NAME` | `McpSquelette` | Server name sent in the handshake, shown by most clients |
| `MCP_HOST` | `0.0.0.0` | Interface to bind (`0.0.0.0` is what a container needs) |
| `MCP_PORT` | `8000` | Port to listen on |
| `ALLOWED_HOSTS` | `["*"]` | Hostnames accepted in the `Host` header. `["*"]` disables the check |
| `ALLOWED_ORIGINS` | `[]` | Browser origins allowed to call `POST /mcp`. Empty rejects all cross-origin browsers |
| `TRUSTED_PROXY_HOSTS` | `["127.0.0.1"]` | Peers whose `X-Forwarded-For` is believed. Widen to your reverse proxy only |
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
├── .env.example              # every variable, documented — copy to .env
├── Dockerfile                # multi-stage, non-root, healthcheck
├── k8s/manifest.yaml         # Service + Deployment + Ingress
├── pyproject.toml            # deps, console script, ruff + pytest config
├── skill.md                  # a Skill for coding agents working in this repo
├── src/mcpserver/
│   ├── server.py             # entrypoint: settings, middlewares, HTTP app
│   ├── settings.py           # every configurable value
│   ├── logging.py            # log format and level
│   ├── errors/               # AppToolError + ErrorCode
│   ├── models/myserver.py    # your Pydantic schemas
│   ├── tools/
│   │   ├── __init__.py       # the single registration point
│   │   └── myservice/        # one package per group of tools
│   └── utils/client_host.py  # rate-limit key resolution
└── tests/                    # runs the real app over the real protocol
```

To rename the project, change `name` in `pyproject.toml`, the `[project.scripts]` entry, and the
`src/mcpserver/` directory — then `uv sync` again. Nothing else depends on the name.

## Development

```bash
uv run pytest -q                  # 11 tests, protocol-level
uv run ruff check . && uv run ruff format --check .
uv run pre-commit install         # lint and format on every commit
```

The tests speak to the app through `fastmcp.Client(mcp)`, so they prove the tool is *registered*
and its schema is right — not merely that the function works when called directly. Add a test in
`tests/test_server.py` for each tool you publish.

## For AI agents

`skill.md` is a [Skill](https://docs.claude.com/en/docs/claude-code/skills) written for coding
agents: it states where a tool goes, which conventions this skeleton enforces (raise
`AppToolError`, return a model, register in one place), and how to verify the result. Drop the
repository in front of an agent that reads skills and it will not need to invent the structure.

## Limits and security

- **No authentication.** McpSquelette serves whoever can reach the port. Put it behind a gateway,
  a VPN or your platform's auth proxy before exposing it.
- **`ALLOWED_HOSTS` defaults to `["*"]`** and logs a warning. Set the real hostname.
- **Rate limiting is in memory, per process.** Two replicas allow twice the requests, and a restart
  resets the counters. Use the platform's rate limiter for a hard guarantee.
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
| Qualité | `pyproject.toml`, `.pre-commit-config.yaml` | `ruff` (lint + format), suite `pytest` qui parle le vrai protocole |
| Guide pour agents | `skill.md` | Un Skill qui explique à un agent comment ajouter un outil correctement |

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

Le serveur répond sur **http://localhost:8000/mcp** (transport Streamable HTTP).

### « It's alive 🧟 »

```bash
npx @modelcontextprotocol/inspector
```

Dans l'inspecteur : transport **Streamable HTTP**, URL `http://localhost:8000/mcp`, puis connect.
L'outil `tool1` apparaît avec son schéma d'entrée. Appelez-le avec `world`, il répond
`Votre choix : world`.

## Votre premier outil, en trois fichiers

L'outil d'exemple livré avec le squelette contient tout le patron. Copiez-le, renommez-le, gardez la
forme.

**1. Les modèles** — `src/mcpserver/models/myserver.py`

```python
class Tool1Choice(StrEnum):
    """Les valeurs acceptées par `tool1`, pour qu'une valeur invalide échoue ici et pas plus loin."""

    HELLO = "hello"
    WORLD = "world"
    EXCLAM = "!"


Tool1Input = Annotated[
    Tool1Choice,
    Field(description="Le mot à renvoyer : 'hello', 'world' ou '!'.", examples=["hello"]),
]


class OutputPhrase(BaseModel):
    """Ce que renvoie `tool1`."""

    returned_phrase: str = Field(description="La phrase construite à partir du mot choisi.")
```

**2. L'outil** — `src/mcpserver/tools/myservice/tools.py`

```python
async def tool1(word: Tool1Input) -> OutputPhrase:
    """Renvoyer le mot choisi dans une phrase."""
    return OutputPhrase(returned_phrase=f"Votre choix : {word}")
```

**3. L'enregistrement** — `src/mcpserver/tools/__init__.py`

```python
from .myservice.tools import tool1

mcp.tool(tool1, annotations=READ_ONLY)
```

C'est tout. Redémarrez : `tool1` est listé, appelable, validé par `Tool1Input` en entrée et par
`OutputPhrase` en sortie.

Deux règles séparent un outil qu'un LLM utilise bien d'un outil qu'il ignore :

- **La docstring est la description de l'outil.** C'est ce que lit le modèle pour décider de vous
  appeler. Dites ce que fait l'outil, quand l'utiliser, ce qu'il renvoie.
- **Chaque `Field(description=...)` fait partie du schéma.** Écrivez-les pour quelqu'un qui n'a
  jamais vu votre code.

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
    ErrorCode.INVALID_INPUT,
    "`word` doit valoir hello, world ou !. Appelez `tool1` avec 'hello' pour tester.",
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

Le point d'entrée est `POST /mcp` sur le port `8000`, en Streamable HTTP. Tout client MCP qui parle
HTTP fonctionne. Entrée `mcpServers` (Claude Desktop, Cursor, et la plupart des autres) :

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

Les clients qui ne parlent que **stdio** ne peuvent pas joindre ce serveur directement : utilisez un
client compatible HTTP, ou placez le serveur derrière une passerelle qui parle les deux.

## Configuration

Tout est lu depuis l'environnement, ou depuis `.env` dans le répertoire de travail. Commencez par
`cp .env.example .env`.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `MCP_NAME` | `McpSquelette` | Nom du serveur envoyé au handshake |
| `MCP_HOST` | `0.0.0.0` | Interface d'écoute (`0.0.0.0` est nécessaire en conteneur) |
| `MCP_PORT` | `8000` | Port d'écoute |
| `ALLOWED_HOSTS` | `["*"]` | Noms d'hôte acceptés dans l'en-tête `Host`. `["*"]` désactive le contrôle |
| `ALLOWED_ORIGINS` | `[]` | Origines navigateur autorisées sur `POST /mcp`. Vide refuse tout navigateur cross-origin |
| `TRUSTED_PROXY_HOSTS` | `["127.0.0.1"]` | Pairs dont `X-Forwarded-For` est cru. À élargir à votre reverse proxy uniquement |
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
├── .env.example              # toutes les variables, documentées — à copier en .env
├── Dockerfile                # multi-étapes, non-root, healthcheck
├── k8s/manifest.yaml         # Service + Deployment + Ingress
├── pyproject.toml            # dépendances, script console, config ruff + pytest
├── skill.md                  # un Skill pour les agents qui travaillent dans ce dépôt
├── src/mcpserver/
│   ├── server.py             # point d'entrée : settings, middlewares, app HTTP
│   ├── settings.py           # chaque valeur configurable
│   ├── logging.py            # format et niveau de journalisation
│   ├── errors/               # AppToolError + ErrorCode
│   ├── models/myserver.py    # vos schémas Pydantic
│   ├── tools/
│   │   ├── __init__.py       # l'unique point d'enregistrement
│   │   └── myservice/        # un paquet par groupe d'outils
│   └── utils/client_host.py  # clé de limitation de débit
└── tests/                    # exécutent la vraie app sur le vrai protocole
```

Pour renommer le projet : `name` dans `pyproject.toml`, l'entrée `[project.scripts]`, et le
répertoire `src/mcpserver/` — puis `uv sync`. Rien d'autre ne dépend du nom.

## Développement

```bash
uv run pytest -q                  # 11 tests, au niveau du protocole
uv run ruff check . && uv run ruff format --check .
uv run pre-commit install         # lint et format à chaque commit
```

Les tests parlent à l'application via `fastmcp.Client(mcp)` : ils prouvent que l'outil est
*enregistré* et que son schéma est correct, pas seulement que la fonction marche quand on l'appelle
directement. Ajoutez un test dans `tests/test_server.py` pour chaque outil publié.

## Pour les agents IA

`skill.md` est un [Skill](https://docs.claude.com/en/docs/claude-code/skills) destiné aux agents de
code : il indique où va un outil, quelles conventions ce squelette impose (lever `AppToolError`,
renvoyer un modèle, enregistrer à un seul endroit) et comment vérifier le résultat. Placez le dépôt
devant un agent qui lit les Skills : il n'aura pas à inventer la structure.

## Limites et sécurité

- **Aucune authentification.** McpSquelette sert quiconque atteint le port. Placez-le derrière une
  passerelle, un VPN ou le proxy d'authentification de votre plateforme avant de l'exposer.
- **`ALLOWED_HOSTS` vaut `["*"]` par défaut** et journalise un avertissement. Mettez le vrai nom
  d'hôte.
- **La limitation de débit est en mémoire, par processus.** Deux réplicas autorisent deux fois plus
  de requêtes, et un redémarrage remet les compteurs à zéro. Pour une garantie ferme, utilisez le
  limiteur de votre plateforme.
- **`mask_error_details=True` est voulu** : seul le texte des `AppToolError` est public. Ne mettez
  jamais de jeton, d'URL interne ou de trace dans le message d'erreur d'un outil.
- **Un processus, un jeu d'outils.** Les outils sont enregistrés au démarrage ; pas de rechargement
  à chaud du schéma en production.

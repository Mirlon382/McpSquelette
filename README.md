# MCP Sirene V3 — INSEE

Serveur **Model Context Protocol (MCP)** pour interroger l’**API Sirene V3.11** de l’Insee depuis un assistant IA compatible MCP. Le modèle peut traduire une demande en langage naturel en appels aux outils de recherche, de comptage, d’analyse et d’export.

> Projet personnel non officiel. Ce dépôt n’est ni développé ni maintenu par l’Insee. Les données et résultats restent soumis aux règles et quotas de l’API Sirene.

## Fonctionnalités

- **Recherche par identifiant** : `rechercher_siren`, `rechercher_siret`, `rechercher_etablissements_siren`.
- **Recherche multicritère** : `rechercher_unites_legales`, `rechercher_etablissements` (activité, localisation, état, dates et autres filtres disponibles).
- **Comptages et analyses** : `compter_etablissements`, `analyser_etablissements`, `statistiques_sirene`.
- **Requêtes avancées** : `requete_avancee` accepte une expression `q` de l’API Sirene V3.11.
- **Historique et succession** : `historique_unite_legale`, `historique_etablissement`, `liens_succession`, `explorer_chaine_succession`.
- **Exports** : `exporter_etablissements`, `exporter_sirene_multiformat` (CSV, XLSX, ODS, Parquet, JSONL), `rechercher_identifiants_en_masse`.
- **Comparaisons à 2 dates** : `comparer_situations_sirene`, dans la limite de la couverture et de la pagination des résultats.

Les recherches volumineuses peuvent être limitées par des plafonds de sécurité et des quotas. Les statistiques effectuées sur un échantillon partiel ne sont pas exhaustives.

## Exemples de demandes à l’assistant

- « Recherche les établissements actifs dans la commune de Puteaux. »
- « Combien d’établissements de restauration sont implantés à Malakoff ? »
- « Liste les unités légales créées entre 1980 et 2003. »
- « Retrouve les changements d’activité de cette unité légale. »
- « Exporte les établissements correspondant à ma requête en Parquet. »
- « Compare les établissements correspondant à ces critères au 1er janvier 2020 et au 1er janvier 2025. »

## Installation

Prévoir Python compatible avec les versions fixées dans `requirements.txt` (environnement d’origine : Python 3.13), une connexion Internet et une clé d’accès à l’API Sirene publique.

```bash
git clone <URL_DU_DEPOT_GITLAB>
cd mcp-sirene-v3
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Éditer `.env` et renseigner **sa propre** `INSEE_API_KEY`. Ne jamais publier ce fichier.

```bash
python server.py
```

Le serveur démarre par défaut sur `0.0.0.0:8000`, avec un point d’accès MCP sous `/mcp`. Le serveur propose également `/exports/{filename}` pour certains fichiers d’export temporaires.

## Variables d’environnement

| Variable | Rôle |
| --- | --- |
| `INSEE_API_KEY` | Clé API Sirene publique (obligatoire) |
| `SIRENE_EXPORT_DIR` | Dossier des exports classiques ; valeur par défaut sous le dossier personnel |
| `SIRENE_EXPORT_DIR_EXT` | Dossier des exports temporaires téléchargeables (par défaut `/tmp/mcp-sirene-exports`) |
| `SIRENE_PUBLIC_BASE_URL` | Adresse publique du serveur, utilisée pour fournir des liens de téléchargement |

Le fichier `.env.example` contient des valeurs fictives, à personnaliser.

## Connexion à un client MCP

Utiliser l’URL HTTPS publique de votre propre serveur suivie de `/mcp` (par exemple `https://votre-domaine.example/mcp`) dans un client compatible **Streamable HTTP**. Le serveur est conçu pour être exposé derrière un reverse proxy ou un tunnel HTTPS.

**À adapter dans le code avant un autre déploiement :** dans `server.py`, la liste `allowed_hosts` et la liste `allowed_origins` incluent actuellement le domaine de l’installation d’origine (`sirenev3.liminalab.fr`). Ajustez-les selon votre domaine et vos clients MCP. Le port et l’adresse d’écoute sont également définis dans le bloc `uvicorn.run(...)` final.

## Sécurité et limites

- Ne publiez jamais votre `.env`, des clés API ou les données produites dans les dossiers d’exports.
- **Attention aux quotas** : tous les utilisateurs partageant une même clé/instance peuvent consommer le quota de l’application.
- Le point de téléchargement d’export repose sur un nom de fichier difficile à deviner et sur une expiration, **pas sur une authentification de l’utilisateur**. Évaluez les risques avant de rendre l’instance publique.
- L’accès au serveur est à sécuriser via vos propres mécanismes (authentification, réseau, proxy, limitations d’accès). Ce dépôt ne fournit pas une solution de sécurisation prête pour un déploiement public.
- Les requêtes et les historiques dépendent des fonctionnalités exposées par l’API V3.11 ; une réponse partielle n’est pas un résultat exhaustif.

## Structure

```text
server.py          Serveur et outils MCP
requirements.txt   Dépendances de l’environnement exporté
.env.example       Configuration d’exemple sans clé réelle
.gitignore         Exclusions Git
README.md          Documentation
```

## Mise à jour

La présente archive reprend une copie du `server.py` extrait du Raspberry Pi le 20 octobre 2026 ; elle ne modifie pas le service qui continue à y fonctionner. Vérifiez les versions des dépendances et la compatibilité du serveur lors d’une réinstallation.

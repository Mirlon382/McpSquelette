import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
import re
import secrets
import threading
import time
from datetime import date
from typing import Callable
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

load_dotenv()
mcp = MCPServer("Sirene INSEE")

API_KEY = os.getenv("INSEE_API_KEY")
BASE_URL = "https://api.insee.fr/api-sirene/3.11"
HEADERS = {"X-INSEE-Api-Key-Integration": API_KEY}


def appel_sirene(endpoint: str, params: dict | None = None) -> dict:
    try:
        response = httpx.get(
            f"{BASE_URL}{endpoint}", headers=HEADERS, params=params, timeout=30
        )
        if response.status_code == 200:
            return response.json()
        return {
            "erreur": f"Erreur API Sirene : HTTP {response.status_code}",
            "detail": response.text,
            "url": str(response.request.url),
        }
    except httpx.RequestError as exc:
        return {"erreur": "Impossible de joindre l'API Sirene", "detail": str(exc)}


def nettoyer_siren(v: str) -> str:
    return v.replace(" ", "").replace("-", "").replace(".", "")


def nettoyer_siret(v: str) -> str:
    return v.replace(" ", "").replace("-", "").replace(".", "")


def siren_valide(v: str) -> bool:
    return v.isdigit() and len(v) == 9


def siret_valide(v: str) -> bool:
    return v.isdigit() and len(v) == 14


def limiter_nombre(n: int) -> int:
    return max(1, min(n, 1000))


def condition(variable: str, valeur: str) -> str:
    return f"{variable}:{valeur.strip()}"


def condition_or(variable: str, valeurs: list[str]) -> str:
    items = [condition(variable, str(v)) for v in valeurs if str(v).strip()]
    if not items:
        return ""
    return items[0] if len(items) == 1 else "(" + " OR ".join(items) + ")"


def condition_prefixe(variable: str, prefixe: str) -> str:
    """Construit une recherche par préfixe Lucene/Sirene, ex. 8*."""
    prefixe = str(prefixe).strip().upper()
    if not prefixe:
        return ""
    # Le joker est ajouté par le MCP pour éviter de demander à l'IA de le fournir.
    return f"{variable}:{prefixe}*"


def intervalle(variable: str, debut: str, fin: str) -> str:
    """Construit un intervalle inclusif Sirene, années ou dates acceptées."""
    debut = str(debut).strip()
    fin = str(fin).strip()
    if not debut or not fin:
        raise ValueError(f"Les deux bornes de {variable} doivent être renseignées.")
    return f"{variable}:[{debut} TO {fin}]"


def prefixe_departement(code_departement: str) -> str:
    """Recherche les codes commune commençant par le code département."""
    code = str(code_departement).strip().upper()
    if not code:
        return ""
    return f"codeCommuneEtablissement:{code}*"


def periode_courante(conditions: list[str]) -> str:
    return "periode(" + " AND ".join([c for c in conditions if c] + ["-dateFin:*"]) + ")"


def periode_historique(conditions: list[str]) -> str:
    return "periode(" + " AND ".join(c for c in conditions if c) + ")"


def chevauchement_periode(conditions: list[str], debut: str, fin: str) -> str:
    base = [c for c in conditions if c]
    terminee = base + [f"dateDebut:[* TO {fin}]", f"dateFin:[{debut} TO *]"]
    en_cours = base + [f"dateDebut:[* TO {fin}]", "-dateFin:*"]
    return (
        "(periode(" + " AND ".join(terminee) + ") OR periode("
        + " AND ".join(en_cours) + "))"
    )


def assembler(blocs: list[str]) -> str:
    return " AND ".join(b for b in blocs if b)


def appel_sirene_pagine(
    endpoint: str,
    params: dict,
    collection: str,
    tous_les_resultats: bool = False,
    limite_securite: int = 50000,
) -> dict:
    """
    Appelle un endpoint de recherche Sirene et, si demandé, parcourt
    automatiquement toutes les pages avec curseurSuivant.

    - Une page demande au maximum 1000 résultats.
    - Si tous_les_resultats=False, un seul appel est effectué.
    - limite_securite évite de renvoyer accidentellement un volume énorme.
      Mettre 0 pour désactiver cette limite.
    """
    params = dict(params)

    if not tous_les_resultats:
        resultat = appel_sirene(endpoint, params)
        if "erreur" in resultat:
            return resultat

        header = resultat.get("header", {})
        elements = resultat.get(collection, [])

        # Les endpoints Siren/Siret renvoient normalement une liste.
        if not isinstance(elements, list):
            elements = []

        total = header.get("total")
        return {
            **resultat,
            "paginationMcp": {
                "total": total,
                "nombreRetourne": len(elements),
                "complet": total is not None and len(elements) >= total,
                "tousLesResultatsDemandes": False,
            },
        }

    params["nombre"] = 1000
    params.pop("curseur", None)

    tous = []
    premier_header = None
    # La pagination Sirene par curseur doit être initialisée avec "*".
    # La réponse fournit ensuite header.curseurSuivant pour la page suivante.
    curseur = "*"
    total = None
    pages = 0
    tronque = False

    while True:
        appel_params = dict(params)
        if curseur:
            appel_params["curseur"] = curseur

        resultat = appel_sirene(endpoint, appel_params)
        if "erreur" in resultat:
            return {
                **resultat,
                "paginationMcp": {
                    "pagesRecuperees": pages,
                    "nombreRetourneAvantErreur": len(tous),
                    "total": total,
                    "complet": False,
                },
            }

        pages += 1
        header = resultat.get("header", {})
        if premier_header is None:
            premier_header = dict(header)

        if total is None:
            total = header.get("total")

        elements = resultat.get(collection, [])
        if not isinstance(elements, list):
            elements = []

        tous.extend(elements)

        if limite_securite > 0 and len(tous) >= limite_securite:
            tous = tous[:limite_securite]
            tronque = total is None or len(tous) < total
            break

        curseur_suivant = header.get("curseurSuivant")

        # Fin normale : pas de curseur suivant, ou tout le total a été récupéré.
        if not curseur_suivant:
            break
        if total is not None and len(tous) >= total:
            break

        # Protection contre un éventuel curseur qui bouclerait.
        if curseur_suivant == curseur:
            return {
                "erreur": "Pagination interrompue : le curseur Sirene n'avance plus.",
                "paginationMcp": {
                    "pagesRecuperees": pages,
                    "nombreRetourne": len(tous),
                    "total": total,
                    "complet": False,
                },
            }

        curseur = curseur_suivant

    complet = total is not None and len(tous) >= total and not tronque

    header_final = premier_header or {}
    header_final["nombre"] = len(tous)

    return {
        "header": header_final,
        collection: tous,
        "paginationMcp": {
            "total": total,
            "nombreRetourne": len(tous),
            "pagesRecuperees": pages,
            "complet": complet,
            "tronqueParLimiteSecurite": tronque,
            "limiteSecurite": limite_securite if limite_securite > 0 else None,
            "tousLesResultatsDemandes": True,
        },
    }


@mcp.tool()
def rechercher_siren(siren: str, situation_courante: bool = True) -> dict:
    """Recherche une unité légale par SIREN."""
    siren = nettoyer_siren(siren)
    if not siren_valide(siren):
        return {"erreur": "Le SIREN doit contenir exactement 9 chiffres."}
    params = {"date": "2999-12-31"} if situation_courante else None
    return appel_sirene(f"/siren/{siren}", params)


@mcp.tool()
def rechercher_unites_legales(
    activites: Optional[list[str]] = None,
    activite_prefixe: Optional[str] = None,
    etats: Optional[list[str]] = None,
    denominations: Optional[list[str]] = None,
    noms: Optional[list[str]] = None,
    categories_juridiques: Optional[list[str]] = None,
    categories_entreprise: Optional[list[str]] = None,
    tranches_effectifs: Optional[list[str]] = None,
    statut_diffusion: Optional[str] = None,
    identifiant_association: Optional[str] = None,
    date_creation_debut: Optional[str] = None,
    date_creation_fin: Optional[str] = None,
    actuellement: bool = True,
    date_situation: Optional[str] = None,
    nombre: int = 20,
    tous_les_resultats: bool = False,
    limite_securite: int = 50000,
) -> dict:
    """
    Recherche multicritère d'unités légales.

    - activite_prefixe permet par exemple "8" pour toutes les activités 8*.
    - date_creation_debut/date_creation_fin acceptent une année (1980) ou une date.
    - date_situation utilise le paramètre natif `date` de l'API Sirene ;
      les critères historisés restent regroupés dans periode(...).
    """
    hist, non_hist = [], []

    if activites:
        hist.append(condition_or("activitePrincipaleUniteLegale", [a.upper() for a in activites]))
    if activite_prefixe:
        # Les jokers ne sont pas acceptés dans periode(...).
        non_hist.append(condition_prefixe("activitePrincipaleUniteLegale", activite_prefixe))
    if etats:
        hist.append(condition_or("etatAdministratifUniteLegale", [e.upper() for e in etats]))
    if denominations:
        hist.append(condition_or("denominationUniteLegale", denominations))
    if noms:
        hist.append(condition_or("nomUniteLegale", noms))
    if categories_juridiques:
        hist.append(condition_or("categorieJuridiqueUniteLegale", categories_juridiques))
    if categories_entreprise:
        non_hist.append(condition_or("categorieEntreprise", categories_entreprise))
    if tranches_effectifs:
        non_hist.append(condition_or("trancheEffectifsUniteLegale", tranches_effectifs))
    if statut_diffusion:
        non_hist.append(condition("statutDiffusionUniteLegale", statut_diffusion))
    if identifiant_association:
        non_hist.append(condition("identifiantAssociationUniteLegale", identifiant_association))

    if date_creation_debut or date_creation_fin:
        if not date_creation_debut or not date_creation_fin:
            return {"erreur": "date_creation_debut et date_creation_fin doivent être renseignés ensemble."}
        try:
            non_hist.append(intervalle("dateCreationUniteLegale", date_creation_debut, date_creation_fin))
        except ValueError as exc:
            return {"erreur": str(exc)}

    blocs = []
    if hist:
        if date_situation:
            # Le paramètre API `date` sélectionne la situation à la date donnée,
            # mais les champs historisés restent dans periode(...).
            blocs.append(periode_historique(hist))
        elif actuellement:
            blocs.append(periode_courante(hist))
        else:
            blocs.append(periode_historique(hist))
    blocs.extend(non_hist)

    q = assembler(blocs)
    if not q:
        return {"erreur": "Indiquez au moins un critère de recherche."}

    params = {"q": q, "nombre": limiter_nombre(nombre)}
    if date_situation:
        params["date"] = date_situation

    return appel_sirene_pagine(
        "/siren", params, "unitesLegales",
        tous_les_resultats=tous_les_resultats,
        limite_securite=limite_securite,
    )


@mcp.tool()
def rechercher_siret(siret: str, situation_courante: bool = True) -> dict:
    """Recherche un établissement par SIRET."""
    siret = nettoyer_siret(siret)
    if not siret_valide(siret):
        return {"erreur": "Le SIRET doit contenir exactement 14 chiffres."}
    params = {"date": "2999-12-31"} if situation_courante else None
    return appel_sirene(f"/siret/{siret}", params)


@mcp.tool()
def rechercher_etablissements(
    activites: Optional[list[str]] = None,
    activite_prefixe: Optional[str] = None,
    etats: Optional[list[str]] = None,
    code_commune: Optional[str] = None,
    code_departement: Optional[str] = None,
    code_postal: Optional[str] = None,
    libelle_commune: Optional[str] = None,
    numero_voie: Optional[str] = None,
    type_voie: Optional[str] = None,
    libelle_voie: Optional[str] = None,
    enseignes: Optional[list[str]] = None,
    siege: Optional[bool] = None,
    tranches_effectifs: Optional[list[str]] = None,
    siren: Optional[str] = None,
    activites_ul: Optional[list[str]] = None,
    activite_ul_prefixe: Optional[str] = None,
    etats_ul: Optional[list[str]] = None,
    denominations_ul: Optional[list[str]] = None,
    categories_juridiques: Optional[list[str]] = None,
    categories_entreprise: Optional[list[str]] = None,
    date_creation_debut: Optional[str] = None,
    date_creation_fin: Optional[str] = None,
    date_creation_ul_debut: Optional[str] = None,
    date_creation_ul_fin: Optional[str] = None,
    jamais_ferme: bool = False,
    actuellement: bool = True,
    actif_entre_debut: Optional[str] = None,
    actif_entre_fin: Optional[str] = None,
    date_situation: Optional[str] = None,
    nombre: int = 20,
    tous_les_resultats: bool = False,
    limite_securite: int = 5000,
) -> dict:
    """
    Recherche multicritère d'établissements Sirene.

    Options historiques importantes :
    - date_situation : situation à une date précise via le paramètre API `date`.
    - actif_entre_debut/fin : au moins un jour actif dans l'intervalle.
    - jamais_ferme : exclut tout établissement ayant une période F.
    - activite_prefixe / activite_ul_prefixe : recherche par préfixe (ex. "8").
    """
    hist_etab, hist_ul, non_hist = [], [], []

    if activites:
        hist_etab.append(condition_or("activitePrincipaleEtablissement", [a.upper() for a in activites]))
    if activite_prefixe:
        # Les jokers ne sont pas acceptés dans periode(...).
        non_hist.append(condition_prefixe("activitePrincipaleEtablissement", activite_prefixe))
    if etats:
        hist_etab.append(condition_or("etatAdministratifEtablissement", [e.upper() for e in etats]))
    if enseignes:
        hist_etab.append(condition_or("enseigne1Etablissement", enseignes))

    if code_commune:
        non_hist.append(condition("codeCommuneEtablissement", code_commune))
    if code_departement:
        non_hist.append(prefixe_departement(code_departement))
    if code_postal:
        non_hist.append(condition("codePostalEtablissement", code_postal))
    if libelle_commune:
        non_hist.append(condition("libelleCommuneEtablissement", libelle_commune))
    if numero_voie:
        non_hist.append(condition("numeroVoieEtablissement", numero_voie))
    if type_voie:
        non_hist.append(condition("typeVoieEtablissement", type_voie.upper()))
    if libelle_voie:
        non_hist.append(condition("libelleVoieEtablissement", libelle_voie))
    if siege is not None:
        non_hist.append(f"etablissementSiege:{str(siege).lower()}")
    if tranches_effectifs:
        non_hist.append(condition_or("trancheEffectifsEtablissement", tranches_effectifs))

    if siren:
        s = nettoyer_siren(siren)
        if not siren_valide(s):
            return {"erreur": "Le SIREN doit contenir exactement 9 chiffres."}
        non_hist.append(f"siren:{s}")

    if activites_ul:
        hist_ul.append(condition_or("activitePrincipaleUniteLegale", [a.upper() for a in activites_ul]))
    if activite_ul_prefixe:
        # Exemple documenté : activitePrincipaleUniteLegale:8*
        non_hist.append(condition_prefixe("activitePrincipaleUniteLegale", activite_ul_prefixe))
    if etats_ul:
        hist_ul.append(condition_or("etatAdministratifUniteLegale", [e.upper() for e in etats_ul]))
    if denominations_ul:
        hist_ul.append(condition_or("denominationUniteLegale", denominations_ul))
    if categories_juridiques:
        hist_ul.append(condition_or("categorieJuridiqueUniteLegale", categories_juridiques))
    if categories_entreprise:
        non_hist.append(condition_or("categorieEntreprise", categories_entreprise))

    if date_creation_debut or date_creation_fin:
        if not date_creation_debut or not date_creation_fin:
            return {"erreur": "date_creation_debut et date_creation_fin doivent être renseignés ensemble."}
        non_hist.append(intervalle("dateCreationEtablissement", date_creation_debut, date_creation_fin))

    if date_creation_ul_debut or date_creation_ul_fin:
        if not date_creation_ul_debut or not date_creation_ul_fin:
            return {"erreur": "date_creation_ul_debut et date_creation_ul_fin doivent être renseignés ensemble."}
        non_hist.append(intervalle("dateCreationUniteLegale", date_creation_ul_debut, date_creation_ul_fin))

    blocs = []

    if actif_entre_debut or actif_entre_fin:
        if not actif_entre_debut or not actif_entre_fin:
            return {"erreur": "actif_entre_debut et actif_entre_fin doivent être renseignés ensemble."}
        # La demande « actif au moins un jour » exige une période A qui chevauche
        # l'intervalle : dateDebut <= fin ET (dateFin >= debut OU dateFin absente).
        if not etats:
            hist_etab.append(condition("etatAdministratifEtablissement", "A"))
        blocs.append(chevauchement_periode(hist_etab, actif_entre_debut, actif_entre_fin))
    elif hist_etab:
        if date_situation:
            blocs.append(periode_historique(hist_etab))
        elif actuellement:
            blocs.append(periode_courante(hist_etab))
        else:
            blocs.append(periode_historique(hist_etab))

    if hist_ul:
        if date_situation:
            blocs.append(periode_historique(hist_ul))
        elif actuellement:
            blocs.append(periode_courante(hist_ul))
        else:
            blocs.append(periode_historique(hist_ul))

    if jamais_ferme:
        blocs.append("-periode(etatAdministratifEtablissement:F)")

    blocs.extend(non_hist)
    q = assembler(blocs)
    if not q:
        return {"erreur": "Indiquez au moins un critère de recherche."}

    params = {"q": q, "nombre": limiter_nombre(nombre)}
    if date_situation:
        params["date"] = date_situation

    return appel_sirene_pagine(
        "/siret", params, "etablissements",
        tous_les_resultats=tous_les_resultats,
        limite_securite=limite_securite,
    )


@mcp.tool()
def rechercher_etablissements_siren(
    siren: str,
    actifs_uniquement: bool = False,
    siege_uniquement: bool = False,
    nombre: int = 100,
    tous_les_resultats: bool = False,
    limite_securite: int = 50000,
) -> dict:
    """Recherche les établissements appartenant à un SIREN."""
    siren = nettoyer_siren(siren)
    if not siren_valide(siren):
        return {"erreur": "Le SIREN doit contenir exactement 9 chiffres."}

    blocs = [f"siren:{siren}"]
    if actifs_uniquement:
        blocs.append(periode_courante([condition("etatAdministratifEtablissement", "A")]))
    if siege_uniquement:
        blocs.append("etablissementSiege:true")

    return appel_sirene_pagine(
        "/siret",
        {
            "q": assembler(blocs),
            "nombre": limiter_nombre(nombre),
        },
        "etablissements",
        tous_les_resultats=tous_les_resultats,
        limite_securite=limite_securite,
    )


# ============================================================
# OUTILS POUR LES GROS VOLUMES
# ============================================================

EXPORT_DIR = Path(os.getenv("SIRENE_EXPORT_DIR", str(Path.home() / "mcp-sirene-exports")))


def _recherche_etablissements_complete(
    q: str,
    limite_securite: int = 50000,
    date_situation: Optional[str] = None,
) -> dict:
    """Récupère tous les établissements correspondant à q par curseur."""
    params = {"q": q, "nombre": 1000}
    if date_situation:
        params["date"] = date_situation
    return appel_sirene_pagine(
        "/siret", params, "etablissements",
        tous_les_resultats=True,
        limite_securite=limite_securite,
    )


def _q_etablissements_courants(
    activites: Optional[list[str]] = None,
    activite_prefixe: Optional[str] = None,
    etats: Optional[list[str]] = None,
    code_commune: Optional[str] = None,
    code_departement: Optional[str] = None,
    code_postal: Optional[str] = None,
    siren: Optional[str] = None,
    siege: Optional[bool] = None,
    activites_ul: Optional[list[str]] = None,
    activite_ul_prefixe: Optional[str] = None,
    jamais_ferme: bool = False,
    date_creation_debut: Optional[str] = None,
    date_creation_fin: Optional[str] = None,
    date_creation_ul_debut: Optional[str] = None,
    date_creation_ul_fin: Optional[str] = None,
    actuellement: bool = True,
    actif_entre_debut: Optional[str] = None,
    actif_entre_fin: Optional[str] = None,
    date_situation: Optional[str] = None,
) -> str:
    """Construit un q partagé par comptage/analyse/export."""
    hist_etab, hist_ul, non_hist = [], [], []

    if activites:
        hist_etab.append(condition_or("activitePrincipaleEtablissement", [a.upper().strip() for a in activites]))
    if activite_prefixe:
        non_hist.append(condition_prefixe("activitePrincipaleEtablissement", activite_prefixe))
    if etats:
        hist_etab.append(condition_or("etatAdministratifEtablissement", [e.upper().strip() for e in etats]))
    if activites_ul:
        hist_ul.append(condition_or("activitePrincipaleUniteLegale", [a.upper().strip() for a in activites_ul]))
    if activite_ul_prefixe:
        non_hist.append(condition_prefixe("activitePrincipaleUniteLegale", activite_ul_prefixe))

    if code_commune:
        non_hist.append(condition("codeCommuneEtablissement", code_commune.strip()))
    if code_departement:
        non_hist.append(prefixe_departement(code_departement))
    if code_postal:
        non_hist.append(condition("codePostalEtablissement", code_postal.strip()))
    if siren:
        s = nettoyer_siren(siren)
        if not siren_valide(s):
            raise ValueError("Le SIREN doit contenir exactement 9 chiffres.")
        non_hist.append(f"siren:{s}")
    if siege is not None:
        non_hist.append(f"etablissementSiege:{str(siege).lower()}")

    if date_creation_debut or date_creation_fin:
        if not date_creation_debut or not date_creation_fin:
            raise ValueError("date_creation_debut et date_creation_fin doivent être renseignés ensemble.")
        non_hist.append(intervalle("dateCreationEtablissement", date_creation_debut, date_creation_fin))
    if date_creation_ul_debut or date_creation_ul_fin:
        if not date_creation_ul_debut or not date_creation_ul_fin:
            raise ValueError("date_creation_ul_debut et date_creation_ul_fin doivent être renseignés ensemble.")
        non_hist.append(intervalle("dateCreationUniteLegale", date_creation_ul_debut, date_creation_ul_fin))

    blocs = []
    if actif_entre_debut or actif_entre_fin:
        if not actif_entre_debut or not actif_entre_fin:
            raise ValueError("actif_entre_debut et actif_entre_fin doivent être renseignés ensemble.")
        if not etats:
            hist_etab.append(condition("etatAdministratifEtablissement", "A"))
        blocs.append(chevauchement_periode(hist_etab, actif_entre_debut, actif_entre_fin))
    elif hist_etab:
        if date_situation:
            blocs.append(periode_historique(hist_etab))
        elif actuellement:
            blocs.append(periode_courante(hist_etab))
        else:
            blocs.append(periode_historique(hist_etab))

    if hist_ul:
        if date_situation:
            blocs.append(periode_historique(hist_ul))
        elif actuellement:
            blocs.append(periode_courante(hist_ul))
        else:
            blocs.append(periode_historique(hist_ul))
    if jamais_ferme:
        blocs.append("-periode(etatAdministratifEtablissement:F)")
    blocs.extend(non_hist)

    if not blocs:
        raise ValueError("Indiquez au moins un critère de recherche.")
    return assembler(blocs)


@mcp.tool()
def compter_etablissements(
    activites: Optional[list[str]] = None,
    activite_prefixe: Optional[str] = None,
    etats: Optional[list[str]] = None,
    code_commune: Optional[str] = None,
    code_departement: Optional[str] = None,
    code_postal: Optional[str] = None,
    siren: Optional[str] = None,
    siege: Optional[bool] = None,
    activites_ul: Optional[list[str]] = None,
    activite_ul_prefixe: Optional[str] = None,
    jamais_ferme: bool = False,
    date_creation_debut: Optional[str] = None,
    date_creation_fin: Optional[str] = None,
    date_creation_ul_debut: Optional[str] = None,
    date_creation_ul_fin: Optional[str] = None,
    actuellement: bool = True,
    actif_entre_debut: Optional[str] = None,
    actif_entre_fin: Optional[str] = None,
    date_situation: Optional[str] = None,
) -> dict:
    """Compte les établissements sans télécharger toutes les fiches."""
    try:
        q = _q_etablissements_courants(
            activites=activites, activite_prefixe=activite_prefixe, etats=etats,
            code_commune=code_commune, code_departement=code_departement,
            code_postal=code_postal, siren=siren, siege=siege,
            activites_ul=activites_ul, activite_ul_prefixe=activite_ul_prefixe,
            jamais_ferme=jamais_ferme,
            date_creation_debut=date_creation_debut, date_creation_fin=date_creation_fin,
            date_creation_ul_debut=date_creation_ul_debut, date_creation_ul_fin=date_creation_ul_fin,
            actuellement=actuellement, actif_entre_debut=actif_entre_debut, actif_entre_fin=actif_entre_fin,
            date_situation=date_situation,
        )
    except ValueError as exc:
        return {"erreur": str(exc)}

    params = {"q": q, "nombre": 1}
    if date_situation:
        params["date"] = date_situation
    resultat = appel_sirene("/siret", params)
    if "erreur" in resultat:
        return resultat

    return {"total": resultat.get("header", {}).get("total"), "requete": q, "date": date_situation}


@mcp.tool()
def requete_avancee(
    collection: str,
    requete: str,
    date_situation: Optional[str] = None,
    nombre: int = 20,
    tous_les_resultats: bool = False,
    limite_securite: int = 50000,
) -> dict:
    """
    Exécute une requête `q` Sirene V3.11 avancée lorsque les filtres structurés
    ne suffisent pas. collection doit valoir `siren` ou `siret`.
    """
    collection = collection.lower().strip()
    if collection not in {"siren", "siret"}:
        return {"erreur": "collection doit valoir siren ou siret."}
    requete = requete.strip()
    if not requete:
        return {"erreur": "La requête q ne peut pas être vide."}

    cle = "unitesLegales" if collection == "siren" else "etablissements"
    params = {"q": requete, "nombre": limiter_nombre(nombre)}
    if date_situation:
        params["date"] = date_situation
    return appel_sirene_pagine(
        f"/{collection}", params, cle,
        tous_les_resultats=tous_les_resultats,
        limite_securite=limite_securite,
    )


@mcp.tool()
def analyser_etablissements(
    activites: Optional[list[str]] = None,
    etats: Optional[list[str]] = None,
    code_commune: Optional[str] = None,
    code_postal: Optional[str] = None,
    siren: Optional[str] = None,
    regrouper_par: str = "activite",
    top: int = 50,
    limite_securite: int = 50000,
) -> dict:
    """
    Parcourt tous les résultats côté Raspberry puis renvoie seulement une
    agrégation compacte.

    regrouper_par :
      activite, commune, code_postal, statut_diffusion, siege
    """
    try:
        q = _q_etablissements_courants(
            activites=activites,
            etats=etats,
            code_commune=code_commune,
            code_postal=code_postal,
            siren=siren,
        )
    except ValueError as exc:
        return {"erreur": str(exc)}

    resultat = _recherche_etablissements_complete(q, limite_securite)
    if "erreur" in resultat:
        return resultat

    etablissements = resultat.get("etablissements", [])
    mapping = {
        "commune": lambda e: e.get("adresseEtablissement", {}).get("codeCommuneEtablissement"),
        "code_postal": lambda e: e.get("adresseEtablissement", {}).get("codePostalEtablissement"),
        "statut_diffusion": lambda e: e.get("statutDiffusionEtablissement"),
        "siege": lambda e: str(e.get("etablissementSiege")),
        "activite": lambda e: (
            (e.get("periodesEtablissement") or [{}])[0]
            .get("activitePrincipaleEtablissement")
        ),
    }

    if regrouper_par not in mapping:
        return {
            "erreur": "regrouper_par non reconnu.",
            "valeurs_acceptees": list(mapping.keys()),
        }

    compteur = Counter()
    for etab in etablissements:
        valeur = mapping[regrouper_par](etab)
        compteur[valeur or "NON_RENSEIGNE"] += 1

    top = max(1, min(top, 500))
    return {
        "requete": q,
        "regrouperPar": regrouper_par,
        "totalApi": resultat.get("paginationMcp", {}).get("total"),
        "nombreAnalyse": len(etablissements),
        "complet": resultat.get("paginationMcp", {}).get("complet"),
        "pagesRecuperees": resultat.get("paginationMcp", {}).get("pagesRecuperees"),
        "groupes": [
            {"valeur": valeur, "nombre": nombre}
            for valeur, nombre in compteur.most_common(top)
        ],
        "nombreGroupes": len(compteur),
    }


@mcp.tool()
def exporter_etablissements(
    activites: Optional[list[str]] = None,
    etats: Optional[list[str]] = None,
    code_commune: Optional[str] = None,
    code_postal: Optional[str] = None,
    siren: Optional[str] = None,
    format_export: str = "csv",
    champs: Optional[list[str]] = None,
    limite_securite: int = 50000,
) -> dict:
    """
    Récupère tous les résultats côté Raspberry et les écrit dans un fichier
    au lieu de renvoyer les fiches complètes à ChatGPT.

    Formats : csv ou jsonl.

    Champs CSV/JSONL disponibles par défaut :
      siren, siret, nic, denomination, activite, etat, siege,
      statut_diffusion, numero_voie, type_voie, libelle_voie,
      code_postal, commune, code_commune.

    Le MCP ne renvoie que les métadonnées de l'export et le chemin du fichier.
    """
    try:
        q = _q_etablissements_courants(
            activites=activites,
            etats=etats,
            code_commune=code_commune,
            code_postal=code_postal,
            siren=siren,
        )
    except ValueError as exc:
        return {"erreur": str(exc)}

    resultat = _recherche_etablissements_complete(q, limite_securite)
    if "erreur" in resultat:
        return resultat

    etablissements = resultat.get("etablissements", [])
    format_export = format_export.lower().strip()

    if format_export not in {"csv", "jsonl"}:
        return {"erreur": "format_export doit valoir csv ou jsonl."}

    def ligne(e: dict) -> dict:
        adresse = e.get("adresseEtablissement") or {}
        ul = e.get("uniteLegale") or {}
        periode = (e.get("periodesEtablissement") or [{}])[0]
        denomination = (
            ul.get("denominationUniteLegale")
            or " ".join(
                x for x in [
                    ul.get("prenom1UniteLegale"),
                    ul.get("nomUniteLegale")
                ] if x
            )
            or None
        )
        return {
            "siren": e.get("siren"),
            "siret": e.get("siret"),
            "nic": e.get("nic"),
            "denomination": denomination,
            "activite": periode.get("activitePrincipaleEtablissement"),
            "etat": periode.get("etatAdministratifEtablissement"),
            "siege": e.get("etablissementSiege"),
            "statut_diffusion": e.get("statutDiffusionEtablissement"),
            "numero_voie": adresse.get("numeroVoieEtablissement"),
            "type_voie": adresse.get("typeVoieEtablissement"),
            "libelle_voie": adresse.get("libelleVoieEtablissement"),
            "code_postal": adresse.get("codePostalEtablissement"),
            "commune": adresse.get("libelleCommuneEtablissement"),
            "code_commune": adresse.get("codeCommuneEtablissement"),
        }

    lignes = [ligne(e) for e in etablissements]
    disponibles = list(lignes[0].keys()) if lignes else [
        "siren", "siret", "nic", "denomination", "activite", "etat", "siege",
        "statut_diffusion", "numero_voie", "type_voie", "libelle_voie",
        "code_postal", "commune", "code_commune"
    ]

    if champs:
        inconnus = [c for c in champs if c not in disponibles]
        if inconnus:
            return {
                "erreur": "Certains champs demandés ne sont pas disponibles.",
                "champs_inconnus": inconnus,
                "champs_disponibles": disponibles,
            }
        colonnes = champs
    else:
        colonnes = disponibles

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    fichier = EXPORT_DIR / f"etablissements_{horodatage}.{format_export}"

    if format_export == "csv":
        with fichier.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=colonnes, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(lignes)
    else:
        with fichier.open("w", encoding="utf-8") as f:
            for item in lignes:
                f.write(json.dumps(
                    {c: item.get(c) for c in colonnes},
                    ensure_ascii=False
                ) + "\\n")

    pagination = resultat.get("paginationMcp", {})
    return {
        "exportReussi": True,
        "format": format_export,
        "fichier": str(fichier),
        "nombreLignes": len(lignes),
        "totalApi": pagination.get("total"),
        "complet": pagination.get("complet"),
        "pagesRecuperees": pagination.get("pagesRecuperees"),
        "tailleOctets": fichier.stat().st_size,
        "champs": colonnes,
        "requete": q,
        "note": (
            "Le fichier est enregistré sur le Raspberry. "
            "La réponse MCP ne contient pas les fiches complètes."
        ),
    }


@mcp.tool()
def historique_unite_legale(siren: str, type_historique: str = "tout") -> dict:
    """Retourne les périodes d'une unité légale."""
    siren = nettoyer_siren(siren)
    if not siren_valide(siren):
        return {"erreur": "Le SIREN doit contenir exactement 9 chiffres."}

    resultat = appel_sirene(f"/siren/{siren}")
    if "erreur" in resultat:
        return resultat

    ul = resultat.get("uniteLegale", {})
    periodes = ul.get("periodesUniteLegale", [])
    champs = {
        "activite": ["activitePrincipaleUniteLegale", "nomenclatureActivitePrincipaleUniteLegale", "changementActivitePrincipaleUniteLegale"],
        "etat": ["etatAdministratifUniteLegale", "changementEtatAdministratifUniteLegale"],
        "denomination": ["denominationUniteLegale", "denominationUsuelle1UniteLegale", "denominationUsuelle2UniteLegale", "denominationUsuelle3UniteLegale", "changementDenominationUniteLegale"],
        "categorie_juridique": ["categorieJuridiqueUniteLegale", "changementCategorieJuridiqueUniteLegale"],
        "nom": ["nomUniteLegale", "changementNomUniteLegale"],
        "nom_usage": ["nomUsageUniteLegale", "changementNomUsageUniteLegale"],
        "siege": ["nicSiegeUniteLegale", "changementNicSiegeUniteLegale"],
    }

    t = type_historique.lower().strip()
    if t == "tout":
        return {"siren": siren, "nombrePeriodes": ul.get("nombrePeriodesUniteLegale"), "periodes": periodes}
    if t not in champs:
        return {"erreur": "Type d'historique non reconnu.", "types_acceptes": ["tout", *champs.keys()]}

    sortie = []
    for p in periodes:
        ligne = {"dateDebut": p.get("dateDebut"), "dateFin": p.get("dateFin")}
        for champ in champs[t]:
            ligne[champ] = p.get(champ)
        sortie.append(ligne)
    return {"siren": siren, "typeHistorique": t, "periodes": sortie}


@mcp.tool()
def historique_etablissement(siret: str, type_historique: str = "tout") -> dict:
    """Retourne les périodes d'un établissement."""
    siret = nettoyer_siret(siret)
    if not siret_valide(siret):
        return {"erreur": "Le SIRET doit contenir exactement 14 chiffres."}

    resultat = appel_sirene(f"/siret/{siret}")
    if "erreur" in resultat:
        return resultat

    etab = resultat.get("etablissement", {})
    periodes = etab.get("periodesEtablissement", [])
    champs = {
        "activite": ["activitePrincipaleEtablissement", "nomenclatureActivitePrincipaleEtablissement", "changementActivitePrincipaleEtablissement"],
        "etat": ["etatAdministratifEtablissement", "changementEtatAdministratifEtablissement"],
        "enseigne": ["enseigne1Etablissement", "enseigne2Etablissement", "enseigne3Etablissement", "changementEnseigneEtablissement"],
        "denomination_usuelle": ["denominationUsuelleEtablissement", "changementDenominationUsuelleEtablissement"],
        "employeur": ["caractereEmployeurEtablissement", "changementCaractereEmployeurEtablissement"],
    }

    t = type_historique.lower().strip()
    if t == "tout":
        return {"siret": siret, "nombrePeriodes": etab.get("nombrePeriodesEtablissement"), "periodes": periodes}
    if t not in champs:
        return {"erreur": "Type d'historique non reconnu.", "types_acceptes": ["tout", *champs.keys()]}

    sortie = []
    for p in periodes:
        ligne = {"dateDebut": p.get("dateDebut"), "dateFin": p.get("dateFin")}
        for champ in champs[t]:
            ligne[champ] = p.get(champ)
        sortie.append(ligne)
    return {"siret": siret, "typeHistorique": t, "periodes": sortie}


@mcp.tool()
def liens_succession(
    siret: str,
    sens: str = "tous",
    continuite_economique: Optional[bool] = None,
    transfert_siege: Optional[bool] = None,
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
    nombre: int = 100,
) -> dict:
    """Recherche les liens de succession d'un établissement."""
    siret = nettoyer_siret(siret)
    if not siret_valide(siret):
        return {"erreur": "Le SIRET doit contenir exactement 14 chiffres."}

    sens = sens.lower().strip()
    if sens not in {"tous", "predecesseurs", "successeurs"}:
        return {"erreur": "sens doit valoir tous, predecesseurs ou successeurs."}
    if (date_debut and not date_fin) or (date_fin and not date_debut):
        return {"erreur": "date_debut et date_fin doivent être renseignées ensemble."}

    def q_lien(variable: str) -> str:
        c = [f"{variable}:{siret}"]
        if continuite_economique is not None:
            c.append(f"continuiteEconomique:{str(continuite_economique).lower()}")
        if transfert_siege is not None:
            c.append(f"transfertSiege:{str(transfert_siege).lower()}")
        if date_debut and date_fin:
            c.append(f"dateLienSuccession:[{date_debut} TO {date_fin}]")
        return assembler(c)

    def appel(variable: str) -> dict:
        return appel_sirene("/siret/liensSuccession", {
            "q": q_lien(variable),
            "nombre": limiter_nombre(nombre),
        })

    if sens == "successeurs":
        return appel("siretEtablissementPredecesseur")
    if sens == "predecesseurs":
        return appel("siretEtablissementSuccesseur")
    return {
        "siret": siret,
        "successeurs": appel("siretEtablissementPredecesseur"),
        "predecesseurs": appel("siretEtablissementSuccesseur"),
    }




# === Fonctions intégrées : exports multiformats, masses, statistiques,
# comparaisons historiques et chaînes de succession ===

MASS_EXPORT_FIELDS = ["siren", "siret", "nic", "denomination", "activite", "etat", "siege", "statut_diffusion", "adresse", "code_postal", "commune", "code_commune"]
EXPORT_DIR_EXT = Path(os.getenv("SIRENE_EXPORT_DIR_EXT", "/tmp/mcp-sirene-exports"))
TTL = 900
# Exemple: SIRENE_PUBLIC_BASE_URL=https://sirene.mondomaine.fr
# Ne jamais ajouter /mcp à la fin : les fichiers sont servis sous /exports/.
SIRENE_PUBLIC_BASE_URL = os.getenv("SIRENE_PUBLIC_BASE_URL", "").rstrip("/")
EXPORT_EXTENSIONS = {"csv", "xlsx", "ods", "parquet", "jsonl"}
LOCK = threading.Lock()


def _date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError("Date invalide : utiliser AAAA-MM-JJ")


def _norm(value: str, n: int) -> str:
    s = re.sub(r"[ .-]", "", str(value))
    if not s.isdigit() or len(s) != n:
        raise ValueError(f"Identifiant attendu : {n} chiffres")
    return s


def _period_at(periods: list, at: str) -> dict:
    candidates = [p for p in periods if p.get("dateDebut") and p["dateDebut"] <= at and (not p.get("dateFin") or at <= p["dateFin"])]
    return max(candidates, key=lambda p: p["dateDebut"]) if candidates else {}


def _flatten(e: dict) -> dict:
    a = e.get("adresseEtablissement") or {}
    ul = e.get("uniteLegale") or {}
    p = (e.get("periodesEtablissement") or [{}])[0]
    return {
        "siren": e.get("siren"), "siret": e.get("siret"), "nic": e.get("nic"),
        "denomination": ul.get("denominationUniteLegale") or " ".join(filter(None, [ul.get("prenom1UniteLegale"), ul.get("nomUniteLegale")])),
        "activite": p.get("activitePrincipaleEtablissement"),
        "etat": p.get("etatAdministratifEtablissement"),
        "siege": e.get("etablissementSiege"),
        "statut_diffusion": e.get("statutDiffusionEtablissement"),
        "adresse": " ".join(str(x) for x in [a.get("numeroVoieEtablissement"), a.get("typeVoieEtablissement"), a.get("libelleVoieEtablissement")] if x and x != "[ND]"),
        "code_postal": a.get("codePostalEtablissement"),
        "commune": a.get("libelleCommuneEtablissement"),
        "code_commune": a.get("codeCommuneEtablissement"),
    }


def _clear_old() -> None:
    with LOCK:
        if not EXPORT_DIR_EXT.exists():
            return
        now = time.time()
        for path in EXPORT_DIR_EXT.iterdir():
            try:
                if path.is_file() and path.name.startswith("sirene_") and now - path.stat().st_mtime >= TTL:
                    path.unlink()
            except OSError:
                pass


def _schedule_delete(path: Path):
    timer = threading.Timer(TTL, lambda: path.unlink(missing_ok=True))
    timer.daemon = True
    timer.start()


def _write(rows: list[dict], fmt: str, fields: list[str]) -> dict:
    fmt = fmt.lower().lstrip(".")
    if fmt not in {"csv", "xlsx", "ods", "parquet", "jsonl"}:
        return {"erreur": "Formats : csv, xlsx, ods, parquet, jsonl"}
    if not rows:
        return {"erreur": "Aucune ligne à exporter"}
    unknown = [c for c in fields if c not in rows[0]]
    if unknown:
        return {"erreur": "Colonnes inconnues", "champs": unknown, "disponibles": list(rows[0])}
    _clear_old()
    EXPORT_DIR_EXT.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = EXPORT_DIR_EXT / f"sirene_{secrets.token_hex(16)}.{fmt}"
    try:
        if fmt == "csv":
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", delimiter=";")
                w.writeheader()
                w.writerows(rows)
        elif fmt == "jsonl":
            with path.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps({c: row.get(c) for c in fields}, ensure_ascii=False, default=str) + "\n")
        elif fmt == "xlsx":
            from openpyxl import Workbook
            wb = Workbook(write_only=True)
            ws = wb.create_sheet("Sirene")
            ws.append(fields)
            for row in rows:
                ws.append([str(row.get(c) if row.get(c) is not None else "") for c in fields])
            wb.save(path)
        elif fmt == "ods":
            from odf.opendocument import OpenDocumentSpreadsheet
            from odf.table import Table, TableRow, TableCell
            from odf.text import P
            doc = OpenDocumentSpreadsheet()
            table = Table(name="Sirene")
            for row in [dict(zip(fields, fields))] + rows:
                tr = TableRow()
                for col in fields:
                    cell = TableCell(valuetype="string")
                    cell.addElement(P(text=str(row.get(col) if row.get(col) is not None else "")))
                    tr.addElement(cell)
                table.addElement(tr)
            doc.spreadsheet.addElement(table)
            doc.save(str(path))
        elif fmt == "parquet":
            import pyarrow as pa
            import pyarrow.parquet as pq
            pq.write_table(pa.Table.from_pylist([{c: row.get(c) for c in fields} for row in rows]), path)
        os.chmod(path, 0o600)
    except ImportError as exc:
        path.unlink(missing_ok=True)
        return {"erreur": f"Dépendance manquante pour {fmt}: {exc}"}
    except Exception as exc:
        path.unlink(missing_ok=True)
        return {"erreur": f"Échec de l'export: {exc}"}
    _schedule_delete(path)
    public_url = (f"{SIRENE_PUBLIC_BASE_URL}/exports/{path.name}"
                  if SIRENE_PUBLIC_BASE_URL else None)
    return {
        "export_reussi": True, "format": fmt,
        "fichier_serveur": str(path), "url_telechargement": public_url,
        "lignes": len(rows), "taille_octets": path.stat().st_size,
        "expiration_secondes": TTL,
        "avertissement": (None if public_url else
                         "Définir SIRENE_PUBLIC_BASE_URL dans .env et redémarrer le service pour obtenir une URL publique."),
    }


def enregistrer_extensions(mcp, appel_sirene: Callable[[str, Optional[dict]], dict]) -> None:
    """Enregistre les outils supplémentaires sur l'instance MCP existante."""

    def collect(collection: str, q: str, limit: int = 5000, at: Optional[str] = None):
        if collection not in {"siren", "siret"}:
            return [], {"erreur": "collection doit être siren ou siret"}
        limit = min(max(int(limit), 1), 20000)
        key = "unitesLegales" if collection == "siren" else "etablissements"
        rows, cursor, seen = [], "*", set()
        total = None
        while len(rows) < limit:
            params = {"q": q, "nombre": min(1000, limit-len(rows)), "curseur": cursor}
            if at:
                params["date"] = _date(at)
            result = appel_sirene("/" + collection, params)
            if "erreur" in result:
                return rows, {"erreur": result["erreur"], "detail": result.get("detail"), "resultats_partiels": len(rows)}
            header = result.get("header") or {}
            total = header.get("total", total)
            batch = result.get(key) or []
            rows.extend(batch)
            new_cursor = header.get("curseurSuivant")
            if not batch or not new_cursor or new_cursor == cursor or new_cursor in seen:
                break
            seen.add(cursor)
            cursor = new_cursor
        return rows, {"total_api": total, "recuperes": len(rows), "complet": (total is not None and len(rows) >= int(total)), "limite": limit}

    @mcp.tool()
    def exporter_sirene_multiformat(collection: str, requete: str, format_export: str = "xlsx", champs: Optional[list[str]] = None, limite: int = 5000, date_situation: Optional[str] = None) -> dict:
        """Exporte une requête q Sirene V3.11 en CSV, Excel, ODS, Parquet ou JSONL. Le fichier temporaire local expire après 15 min."""
        rows, meta = collect(collection, requete, limite, date_situation)
        if "erreur" in meta:
            return meta
        flat = [_flatten(x) if collection == "siret" else {
            "siren": x.get("siren"), "denomination": x.get("denominationUniteLegale"),
            "etat": (x.get("periodesUniteLegale") or [{}])[0].get("etatAdministratifUniteLegale"),
            "activite": (x.get("periodesUniteLegale") or [{}])[0].get("activitePrincipaleUniteLegale"),
            "date_creation": x.get("dateCreationUniteLegale")
        } for x in rows]
        fields = champs or (list(flat[0]) if flat else [])
        result = _write(flat, format_export, fields)
        result.update(meta)
        return result

    @mcp.tool()
    def rechercher_identifiants_en_masse(identifiants: list[str], format_export: str = "xlsx", limite: int = 10000) -> dict:
        """Recherche une liste de SIREN/SIRET (maximum 10000), regroupe les données et exporte les résultats. Renvoie séparément introuvables/invalides."""
        if not identifiants or len(identifiants) > min(10000, max(1, int(limite))):
            return {"erreur": "Fournir entre 1 et 10000 identifiants (dans la limite choisie)"}
        values, bad = [], []
        for item in dict.fromkeys(str(x) for x in identifiants):
            v = re.sub(r"[ .-]", "", item)
            if len(v) not in {9, 14} or not v.isdigit():
                bad.append(item)
            else:
                values.append(v)
        found, missing, errors = [], [], []
        for v in values:
            collection = "siren" if len(v) == 9 else "siret"
            result = appel_sirene(f"/{collection}/{v}")
            obj = result.get("uniteLegale" if collection == "siren" else "etablissement")
            if obj:
                if collection == "siret":
                    found.append(_flatten(obj))
                else:
                    p = (obj.get("periodesUniteLegale") or [{}])[0]
                    found.append({"siren": v, "siret": None, "nic": None, "denomination": obj.get("denominationUniteLegale"), "activite": p.get("activitePrincipaleUniteLegale"), "etat": p.get("etatAdministratifUniteLegale"), "siege": None, "statut_diffusion": obj.get("statutDiffusionUniteLegale"), "adresse": None, "code_postal": None, "commune": None, "code_commune": None})
            elif "erreur" in result and "404" not in str(result.get("erreur")):
                errors.append({"identifiant": v, "erreur": result["erreur"]})
            else:
                missing.append(v)
        export = _write(found, format_export, MASS_EXPORT_FIELDS) if found else {"export_reussi": False, "raison": "Aucun résultat"}
        return {"demandes_uniques": len(values), "trouves": len(found), "introuvables": missing, "invalides": bad, "erreurs_api": errors[:50], **export}

    @mcp.tool()
    def statistiques_sirene(collection: str, requete: str, regrouper_par: str = "activite", limite: int = 5000, top: int = 50, date_situation: Optional[str] = None) -> dict:
        """Agrège les résultats par activité, état, commune, statut de diffusion, siège, catégorie juridique (unités légales) et effectif."""
        rows, meta = collect(collection, requete, limite, date_situation)
        if "erreur" in meta:
            return meta
        paths = {
            "activite": "activitePrincipale", "etat": "etatAdministratif", "effectif": "trancheEffectifs", "categorie_juridique": "categorieJuridiqueUniteLegale",
            "commune": "codeCommuneEtablissement", "statut_diffusion": "statutDiffusion", "siege": "etablissementSiege"}
        if regrouper_par not in paths:
            return {"erreur": "Regroupement inconnu", "options": list(paths)}
        counter = Counter()
        for obj in rows:
            period = (obj.get("periodesEtablissement") or [{}])[0] if collection == "siret" else (obj.get("periodesUniteLegale") or [{}])[0]
            if regrouper_par in {"activite", "etat"}:
                suffix = "Etablissement" if collection == "siret" else "UniteLegale"
                value = period.get(paths[regrouper_par] + suffix)
            elif regrouper_par == "commune":
                value = (obj.get("adresseEtablissement") or {}).get("codeCommuneEtablissement")
            elif regrouper_par == "effectif":
                value = obj.get("trancheEffectifsEtablissement" if collection == "siret" else "trancheEffectifsUniteLegale")
            elif regrouper_par == "categorie_juridique":
                value = period.get("categorieJuridiqueUniteLegale") if collection == "siren" else None
            else:
                key = "statutDiffusion" + ("Etablissement" if collection == "siret" else "UniteLegale") if regrouper_par == "statut_diffusion" else paths[regrouper_par]
                value = obj.get(key)
            counter[str(value) if value is not None else "NON_RENSEIGNE"] += 1
        return {**meta, "regroupement": regrouper_par, "groupes": [{"valeur": k, "nombre": v, "pourcentage_echantillon": round(v * 100 / len(rows), 2) if rows else 0} for k, v in counter.most_common(max(1, min(top, 500)))], "avertissement": "Pourcentages calculés sur les fiches récupérées ; ce n'est pas exhaustif si complet=false."}

    @mcp.tool()
    def comparer_situations_sirene(collection: str, requete: str, date_debut: str, date_fin: str, limite: int = 5000) -> dict:
        """Compare les résultats de la MÊME requête à deux dates avec l'API V3.11; identifie entrants, sortants et états modifiés. Les changements portent sur la population filtrée."""
        d1, d2 = _date(date_debut), _date(date_fin)
        if d1 > d2:
            return {"erreur": "date_debut doit précéder date_fin"}
        a, meta_a = collect(collection, requete, limite, d1)
        b, meta_b = collect(collection, requete, limite, d2)
        if "erreur" in meta_a or "erreur" in meta_b:
            return {"erreur": "Comparaison incomplète", "debut": meta_a, "fin": meta_b}
        if not meta_a["complet"] or not meta_b["complet"]:
            return {"erreur": "Résultats tronqués : comparaison non fiable. Augmenter limite ou réduire les critères.", "debut": meta_a, "fin": meta_b}
        field = "siren" if collection == "siren" else "siret"
        aa, bb = {x[field]: x for x in a}, {x[field]: x for x in b}
        entrants = sorted(bb.keys() - aa.keys())
        sortants = sorted(aa.keys() - bb.keys())
        changes = []
        for k in aa.keys() & bb.keys():
            pa = _period_at(aa[k].get("periodesUniteLegale" if collection == "siren" else "periodesEtablissement") or [], d1)
            pb = _period_at(bb[k].get("periodesUniteLegale" if collection == "siren" else "periodesEtablissement") or [], d2)
            if pa != pb:
                differences = {key: {"debut": pa.get(key), "fin": pb.get(key)} for key in pa.keys() | pb.keys() if pa.get(key) != pb.get(key)}
                if differences:
                    changes.append({field: k, "changements": differences})
        return {"requete": requete, "dates": [d1, d2], "total_debut": len(a), "total_fin": len(b), "entrants": entrants[:500], "sortants": sortants[:500], "changements": changes[:200], "nombres": {"entrants": len(entrants), "sortants": len(sortants), "changements": len(changes)}, "listes_tronquees": len(entrants)>500 or len(sortants)>500 or len(changes)>200,
                "precision": "Entrées/sorties de la population définie par q, pas nécessairement des créations/cessations juridiques."}

    @mcp.tool()
    def explorer_chaine_succession(siret: str, profondeur: int = 3, maximum_liens: int = 200) -> dict:
        """Explore les liens de succession V3.11 dans les deux sens, avec détection de cycles. Pour un lien direct, utiliser l'outil existant liens_succession."""
        start = _norm(siret, 14)
        depth = max(1, min(5, int(profondeur)))
        maximum_liens = max(1, min(1000, int(maximum_liens)))
        frontier, seen, links, errors = {start}, {start}, {}, []
        for step in range(depth):
            nxt = set()
            for current in frontier:
                for key in ("siretEtablissementPredecesseur", "siretEtablissementSuccesseur"):
                    result = appel_sirene("/siret/liensSuccession", {"q": f"{key}:{current}", "nombre": 1000})
                    if "erreur" in result:
                        errors.append({"siret": current, "erreur": result["erreur"]})
                        continue
                    for lien in result.get("liensSuccession") or []:
                        p = lien.get("siretEtablissementPredecesseur")
                        s = lien.get("siretEtablissementSuccesseur")
                        if not p or not s:
                            continue
                        links[(p,s)] = {"predecesseur":p, "successeur":s, "date":lien.get("dateLienSuccession"), "continuite_economique":lien.get("continuiteEconomique"), "transfert_siege":lien.get("transfertSiege")}
                        for node in (p,s):
                            if node not in seen:
                                nxt.add(node)
                        if len(links) >= maximum_liens:
                            break
                    if len(links) >= maximum_liens:
                        break
                if len(links) >= maximum_liens:
                    break
            seen.update(nxt)
            frontier = nxt
            if not frontier or len(links) >= maximum_liens:
                break
        return {"siret":start, "etablissements":sorted(seen), "liens":list(links.values()), "nombre_liens":len(links), "plafond_atteint":len(links)>=maximum_liens, "profondeur_max":depth, "erreurs":errors[:30], "avertissement":"Une réponse API plafonnée à 1000 liens par recherche peut nécessiter une pagination pour les cas volumineux."}


enregistrer_extensions(mcp, appel_sirene)


async def _telecharger_export(request):
    """Téléchargement d'un export temporaire par nom imprévisible (jeton 128 bits)."""
    filename = request.path_params["filename"]
    # Empêche la traversée de répertoire et les chemins forgés.
    if not re.fullmatch(r"sirene_[0-9a-f]{32}\.(?:csv|xlsx|ods|parquet|jsonl)", filename):
        return JSONResponse({"erreur": "Fichier introuvable"}, status_code=404)
    path = EXPORT_DIR_EXT / filename
    try:
        info = path.stat()
        if not path.is_file():
            return JSONResponse({"erreur": "Fichier introuvable"}, status_code=404)
        if time.time() - info.st_mtime >= TTL:
            path.unlink(missing_ok=True)
            return JSONResponse({"erreur": "Fichier expiré"}, status_code=410)
    except OSError:
        return JSONResponse({"erreur": "Fichier introuvable ou expiré"}, status_code=404)
    return FileResponse(path, filename=filename, media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@asynccontextmanager
async def _lifespan_sirene(app):
    _clear_old()
    async with mcp.session_manager.run():
        yield


# Conserve le endpoint MCP d'origine /mcp ; ajoute seulement /exports/{filename}.
# Mount('/') doit rester le dernier chemin (sinon il intercepte les téléchargements).
app = Starlette(
    routes=[
        Route("/exports/{filename}", _telecharger_export, methods=["GET"]),
        Mount("/", app=mcp.streamable_http_app(
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[
                    "sirenev3.liminalab.fr",
                    "sirenev3.liminalab.fr:*",
                    "localhost",
                    "localhost:*",
                    "127.0.0.1",
                    "127.0.0.1:*",
                ],
                allowed_origins=[
                    "https://chatgpt.com",
                    "https://claude.ai",
                    "https://mistral.ai",
                    "https://sirenev3.liminalab.fr",
                ],
            ),
        )),
    ],
    lifespan=_lifespan_sirene,
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

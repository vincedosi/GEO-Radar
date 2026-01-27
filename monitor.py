import gspread
import json
import os
import time
import re
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import requests

# --- 1. GESTION DES SECRETS (Compatible GitHub & Streamlit) ---
def get_secret(key):
    """Récupère un secret depuis les variables d'environnement ou Streamlit."""
    # Priorité 1 : Variable d'environnement (GitHub Actions)
    if key in os.environ:
        return os.environ[key]
    # Priorité 2 : Streamlit Secrets
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except:
        pass
    return None

# --- 2. CONNEXION GOOGLE ---
def connect_sheets():
    """Établit la connexion avec Google Sheets via OAuth2."""
    raw = get_secret("GOOGLE_JSON_KEY")
    if not raw:
        raise ValueError("❌ Secret GOOGLE_JSON_KEY introuvable.")

    if isinstance(raw, str):
        try:
            clean_json = raw.strip().strip("'").strip('"')
            creds_dict = json.loads(clean_json)
        except json.JSONDecodeError:
            raise ValueError("❌ Le format du JSON Google Key est invalide.")
    else:
        creds_dict = raw

    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope))

# --- 3. FONCTIONS IA ---
def ask_ai(engine, query):
    """Interroge un moteur IA (Perplexity ou Gemini) avec une requête."""
    prompt = f"""Tu es un assistant qui répond aux questions des utilisateurs.
Réponds à cette question de manière détaillée et cite tes sources : {query}

À la fin de ta réponse, ajoute une ligne séparée avec :
SOURCES: [liste des domaines/sites que tu as utilisés, séparés par des virgules]"""

    try:
        if engine == "perplexity":
            key = get_secret('PERPLEXITY_API_KEY')
            if not key:
                return {"text": "Erreur: Clé API manquante", "error": True}
            r = requests.post(
                "https://api.perplexity.ai/chat/completions",
                json={"model": "sonar", "messages": [{"role": "user", "content": prompt}]},
                headers={"Authorization": f"Bearer {key}"},
                timeout=60
            )
            if r.status_code == 200:
                return {"text": r.json()['choices'][0]['message']['content'], "error": False}
            return {"text": f"Erreur API: {r.status_code}", "error": True}

        elif engine == "gemini":
            key = get_secret('GEMINI_API_KEY')
            if not key:
                return {"text": "Erreur: Clé API manquante", "error": True}
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            if r.status_code == 200:
                return {"text": r.json()['candidates'][0]['content']['parts'][0]['text'], "error": False}
            return {"text": f"Erreur API: {r.status_code}", "error": True}

    except Exception as e:
        return {"text": f"Erreur: {e}", "error": True}

    return {"text": "Moteur inconnu", "error": True}

# --- 4. PARSING ET EXTRACTION ---
def extract_sources_from_text(text):
    """Extrait les sources/domaines mentionnés dans le texte de réponse."""
    sources = []

    # Pattern pour les URLs complètes
    url_pattern = r'https?://(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+)'
    urls = re.findall(url_pattern, text)
    sources.extend(urls)

    # Pattern pour les domaines simples (ex: exemple.com, site.fr)
    domain_pattern = r'\b([a-zA-Z0-9-]+\.(?:com|fr|org|net|gov|io|co|eu|be|ch|ca))\b'
    domains = re.findall(domain_pattern, text.lower())
    sources.extend(domains)

    # Pattern pour la ligne SOURCES: explicite
    sources_line = re.search(r'SOURCES?:\s*\[?([^\]\n]+)\]?', text, re.IGNORECASE)
    if sources_line:
        explicit_sources = [s.strip() for s in sources_line.group(1).split(',')]
        sources.extend(explicit_sources)

    # Nettoyage et déduplication
    cleaned = []
    seen = set()
    for s in sources:
        s = s.strip().lower().replace('www.', '')
        if s and len(s) > 3 and s not in seen and '.' in s:
            seen.add(s)
            cleaned.append(s)

    return cleaned[:10]  # Limite à 10 sources

def calculate_geo_score(text, url_cible, urls_partenaires, mots_signatures):
    """
    Calcule le score GEO (0-100) basé sur :
    - Mention de l'URL cible officielle : 50 points
    - Mention d'un partenaire : 20 points
    - Présence des mots signatures : jusqu'à 30 points
    """
    if not text:
        return 0

    text_lower = text.lower()
    score = 0

    # Points pour mention de l'URL cible (50 pts)
    if url_cible and url_cible.lower() in text_lower:
        score += 50

    # Points pour mention d'un partenaire (20 pts)
    for partenaire in urls_partenaires:
        if partenaire and partenaire.lower() in text_lower:
            score += 20
            break  # Un seul bonus partenaire

    # Points pour les mots signatures (jusqu'à 30 pts)
    if mots_signatures:
        keywords_found = sum(1 for mot in mots_signatures if mot.lower() in text_lower)
        keyword_score = min(30, (keywords_found / len(mots_signatures)) * 30) if mots_signatures else 0
        score += keyword_score

    return min(100, score)  # Plafonné à 100

def find_main_competitor(sources, url_cible, urls_partenaires):
    """Identifie le concurrent principal parmi les sources détectées."""
    friendly_urls = [url_cible.lower()] + [u.lower() for u in urls_partenaires if u]

    for source in sources:
        source_lower = source.lower()
        is_friendly = any(friendly in source_lower or source_lower in friendly for friendly in friendly_urls if friendly)
        if not is_friendly:
            return source

    return "N/A"

# --- 5. MAIN ---
def main():
    print("🚀 DÉMARRAGE DU SCAN GEO-Radar...")

    try:
        client = connect_sheets()
        sh = client.open("GEO-Radar_DATA")

        # Lecture de la configuration
        ws_config = sh.worksheet("CONFIG_CIBLES")
        all_values = ws_config.get_all_values()

        if not all_values:
            print("⚠️ Feuille CONFIG_CIBLES vide.")
            return

        headers = all_values[0]

        # Repérage des colonnes
        try:
            idx_client = headers.index("Client") if "Client" in headers else None
            idx_kw = headers.index("Mot_Cle")
            idx_url = headers.index("URL_Cible")
            idx_partenaires = headers.index("URLs_Partenaires") if "URLs_Partenaires" in headers else None
            idx_mots = headers.index("Mots_Signatures") if "Mots_Signatures" in headers else None
        except ValueError as e:
            print(f"❌ ERREUR : Colonne manquante - {e}")
            return

        print(f"✅ Configuration chargée. {len(all_values)-1} lignes à traiter.")

        ws_logs = sh.worksheet("LOGS_RESULTATS")

        # Traitement de chaque ligne de configuration
        for row in all_values[1:]:
            if len(row) <= idx_url:
                continue

            # Extraction des données de config
            client_name = row[idx_client] if idx_client is not None and len(row) > idx_client else "Client"
            query = row[idx_kw]
            url_cible = row[idx_url]

            urls_partenaires = []
            if idx_partenaires is not None and len(row) > idx_partenaires and row[idx_partenaires]:
                urls_partenaires = [u.strip() for u in row[idx_partenaires].split(',') if u.strip()]

            mots_signatures = []
            if idx_mots is not None and len(row) > idx_mots and row[idx_mots]:
                mots_signatures = [m.strip() for m in row[idx_mots].split(',') if m.strip()]

            if not query or not url_cible:
                continue

            print(f"🔎 Analyse: '{query}' pour {client_name}")

            # Interrogation des deux moteurs IA
            print("   ⚡ Requête Perplexity...")
            res_pplx = ask_ai("perplexity", query)
            time.sleep(2)  # Délai entre les requêtes

            print("   ♊ Requête Gemini...")
            res_gem = ask_ai("gemini", query)

            # Extraction des sources
            sources_pplx = extract_sources_from_text(res_pplx["text"]) if not res_pplx["error"] else []
            sources_gem = extract_sources_from_text(res_gem["text"]) if not res_gem["error"] else []

            # Calcul des scores GEO
            score_pplx = calculate_geo_score(res_pplx["text"], url_cible, urls_partenaires, mots_signatures) if not res_pplx["error"] else 0
            score_gem = calculate_geo_score(res_gem["text"], url_cible, urls_partenaires, mots_signatures) if not res_gem["error"] else 0
            score_global = (score_pplx + score_gem) // 2

            # Identification du concurrent principal
            all_sources = sources_pplx + sources_gem
            concurrent = find_main_competitor(all_sources, url_cible, urls_partenaires)

            # Formatage des sources pour stockage
            sources_str = f"PPLX: {', '.join(sources_pplx) if sources_pplx else 'N/A'} | GEM: {', '.join(sources_gem) if sources_gem else 'N/A'}"

            # Note de recommandation (1-5) basée sur le score global
            note_reco = min(5, max(1, score_global // 20))

            # Écriture dans les logs
            try:
                ws_logs.append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Timestamp
                    client_name,                                    # Client
                    query,                                          # Mot_Cle
                    score_global,                                   # Score_Global
                    score_pplx,                                     # Score_PPLX
                    score_gem,                                      # Score_GEM
                    note_reco,                                      # Note_Recommandation
                    sources_str,                                    # Sources_Detectees
                    concurrent,                                     # Concurrent_Principal
                    res_pplx["text"][:1500] if not res_pplx["error"] else "Erreur",  # Texte_PPLX
                    res_gem["text"][:1500] if not res_gem["error"] else "Erreur"     # Texte_GEM
                ])
                print(f"   ✅ Score: {score_global}% (PPLX: {score_pplx}%, GEM: {score_gem}%)")
            except Exception as e:
                print(f"   ❌ Erreur écriture: {e}")

            time.sleep(2)  # Délai entre les analyses

        print("🏁 Scan terminé !")

    except Exception as e:
        print(f"❌ ERREUR GENERALE : {e}")

if __name__ == "__main__":
    main()

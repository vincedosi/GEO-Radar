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
    raw = get_secret("GOOGLE_JSON_KEY")
    if not raw:
        raise ValueError("❌ Secret GOOGLE_JSON_KEY introuvable.")

    # Nettoyage si c'est une chaîne de caractères (cas GitHub)
    if isinstance(raw, str):
        try:
            # On enlève les guillemets simples/doubles au début et à la fin
            clean_json = raw.strip().strip("'").strip('"')
            creds_dict = json.loads(clean_json)
        except json.JSONDecodeError:
            # Si ça échoue, on essaie de l'utiliser tel quel (parfois Streamlit envoie déjà un dict)
            raise ValueError("❌ Le format du JSON Google Key est invalide.")
    else:
        # Cas Streamlit (déjà un dictionnaire)
        creds_dict = raw

    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope))

# --- 3. FONCTIONS IA ---
def ask_ai_advanced(engine, question, target_url):
    """Interroge les moteurs IA avec un prompt structuré pour l'analyse GEO"""
    prompt = f"""Tu es un assistant spécialisé en SEO. Réponds à cette question de manière complète et utile.

Question : {question}

À la fin de ta réponse, ajoute obligatoirement ces métadonnées sur une ligne séparée :
METADATA | SOURCES: [liste les sites web que tu cites ou recommandes, séparés par des virgules] | RECO: [note de 1 à 5 indiquant si tu recommandes {target_url}] | TOP_CONCURRENT: [le principal concurrent que tu mentionnes]

Exemple de format METADATA :
METADATA | SOURCES: site1.com, site2.fr, site3.org | RECO: 4 | TOP_CONCURRENT: concurrent.com
"""

    try:
        if engine == "perplexity":
            key = get_secret('PERPLEXITY_API_KEY')
            if not key:
                return "Erreur Perplexity: Clé API manquante", {}
            r = requests.post(
                "https://api.perplexity.ai/chat/completions",
                json={"model": "sonar", "messages": [{"role": "user", "content": prompt}]},
                headers={"Authorization": f"Bearer {key}"},
                timeout=45
            )
            if r.status_code != 200:
                return f"Erreur Perplexity: HTTP {r.status_code}", {}
            return r.json()['choices'][0]['message']['content'], {}

        elif engine == "gemini":
            key = get_secret('GEMINI_API_KEY')
            if not key:
                return "Erreur Gemini: Clé API manquante", {}
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
            r = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=45
            )
            if r.status_code != 200:
                return f"Erreur Gemini: HTTP {r.status_code}", {}
            return r.json()['candidates'][0]['content']['parts'][0]['text'], {}

    except Exception as e:
        return f"Erreur API {engine}: {e}", {}

    return "Moteur inconnu", {}


def parse_metadata(response_text):
    """Extrait les métadonnées (sources, score de recommandation, concurrent) de la réponse IA"""
    metadata = {
        "sources": [],
        "reco_score": 0,
        "top_concurrent": "N/A"
    }

    if not response_text or not isinstance(response_text, str):
        return metadata

    # Recherche de la ligne METADATA
    metadata_match = re.search(r'METADATA\s*\|\s*SOURCES:\s*\[?([^\]|]*)\]?\s*\|\s*RECO:\s*(\d)\s*\|\s*TOP_CONCURRENT:\s*\[?([^\]|\n]*)\]?', response_text, re.IGNORECASE)

    if metadata_match:
        # Sources
        sources_str = metadata_match.group(1).strip()
        if sources_str and sources_str.lower() not in ['n/a', 'aucun', 'none', '']:
            sources = [s.strip() for s in sources_str.split(',') if s.strip()]
            metadata["sources"] = sources

        # Score de recommandation
        try:
            metadata["reco_score"] = int(metadata_match.group(2))
        except ValueError:
            metadata["reco_score"] = 0

        # Top concurrent
        concurrent = metadata_match.group(3).strip()
        if concurrent and concurrent.lower() not in ['n/a', 'aucun', 'none', '']:
            metadata["top_concurrent"] = concurrent

    return metadata


def calculate_geo_score(response_text, target_url, partner_urls=None, signature_words=None):
    """
    Calcule le score de visibilité GEO (0-100) basé sur :
    - Mention du site officiel (50 pts max)
    - Mention de sites partenaires (20 pts max)
    - Présence de mots-clés signatures (30 pts max)
    """
    if not response_text or not isinstance(response_text, str):
        return 0

    score = 0
    text_lower = response_text.lower()
    target_lower = target_url.lower() if target_url else ""

    # 1. Mention du site officiel (50 points)
    if target_lower and target_lower in text_lower:
        score += 50

    # 2. Mention des partenaires (20 points max, répartis entre partenaires)
    if partner_urls:
        partner_score_per_site = 20 / len(partner_urls) if partner_urls else 0
        for partner in partner_urls:
            if partner and partner.lower() in text_lower:
                score += partner_score_per_site

    # 3. Mots-clés signatures (30 points max, répartis entre mots-clés)
    if signature_words:
        keyword_score_per_word = 30 / len(signature_words) if signature_words else 0
        for keyword in signature_words:
            if keyword and keyword.lower() in text_lower:
                score += keyword_score_per_word

    # Plafonner à 100
    return min(100, round(score))

# --- 4. MAIN (LECTURE ROBUSTE) ---
def main():
    print("🚀 DÉMARRAGE GEO-Radar Monitor V4...")

    try:
        client = connect_sheets()
        sh = client.open("GEO-Radar_DATA")

        # Lecture de la configuration depuis CONFIG_CIBLES
        ws = sh.worksheet("CONFIG_CIBLES")
        all_values = ws.get_all_values()

        if not all_values:
            print("⚠️ Feuille CONFIG_CIBLES vide.")
            return

        headers = all_values[0]

        # Repérage des colonnes
        try:
            idx_kw = headers.index("Mot_Cle")
            idx_url = headers.index("URL_Cible")
        except ValueError:
            print("❌ ERREUR : Colonnes 'Mot_Cle' ou 'URL_Cible' introuvables.")
            return

        # Colonnes optionnelles
        idx_client = headers.index("Client") if "Client" in headers else None
        idx_partners = headers.index("URLs_Partenaires") if "URLs_Partenaires" in headers else None
        idx_signatures = headers.index("Mots_Signatures") if "Mots_Signatures" in headers else None

        print(f"✅ Lecture OK. {len(all_values)-1} lignes de configuration trouvées.")

        # Feuille de logs
        logs_ws = sh.worksheet("LOGS_RESULTATS")

        # Boucle sur les configurations
        for row in all_values[1:]:
            if len(row) <= idx_url:
                continue

            keyword = row[idx_kw].strip()
            target_url = row[idx_url].strip()

            if not keyword or not target_url:
                continue

            # Récupération des infos optionnelles
            client_name = row[idx_client].strip() if idx_client and len(row) > idx_client else "N/A"
            partner_urls = []
            if idx_partners and len(row) > idx_partners and row[idx_partners]:
                partner_urls = [p.strip() for p in row[idx_partners].split(",") if p.strip()]
            signature_words = []
            if idx_signatures and len(row) > idx_signatures and row[idx_signatures]:
                signature_words = [s.strip() for s in row[idx_signatures].split(",") if s.strip()]

            print(f"🔎 Analyse : '{keyword}' pour {client_name}")

            # --- Appel Perplexity ---
            print("   ⚡ Interrogation Perplexity...")
            response_pplx, _ = ask_ai_advanced("perplexity", keyword, target_url)
            metadata_pplx = parse_metadata(response_pplx)
            score_pplx = calculate_geo_score(response_pplx, target_url, partner_urls, signature_words)

            time.sleep(2)  # Délai entre les requêtes

            # --- Appel Gemini ---
            print("   ♊ Interrogation Gemini...")
            response_gem, _ = ask_ai_advanced("gemini", keyword, target_url)
            metadata_gem = parse_metadata(response_gem)
            score_gem = calculate_geo_score(response_gem, target_url, partner_urls, signature_words)

            # --- Calcul du score global ---
            score_global = round((score_pplx + score_gem) / 2)

            # --- Formatage des sources détectées ---
            sources_pplx_str = ", ".join(metadata_pplx["sources"]) if metadata_pplx["sources"] else "N/A"
            sources_gem_str = ", ".join(metadata_gem["sources"]) if metadata_gem["sources"] else "N/A"
            sources_combined = f"PPLX: {sources_pplx_str} | GEM: {sources_gem_str}"

            # --- Note de recommandation (moyenne des deux) ---
            reco_pplx = metadata_pplx.get("reco_score", 0)
            reco_gem = metadata_gem.get("reco_score", 0)
            reco_count = (1 if reco_pplx > 0 else 0) + (1 if reco_gem > 0 else 0)
            note_reco = round((reco_pplx + reco_gem) / reco_count) if reco_count > 0 else 0

            # --- Concurrent principal ---
            concurrent = metadata_pplx.get("top_concurrent", "N/A")
            if concurrent == "N/A":
                concurrent = metadata_gem.get("top_concurrent", "N/A")

            # --- Écriture dans LOGS_RESULTATS ---
            # Colonnes attendues par app.py :
            # Timestamp, Client, Mot_Cle, Score_Global, Score_PPLX, Score_GEM,
            # Note_Recommandation, Sources_Detectees, Concurrent_Principal,
            # Texte_PPLX, Texte_GEM
            try:
                log_row = [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Timestamp
                    client_name,                                    # Client
                    keyword,                                        # Mot_Cle
                    score_global,                                   # Score_Global
                    score_pplx,                                     # Score_PPLX
                    score_gem,                                      # Score_GEM
                    note_reco,                                      # Note_Recommandation
                    sources_combined,                               # Sources_Detectees
                    concurrent,                                     # Concurrent_Principal
                    response_pplx[:5000] if response_pplx else "",  # Texte_PPLX (limité)
                    response_gem[:5000] if response_gem else ""     # Texte_GEM (limité)
                ]
                logs_ws.append_row(log_row)
                print(f"   ✅ Score GEO: {score_global}% (PPLX: {score_pplx}%, GEM: {score_gem}%)")
            except Exception as e:
                print(f"   ❌ Erreur écriture log: {e}")

            time.sleep(2)  # Délai entre les requêtes

        print("🏁 Scan terminé avec succès !")

    except Exception as e:
        print(f"❌ ERREUR GENERALE : {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

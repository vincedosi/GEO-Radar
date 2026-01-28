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
    """Récupère un secret depuis les variables d'environnement ou Streamlit"""
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
    """Connexion à Google Sheets avec gestion robuste des credentials"""
    raw = get_secret("GOOGLE_JSON_KEY")
    if not raw:
        raise ValueError("❌ Secret GOOGLE_JSON_KEY introuvable.")

    # Nettoyage si c'est une chaîne de caractères (cas GitHub)
    if isinstance(raw, str):
        try:
            clean_json = raw.strip().strip("'").strip('"')
            creds_dict = json.loads(clean_json)
        except json.JSONDecodeError:
            raise ValueError("❌ Le format du JSON Google Key est invalide.")
    else:
        # Cas Streamlit (déjà un dictionnaire)
        creds_dict = dict(raw)

    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope))

# --- 3. FONCTIONS IA ---
def ask_perplexity(query, target):
    """Interroge l'API Perplexity"""
    key = get_secret('PERPLEXITY_API_KEY')
    if not key:
        return {"error": "Clé PERPLEXITY_API_KEY manquante", "text": "", "sources": []}

    prompt = f"""Tu es un expert SEO. Réponds à la question suivante de manière détaillée et cite tes sources.

Question: {query}

À la fin de ta réponse, ajoute une ligne avec le format suivant:
SOURCES: [liste des domaines sources séparés par des virgules]
RECOMMANDATION: [note de 1 à 5 sur la pertinence de {target} pour cette requête]
CONCURRENT: [domaine du concurrent principal mentionné]"""

    try:
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            json={"model": "sonar", "messages": [{"role": "user", "content": prompt}]},
            headers={"Authorization": f"Bearer {key}"},
            timeout=60
        )
        r.raise_for_status()
        text = r.json()['choices'][0]['message']['content']
        sources = extract_sources(text)
        return {"text": text, "sources": sources, "error": None}
    except Exception as e:
        return {"error": str(e), "text": "", "sources": []}

def ask_gemini(query, target):
    """Interroge l'API Google Gemini"""
    key = get_secret('GEMINI_API_KEY')
    if not key:
        return {"error": "Clé GEMINI_API_KEY manquante", "text": "", "sources": []}

    prompt = f"""Tu es un expert SEO. Réponds à la question suivante de manière détaillée et cite tes sources.

Question: {query}

À la fin de ta réponse, ajoute une ligne avec le format suivant:
SOURCES: [liste des domaines sources séparés par des virgules]
RECOMMANDATION: [note de 1 à 5 sur la pertinence de {target} pour cette requête]
CONCURRENT: [domaine du concurrent principal mentionné]"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
        r = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60
        )
        r.raise_for_status()
        text = r.json()['candidates'][0]['content']['parts'][0]['text']
        sources = extract_sources(text)
        return {"text": text, "sources": sources, "error": None}
    except Exception as e:
        return {"error": str(e), "text": "", "sources": []}

def ask_chatgpt(query, target):
    """Interroge l'API OpenAI ChatGPT"""
    key = get_secret('OPENAI_API_KEY')
    if not key:
        return {"error": "Clé OPENAI_API_KEY manquante", "text": "", "sources": []}

    prompt = f"""Tu es un expert SEO. Réponds à la question suivante de manière détaillée et cite tes sources.

Question: {query}

À la fin de ta réponse, ajoute une ligne avec le format suivant:
SOURCES: [liste des domaines sources séparés par des virgules]
RECOMMANDATION: [note de 1 à 5 sur la pertinence de {target} pour cette requête]
CONCURRENT: [domaine du concurrent principal mentionné]"""

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]},
            headers={"Authorization": f"Bearer {key}"},
            timeout=60
        )
        r.raise_for_status()
        text = r.json()['choices'][0]['message']['content']
        sources = extract_sources(text)
        return {"text": text, "sources": sources, "error": None}
    except Exception as e:
        return {"error": str(e), "text": "", "sources": []}

# --- 4. EXTRACTION ET CALCUL ---
def extract_sources(text):
    """Extrait les sources mentionnées dans la réponse"""
    sources = []
    # Cherche les URLs
    url_pattern = r'https?://(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+)'
    urls = re.findall(url_pattern, text)
    sources.extend(urls)

    # Cherche la ligne SOURCES:
    sources_match = re.search(r'SOURCES?:\s*\[?([^\]\n]+)\]?', text, re.IGNORECASE)
    if sources_match:
        raw_sources = sources_match.group(1)
        for src in raw_sources.split(','):
            src = src.strip().strip('"\'')
            if src and src not in sources:
                sources.append(src)

    return list(set(sources))[:10]  # Max 10 sources uniques

def extract_recommendation(text):
    """Extrait la note de recommandation (1-5)"""
    match = re.search(r'RECOMMANDATION:\s*(\d)', text, re.IGNORECASE)
    if match:
        return min(5, max(1, int(match.group(1))))
    return 3  # Valeur par défaut

def extract_competitor(text):
    """Extrait le concurrent principal mentionné"""
    match = re.search(r'CONCURRENT:\s*\[?([^\]\n,]+)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"\'')
    return "N/A"

def calculate_geo_score(text, target, partners=None, keywords=None):
    """
    Calcule le score GEO (0-100) basé sur:
    - Mention du site cible (50 pts)
    - Mention des partenaires (20 pts)
    - Présence des mots-clés signature (30 pts)
    """
    if not text:
        return 0

    text_lower = text.lower()
    score = 0

    # Score pour mention du site cible
    target_domain = target.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0].lower()
    if target_domain in text_lower:
        score += 50

    # Score pour partenaires
    if partners:
        for partner in partners:
            partner_clean = partner.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0].lower()
            if partner_clean in text_lower:
                score += 10
                break  # Max 20 pts pour partenaires (on pourrait additionner)

    # Score pour mots-clés signature
    if keywords:
        kw_score = 0
        for kw in keywords:
            if kw.lower() in text_lower:
                kw_score += 10
        score += min(30, kw_score)  # Max 30 pts pour les mots-clés

    return min(100, score)

# --- 5. MAIN ---
def main():
    print("🚀 DÉMARRAGE GEO-RADAR MONITOR (V4 - Multi-moteurs)...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        client = connect_sheets()
        sh = client.open("GEO-Radar_DATA")
        print("✅ Connexion Google Sheets OK")

        # Lecture de la configuration
        ws_config = sh.worksheet("CONFIG_CIBLES")
        all_values = ws_config.get_all_values()

        if not all_values or len(all_values) < 2:
            print("⚠️ Feuille CONFIG_CIBLES vide ou sans données.")
            return

        headers = all_values[0]

        # Mapping des colonnes
        try:
            idx_kw = headers.index("Mot_Cle")
            idx_url = headers.index("URL_Cible")
        except ValueError:
            print("❌ ERREUR : Colonnes 'Mot_Cle' ou 'URL_Cible' introuvables.")
            return

        # Colonnes optionnelles
        idx_partners = headers.index("URLs_Partenaires") if "URLs_Partenaires" in headers else None
        idx_keywords = headers.index("Mots_Signatures") if "Mots_Signatures" in headers else None
        idx_client = headers.index("Client") if "Client" in headers else None

        print(f"✅ Configuration chargée. {len(all_values)-1} requêtes à analyser.")

        # Feuille de résultats
        ws_logs = sh.worksheet("LOGS_RESULTATS")

        # Vérification/création des en-têtes
        expected_headers = [
            "Date", "Client", "Mot_Cle", "URL_Cible",
            "Score_Global", "Score_PPLX", "Score_GEM", "Score_GPT",
            "Texte_PPLX", "Texte_GEM", "Texte_GPT",
            "Sources_Detectees", "Note_Recommandation", "Concurrent_Principal"
        ]

        existing_headers = ws_logs.row_values(1) if ws_logs.row_count > 0 else []
        if not existing_headers or existing_headers != expected_headers:
            print("📝 Mise à jour des en-têtes LOGS_RESULTATS...")
            ws_logs.update('A1', [expected_headers])

        # Boucle sur les requêtes
        for row in all_values[1:]:
            if len(row) <= idx_url:
                continue

            query = row[idx_kw].strip()
            target = row[idx_url].strip()

            if not query or not target:
                continue

            # Données optionnelles
            client_name = row[idx_client].strip() if idx_client and len(row) > idx_client else "Default"
            partners = row[idx_partners].split(',') if idx_partners and len(row) > idx_partners else []
            partners = [p.strip() for p in partners if p.strip()]
            keywords = row[idx_keywords].split(',') if idx_keywords and len(row) > idx_keywords else []
            keywords = [k.strip() for k in keywords if k.strip()]

            print(f"\n🔎 Analyse: {query}")
            print(f"   Client: {client_name} | Cible: {target}")

            # Interrogation des 3 moteurs IA
            print("   ⚡ Interrogation Perplexity...")
            res_pplx = ask_perplexity(query, target)
            time.sleep(2)

            print("   ♊ Interrogation Gemini...")
            res_gem = ask_gemini(query, target)
            time.sleep(2)

            print("   🤖 Interrogation ChatGPT...")
            res_gpt = ask_chatgpt(query, target)
            time.sleep(2)

            # Calcul des scores
            score_pplx = calculate_geo_score(res_pplx['text'], target, partners, keywords)
            score_gem = calculate_geo_score(res_gem['text'], target, partners, keywords)
            score_gpt = calculate_geo_score(res_gpt['text'], target, partners, keywords)
            score_global = round((score_pplx + score_gem + score_gpt) / 3)

            # Extraction des métadonnées
            all_sources = res_pplx['sources'] + res_gem['sources'] + res_gpt['sources']
            sources_str = f"PPLX:{','.join(res_pplx['sources'][:5])}|GEM:{','.join(res_gem['sources'][:5])}|GPT:{','.join(res_gpt['sources'][:5])}"

            # Note de recommandation (moyenne des 3)
            reco_pplx = extract_recommendation(res_pplx['text'])
            reco_gem = extract_recommendation(res_gem['text'])
            reco_gpt = extract_recommendation(res_gpt['text'])
            avg_reco = round((reco_pplx + reco_gem + reco_gpt) / 3)

            # Concurrent principal
            competitor = extract_competitor(res_pplx['text']) or extract_competitor(res_gem['text']) or extract_competitor(res_gpt['text'])

            print(f"   📊 Scores: PPLX={score_pplx}% | GEM={score_gem}% | GPT={score_gpt}% | Global={score_global}%")

            # Écriture dans les logs
            row_data = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                client_name,
                query,
                target,
                score_global,
                score_pplx,
                score_gem,
                score_gpt,
                res_pplx['text'][:5000] if res_pplx['text'] else (res_pplx.get('error', '')),
                res_gem['text'][:5000] if res_gem['text'] else (res_gem.get('error', '')),
                res_gpt['text'][:5000] if res_gpt['text'] else (res_gpt.get('error', '')),
                sources_str,
                avg_reco,
                competitor
            ]

            try:
                ws_logs.append_row(row_data, value_input_option='USER_ENTERED')
                print("   ✅ Résultats sauvegardés")
            except Exception as e:
                print(f"   ❌ Erreur écriture: {e}")

            # Pause entre les requêtes
            time.sleep(3)

        print("\n✅ SCAN TERMINÉ")

    except Exception as e:
        print(f"❌ ERREUR GÉNÉRALE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

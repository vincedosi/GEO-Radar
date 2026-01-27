import gspread
import json
import os
import time
import re
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import requests

# Helper pour récupérer les secrets (env vars ou st.secrets)
def get_secret(key):
    # D'abord essayer les variables d'environnement (GitHub Actions)
    value = os.environ.get(key)
    if value:
        return value
    # Sinon essayer st.secrets (Streamlit Cloud)
    try:
        import streamlit as st
        return st.secrets[key]
    except:
        return None

# 1. CONNEXION GOOGLE SHEETS
def connect_sheets():
    creds_dict = json.loads(get_secret("GOOGLE_JSON_KEY"))
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# 2. IA : EXTRACTION AVANCÉE
def ask_ai_advanced(engine, question, url_cible):
    prompt = f"""
    Réponds à cette question : "{question}".

    APRES ta réponse, ajoute une section "METADATA" avec ce format exact :
    SOURCES: [liste des domaines des sites consultés]
    RECO: [note de 1 à 5 sur la force de recommandation de {url_cible}]
    TOP_CONCURRENT: [le domaine du site le plus cité à part {url_cible}]
    """

    if engine == "perplexity":
        api_key = get_secret('PERPLEXITY_API_KEY')
        if not api_key:
            return "Erreur Perplexity: clé API manquante"
        url = "https://api.perplexity.ai/chat/completions"
        payload = {
            "model": "sonar",
            "messages": [{"role": "system", "content": "Tu es un auditeur SEO."}, {"role": "user", "content": prompt}]
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            res.raise_for_status()
            return res.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"Erreur Perplexity: {str(e)}"

    elif engine == "gemini":
        api_key = get_secret("GEMINI_API_KEY")
        if not api_key:
            return "Erreur Gemini: clé API manquante"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        headers = {"Content-Type": "application/json"}
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            res.raise_for_status()
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            return f"Erreur Gemini: {str(e)}"

    elif engine == "chatgpt":
        api_key = get_secret("OPENAI_API_KEY")
        if not api_key:
            return "Erreur ChatGPT: clé API manquante"
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": "Tu es un auditeur SEO."}, {"role": "user", "content": prompt}]
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            res.raise_for_status()
            return res.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"Erreur ChatGPT: {str(e)}"

    return "Erreur: moteur inconnu"

# 3. PARSING DES METADATA
def parse_metadata(text):
    try:
        sources = re.findall(r"SOURCES:\s*\[(.*?)\]", text)
        reco = re.findall(r"RECO:\s*(\d)", text)
        concurrent = re.findall(r"TOP_CONCURRENT:\s*\[?(.*?)\]?$", text, re.MULTILINE)

        return {
            "sources": sources[0] if sources else "N/A",
            "reco": reco[0] if reco else "1",
            "concurrent": concurrent[0].strip("[] ") if concurrent else "N/A"
        }
    except:
        return {"sources": "N/A", "reco": "1", "concurrent": "N/A"}

# 4. SCORE & ANALYSE
def calculate_geo_score(answer, url_cible, partenaires, mots_signatures):
    score = 0
    details = []
    target = url_cible.replace("https://", "").replace("www.", "").strip("/")

    # Vérifier si la réponse est une erreur
    if answer.startswith("Erreur"):
        return 0, "ERREUR"

    if target.lower() in answer.lower():
        score += 50
        details.append("OFFICIEL")

    for p in partenaires:
        p_clean = p.strip().lower().replace("https://", "").replace("www.", "")
        if p_clean and p_clean in answer.lower():
            if score < 50: score += 20; details.append(f"PARTENAIRE({p_clean})")
            break

    found = sum(1 for m in mots_signatures if m.strip().lower() in answer.lower())
    sem_score = min(found * 10, 30)
    if sem_score > 0:
        score += sem_score; details.append(f"SEM(+{sem_score})")

    return min(score, 100), " | ".join(details)

# 5. MAIN
def main():
    print("🛰️ GEO-Radar Monitor")
    print("Surveillance en cours...")

    client = connect_sheets()
    sh = client.open("GEO-Radar_DATA")
    config_data = sh.worksheet("CONFIG_CIBLES").get_all_records()
    log_ws = sh.worksheet("LOGS_RESULTATS")

    for row in config_data:
        q = row['Mot_Cle']
        target = row['URL_Cible']

        print(f"🔍 Analyse: {q}")

        # Requêtes aux 3 moteurs IA
        ans_pplx = ask_ai_advanced("perplexity", q, target)
        ans_gem = ask_ai_advanced("gemini", q, target)
        ans_gpt = ask_ai_advanced("chatgpt", q, target)

        # Parsing des métadonnées
        meta_p = parse_metadata(ans_pplx)
        meta_g = parse_metadata(ans_gem)
        meta_gpt = parse_metadata(ans_gpt)

        # Calcul des scores
        s_pplx, d_pplx = calculate_geo_score(ans_pplx, target, str(row['URLs_Partenaires']).split(','), str(row['Mots_Signatures']).split(','))
        s_gem, d_gem = calculate_geo_score(ans_gem, target, str(row['URLs_Partenaires']).split(','), str(row['Mots_Signatures']).split(','))
        s_gpt, d_gpt = calculate_geo_score(ans_gpt, target, str(row['URLs_Partenaires']).split(','), str(row['Mots_Signatures']).split(','))

        # Score global (moyenne des 3)
        scores_valides = [s for s in [s_pplx, s_gem, s_gpt] if s > 0]
        score_global = sum(scores_valides) / len(scores_valides) if scores_valides else 0

        log_ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            row['Client'], q, score_global, s_pplx, s_gem, s_gpt,
            f"PPLX: {d_pplx} / GEM: {d_gem} / GPT: {d_gpt}",
            ans_pplx, ans_gem, ans_gpt,
            f"PPLX: {meta_p['sources']} | GEM: {meta_g['sources']} | GPT: {meta_gpt['sources']}",
            max(int(meta_p['reco']), int(meta_g['reco']), int(meta_gpt['reco'])),
            meta_p['concurrent'] if s_pplx < 50 else meta_g['concurrent'] if s_gem < 50 else "N/A"
        ])
        print(f"✅ Scan fini pour : {q}")
        time.sleep(2)

    print("🎉 Tous les scans sont terminés!")

if __name__ == "__main__":
    main()

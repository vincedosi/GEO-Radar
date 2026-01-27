import gspread
import json
import os
import time
import re
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import requests

# --- 1. RÉCUPÉRATION SÉCURISÉE DES SECRETS ---
def get_secret(key):
    # 1. Vérifier les variables d'environnement (GitHub Actions / Local)
    value = os.environ.get(key)
    if value:
        return value
    # 2. Vérifier Streamlit Secrets
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except (ImportError, Exception):
        pass
    return None

def connect_sheets():
    raw_creds = get_secret("GOOGLE_JSON_KEY")
    if not raw_creds:
        raise ValueError("ERREUR: Le secret GOOGLE_JSON_KEY est introuvable.")

    # Correction : On ne JSON.LOAD que si c'est du texte (GitHub Actions)
    # Si c'est déjà un dictionnaire (Streamlit), on l'utilise tel quel
    if isinstance(raw_creds, str):
        try:
            clean_creds = raw_creds.strip().strip("'").strip('"')
            creds_dict = json.loads(clean_creds)
        except json.JSONDecodeError as e:
            print(f"❌ Erreur critique format JSON : {e}")
            raise
    else:
        creds_dict = raw_creds

    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- 2. IA : MOTEURS DE RÉPONSE ---
def ask_ai_advanced(engine, question, url_cible):
    prompt = f"""
    Réponds à cette question : "{question}".

    IMPORTANT : Après ta réponse, ajoute obligatoirement cette section exactement ainsi :
    METADATA
    SOURCES: [liste des domaines]
    RECO: [note de 1 à 5 sur la recommandation de {url_cible}]
    TOP_CONCURRENT: [domaine du concurrent principal]
    """

    if engine == "perplexity":
        api_key = get_secret('PERPLEXITY_API_KEY')
        if not api_key: return "Erreur: clé PPLX manquante"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "sonar",
            "messages": [{"role": "system", "content": "Tu es un expert SEO."}, {"role": "user", "content": prompt}]
        }
        try:
            res = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=60)
            return res.json()['choices'][0]['message']['content']
        except Exception as e: return f"Erreur Perplexity: {str(e)}"

    elif engine == "gemini":
        api_key = get_secret("GEMINI_API_KEY")
        if not api_key: return "Erreur: clé Gemini manquante"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            res = requests.post(url, json=payload, timeout=60)
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e: return f"Erreur Gemini: {str(e)}"

    elif engine == "chatgpt":
        api_key = get_secret("OPENAI_API_KEY")
        if not api_key: return "Erreur: clé OpenAI manquante"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": "Expert SEO."}, {"role": "user", "content": prompt}]
        }
        try:
            res = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=60)
            return res.json()['choices'][0]['message']['content']
        except Exception as e: return f"Erreur ChatGPT: {str(e)}"

    return "Erreur: moteur inconnu"

# --- 3. PARSING & ANALYSE ---
def parse_metadata(text):
    try:
        sources = re.findall(r"SOURCES:\s*\[?(.*?)\]?$", text, re.MULTILINE | re.IGNORECASE)
        reco = re.findall(r"RECO:\s*(\d)", text)
        concurrent = re.findall(r"TOP_CONCURRENT:\s*\[?(.*?)\]?$", text, re.MULTILINE | re.IGNORECASE)

        return {
            "sources": sources[0].strip() if sources else "N/A",
            "reco": reco[0] if reco else "1",
            "concurrent": concurrent[0].strip() if concurrent else "N/A"
        }
    except:
        return {"sources": "N/A", "reco": "1", "concurrent": "N/A"}

def calculate_geo_score(answer, url_cible, partenaires, mots_signatures):
    if not answer or answer.startswith("Erreur"): return 0, "ERREUR"
    score = 0
    details = []
    target_clean = url_cible.lower().replace("https://", "").replace("www.", "").strip("/")

    if target_clean in answer.lower():
        score += 50
        details.append("OFFICIEL")

    for p in [p.strip().lower() for p in partenaires if p.strip()]:
        p_clean = p.replace("https://", "").replace("www.", "")
        if p_clean in answer.lower():
            if score < 50:
                score += 20
                details.append(f"PARTENAIRE({p_clean})")
            break

    found_mots = [m.strip() for m in mots_signatures if m.strip() and m.strip().lower() in answer.lower()]
    sem_score = min(len(found_mots) * 10, 30)
    if sem_score > 0:
        score += sem_score
        details.append(f"SEM(+{sem_score})")

    return min(score, 100), " | ".join(details)

# --- 4. EXECUTION ---
def main():
    print("🛰️ GEO-Radar Monitor - Démarrage")
    
    try:
        client = connect_sheets()
        sh = client.open("GEO-Radar_DATA")
        config_ws = sh.worksheet("CONFIG_CIBLES")
        log_ws = sh.worksheet("LOGS_RESULTATS")
        
        # MÉTHODE 2 : Lecture manuelle pour éviter l'erreur de colonnes en doublon
        all_rows = config_ws.get_all_values()
        if not all_rows:
            print("⚠️ Feuille CONFIG_CIBLES vide.")
            return

        headers = all_rows[0]
        config_data = []
        for row in all_rows[1:]:
            # On mappe les headers aux valeurs, en ignorant les colonnes sans nom
            record = {headers[i]: row[i] for i in range(len(headers)) if i < len(row) and headers[i].strip() != ""}
            if any(record.values()):
                config_data.append(record)
        
        print(f"✅ {len(config_data)} lignes chargées.")

    except Exception as e:
        print(f"❌ Erreur de configuration Google Sheets: {e}")
        return

    for row in config_data:
        q = row.get('Mot_Cle')
        target = row.get('URL_Cible')
        if not q or not target: continue

        print(f"🔍 Analyse : {q}")

        ans_pplx = ask_ai_advanced("perplexity", q, target)
        ans_gem = ask_ai_advanced("gemini", q, target)
        ans_gpt = ask_ai_advanced("chatgpt", q, target)

        m_p, m_g, m_gpt = parse_metadata(ans_pplx), parse_metadata(ans_gem), parse_metadata(ans_gpt)

        partenaires = str(row.get('URLs_Partenaires', "")).split(',')
        signatures = str(row.get('Mots_Signatures', "")).split(',')
        
        s_pplx, d_pplx = calculate_geo_score(ans_pplx, target, partenaires, signatures)
        s_gem, d_gem = calculate_geo_score(ans_gem, target, partenaires, signatures)
        s_gpt, d_gpt = calculate_geo_score(ans_gpt, target, partenaires, signatures)

        scores_v = [s for s in [s_pplx, s_gem, s_gpt] if s >= 0]
        score_global = sum(scores_v) / len(scores_v) if scores_v else 0

        try:
            log_ws.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                row.get('Client', 'Inconnu'), q, round(score_global, 1),
                s_pplx, s_gem, s_gpt,
                f"PPLX: {d_pplx} | GEM: {d_gem} | GPT: {d_gpt}",
                ans_pplx[:500], ans_gem[:500], ans_gpt[:500],
                f"P: {m_p['sources']} | G: {m_g['sources']} | T: {m_gpt['sources']}",
                max(int(m_p['reco']), int(m_g['reco']), int(m_gpt['reco'])),
                m_p['concurrent'] if s_pplx < 50 else "N/A"
            ])
            print(f"✅ Logged: {q} (Score: {score_global})")
        except Exception as e:
            print(f"❌ Erreur écriture Sheets: {e}")

        time.sleep(2)

    print("🎉 Terminé !")

if __name__ == "__main__":
    main()

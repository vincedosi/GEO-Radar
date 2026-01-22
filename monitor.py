import streamlit as st
import gspread
import json
import os
import time
import re
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
import requests

# 1. CONNEXION GOOGLE SHEETS
def connect_sheets():
    creds_dict = json.loads(st.secrets["GOOGLE_JSON_KEY"])
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
        url = "https://api.perplexity.ai/chat/completions"
        payload = {
            "model": "sonar",
            "messages": [{"role": "system", "content": "Tu es un auditeur SEO."}, {"role": "user", "content": prompt}]
        }
        headers = {"Authorization": f"Bearer {st.secrets['PERPLEXITY_API_KEY']}", "Content-Type": "application/json"}
        try:
            res = requests.post(url, json=payload, headers=headers).json()
            return res['choices'][0]['message']['content']
        except: return "Erreur Perplexity"
    
    else: # Gemini
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        try:
            return model.generate_content(prompt).text
        except: return "Erreur Gemini"

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
    st.title("🛰️ GEO-Radar Monitor")
    st.write("Surveillance en cours...")
    
    client = connect_sheets()
    sh = client.open("GEO-Radar_DATA")
    config_data = sh.worksheet("CONFIG_CIBLES").get_all_records()
    log_ws = sh.worksheet("LOGS_RESULTATS")
    
    for row in config_data:
        q = row['Mot_Cle']
        target = row['URL_Cible']
        
        st.write(f"🔍 Analyse: {q}")
        
        ans_pplx = ask_ai_advanced("perplexity", q, target)
        ans_gem = ask_ai_advanced("gemini", q, target)
        
        meta_p = parse_metadata(ans_pplx)
        meta_g = parse_metadata(ans_gem)
        
        s_pplx, d_pplx = calculate_geo_score(ans_pplx, target, str(row['URLs_Partenaires']).split(','), str(row['Mots_Signatures']).split(','))
        s_gem, d_gem = calculate_geo_score(ans_gem, target, str(row['URLs_Partenaires']).split(','), str(row['Mots_Signatures']).split(','))
        
        log_ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            row['Client'], q, (s_pplx + s_gem) / 2, s_pplx, s_gem,
            f"PPLX: {d_pplx} / GEM: {d_gem}",
            ans_pplx, ans_gem,
            f"PPLX: {meta_p['sources']} | GEM: {meta_g['sources']}",
            max(int(meta_p['reco']), int(meta_g['reco'])),
            meta_p['concurrent'] if s_pplx < 50 else "N/A"
        ])
        st.success(f"✅ Scan fini pour : {q}")
        time.sleep(2)

if __name__ == "__main__":
    main()

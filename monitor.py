import gspread
import json
import os
import time
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
import requests

def connect_sheets():
    creds_dict = json.loads(os.environ["GOOGLE_JSON_KEY"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def ask_perplexity(question):
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
        "model": "sonar", 
        "messages": [
            {"role": "system", "content": "Réponds de manière précise et cite les sites web utilisés."}, 
            {"role": "user", "content": question}
        ]
    }
    headers = {"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}", "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()['choices'][0]['message']['content']
    except:
        return "Erreur Perplexity"

def ask_gemini(question):
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
    try:
        response = model.generate_content(question)
        return response.text
    except:
        return "Erreur Gemini"

def calculate_geo_score(answer, url_cible, partenaires, mots_signatures):
    score = 0
    details = []
    target = url_cible.replace("https://", "").replace("www.", "").strip("/")
    
    # 1. Visibilité Directe (50 pts)
    if target.lower() in answer.lower():
        score += 50
        details.append("OFFICIEL")
    
    # 2. Partenaires (20 pts)
    for p in partenaires:
        p_clean = p.strip().lower().replace("https://", "").replace("www.", "")
        if p_clean and p_clean in answer.lower():
            if score < 50: score += 20; details.append(f"PARTENAIRE({p_clean})")
            break
        
    # 3. Sémantique (30 pts)
    found = sum(1 for m in mots_signatures if m.strip().lower() in answer.lower())
    sem_score = min(found * 10, 30)
    if sem_score > 0:
        score += sem_score; details.append(f"SEM(+{sem_score})")
    
    return min(score, 100), " | ".join(details)

def main():
    client = connect_sheets()
    sh = client.open("GEO-Radar_DATA")
    config_data = sh.worksheet("CONFIG_CIBLES").get_all_records()
    log_ws = sh.worksheet("LOGS_RESULTATS")
    
    for row in config_data:
        q = row['Mot_Cle']
        ans_pplx = ask_perplexity(q)
        ans_gem = ask_gemini(q)
        
        s_pplx, d_pplx = calculate_geo_score(ans_pplx, row['URL_Cible'], str(row['URLs_Partenaires']).split(','), str(row['Mots_Signatures']).split(','))
        s_gem, d_gem = calculate_geo_score(ans_gem, row['URL_Cible'], str(row['URLs_Partenaires']).split(','), str(row['Mots_Signatures']).split(','))
        
        # Enregistrement avec les nouvelles colonnes
        log_ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            row['Client'],
            q,
            (s_pplx + s_gem) / 2, # Global
            s_pplx,              # Score PPLX
            s_gem,               # Score GEM
            f"PPLX: {d_pplx} / GEM: {d_gem}",
            ans_pplx,            # Texte complet PPLX
            ans_gem              # Texte complet GEM
        ])
        time.sleep(2)

if __name__ == "__main__":
    main()

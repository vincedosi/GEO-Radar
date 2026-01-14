import gspread
import json
import os
import time
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
import requests

# 1. CONNEXION GOOGLE SHEETS
def connect_sheets():
    # On récupère le secret depuis GitHub Actions
    creds_dict = json.loads(os.environ["GOOGLE_JSON_KEY"])
    
    # On définit les accès (scopes)
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Connexion
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# 2. CONFIGURATION DES IA
def ask_perplexity(question):
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
        "model": "pplx-7b-online", # ou le modèle de ton choix
        "messages": [{"role": "system", "content": "Be precise and list sources."}, 
                     {"role": "user", "content": question}]
    }
    headers = {
        "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        content = res_json['choices'][0]['message']['content']
        # Simulation d'extraction de sources pour la démo
        return content, ["source_extracted_from_text"]
    except:
        return "Erreur Perplexity", []

def ask_gemini(question):
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-pro')
    try:
        response = model.generate_content(question)
        return response.text, []
    except:
        return "Erreur Gemini", []

# 3. LOGIQUE DE CALCUL DU SCORE
def calculate_geo_score(answer, sources, url_cible, partenaires, mots_signatures):
    score = 0
    details = []
    
    # Visibilité Directe (50 pts)
    if url_cible.lower() in answer.lower() or any(url_cible.lower() in s.lower() for s in sources):
        score += 50
        details.append("Site Officiel Cité (+50)")
    
    # Visibilité Indirecte (20 pts)
    elif any(p.strip().lower() in answer.lower() for p in partenaires if p.strip()):
        score += 20
        details.append("Partenaire Cité (+20)")
        
    # Sémantique (30 pts)
    for mot in mots_signatures:
        if mot.strip().lower() in answer.lower():
            score += 10 # 10 pts par mot trouvé, max 30
    
    return min(score, 100), ", ".join(details)

# 4. PROGRAMME PRINCIPAL
def main():
    print("🚀 Démarrage GEO-Radar...")
    client = connect_sheets()
    sh = client.open("GEO-Radar_DATA")
    
    # Lecture config
    config_ws = sh.worksheet("CONFIG_CIBLES")
    config_data = config_ws.get_all_records()
    
    # Préparation logs
    log_ws = sh.worksheet("LOGS_RESULTATS")
    
    for row in config_data:
        client_name = row['Client']
        query = row['Mot_Cle']
        url_cible = row['URL_Cible']
        partenaires = row['URLs_Partenaires'].split(',')
        mots_signatures = row['Mots_Signatures'].split(',')
        
        print(f"🔍 Scan pour {client_name} : {query}")
        
        # Interroger les IA
        ans_pplx, src_pplx = ask_perplexity(query)
        ans_gemini, src_gemini = ask_gemini(query)
        
        # Calcul score (Moyenne simplifiée pour l'exemple)
        score_pplx, det_pplx = calculate_geo_score(ans_pplx, src_pplx, url_cible, partenaires, mots_signatures)
        score_gem, det_gem = calculate_geo_score(ans_gemini, [], url_cible, partenaires, mots_signatures)
        
        score_global = (score_pplx + score_gem) / 2
        
        # Écriture dans Google Sheets
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_ws.append_row([
            timestamp, 
            client_name, 
            query, 
            str(src_pplx), 
            "Gemini", 
            "N/A", 
            score_global, 
            f"PPLX: {det_pplx} | GEM: {det_gem}"
        ])
        
        print(f"✅ Score : {score_global}/100")
        time.sleep(2) # Pause pour éviter les limites d'API

if __name__ == "__main__":
    main()

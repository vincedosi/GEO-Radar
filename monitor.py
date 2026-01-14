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
    creds_dict = json.loads(os.environ["GOOGLE_JSON_KEY"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# 2. CONFIGURATION DES IA
def ask_perplexity(question):
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
        "model": "sonar", 
        "messages": [
            {"role": "system", "content": "Tu es un expert en recherche. Réponds de manière détaillée et cite TOUJOURS les noms de domaines des sites sources utilisés (ex: site.com)."}, 
            {"role": "user", "content": question}
        ]
    }
    headers = {
        "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        content = response.json()['choices'][0]['message']['content']
        # On simule l'extraction de sources en récupérant le texte
        return content, [content] 
    except:
        return "Erreur Perplexity", []

def ask_gemini(question):
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
    try:
        response = model.generate_content(f"Réponds à cette question et cite tes sources : {question}")
        return response.text, [response.text]
    except:
        return "Erreur Gemini", []

# 3. LOGIQUE DE CALCUL DU SCORE (Optimisée)
def calculate_geo_score(answer, url_cible, partenaires, mots_signatures):
    score = 0
    details = []
    
    # Nettoyage URL pour match flexible
    target = url_cible.replace("https://", "").replace("http://", "").replace("www.", "").strip("/")
    
    # 1. Visibilité Directe (50 pts)
    if target.lower() in answer.lower():
        score += 50
        details.append("Site Officiel Cité")
    
    # 2. Visibilité Indirecte (20 pts)
    for p in partenaires:
        p_clean = p.strip().lower().replace("https://", "").replace("www.", "")
        if p_clean and p_clean in answer.lower():
            if score < 50: # On ne cumule pas si le site officiel est déjà là
                score += 20
                details.append(f"Partenaire ({p_clean})")
            break
        
    # 3. Sémantique (30 pts)
    found_mots = 0
    for mot in mots_signatures:
        if mot.strip().lower() in answer.lower():
            found_mots += 1
    
    sem_score = min(found_mots * 10, 30)
    if sem_score > 0:
        score += sem_score
        details.append(f"Sémantique (+{sem_score})")
    
    return min(score, 100), " | ".join(details)

# 4. PROGRAMME PRINCIPAL
def main():
    print("🚀 Démarrage GEO-Radar...")
    client = connect_sheets()
    sh = client.open("GEO-Radar_DATA")
    
    config_ws = sh.worksheet("CONFIG_CIBLES")
    config_data = config_ws.get_all_records()
    log_ws = sh.worksheet("LOGS_RESULTATS")
    
    for row in config_data:
        client_name = row['Client']
        query = row['Mot_Cle']
        url_cible = row['URL_Cible']
        partenaires = str(row['URLs_Partenaires']).split(',')
        mots_signatures = str(row['Mots_Signatures']).split(',')
        
        # Interroger les IA
        ans_pplx, _ = ask_perplexity(query)
        ans_gemini, _ = ask_gemini(query)
        
        # Calcul scores
        score_pplx, det_pplx = calculate_geo_score(ans_pplx, url_cible, partenaires, mots_signatures)
        score_gem, det_gem = calculate_geo_score(ans_gemini, url_cible, partenaires, mots_signatures)
        
        score_global = (score_pplx + score_gem) / 2
        
        # Écriture logs
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_ws.append_row([
            timestamp, client_name, query, 
            "Perplexity", "Gemini", "N/A", 
            score_global, f"PPLX: {det_pplx} | GEM: {det_gem}"
        ])
        print(f"✅ {client_name} - {query} : {score_global}/100")
        time.sleep(2)

if __name__ == "__main__":
    main()

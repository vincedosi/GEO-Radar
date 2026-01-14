import os
import json
import requests
import gspread
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from mistralai import Mistral

# CONFIGURATION
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_google_client():
    """Connexion sécurisée via la variable d'environnement JSON"""
    json_str = os.getenv("GOOGLE_JSON_KEY")
    if not json_str:
        raise ValueError("La variable GOOGLE_JSON_KEY est vide !")
    creds_dict = json.loads(json_str)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def check_perplexity(api_key, query):
    """Interroge Perplexity Sonar"""
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "sonar-pro", # Ou sonar-reasoning-pro
        "messages": [{"role": "user", "content": query}]
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        content = data['choices'][0]['message']['content']
        citations = data.get('citations', [])
        return content, citations
    except Exception as e:
        print(f"Erreur Perplexity: {e}")
        return "", []

def check_gemini(api_key, query):
    """Interroge Gemini avec Grounding"""
    genai.configure(api_key=api_key)
    tools_config = {'google_search_retrieval': {}}
    model = genai.GenerativeModel('models/gemini-1.5-pro-002') # Modèle récent
    try:
        response = model.generate_content(query, tools=tools_config)
        content = response.text
        # Extraction des sources via les métadonnées de grounding
        sources = []
        if response.candidates[0].grounding_metadata.grounding_chunks:
            for chunk in response.candidates[0].grounding_metadata.grounding_chunks:
                if chunk.web:
                    sources.append(chunk.web.uri)
        return content, sources
    except Exception as e:
        print(f"Erreur Gemini: {e}")
        return "", []

def check_mistral(api_key, query):
    """Interroge Mistral (Web Search si dispo ou Prompt Engineering)"""
    client = Mistral(api_key=api_key)
    try:
        # Note: Mistral Web Search est en beta, ici on force via prompt
        resp = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": query}]
        )
        content = resp.choices[0].message.content
        # Extraction basique des URLs dans le texte (regex simple ou via le prompt)
        import re
        urls = re.findall(r'(https?://[^\s]+)', content)
        return content, urls
    except Exception as e:
        print(f"Erreur Mistral: {e}")
        return "", []

def calculate_score(text, sources, url_cible, url_partenaires, mots_signatures):
    """Calcul du GEO Score sur 100"""
    score = 0
    details = []
    
    # 1. VISIBILITÉ (50 pts ou 20 pts)
    found_main = any(url_cible in s for s in sources)
    found_partner = any(any(p in s for s in sources) for p in url_partenaires)
    
    if found_main:
        score += 50
        details.append("Cible trouvée (+50)")
    elif found_partner:
        score += 20
        details.append("Partenaire trouvé (+20)")
    
    # 2. RANKING (30 pts) - Top 3
    # On suppose que la liste 'sources' est ordonnée
    if found_main:
        # Vérifie si l'URL cible est dans les 3 premières sources
        top_3 = sources[:3]
        if any(url_cible in s for s in top_3):
            score += 30
            details.append("Top 3 Ranking (+30)")

    # 3. SÉMANTIQUE (20 pts)
    found_keyword = any(kw.lower() in text.lower() for kw in mots_signatures)
    if found_keyword:
        score += 20
        details.append("Mot-clé signature (+20)")
        
    return score, ", ".join(details)

def main():
    print("🚀 Démarrage GEO-Radar...")
    
    # Chargement clés
    PPLX_KEY = os.getenv("PERPLEXITY_API_KEY")
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    MISTRAL_KEY = os.getenv("MISTRAL_API_KEY")
    
    # Connexion GSheet
    gc = get_google_client()
    sh = gc.open("GEO-Radar_DATA") # NOM EXACT DE TON FICHIER
    ws_config = sh.worksheet("CONFIG_CIBLES")
    ws_logs = sh.worksheet("LOGS_RESULTATS")
    
    configs = ws_config.get_all_records()
    
    new_rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for row in configs:
        client = row['Client']
        mot_cle = row['Mot_Cle']
        url_cible = row['URL_Cible']
        partners = [u.strip() for u in row['URLs_Partenaires'].split(',') if u.strip()]
        signatures = [w.strip() for w in row['Mots_Signatures'].split(',') if w.strip()]
        
        print(f"Testing: {client} - {mot_cle}...")
        
        prompt = f"Réponds à cette question en utilisant le web et liste explicitement tes sources URL : {mot_cle}"
        
        # 1. Perplexity
        txt_p, src_p = check_perplexity(PPLX_KEY, prompt)
        score_p, det_p = calculate_score(txt_p, src_p, url_cible, partners, signatures)
        
        # 2. Gemini
        txt_g, src_g = check_gemini(GEMINI_KEY, prompt)
        score_g, det_g = calculate_score(txt_g, src_g, url_cible, partners, signatures)
        
        # 3. Mistral
        txt_m, src_m = check_mistral(MISTRAL_KEY, prompt)
        score_m, det_m = calculate_score(txt_m, src_m, url_cible, partners, signatures)
        
        # Moyenne
        global_score = round((score_p + score_g + score_m) / 3, 1)
        
        new_rows.append([
            timestamp, client, mot_cle,
            "\n".join(src_p), "\n".join(src_g), "\n".join(src_m),
            global_score,
            f"PPLX:{score_p} GEM:{score_g} MIS:{score_m}"
        ])
        
    # Écriture dans le sheet
    if new_rows:
        ws_logs.append_rows(new_rows)
        print("✅ Logs mis à jour !")

if __name__ == "__main__":
    main()
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
def ask_ai(engine, q, target):
    # Prompt simplifié pour éviter les erreurs de formatage
    prompt = f"Analyse SEO pour '{q}'. Cible: {target}. Réponds puis ajoute: METADATA | SOURCES: [site1, site2] | RECO: 3 | TOP_CONCURRENT: [domaine]"
    
    try:
        if engine == "perplexity":
            key = get_secret('PERPLEXITY_API_KEY')
            if not key: return "Clé manquante"
            r = requests.post("https://api.perplexity.ai/chat/completions", 
                json={"model": "sonar", "messages": [{"role": "user", "content": prompt}]},
                headers={"Authorization": f"Bearer {key}"}, timeout=45)
            return r.json()['choices'][0]['message']['content']
            
        elif engine == "gemini":
            key = get_secret('GEMINI_API_KEY')
            if not key: return "Clé manquante"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=45)
            return r.json()['candidates'][0]['content']['parts'][0]['text']

        elif engine == "chatgpt":
            key = get_secret('OPENAI_API_KEY')
            if not key: return "Clé manquante"
            r = requests.post("https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]},
                headers={"Authorization": f"Bearer {key}"}, timeout=45)
            return r.json()['choices'][0]['message']['content']
            
    except Exception as e:
        return f"Erreur API: {e}"
    return "Moteur inconnu"

# --- 4. MAIN (LECTURE ROBUSTE) ---
def main():
    print("🚀 DÉMARRAGE VERSION CORRIGÉE (V3)...")
    
    try:
        client = connect_sheets()
        sh = client.open("GEO-Radar_DATA")
        
        # --- C'EST ICI QUE TOUT CHANGE ---
        # On n'utilise plus get_all_records(). On lit tout en brut.
        ws = sh.worksheet("CONFIG_CIBLES")
        all_values = ws.get_all_values()
        
        if not all_values:
            print("⚠️ Feuille vide.")
            return

        headers = all_values[0] # La ligne 1
        data = []
        
        # On repère les colonnes vitales
        try:
            idx_kw = headers.index("Mot_Cle")
            idx_url = headers.index("URL_Cible")
        except ValueError:
            print("❌ ERREUR : Colonnes 'Mot_Cle' ou 'URL_Cible' introuvables (Vérifiez l'orthographe exacte).")
            return

        print(f"✅ Lecture OK. {len(all_values)-1} lignes trouvées.")

        # Boucle sur les données
        for row in all_values[1:]:
            # Sécurité : si la ligne est trop courte (vide), on saute
            if len(row) <= idx_url: continue
            
            q = row[idx_kw]
            target = row[idx_url]
            
            if not q or not target: continue

            print(f"🔎 Analyse de : {q}")
            
            # Test simple avec Perplexity pour commencer
            res = ask_ai("perplexity", q, target)
            
            # Ecriture simplifiée dans les logs
            try:
                sh.worksheet("LOGS_RESULTATS").append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Test", q, "OK", res[:100] # On coupe pour pas surcharger
                ])
                print("   ✅ Sauvegardé dans LOGS_RESULTATS")
            except Exception as e:
                print(f"   ❌ Erreur écriture log: {e}")
                
            time.sleep(1)

    except Exception as e:
        print(f"❌ ERREUR GENERALE : {e}")

if __name__ == "__main__":
    main()

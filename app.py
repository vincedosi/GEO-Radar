import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
import json
import os
from google.oauth2.service_account import Credentials

# 1. CONFIG PAGE & CSS
st.set_page_config(page_title="GEO-Radar Analytics", layout="wide", page_icon="📡")

st.markdown("""
<style>
    /* Clean UI */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp {background-color: #f8f9fa;}
    
    /* Headers */
    h1, h2, h3 {font-family: 'Helvetica Neue', sans-serif; color: #0f172a;}
    
    /* Metrics */
    div[data-testid="metric-container"] {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# 2. CONNEXION DONNÉES
@st.cache_resource
def get_data():
    # Gestion Secret : Local (.toml) ou Cloud (st.secrets)
    if "GOOGLE_JSON_KEY" in st.secrets:
        creds_dict = json.loads(st.secrets["GOOGLE_JSON_KEY"])
    else:
        # Fallback pour local si pas dans toml (déconseillé mais utile pour debug)
        return pd.DataFrame()
        
    # À vérifier/modifier dans monitor.py et app.py
    scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    sh = client.open("GEO-Radar_DATA")
    ws = sh.worksheet("LOGS_RESULTATS")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    return df

try:
    df = get_data()
except Exception as e:
    st.error(f"Erreur de connexion : {e}")
    st.stop()

# 3. INTERFACE PRINCIPALE
st.title("📡 GEO-Radar | Performance Sémantique")

tab1, tab2 = st.tabs(["📊 Dashboard", "🎓 Méthodologie"])

with tab1:
    # --- SIDEBAR FILTERS ---
    st.sidebar.header("Filtres")
    
    # Cascade : Client -> Question
    clients_list = df['Client'].unique().tolist()
    selected_client = st.sidebar.selectbox("Choisir un Client", clients_list)
    
    # Filtrer les données pour ce client
    df_client = df[df['Client'] == selected_client]
    
    # Questions dispo pour ce client
    questions_list = ["🌍 VUE GLOBALE (Moyenne)"] + df_client['Mot_Cle'].unique().tolist()
    selected_question = st.sidebar.selectbox("Choisir une Question", questions_list)
    
    # Préparation données graphiques
    if selected_question == "🌍 VUE GLOBALE (Moyenne)":
        # On moyenne tous les mots clés par jour
        df_viz = df_client.groupby(df_client['Timestamp'].dt.date).agg({
            'Score_Global': 'mean'
        }).reset_index()
        df_viz.columns = ['Date', 'Score']
        chart_title = f"Visibilité Globale - {selected_client}"
    else:
        # On prend juste la question
        df_viz = df_client[df_client['Mot_Cle'] == selected_question].copy()
        df_viz['Date'] = df_viz['Timestamp'].dt.date
        df_viz = df_viz[['Date', 'Score_Global']]
        df_viz.columns = ['Date', 'Score']
        chart_title = f"Visibilité : {selected_question}"

    # --- KPIs ---
    col1, col2, col3 = st.columns(3)
    
    last_score = df_viz['Score'].iloc[-1] if not df_viz.empty else 0
    prev_score = df_viz['Score'].iloc[-2] if len(df_viz) > 1 else last_score
    delta = last_score - prev_score
    
    col1.metric("GEO Score Actuel", f"{last_score:.1f}/100", f"{delta:.1f}")
    col2.metric("Nb de Tests", len(df_client))
    col3.metric("Moteur Leader", "Perplexity") # À dynamiser plus tard

    # --- GRAPHIQUE PLOTLY ---
    st.subheader("📈 Évolution de la Visibilité")
    
    # Note: Pour un vrai détail par IA, il faudrait parser la colonne 'Details_Score'
    # Ici on affiche le Score Global pour simplifier la V1
    fig = px.line(df_viz, x='Date', y='Score', title=chart_title, markers=True)
    fig.update_layout(yaxis_range=[0, 105], template="plotly_white")
    fig.update_traces(line_color='#4F46E5', line_width=3)
    st.plotly_chart(fig, use_container_width=True)

    # --- TABLEAU RECENT ---
    st.subheader("Derniers Logs")
    st.dataframe(df_client.sort_values('Timestamp', ascending=False).head(10), use_container_width=True)

with tab2:
    st.header("Comment est calculé le Score ?")
    st.markdown("""
    Le **GEO Score** est calculé sur **100 points** pour chaque réponse d'IA.
    
    | Critère | Points | Condition |
    | :--- | :---: | :--- |
    | **Visibilité Directe** | **50 pts** | L'IA cite votre site officiel en source. |
    | *Visibilité Indirecte* | *20 pts* | L'IA cite un partenaire média (si site officiel absent). |
    | **Ranking** | **30 pts** | Votre lien apparaît dans le **TOP 3** des sources. |
    | **Sémantique** | **20 pts** | L'IA utilise vos "Mots-Clés Signatures". |
    
    Un score > **80/100** indique une domination sémantique totale (Authoritative Source).

    """)

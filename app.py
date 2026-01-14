import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
import json
import re
from google.oauth2.service_account import Credentials

# 1. CONFIGURATION & STYLE
st.set_page_config(page_title="GEO-Radar Pro", layout="wide", page_icon="📡")

st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .highlight { background-color: #fef08a; font-weight: bold; padding: 2px 4px; border-radius: 4px; }
    .reponse-ia { 
        padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; 
        background-color: white; line-height: 1.6; font-size: 14px;
        max-height: 400px; overflow-y: auto;
    }
    .reco-stars { color: #f59e0b; font-size: 20px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# 2. CHARGEMENT DES DONNÉES
@st.cache_resource(ttl=600)
def get_data():
    creds_dict = json.loads(st.secrets["GOOGLE_JSON_KEY"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("GEO-Radar_DATA")
    df = pd.DataFrame(sh.worksheet("LOGS_RESULTATS").get_all_records())
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    return df

# 3. FONCTION DE SURLIGNAGE (Le "Highlight")
def highlight_text(text, target_url, keywords):
    if not text: return ""
    # Surligner l'URL cible
    clean_target = target_url.replace("https://", "").replace("www.", "").strip("/")
    pattern = re.compile(re.escape(clean_target), re.IGNORECASE)
    text = pattern.sub(f'<span class="highlight">{clean_target}</span>', text)
    
    # Mettre en gras les mots signatures
    for kw in keywords:
        if kw.strip():
            kw_pattern = re.compile(re.escape(kw.strip()), re.IGNORECASE)
            text = kw_pattern.sub(f'**{kw.strip()}**', text)
    return text

try:
    df = get_data()
except Exception as e:
    st.error(f"Erreur : {e}"); st.stop()

# --- SIDEBAR ---
st.sidebar.title("📡 GEO-Radar Pro")
selected_client = st.sidebar.selectbox("🎯 Client", df['Client'].unique())
df_c = df[df['Client'] == selected_client].sort_values('Timestamp', ascending=False)

# --- HEADER ---
st.title(f"Audit de Visibilité IA : {selected_client}")

tab1, tab2, tab3 = st.tabs(["📈 Dashboard Stratégique", "🥊 Analyse Concurrentielle", "🔍 Explorateur de Preuves"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    avg_score = df_c['Score_Global'].mean()
    c1.metric("Score GEO Global", f"{avg_score:.1f}%")
    
    # Calcul de la recommandation moyenne
    reco_avg = df_c['Note_Recommandation'].astype(int).mean()
    stars = "⭐" * int(reco_avg)
    c2.markdown(f"<div class='stMetric'><b>Recommandation</b><br><span class='reco-stars'>{stars}</span></div>", unsafe_allow_html=True)
    
    c3.metric("Moteur Leader", "Perplexity" if df_c['Score_PPLX'].mean() > df_c['Score_GEM'].mean() else "Gemini")
    
    delta = df_c['Score_Global'].iloc[0] - df_c['Score_Global'].iloc[-1] if len(df_c) > 1 else 0
    c4.metric("Progression", f"{delta:+.1f}%", delta=delta)

    st.subheader("📊 Évolution de la Domination Sémantique")
    fig = px.area(df_c.groupby(df_c['Timestamp'].dt.date)['Score_Global'].mean().reset_index(), 
                 x='Timestamp', y='Score_Global', color_discrete_sequence=['#4F46E5'])
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("🥊 Part de Voix : Moteur par Moteur")
        df_ia = df_c.groupby('Mot_Cle')[['Score_PPLX', 'Score_GEM']].last().reset_index()
        fig_ia = go.Figure(data=[
            go.Bar(name='Perplexity', x=df_ia['Mot_Cle'], y=df_ia['Score_PPLX'], marker_color='#4F46E5'),
            go.Bar(name='Gemini', x=df_ia['Mot_Cle'], y=df_ia['Score_GEM'], marker_color='#10B981')
        ])
        fig_ia.update_layout(barmode='group', template="plotly_white")
        st.plotly_chart(fig_ia, use_container_width=True)

    with col_right:
        st.subheader("🏴‍☠️ Principaux Concurrents")
        top_conc = df_c[df_c['Concurrent_Principal'] != 'N/A']['Concurrent_Principal'].value_counts()
        if not top_conc.empty:
            fig_conc = px.pie(values=top_conc.values, names=top_conc.index, hole=.4, color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig_conc, use_container_width=True)
        else:
            st.write("Aucun concurrent dominant détecté. Domination totale !")

with tab3:
    st.subheader("🔍 Analyse des Verbatims & Surlignage")
    q_list = df_c['Mot_Cle'].unique()
    sel_q = st.selectbox("Choisir une question :", q_list)
    
    entry = df_c[df_c['Mot_Cle'] == sel_q].iloc[0]
    
    # On récupère les mots signatures depuis l'autre onglet (ou via un fallback)
    # Pour l'instant on utilise les détails du calcul pour extraire les mots si besoin
    kw_list = [] # Ici on pourrait charger les vrais mots signatures du client
    
    c_pplx, c_gem = st.columns(2)
    
    with c_pplx:
        st.markdown(f"#### ⚡ Perplexity (Score: {entry['Score_PPLX']})")
        is_cited = entry['Score_PPLX'] >= 50
        st.info("✅ Cité" if is_cited else "❌ Non Cité")
        txt = highlight_text(entry['Texte_PPLX'], "tabac-info-service.fr", kw_list) # Remplace par l'URL dynamique
        st.markdown(f"<div class='reponse-ia'>{txt}</div>", unsafe_allow_html=True)
        
    with c_gem:
        st.markdown(f"#### ♊ Gemini (Score: {entry['Score_GEM']})")
        is_cited_g = entry['Score_GEM'] >= 50
        st.info("✅ Cité" if is_cited_g else "❌ Non Cité")
        txt_g = highlight_text(entry['Texte_GEM'], "tabac-info-service.fr", kw_list)
        st.markdown(f"<div class='reponse-ia'>{txt_g}</div>", unsafe_allow_html=True)

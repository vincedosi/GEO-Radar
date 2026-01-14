import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
import json
from google.oauth2.service_account import Credentials

# 1. CONFIGURATION
st.set_page_config(page_title="GEO-Radar V2", layout="wide", page_icon="📡")

# Style CSS personnalisé
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .reponse-ia { padding: 15px; border-left: 5px solid #4F46E5; background-color: #f1f5f9; margin-bottom: 10px; border-radius: 0 10px 10px 0; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource(ttl=600)
def get_data():
    creds_dict = json.loads(st.secrets["GOOGLE_JSON_KEY"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    sh = client.open("GEO-Radar_DATA")
    ws = sh.worksheet("LOGS_RESULTATS")
    df = pd.DataFrame(ws.get_all_records())
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    return df

try:
    df = get_data()
except Exception as e:
    st.error(f"Erreur de chargement : {e}")
    st.stop()

# --- SIDEBAR ---
st.sidebar.title("📡 GEO-Radar Admin")
client_list = df['Client'].unique()
selected_client = st.sidebar.selectbox("🎯 Client", client_list)
df_c = df[df['Client'] == selected_client].copy()

if st.sidebar.button("🔄 Actualiser les données"):
    st.cache_resource.clear()
    st.rerun()

# --- HEADER ---
st.title(f"Analyse de Visibilité IA : {selected_client}")

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📊 Performance Globale", "🤖 Comparatif IA", "🔍 Explorateur de Réponses"])

with tab1:
    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    avg_score = df_c['Score_Global'].mean()
    c1.metric("Score GEO Moyen", f"{avg_score:.1f}%")
    c2.metric("Total Tests", len(df_c))
    
    best_ia = "Perplexity" if df_c['Score_PPLX'].mean() > df_c['Score_GEM'].mean() else "Gemini"
    c3.metric("IA la plus favorable", best_ia)
    
    direct_hit = (df_c['Score_Global'] >= 50).sum() / len(df_c) * 100
    c4.metric("% Citation Directe", f"{direct_hit:.0f}%")

    # Graphique Evolution
    st.subheader("📈 Évolution temporelle du Score Global")
    df_trend = df_c.groupby(df_c['Timestamp'].dt.date)['Score_Global'].mean().reset_index()
    fig_trend = px.line(df_trend, x='Timestamp', y='Score_Global', markers=True, line_shape="spline")
    fig_trend.update_layout(yaxis_range=[0, 105], template="plotly_white")
    st.plotly_chart(fig_trend, use_container_width=True)

with tab2:
    st.subheader("🤖 Perplexity vs Gemini")
    
    col_a, col_b = st.columns(2)
    
    # Bar chart de comparaison par Mot Clé
    df_ia = df_c.groupby('Mot_Cle')[['Score_PPLX', 'Score_GEM']].last().reset_index()
    fig_ia = go.Figure(data=[
        go.Bar(name='Perplexity', x=df_ia['Mot_Cle'], y=df_ia['Score_PPLX'], marker_color='#4F46E5'),
        go.Bar(name='Gemini', x=df_ia['Mot_Cle'], y=df_ia['Score_GEM'], marker_color='#10B981')
    ])
    fig_ia.update_layout(barmode='group', template="plotly_white", yaxis_range=[0, 105])
    st.plotly_chart(fig_ia, use_container_width=True)

with tab3:
    st.subheader("🔍 Analyse détaillée des réponses")
    
    # Sélecteur de question
    q_list = df_c['Mot_Cle'].unique()
    sel_q = st.selectbox("Sélectionnez une question pour voir les preuves :", q_list)
    
    last_entry = df_c[df_c['Mot_Cle'] == sel_q].iloc[0]
    
    col_pplx, col_gem = st.columns(2)
    
    with col_pplx:
        st.markdown(f"### ⚡ Perplexity (Score: {last_entry['Score_PPLX']})")
        st.markdown(f"<div class='reponse-ia'>{last_entry['Texte_PPLX']}</div>", unsafe_allow_html=True)
        
    with col_gem:
        st.markdown(f"### ♊ Gemini (Score: {last_entry['Score_GEM']})")
        st.markdown(f"<div class='reponse-ia'>{last_entry['Texte_GEM']}</div>", unsafe_allow_html=True)

    st.divider()
    st.write("**Détails du calcul :**", last_entry['Details_Calcul'])

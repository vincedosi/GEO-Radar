import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
import json
import re
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from collections import Counter
import io

# =============================================================================
# 1. CONFIGURATION CLIENTS
# =============================================================================
CONFIG_CLIENTS = {
    "SPF": {
        "url_cible": "tabac-info-service.fr",
        "urls_partenaires": ["sante.gouv.fr", "santepubliquefrance.fr", "ameli.fr", "mois-sans-tabac.tabac-info-service.fr"],
        "mots_signatures": ["3989", "kit gratuit", "accompagnement", "défi collectif", "30 jours", "inscription", 
                           "consultation", "tabacologue", "pharmacies partenaires", "espace personnel", 
                           "app gratuite", "coaching", "suivi", "Mois sans tabac"],
        "couleur": "#4F46E5"
    },
    "Conforama": {
        "url_cible": "conforama.fr",
        "urls_partenaires": [],
        "mots_signatures": ["confo", "canapé convertible", "stock", "matelas ressorts", "mémoire de forme",
                           "hublot", "livraison gratuite", "garantie", "design", "velours", "confort",
                           "bon plan", "promo", "électroménager"],
        "couleur": "#DC2626"
    },
    "IKEA": {
        "url_cible": "ikea.com",
        "urls_partenaires": [],
        "mots_signatures": ["EKTORP", "KIVIK", "design suédois", "PAX", "BILLY", "gain de place",
                           "BEKANT", "METOD", "plan de travail", "îlot central"],
        "couleur": "#0058A3"
    }
}

# =============================================================================
# 2. CONFIGURATION STREAMLIT & STYLES
# =============================================================================
st.set_page_config(page_title="GEO-Radar Pro", layout="wide", page_icon="📡")

st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    
    /* KPI Cards */
    .kpi-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
        text-align: center;
    }
    .kpi-value { font-size: 28px; font-weight: 700; color: #1e293b; }
    .kpi-label { font-size: 13px; color: #64748b; margin-top: 4px; }
    
    /* Source cards */
    .source-card {
        background: white;
        padding: 16px;
        border-radius: 12px;
        border-left: 4px solid #10b981;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .source-card.client { border-left-color: #10b981; background: #f0fdf4; }
    .source-card.partenaire { border-left-color: #3b82f6; background: #eff6ff; }
    .source-card.concurrent { border-left-color: #ef4444; background: #fef2f2; }
    
    /* Badges */
    .badge-client { 
        background: #dcfce7; color: #166534; 
        padding: 4px 12px; border-radius: 20px; 
        font-size: 12px; font-weight: 600;
    }
    .badge-partenaire { 
        background: #dbeafe; color: #1e40af; 
        padding: 4px 12px; border-radius: 20px; 
        font-size: 12px; font-weight: 600;
    }
    .badge-concurrent { 
        background: #fee2e2; color: #991b1b; 
        padding: 4px 12px; border-radius: 20px; 
        font-size: 12px; font-weight: 600;
    }
    
    /* Section headers */
    .section-header {
        font-size: 18px;
        font-weight: 600;
        color: #334155;
        margin: 24px 0 16px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid #e2e8f0;
    }
    
    /* Highlight */
    .highlight-url { background-color: #fef08a; font-weight: bold; padding: 2px 6px; border-radius: 4px; }
    .highlight-keyword { background-color: #bbf7d0; font-weight: 600; padding: 1px 4px; border-radius: 3px; }
    .highlight-concurrent { background-color: #fecaca; padding: 1px 4px; border-radius: 3px; }
    
    /* Response box */
    .reponse-ia {
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        background-color: white;
        line-height: 1.8;
        font-size: 14px;
        max-height: 500px;
        overflow-y: auto;
    }
    
    /* Citation status */
    .citation-yes { background: #dcfce7; color: #166534; padding: 6px 12px; border-radius: 8px; font-weight: 600; }
    .citation-no { background: #fee2e2; color: #991b1b; padding: 6px 12px; border-radius: 8px; font-weight: 600; }
    
    /* Big number */
    .big-number {
        font-size: 48px;
        font-weight: 800;
        background: linear-gradient(135deg, #4F46E5, #7C3AED);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
    }
    
    /* Podium */
    .podium { display: flex; align-items: flex-end; justify-content: center; gap: 8px; margin: 20px 0; }
    .podium-item { text-align: center; padding: 12px; border-radius: 8px; }
    .podium-1 { background: linear-gradient(135deg, #fef08a, #fbbf24); height: 140px; width: 100px; }
    .podium-2 { background: linear-gradient(135deg, #e5e7eb, #9ca3af); height: 110px; width: 90px; }
    .podium-3 { background: linear-gradient(135deg, #fed7aa, #f97316); height: 90px; width: 90px; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 3. FONCTIONS UTILITAIRES
# =============================================================================

@st.cache_resource(ttl=600)
def get_data():
    """Charge les données depuis Google Sheets"""
    creds_dict = json.loads(st.secrets["GOOGLE_JSON_KEY"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("GEO-Radar_DATA")
    df = pd.DataFrame(sh.worksheet("LOGS_RESULTATS").get_all_records())
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    return df

def get_client_config(client_name):
    """Récupère la config d'un client"""
    return CONFIG_CLIENTS.get(client_name, {
        "url_cible": "",
        "urls_partenaires": [],
        "mots_signatures": [],
        "couleur": "#6366f1"
    })

def parse_sources(sources_str):
    """Parse la colonne Sources_Detectees pour extraire les sources par moteur"""
    result = {"PPLX": [], "GEM": []}
    
    if not sources_str or pd.isna(sources_str) or sources_str == "":
        return result
    
    # Format: "PPLX: source1, source2 | GEM: source1, source2"
    parts = str(sources_str).split("|")
    
    for part in parts:
        part = part.strip()
        if part.startswith("PPLX:"):
            sources = part.replace("PPLX:", "").strip()
            if sources and sources != "N/A":
                result["PPLX"] = [s.strip() for s in sources.split(",") if s.strip() and s.strip() != "N/A"]
        elif part.startswith("GEM:"):
            sources = part.replace("GEM:", "").strip()
            if sources and sources != "N/A":
                result["GEM"] = [s.strip() for s in sources.split(",") if s.strip() and s.strip() != "N/A"]
    
    return result

def classify_source(source, config):
    """Classifie une source : client, partenaire ou concurrent"""
    source_lower = source.lower()
    url_cible = config.get("url_cible", "").lower()
    urls_partenaires = [u.lower() for u in config.get("urls_partenaires", [])]
    
    if url_cible and url_cible in source_lower:
        return "client"
    for partenaire in urls_partenaires:
        if partenaire and partenaire in source_lower:
            return "partenaire"
    return "concurrent"

def analyze_all_sources(df, config):
    """Analyse complète de toutes les sources citées"""
    all_sources_pplx = []
    all_sources_gem = []
    all_sources_combined = []
    
    for _, row in df.iterrows():
        parsed = parse_sources(row.get('Sources_Detectees', ''))
        all_sources_pplx.extend(parsed["PPLX"])
        all_sources_gem.extend(parsed["GEM"])
        all_sources_combined.extend(parsed["PPLX"] + parsed["GEM"])
    
    # Compter les occurrences
    count_pplx = Counter(all_sources_pplx)
    count_gem = Counter(all_sources_gem)
    count_combined = Counter(all_sources_combined)
    
    # Classifier chaque source
    sources_analysis = []
    for source, count in count_combined.most_common():
        classification = classify_source(source, config)
        sources_analysis.append({
            "source": source,
            "total": count,
            "pplx": count_pplx.get(source, 0),
            "gem": count_gem.get(source, 0),
            "type": classification
        })
    
    return pd.DataFrame(sources_analysis)

def calculate_visibility_metrics(df, config):
    """Calcule les métriques de visibilité"""
    total_queries = len(df)
    if total_queries == 0:
        return {"taux_citation": 0, "taux_pplx": 0, "taux_gem": 0, "part_voix": 0}
    
    url_cible = config.get("url_cible", "").lower()
    urls_partenaires = [u.lower() for u in config.get("urls_partenaires", [])]
    all_friendly_urls = [url_cible] + urls_partenaires
    
    cited_pplx = 0
    cited_gem = 0
    cited_any = 0
    total_sources = 0
    client_sources = 0
    
    for _, row in df.iterrows():
        parsed = parse_sources(row.get('Sources_Detectees', ''))
        
        # Check if client/partenaire is cited
        pplx_sources_lower = [s.lower() for s in parsed["PPLX"]]
        gem_sources_lower = [s.lower() for s in parsed["GEM"]]
        
        is_cited_pplx = any(url in " ".join(pplx_sources_lower) for url in all_friendly_urls if url)
        is_cited_gem = any(url in " ".join(gem_sources_lower) for url in all_friendly_urls if url)
        
        if is_cited_pplx:
            cited_pplx += 1
        if is_cited_gem:
            cited_gem += 1
        if is_cited_pplx or is_cited_gem:
            cited_any += 1
        
        # Count for part de voix
        all_sources = parsed["PPLX"] + parsed["GEM"]
        total_sources += len(all_sources)
        for src in all_sources:
            if any(url in src.lower() for url in all_friendly_urls if url):
                client_sources += 1
    
    return {
        "taux_citation": (cited_any / total_queries) * 100 if total_queries > 0 else 0,
        "taux_pplx": (cited_pplx / total_queries) * 100 if total_queries > 0 else 0,
        "taux_gem": (cited_gem / total_queries) * 100 if total_queries > 0 else 0,
        "part_voix": (client_sources / total_sources) * 100 if total_sources > 0 else 0,
        "nb_requetes": total_queries,
        "nb_cite": cited_any
    }

def filter_by_date(df, start_date, end_date):
    """Filtre par date"""
    mask = (df['Timestamp'].dt.date >= start_date) & (df['Timestamp'].dt.date <= end_date)
    return df[mask]

def resample_data(df, granularity):
    """Agrège selon granularité"""
    df_copy = df.copy()
    if granularity == "Jour":
        df_copy['Periode'] = df_copy['Timestamp'].dt.date
    elif granularity == "Semaine":
        df_copy['Periode'] = df_copy['Timestamp'].dt.to_period('W').apply(lambda x: x.start_time.date())
    elif granularity == "Mois":
        df_copy['Periode'] = df_copy['Timestamp'].dt.to_period('M').apply(lambda x: x.start_time.date())
    elif granularity == "Année":
        df_copy['Periode'] = df_copy['Timestamp'].dt.to_period('Y').apply(lambda x: x.start_time.date())
    return df_copy

def highlight_text_advanced(text, config, all_sources=None):
    """Surlignage enrichi"""
    if not text or not isinstance(text, str):
        return ""
    
    result = text
    
    # URL cible (vert)
    if config.get("url_cible"):
        url = config["url_cible"]
        pattern = re.compile(re.escape(url), re.IGNORECASE)
        result = pattern.sub(f'<span class="highlight-keyword">{url}</span>', result)
    
    # URLs partenaires (vert aussi)
    for partner in config.get("urls_partenaires", []):
        if partner:
            pattern = re.compile(re.escape(partner), re.IGNORECASE)
            result = pattern.sub(f'<span class="highlight-keyword">{partner}</span>', result)
    
    # Mots signatures (jaune)
    for kw in config.get("mots_signatures", []):
        if kw and kw.strip():
            pattern = re.compile(re.escape(kw.strip()), re.IGNORECASE)
            result = pattern.sub(f'<span class="highlight-url">{kw.strip()}</span>', result)
    
    # Concurrents (rouge) - si fournis
    if all_sources:
        for src in all_sources:
            if classify_source(src, config) == "concurrent":
                pattern = re.compile(re.escape(src), re.IGNORECASE)
                result = pattern.sub(f'<span class="highlight-concurrent">{src}</span>', result)
    
    return result

def generate_pdf_report(df_client, client_name, config, visibility_metrics, sources_df, start_date, end_date):
    """Génère un rapport PDF"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.units import cm
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, spaceAfter=30, textColor=colors.HexColor('#1e293b'))
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'], fontSize=16, spaceAfter=20, textColor=colors.HexColor('#475569'))
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=11, spaceAfter=12)
    
    elements = []
    
    # PAGE 1: Résumé Visibilité
    elements.append(Paragraph("📡 GEO-Radar Pro - Rapport de Visibilité IA", title_style))
    elements.append(Paragraph(f"Client : {client_name}", subtitle_style))
    elements.append(Paragraph(f"Période : {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}", normal_style))
    elements.append(Spacer(1, 20))
    
    # KPIs
    elements.append(Paragraph("🎯 Métriques de Visibilité", subtitle_style))
    kpi_data = [
        ["Taux de Citation", "Citation Perplexity", "Citation Gemini", "Part de Voix"],
        [f"{visibility_metrics['taux_citation']:.1f}%", 
         f"{visibility_metrics['taux_pplx']:.1f}%", 
         f"{visibility_metrics['taux_gem']:.1f}%",
         f"{visibility_metrics['part_voix']:.1f}%"]
    ]
    kpi_table = Table(kpi_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 30))
    
    # Synthèse
    elements.append(Paragraph("📊 Synthèse", subtitle_style))
    synthese = f"""
    Sur {visibility_metrics['nb_requetes']} requêtes analysées, {client_name} est cité dans {visibility_metrics['nb_cite']} réponses IA,
    soit un taux de citation de {visibility_metrics['taux_citation']:.1f}%. 
    La part de voix globale (proportion de citations vs concurrents) est de {visibility_metrics['part_voix']:.1f}%.
    """
    elements.append(Paragraph(synthese, normal_style))
    
    elements.append(PageBreak())
    
    # PAGE 2: Top Sources
    elements.append(Paragraph("🏆 Top 15 Sources Citées par les IA", title_style))
    
    if len(sources_df) > 0:
        top_sources = sources_df.head(15)
        src_data = [["Source", "Total", "Perplexity", "Gemini", "Type"]]
        for _, row in top_sources.iterrows():
            type_label = "🟢 Client" if row['type'] == 'client' else ("🔵 Partenaire" if row['type'] == 'partenaire' else "🔴 Concurrent")
            src_data.append([
                row['source'][:35] + "..." if len(row['source']) > 35 else row['source'],
                str(row['total']),
                str(row['pplx']),
                str(row['gem']),
                type_label
            ])
        
        src_table = Table(src_data, colWidths=[6*cm, 2*cm, 2.5*cm, 2.5*cm, 3*cm])
        src_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10B981')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ]))
        elements.append(src_table)
    
    elements.append(PageBreak())
    
    # PAGE 3: Détail par requête
    elements.append(Paragraph("🔍 Détail par Requête", title_style))
    
    if len(df_client) > 0:
        req_data = [["Requête", "Score", "PPLX", "GEM", "Concurrent"]]
        for _, row in df_client.head(15).iterrows():
            req_data.append([
                str(row['Mot_Cle'])[:40] + "..." if len(str(row['Mot_Cle'])) > 40 else str(row['Mot_Cle']),
                f"{row['Score_Global']}%",
                f"{row['Score_PPLX']}%",
                f"{row['Score_GEM']}%",
                str(row.get('Concurrent_Principal', 'N/A'))[:20]
            ])
        
        req_table = Table(req_data, colWidths=[6*cm, 2*cm, 2*cm, 2*cm, 4*cm])
        req_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B5CF6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ]))
        elements.append(req_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# =============================================================================
# 4. CHARGEMENT DES DONNÉES
# =============================================================================
try:
    df = get_data()
except Exception as e:
    st.error(f"❌ Erreur de connexion : {e}")
    st.stop()

# =============================================================================
# 5. SIDEBAR
# =============================================================================
with st.sidebar:
    st.markdown("## 📡 GEO-Radar Pro")
    st.caption("Audit de Visibilité IA")
    
    st.markdown("---")
    
    # Client
    st.markdown("##### 🎯 Client")
    clients_disponibles = df['Client'].unique().tolist()
    selected_client = st.selectbox("", clients_disponibles, label_visibility="collapsed")
    config = get_client_config(selected_client)
    
    st.markdown("---")
    
    # Période
    st.markdown("##### 📅 Période")
    min_date = df['Timestamp'].min().date()
    max_date = df['Timestamp'].max().date()
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Début", value=min_date, min_value=min_date, max_value=max_date)
    with col_d2:
        end_date = st.date_input("Fin", value=max_date, min_value=min_date, max_value=max_date)
    
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if st.button("7j", use_container_width=True):
            start_date = max_date - timedelta(days=7)
    with col_r2:
        if st.button("30j", use_container_width=True):
            start_date = max_date - timedelta(days=30)
    
    st.markdown("---")
    
    # Granularité
    st.markdown("##### ⏱️ Granularité")
    granularity = st.radio("", ["Jour", "Semaine", "Mois"], horizontal=True, label_visibility="collapsed")
    
    st.markdown("---")
    
    # Config
    with st.expander("⚙️ Config Client"):
        st.markdown(f"**URL cible:** `{config.get('url_cible', 'N/A')}`")
        st.markdown(f"**Partenaires:** {len(config.get('urls_partenaires', []))}")
        if config.get('urls_partenaires'):
            for p in config['urls_partenaires'][:5]:
                st.caption(f"• {p}")

# =============================================================================
# 6. FILTRAGE
# =============================================================================
df_client = df[df['Client'] == selected_client].copy()
df_client = filter_by_date(df_client, start_date, end_date)
df_resampled = resample_data(df_client, granularity)

# Analyse des sources
sources_df = analyze_all_sources(df_client, config)
visibility_metrics = calculate_visibility_metrics(df_client, config)

# =============================================================================
# 7. HEADER
# =============================================================================
st.title(f"📡 Visibilité IA : {selected_client}")
st.caption(f"📅 {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')} | 📊 {len(df_client)} requêtes analysées")

# =============================================================================
# 8. ONGLETS
# =============================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏆 Sources Citées", 
    "📈 Dashboard", 
    "🥊 Concurrence", 
    "🔍 Preuves",
    "📥 Export"
])

# -----------------------------------------------------------------------------
# ONGLET 1 : SOURCES CITÉES (PRIORITÉ #1)
# -----------------------------------------------------------------------------
with tab1:
    st.markdown('<p class="section-header">🎯 Qui est cité par les IA ?</p>', unsafe_allow_html=True)
    
    # KPIs Visibilité
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: #10b981;">{visibility_metrics['taux_citation']:.0f}%</div>
            <div class="kpi-label">Taux de Citation Global</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: #8b5cf6;">{visibility_metrics['taux_pplx']:.0f}%</div>
            <div class="kpi-label">Citation Perplexity</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: #06b6d4;">{visibility_metrics['taux_gem']:.0f}%</div>
            <div class="kpi-label">Citation Gemini</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: #f59e0b;">{visibility_metrics['part_voix']:.1f}%</div>
            <div class="kpi-label">Part de Voix</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Deux colonnes : Podium + Tableau
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.markdown('<p class="section-header">🥇 Top 3 Sources</p>', unsafe_allow_html=True)
        
        if len(sources_df) >= 3:
            top3 = sources_df.head(3)
            
            # Podium visuel
            st.markdown(f"""
            <div style="display: flex; align-items: flex-end; justify-content: center; gap: 8px; margin: 20px 0;">
                <div style="text-align: center;">
                    <div style="font-size: 12px; margin-bottom: 4px;">🥈</div>
                    <div style="background: linear-gradient(135deg, #e5e7eb, #9ca3af); padding: 12px 8px; border-radius: 8px; width: 90px; height: 80px;">
                        <div style="font-size: 11px; font-weight: 600; word-wrap: break-word;">{top3.iloc[1]['source'][:15]}</div>
                        <div style="font-size: 16px; font-weight: 700; margin-top: 8px;">{top3.iloc[1]['total']}</div>
                    </div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 14px; margin-bottom: 4px;">🥇</div>
                    <div style="background: linear-gradient(135deg, #fef08a, #fbbf24); padding: 12px 8px; border-radius: 8px; width: 100px; height: 100px;">
                        <div style="font-size: 11px; font-weight: 600; word-wrap: break-word;">{top3.iloc[0]['source'][:15]}</div>
                        <div style="font-size: 20px; font-weight: 700; margin-top: 8px;">{top3.iloc[0]['total']}</div>
                    </div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 12px; margin-bottom: 4px;">🥉</div>
                    <div style="background: linear-gradient(135deg, #fed7aa, #f97316); padding: 12px 8px; border-radius: 8px; width: 90px; height: 70px;">
                        <div style="font-size: 11px; font-weight: 600; word-wrap: break-word;">{top3.iloc[2]['source'][:15]}</div>
                        <div style="font-size: 16px; font-weight: 700; margin-top: 8px;">{top3.iloc[2]['total']}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Types
            for i, row in top3.iterrows():
                badge_class = f"badge-{row['type']}"
                st.markdown(f"<span class='{badge_class}'>{row['source']}</span>", unsafe_allow_html=True)
        else:
            st.info("Pas assez de données")
    
    with col_right:
        st.markdown('<p class="section-header">📊 Classement Complet des Sources</p>', unsafe_allow_html=True)
        
        if len(sources_df) > 0:
            # Ajouter une colonne pour le badge type
            display_df = sources_df.copy()
            display_df['Type'] = display_df['type'].map({
                'client': '🟢 Client',
                'partenaire': '🔵 Partenaire', 
                'concurrent': '🔴 Concurrent'
            })
            
            max_total = int(display_df['total'].max()) if len(display_df) > 0 else 10
            st.dataframe(
                display_df[['source', 'total', 'pplx', 'gem', 'Type']].head(20),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "source": st.column_config.TextColumn("Source", width="large"),
                    "total": st.column_config.ProgressColumn("Total", min_value=0, max_value=max_total, format="%d"),
                    "pplx": st.column_config.NumberColumn("Perplexity", format="%d"),
                    "gem": st.column_config.NumberColumn("Gemini", format="%d"),
                    "Type": st.column_config.TextColumn("Type")
                }
            )
    
    # Graphique : Répartition Client vs Concurrents
    st.markdown('<p class="section-header">📈 Répartition des Citations</p>', unsafe_allow_html=True)
    
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        if len(sources_df) > 0:
            type_counts = sources_df.groupby('type')['total'].sum().reset_index()
            type_counts['type'] = type_counts['type'].map({
                'client': 'Votre site',
                'partenaire': 'Partenaires',
                'concurrent': 'Concurrents'
            })
            
            fig_pie = px.pie(
                type_counts, 
                values='total', 
                names='type',
                color='type',
                color_discrete_map={
                    'Votre site': '#10b981',
                    'Partenaires': '#3b82f6',
                    'Concurrents': '#ef4444'
                },
                hole=0.4
            )
            fig_pie.update_layout(
                title="Part de Voix par Type",
                height=350,
                margin=dict(l=20, r=20, t=50, b=20)
            )
            st.plotly_chart(fig_pie, use_container_width=True)
    
    with col_g2:
        if len(sources_df) > 0:
            top10 = sources_df.head(10)
            colors_list = ['#10b981' if t == 'client' else '#3b82f6' if t == 'partenaire' else '#ef4444' for t in top10['type']]
            
            fig_bar = go.Figure(go.Bar(
                x=top10['total'],
                y=top10['source'],
                orientation='h',
                marker_color=colors_list
            ))
            fig_bar.update_layout(
                title="Top 10 Sources",
                height=350,
                margin=dict(l=20, r=20, t=50, b=20),
                yaxis=dict(autorange="reversed")
            )
            st.plotly_chart(fig_bar, use_container_width=True)

# -----------------------------------------------------------------------------
# ONGLET 2 : DASHBOARD
# -----------------------------------------------------------------------------
with tab2:
    st.markdown('<p class="section-header">📈 Évolution de la Visibilité</p>', unsafe_allow_html=True)
    
    # KPIs scores
    col1, col2, col3, col4 = st.columns(4)
    
    avg_score = df_client['Score_Global'].mean() if len(df_client) > 0 else 0
    avg_pplx = df_client['Score_PPLX'].mean() if len(df_client) > 0 else 0
    avg_gem = df_client['Score_GEM'].mean() if len(df_client) > 0 else 0
    avg_reco = df_client['Note_Recommandation'].astype(float).mean() if len(df_client) > 0 and 'Note_Recommandation' in df_client.columns else 0
    
    with col1:
        st.metric("Score GEO Global", f"{avg_score:.0f}%")
    with col2:
        st.metric("Score Perplexity", f"{avg_pplx:.0f}%")
    with col3:
        st.metric("Score Gemini", f"{avg_gem:.0f}%")
    with col4:
        stars = "⭐" * int(round(avg_reco))
        st.metric("Recommandation", stars if stars else "—")
    
    # Graphique évolution
    if len(df_resampled) > 0:
        df_evolution = df_resampled.groupby('Periode').agg({
            'Score_Global': 'mean',
            'Score_PPLX': 'mean',
            'Score_GEM': 'mean'
        }).reset_index()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_evolution['Periode'], y=df_evolution['Score_Global'],
            mode='lines+markers', name='Score Global',
            line=dict(color=config.get('couleur', '#4F46E5'), width=3),
            fill='tozeroy', fillcolor='rgba(79,70,229,0.1)'
        ))
        fig.add_trace(go.Scatter(
            x=df_evolution['Periode'], y=df_evolution['Score_PPLX'],
            mode='lines', name='Perplexity',
            line=dict(color='#8B5CF6', width=2, dash='dot')
        ))
        fig.add_trace(go.Scatter(
            x=df_evolution['Periode'], y=df_evolution['Score_GEM'],
            mode='lines', name='Gemini',
            line=dict(color='#10B981', width=2, dash='dot')
        ))
        fig.update_layout(
            template="plotly_white",
            height=400,
            legend=dict(orientation="h", y=1.1),
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Performance par mot-clé
    st.markdown('<p class="section-header">🎯 Performance par Requête</p>', unsafe_allow_html=True)
    
    if len(df_client) > 0:
        st.dataframe(
            df_client[['Mot_Cle', 'Score_Global', 'Score_PPLX', 'Score_GEM', 'Note_Recommandation', 'Concurrent_Principal']].sort_values('Score_Global', ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Mot_Cle": st.column_config.TextColumn("Requête", width="large"),
                "Score_Global": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d%%"),
                "Score_PPLX": st.column_config.ProgressColumn("PPLX", min_value=0, max_value=100, format="%d%%"),
                "Score_GEM": st.column_config.ProgressColumn("Gemini", min_value=0, max_value=100, format="%d%%"),
                "Note_Recommandation": st.column_config.NumberColumn("Reco", format="%d ⭐"),
                "Concurrent_Principal": st.column_config.TextColumn("Concurrent")
            }
        )

# -----------------------------------------------------------------------------
# ONGLET 3 : CONCURRENCE
# -----------------------------------------------------------------------------
with tab3:
    st.markdown('<p class="section-header">🥊 Analyse Concurrentielle</p>', unsafe_allow_html=True)
    
    # Top concurrents
    if len(sources_df) > 0:
        concurrents_df = sources_df[sources_df['type'] == 'concurrent'].head(10)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### 🏴‍☠️ Top Concurrents par Citations")
            if len(concurrents_df) > 0:
                fig_conc = px.bar(
                    concurrents_df,
                    x='total',
                    y='source',
                    orientation='h',
                    color='total',
                    color_continuous_scale='Reds'
                )
                fig_conc.update_layout(
                    height=400,
                    yaxis=dict(autorange="reversed"),
                    showlegend=False
                )
                st.plotly_chart(fig_conc, use_container_width=True)
        
        with col2:
            st.markdown("##### 📊 Perplexity vs Gemini")
            if len(concurrents_df) > 0:
                fig_compare = go.Figure()
                fig_compare.add_trace(go.Bar(
                    name='Perplexity',
                    x=concurrents_df['source'],
                    y=concurrents_df['pplx'],
                    marker_color='#8B5CF6'
                ))
                fig_compare.add_trace(go.Bar(
                    name='Gemini',
                    x=concurrents_df['source'],
                    y=concurrents_df['gem'],
                    marker_color='#10B981'
                ))
                fig_compare.update_layout(
                    barmode='group',
                    height=400,
                    xaxis_tickangle=-45
                )
                st.plotly_chart(fig_compare, use_container_width=True)
    
    # Concurrent principal par requête
    st.markdown('<p class="section-header">🎯 Concurrent Principal par Requête</p>', unsafe_allow_html=True)
    
    if 'Concurrent_Principal' in df_client.columns:
        conc_counts = df_client[df_client['Concurrent_Principal'] != 'N/A']['Concurrent_Principal'].value_counts()
        
        if len(conc_counts) > 0:
            col1, col2 = st.columns([1, 2])
            
            with col1:
                fig_pie_conc = px.pie(
                    values=conc_counts.values,
                    names=conc_counts.index,
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig_pie_conc.update_layout(height=300)
                st.plotly_chart(fig_pie_conc, use_container_width=True)
            
            with col2:
                st.dataframe(
                    df_client[['Mot_Cle', 'Concurrent_Principal', 'Score_Global']].sort_values('Score_Global'),
                    use_container_width=True,
                    hide_index=True
                )

# -----------------------------------------------------------------------------
# ONGLET 4 : PREUVES
# -----------------------------------------------------------------------------
with tab4:
    st.markdown('<p class="section-header">🔍 Explorateur de Preuves</p>', unsafe_allow_html=True)
    
    # Sélection requête
    if len(df_client) > 0:
        requetes = df_client['Mot_Cle'].unique().tolist()
        selected_query = st.selectbox("📝 Sélectionner une requête :", requetes)
        
        entry = df_client[df_client['Mot_Cle'] == selected_query].iloc[0]
        
        # Légende
        st.markdown("""
        <div style="display: flex; gap: 20px; margin: 16px 0; padding: 12px; background: #f8fafc; border-radius: 8px; font-size: 13px;">
            <span><span class="highlight-keyword">Vert</span> = Votre site / Partenaire</span>
            <span><span class="highlight-url">Jaune</span> = Mot signature</span>
            <span><span class="highlight-concurrent">Rouge</span> = Concurrent</span>
        </div>
        """, unsafe_allow_html=True)
        
        # Sources de cette requête
        parsed_sources = parse_sources(entry.get('Sources_Detectees', ''))
        
        st.markdown("##### 📋 Sources citées pour cette requête")
        col_src1, col_src2 = st.columns(2)
        
        with col_src1:
            st.markdown("**⚡ Perplexity**")
            if parsed_sources['PPLX']:
                for src in parsed_sources['PPLX']:
                    src_type = classify_source(src, config)
                    badge = f"badge-{src_type}"
                    st.markdown(f"<span class='{badge}'>{src}</span>", unsafe_allow_html=True)
            else:
                st.caption("Aucune source détectée")
        
        with col_src2:
            st.markdown("**♊ Gemini**")
            if parsed_sources['GEM']:
                for src in parsed_sources['GEM']:
                    src_type = classify_source(src, config)
                    badge = f"badge-{src_type}"
                    st.markdown(f"<span class='{badge}'>{src}</span>", unsafe_allow_html=True)
            else:
                st.caption("Aucune source détectée")
        
        st.markdown("---")
        
        # Réponses complètes
        col_pplx, col_gem = st.columns(2)
        
        all_sources = parsed_sources['PPLX'] + parsed_sources['GEM']
        
        with col_pplx:
            st.markdown(f"""
            <div style="background: #8B5CF6; color: white; padding: 12px 16px; border-radius: 8px 8px 0 0;">
                <strong>⚡ Perplexity</strong> — Score : {entry['Score_PPLX']}%
            </div>
            """, unsafe_allow_html=True)
            
            is_cited = entry['Score_PPLX'] >= 50
            st.markdown(f"<span class='{'citation-yes' if is_cited else 'citation-no'}'>{'✅ Cité' if is_cited else '❌ Non cité'}</span>", unsafe_allow_html=True)
            
            text = highlight_text_advanced(entry.get('Texte_PPLX', ''), config, all_sources)
            st.markdown(f'<div class="reponse-ia">{text if text else "<em>Aucun texte</em>"}</div>', unsafe_allow_html=True)
        
        with col_gem:
            st.markdown(f"""
            <div style="background: #10B981; color: white; padding: 12px 16px; border-radius: 8px 8px 0 0;">
                <strong>♊ Gemini</strong> — Score : {entry['Score_GEM']}%
            </div>
            """, unsafe_allow_html=True)
            
            is_cited_g = entry['Score_GEM'] >= 50
            st.markdown(f"<span class='{'citation-yes' if is_cited_g else 'citation-no'}'>{'✅ Cité' if is_cited_g else '❌ Non cité'}</span>", unsafe_allow_html=True)
            
            text_g = highlight_text_advanced(entry.get('Texte_GEM', ''), config, all_sources)
            st.markdown(f'<div class="reponse-ia">{text_g if text_g else "<em>Aucun texte</em>"}</div>', unsafe_allow_html=True)
    else:
        st.warning("Aucune donnée disponible")

# -----------------------------------------------------------------------------
# ONGLET 5 : EXPORT
# -----------------------------------------------------------------------------
with tab5:
    st.markdown('<p class="section-header">📥 Export des Données</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📄 Rapport PDF")
        st.markdown("Génère un rapport complet avec :")
        st.markdown("- Métriques de visibilité")
        st.markdown("- Top sources citées")
        st.markdown("- Détail par requête")
        
        if st.button("🔄 Générer le PDF", type="primary", use_container_width=True):
            with st.spinner("Génération..."):
                try:
                    pdf = generate_pdf_report(
                        df_client, selected_client, config,
                        visibility_metrics, sources_df,
                        start_date, end_date
                    )
                    st.download_button(
                        "📥 Télécharger PDF",
                        data=pdf,
                        file_name=f"GEO-Radar_{selected_client}_{start_date}_{end_date}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except ImportError:
                    st.error("Installez `reportlab` : pip install reportlab")
                except Exception as e:
                    st.error(f"Erreur : {e}")
    
    with col2:
        st.markdown("##### 📊 Export CSV")
        
        # Données brutes
        if len(df_client) > 0:
            csv_data = df_client.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Données complètes (CSV)",
                data=csv_data,
                file_name=f"GEO-Radar_data_{selected_client}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        # Sources
        if len(sources_df) > 0:
            csv_sources = sources_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Analyse des Sources (CSV)",
                data=csv_sources,
                file_name=f"GEO-Radar_sources_{selected_client}.csv",
                mime="text/csv",
                use_container_width=True
            )

# =============================================================================
# FOOTER
# =============================================================================
st.markdown("---")
st.caption(f"📡 GEO-Radar Pro | Dernière MAJ : {df['Timestamp'].max().strftime('%d/%m/%Y %H:%M')}")

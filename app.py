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
    /* Global */
    .main { background-color: #f8fafc; }
    [data-testid="stSidebar"] { background-color: #1e293b; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] .stSelectbox label { color: #94a3b8 !important; }
    
    /* KPI Cards */
    .kpi-card {
        background: white;
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
        text-align: center;
        transition: transform 0.2s;
    }
    .kpi-card:hover { transform: translateY(-2px); }
    .kpi-value { font-size: 32px; font-weight: 700; }
    .kpi-label { font-size: 13px; color: #64748b; margin-top: 4px; }
    .kpi-trend-up { color: #10b981; font-size: 12px; }
    .kpi-trend-down { color: #ef4444; font-size: 12px; }
    
    /* Status indicators */
    .status-excellent { color: #10b981; }
    .status-good { color: #3b82f6; }
    .status-medium { color: #f59e0b; }
    .status-bad { color: #ef4444; }
    
    /* Info boxes */
    .info-box {
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        border-left: 4px solid #3b82f6;
        padding: 16px 20px;
        border-radius: 0 12px 12px 0;
        margin: 16px 0;
        font-size: 14px;
        line-height: 1.6;
    }
    .info-box-title {
        font-weight: 600;
        color: #1e40af;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    /* Insight boxes */
    .insight-box {
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
        border-left: 4px solid #10b981;
        padding: 16px 20px;
        border-radius: 0 12px 12px 0;
        margin: 16px 0;
    }
    .insight-box.warning {
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
        border-left-color: #f59e0b;
    }
    .insight-box.danger {
        background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
        border-left-color: #ef4444;
    }
    
    /* Source cards */
    .source-card {
        background: white;
        padding: 12px 16px;
        border-radius: 10px;
        border-left: 4px solid #10b981;
        margin-bottom: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .source-card.client { border-left-color: #10b981; background: #f0fdf4; }
    .source-card.partenaire { border-left-color: #3b82f6; background: #eff6ff; }
    .source-card.concurrent { border-left-color: #ef4444; background: #fef2f2; }
    
    /* Badges */
    .badge { 
        padding: 4px 12px; 
        border-radius: 20px; 
        font-size: 12px; 
        font-weight: 600;
        display: inline-block;
        margin: 2px;
    }
    .badge-client { background: #dcfce7; color: #166534; }
    .badge-partenaire { background: #dbeafe; color: #1e40af; }
    .badge-concurrent { background: #fee2e2; color: #991b1b; }
    .badge-score-high { background: #dcfce7; color: #166534; }
    .badge-score-medium { background: #fef3c7; color: #92400e; }
    .badge-score-low { background: #fee2e2; color: #991b1b; }
    
    /* Section headers */
    .section-header {
        font-size: 20px;
        font-weight: 700;
        color: #1e293b;
        margin: 28px 0 16px 0;
        padding-bottom: 12px;
        border-bottom: 3px solid #e2e8f0;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    /* Highlight */
    .highlight-client { background-color: #bbf7d0; font-weight: 600; padding: 2px 6px; border-radius: 4px; }
    .highlight-keyword { background-color: #fef08a; font-weight: 600; padding: 2px 6px; border-radius: 4px; }
    .highlight-concurrent { background-color: #fecaca; padding: 2px 6px; border-radius: 4px; }
    
    /* Response box */
    .reponse-ia {
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        background-color: white;
        line-height: 1.8;
        font-size: 14px;
        max-height: 450px;
        overflow-y: auto;
    }
    
    /* Motor header */
    .motor-header {
        padding: 14px 20px;
        border-radius: 12px 12px 0 0;
        color: white;
        font-weight: 600;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .motor-header.pplx { background: linear-gradient(135deg, #8B5CF6, #7C3AED); }
    .motor-header.gem { background: linear-gradient(135deg, #10B981, #059669); }
    
    /* Citation badge */
    .citation-yes { 
        background: #dcfce7; 
        color: #166534; 
        padding: 6px 14px; 
        border-radius: 20px; 
        font-weight: 600;
        font-size: 13px;
    }
    .citation-no { 
        background: #fee2e2; 
        color: #991b1b; 
        padding: 6px 14px; 
        border-radius: 20px; 
        font-weight: 600;
        font-size: 13px;
    }
    
    /* Metric interpretation */
    .metric-interpret {
        font-size: 13px;
        color: #64748b;
        margin-top: 8px;
        padding: 8px 12px;
        background: #f8fafc;
        border-radius: 8px;
    }
    
    /* Tooltip style info */
    .help-tooltip {
        display: inline-block;
        width: 18px;
        height: 18px;
        background: #e2e8f0;
        color: #64748b;
        border-radius: 50%;
        text-align: center;
        font-size: 12px;
        line-height: 18px;
        cursor: help;
        margin-left: 6px;
    }
    
    /* Legend */
    .legend-box {
        display: flex;
        gap: 24px;
        padding: 14px 20px;
        background: #f8fafc;
        border-radius: 10px;
        margin: 16px 0;
        flex-wrap: wrap;
    }
    .legend-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
    }
    .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
    }
    
    /* Recommendation card */
    .reco-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #e2e8f0;
        margin: 12px 0;
    }
    .reco-title {
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .reco-content {
        color: #475569;
        font-size: 14px;
        line-height: 1.6;
    }
    
    /* Progress ring */
    .progress-ring {
        width: 120px;
        height: 120px;
        margin: 0 auto;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 3. FONCTIONS UTILITAIRES
# =============================================================================

def _to_dict(obj):
    """Convertit un AttrDict Streamlit en dict Python standard via JSON"""
    try:
        # Méthode la plus fiable : sérialiser en JSON puis désérialiser
        return json.loads(json.dumps(dict(obj)))
    except (TypeError, ValueError):
        # Fallback : conversion manuelle récursive
        if hasattr(obj, 'keys'):
            return {k: _to_dict(v) if hasattr(v, 'keys') else v for k, v in obj.items()}
        return obj

def _fix_private_key(creds):
    """Corrige le format PEM de la clé privée"""
    if "private_key" in creds and isinstance(creds["private_key"], str):
        pk = creds["private_key"]
        # Remplace les séquences échappées par de vrais sauts de ligne
        pk = pk.replace("\\n", "\n").replace("\\\\n", "\n")
        # S'assure que le format PEM est correct
        if "-----BEGIN" in pk and "\n" not in pk.split("-----")[2][:50]:
            # La clé n'a pas de vrais sauts de ligne, on les ajoute
            pk = pk.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n")
            pk = pk.replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----\n")
        creds["private_key"] = pk
    return creds

@st.cache_resource(ttl=600)
def get_data():
    """Charge les données depuis Google Sheets"""
    raw = st.secrets["GOOGLE_JSON_KEY"]

    # Gère les deux cas : chaîne JSON ou dict déjà parsé (AttrDict Streamlit)
    if isinstance(raw, str):
        creds_dict = json.loads(raw)
    else:
        creds_dict = _to_dict(raw)

    # Corrige le format de la clé privée
    creds_dict = _fix_private_key(creds_dict)

    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("GEO-Radar_DATA")
    ws = sh.worksheet("LOGS_RESULTATS")

    # Récupère toutes les valeurs et crée le DataFrame manuellement
    # pour gérer les colonnes vides ou en double
    all_values = ws.get_all_values()
    if not all_values:
        return pd.DataFrame()

    headers = all_values[0]
    data = all_values[1:]

    # Filtre les colonnes vides et renomme les doublons
    clean_headers = []
    seen = {}
    for i, h in enumerate(headers):
        if not h or h.strip() == '':
            continue  # Ignore les colonnes sans en-tête
        if h in seen:
            seen[h] += 1
            clean_headers.append((i, f"{h}_{seen[h]}"))
        else:
            seen[h] = 0
            clean_headers.append((i, h))

    # Crée le DataFrame avec seulement les colonnes valides
    df_data = [[row[i] for i, _ in clean_headers] for row in data]
    df = pd.DataFrame(df_data, columns=[h for _, h in clean_headers])

    if 'Timestamp' in df.columns:
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
    """Parse la colonne Sources_Detectees"""
    result = {"PPLX": [], "GEM": []}
    if not sources_str or pd.isna(sources_str) or sources_str == "":
        return result
    
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
    
    count_pplx = Counter(all_sources_pplx)
    count_gem = Counter(all_sources_gem)
    count_combined = Counter(all_sources_combined)
    
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
        return {"taux_citation": 0, "taux_pplx": 0, "taux_gem": 0, "part_voix": 0, "nb_requetes": 0, "nb_cite": 0}
    
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
        
        all_sources = parsed["PPLX"] + parsed["GEM"]
        total_sources += len(all_sources)
        for src in all_sources:
            if any(url in src.lower() for url in all_friendly_urls if url):
                client_sources += 1
    
    return {
        "taux_citation": (cited_any / total_queries) * 100,
        "taux_pplx": (cited_pplx / total_queries) * 100,
        "taux_gem": (cited_gem / total_queries) * 100,
        "part_voix": (client_sources / total_sources) * 100 if total_sources > 0 else 0,
        "nb_requetes": total_queries,
        "nb_cite": cited_any
    }

def get_visibility_status(taux):
    """Retourne le status et l'interprétation selon le taux"""
    if taux >= 70:
        return "excellent", "🟢 Excellent", "Votre visibilité est excellente ! Les IA vous citent très régulièrement."
    elif taux >= 50:
        return "good", "🔵 Bon", "Bonne visibilité. Vous êtes bien référencé par les IA."
    elif taux >= 30:
        return "medium", "🟡 Moyen", "Visibilité moyenne. Il y a des opportunités d'amélioration."
    else:
        return "bad", "🔴 Faible", "Visibilité faible. Les IA citent rarement votre site."

def get_interpretation_text(metrics, sources_df, config):
    """Génère un texte d'interprétation automatique"""
    taux = metrics['taux_citation']
    part_voix = metrics['part_voix']
    
    # Compter les types de sources
    if len(sources_df) > 0:
        type_counts = sources_df.groupby('type')['total'].sum()
        client_total = type_counts.get('client', 0) + type_counts.get('partenaire', 0)
        concurrent_total = type_counts.get('concurrent', 0)
        total = client_total + concurrent_total
    else:
        client_total, concurrent_total, total = 0, 0, 0
    
    # Top concurrent
    concurrents = sources_df[sources_df['type'] == 'concurrent']
    top_concurrent = concurrents.iloc[0]['source'] if len(concurrents) > 0 else "N/A"
    
    interpretations = []
    
    # Interprétation du taux de citation
    if taux >= 70:
        interpretations.append(f"🎯 **Excellente performance !** Vous êtes cité dans {taux:.0f}% des réponses IA analysées.")
    elif taux >= 50:
        interpretations.append(f"✅ **Bonne visibilité.** Vous apparaissez dans {taux:.0f}% des réponses, mais il reste une marge de progression.")
    elif taux >= 30:
        interpretations.append(f"⚠️ **Visibilité moyenne.** Avec {taux:.0f}% de citation, vous n'êtes pas assez présent dans les réponses IA.")
    else:
        interpretations.append(f"🚨 **Alerte visibilité !** Seulement {taux:.0f}% de citation. Les IA ne vous considèrent pas comme une source de référence.")
    
    # Interprétation de la part de voix
    if total > 0:
        if part_voix >= 20:
            interpretations.append(f"📊 Votre part de voix ({part_voix:.1f}%) est solide face à la concurrence.")
        elif part_voix >= 10:
            interpretations.append(f"📊 Part de voix de {part_voix:.1f}% — vous êtes présent mais les concurrents dominent.")
        else:
            interpretations.append(f"📊 Part de voix faible ({part_voix:.1f}%). **{top_concurrent}** et d'autres captent l'essentiel des citations.")
    
    # Différence Perplexity vs Gemini
    diff = abs(metrics['taux_pplx'] - metrics['taux_gem'])
    if diff > 20:
        better = "Perplexity" if metrics['taux_pplx'] > metrics['taux_gem'] else "Gemini"
        worse = "Gemini" if better == "Perplexity" else "Perplexity"
        interpretations.append(f"💡 **Écart notable** : vous performez mieux sur {better} ({max(metrics['taux_pplx'], metrics['taux_gem']):.0f}%) que sur {worse} ({min(metrics['taux_pplx'], metrics['taux_gem']):.0f}%).")
    
    return interpretations

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
    return df_copy

def highlight_text_advanced(text, config, all_sources=None):
    """Surlignage enrichi du texte"""
    if not text or not isinstance(text, str):
        return ""
    
    result = text
    
    # URL cible (vert)
    if config.get("url_cible"):
        url = config["url_cible"]
        pattern = re.compile(re.escape(url), re.IGNORECASE)
        result = pattern.sub(f'<span class="highlight-client">{url}</span>', result)
    
    # URLs partenaires (vert)
    for partner in config.get("urls_partenaires", []):
        if partner:
            pattern = re.compile(re.escape(partner), re.IGNORECASE)
            result = pattern.sub(f'<span class="highlight-client">{partner}</span>', result)
    
    # Mots signatures (jaune)
    for kw in config.get("mots_signatures", []):
        if kw and kw.strip():
            pattern = re.compile(re.escape(kw.strip()), re.IGNORECASE)
            result = pattern.sub(f'<span class="highlight-keyword">{kw.strip()}</span>', result)
    
    # Concurrents (rouge)
    if all_sources:
        for src in all_sources:
            if classify_source(src, config) == "concurrent":
                pattern = re.compile(re.escape(src), re.IGNORECASE)
                result = result.replace(src, f'<span class="highlight-concurrent">{src}</span>')
    
    return result

def generate_recommendations(metrics, sources_df, config):
    """Génère des recommandations automatiques"""
    recommendations = []
    
    taux = metrics['taux_citation']
    part_voix = metrics['part_voix']
    
    # Recommandations basées sur le taux de citation
    if taux < 50:
        recommendations.append({
            "icon": "🎯",
            "title": "Améliorer votre référencement IA",
            "content": "Créez du contenu qui répond directement aux questions des utilisateurs. Les IA privilégient les sources qui apportent des réponses claires et structurées."
        })
    
    # Recommandations basées sur la part de voix
    if part_voix < 15:
        concurrents = sources_df[sources_df['type'] == 'concurrent'].head(3)
        if len(concurrents) > 0:
            top_conc = ", ".join(concurrents['source'].tolist())
            recommendations.append({
                "icon": "🥊",
                "title": "Analyser la concurrence",
                "content": f"Vos principaux concurrents ({top_conc}) sont plus cités. Étudiez leur contenu pour comprendre ce qui les rend plus visibles."
            })
    
    # Recommandations selon l'écart Perplexity/Gemini
    if metrics['taux_pplx'] > metrics['taux_gem'] + 20:
        recommendations.append({
            "icon": "♊",
            "title": "Optimiser pour Gemini",
            "content": "Vous performez moins bien sur Gemini. Ce moteur valorise les contenus bien structurés avec des données factuelles et des sources officielles."
        })
    elif metrics['taux_gem'] > metrics['taux_pplx'] + 20:
        recommendations.append({
            "icon": "⚡",
            "title": "Optimiser pour Perplexity",
            "content": "Vous performez moins bien sur Perplexity. Ce moteur privilégie les contenus récents, les FAQ détaillées et les articles de blog informatifs."
        })
    
    # Recommandation générale si tout va bien
    if taux >= 70 and part_voix >= 20:
        recommendations.append({
            "icon": "🏆",
            "title": "Maintenir votre position",
            "content": "Excellente visibilité ! Continuez à publier du contenu de qualité et surveillez les nouveaux concurrents qui pourraient émerger."
        })
    
    return recommendations

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
    
    # PAGE 1
    elements.append(Paragraph("📡 GEO-Radar Pro - Rapport de Visibilité IA", title_style))
    elements.append(Paragraph(f"Client : {client_name}", subtitle_style))
    elements.append(Paragraph(f"Période : {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}", normal_style))
    elements.append(Spacer(1, 20))
    
    # KPIs
    elements.append(Paragraph("🎯 Métriques de Visibilité", subtitle_style))
    kpi_data = [
        ["Taux de Citation", "Perplexity", "Gemini", "Part de Voix"],
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
    
    # Interprétation
    status, label, interpretation = get_visibility_status(visibility_metrics['taux_citation'])
    elements.append(Paragraph(f"📊 Interprétation : {label}", subtitle_style))
    elements.append(Paragraph(interpretation, normal_style))
    
    elements.append(PageBreak())
    
    # PAGE 2 - Sources
    elements.append(Paragraph("🏆 Top 15 Sources Citées par les IA", title_style))
    
    if len(sources_df) > 0:
        top_sources = sources_df.head(15)
        src_data = [["Source", "Total", "PPLX", "GEM", "Type"]]
        for _, row in top_sources.iterrows():
            type_label = "Client" if row['type'] == 'client' else ("Partenaire" if row['type'] == 'partenaire' else "Concurrent")
            src_data.append([
                row['source'][:30] + "..." if len(row['source']) > 30 else row['source'],
                str(row['total']), str(row['pplx']), str(row['gem']), type_label
            ])
        
        src_table = Table(src_data, colWidths=[6*cm, 2*cm, 2*cm, 2*cm, 3*cm])
        src_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10B981')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ]))
        elements.append(src_table)
    
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
    st.info("💡 Vérifiez que le secret `GOOGLE_JSON_KEY` est bien configuré dans les paramètres Streamlit.")
    st.stop()

# =============================================================================
# 5. SIDEBAR
# =============================================================================
with st.sidebar:
    st.markdown("## 📡 GEO-Radar Pro")
    st.caption("Audit de Visibilité IA")
    
    st.markdown("---")
    
    # Client
    st.markdown("##### 🎯 Sélection Client")
    clients_disponibles = df['Client'].unique().tolist()
    selected_client = st.selectbox("Client", clients_disponibles, label_visibility="collapsed")
    config = get_client_config(selected_client)
    
    st.markdown("---")
    
    # Période
    st.markdown("##### 📅 Période d'analyse")
    min_date = df['Timestamp'].min().date()
    max_date = df['Timestamp'].max().date()
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Du", value=min_date, min_value=min_date, max_value=max_date)
    with col_d2:
        end_date = st.date_input("Au", value=max_date, min_value=min_date, max_value=max_date)
    
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        if st.button("7j", use_container_width=True, help="7 derniers jours"):
            start_date = max_date - timedelta(days=7)
    with col_r2:
        if st.button("30j", use_container_width=True, help="30 derniers jours"):
            start_date = max_date - timedelta(days=30)
    with col_r3:
        if st.button("Tout", use_container_width=True, help="Toute la période"):
            start_date = min_date
    
    st.markdown("---")
    
    # Granularité
    st.markdown("##### ⏱️ Granularité")
    granularity = st.radio("Granularité", ["Jour", "Semaine", "Mois"], horizontal=True, label_visibility="collapsed")
    
    st.markdown("---")
    
    # Config client
    with st.expander("⚙️ Configuration Client", expanded=False):
        st.markdown(f"**URL cible :**")
        st.code(config.get('url_cible', 'Non définie'), language=None)
        
        if config.get('urls_partenaires'):
            st.markdown(f"**Partenaires ({len(config['urls_partenaires'])}) :**")
            for p in config['urls_partenaires'][:5]:
                st.caption(f"• {p}")
        
        st.markdown(f"**Mots signatures ({len(config.get('mots_signatures', []))}) :**")
        st.caption(", ".join(config.get('mots_signatures', [])[:5]) + "...")
    
    st.markdown("---")
    st.caption("💡 Les données sont mises en cache 10 min")

# =============================================================================
# 6. FILTRAGE DES DONNÉES
# =============================================================================
df_client = df[df['Client'] == selected_client].copy()
df_client = filter_by_date(df_client, start_date, end_date)
df_resampled = resample_data(df_client, granularity)

# Analyse
sources_df = analyze_all_sources(df_client, config)
visibility_metrics = calculate_visibility_metrics(df_client, config)

# =============================================================================
# 7. HEADER
# =============================================================================
st.markdown(f"# 📡 Visibilité IA : **{selected_client}**")

# Résumé rapide
status, status_label, status_text = get_visibility_status(visibility_metrics['taux_citation'])
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.caption(f"📅 {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')} • {visibility_metrics['nb_requetes']} requêtes analysées")
with col_h2:
    st.markdown(f"<span class='badge badge-score-{'high' if status == 'excellent' else 'medium' if status in ['good', 'medium'] else 'low'}'>{status_label}</span>", unsafe_allow_html=True)

# =============================================================================
# 8. ONGLETS PRINCIPAUX
# =============================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏆 Sources & Visibilité", 
    "📈 Évolution", 
    "🥊 Concurrence", 
    "🔍 Preuves",
    "📥 Export"
])

# -----------------------------------------------------------------------------
# ONGLET 1 : SOURCES & VISIBILITÉ
# -----------------------------------------------------------------------------
with tab1:
    # Box explicative
    st.markdown("""
    <div class="info-box">
        <div class="info-box-title">💡 Comment lire ce tableau de bord ?</div>
        <p style="margin:0; color: #1e40af;">
        Ce dashboard analyse les <strong>sources citées par les IA</strong> (Perplexity, Gemini) quand un utilisateur pose une question liée à votre activité.
        L'objectif : mesurer si <strong>votre site apparaît</strong> dans les réponses et quelle est votre <strong>part de voix</strong> face aux concurrents.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # KPIs avec explications
    st.markdown('<div class="section-header">🎯 Vos Indicateurs de Visibilité</div>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        status_color = "#10b981" if visibility_metrics['taux_citation'] >= 50 else "#f59e0b" if visibility_metrics['taux_citation'] >= 30 else "#ef4444"
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: {status_color};">{visibility_metrics['taux_citation']:.0f}%</div>
            <div class="kpi-label">Taux de Citation</div>
            <div class="metric-interpret">% de requêtes où vous êtes cité</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: #8b5cf6;">{visibility_metrics['taux_pplx']:.0f}%</div>
            <div class="kpi-label">⚡ Perplexity</div>
            <div class="metric-interpret">Taux sur ce moteur IA</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: #10b981;">{visibility_metrics['taux_gem']:.0f}%</div>
            <div class="kpi-label">♊ Gemini</div>
            <div class="metric-interpret">Taux sur ce moteur IA</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        pv_color = "#10b981" if visibility_metrics['part_voix'] >= 15 else "#f59e0b" if visibility_metrics['part_voix'] >= 8 else "#ef4444"
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color: {pv_color};">{visibility_metrics['part_voix']:.1f}%</div>
            <div class="kpi-label">Part de Voix</div>
            <div class="metric-interpret">Vos citations / Total citations</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Interprétation automatique
    interpretations = get_interpretation_text(visibility_metrics, sources_df, config)
    if interpretations:
        insight_class = "insight-box" if visibility_metrics['taux_citation'] >= 50 else "insight-box warning" if visibility_metrics['taux_citation'] >= 30 else "insight-box danger"
        st.markdown(f"""
        <div class="{insight_class}">
            <strong>📊 Analyse automatique :</strong><br>
            {"<br>".join(interpretations)}
        </div>
        """, unsafe_allow_html=True)
    
    # Légende
    st.markdown("""
    <div class="legend-box">
        <div class="legend-item"><div class="legend-dot" style="background: #10b981;"></div> Votre site (client)</div>
        <div class="legend-item"><div class="legend-dot" style="background: #3b82f6;"></div> Sites partenaires</div>
        <div class="legend-item"><div class="legend-dot" style="background: #ef4444;"></div> Concurrents</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Deux colonnes : Graphique + Tableau
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.markdown('<div class="section-header">📊 Répartition des Citations</div>', unsafe_allow_html=True)
        
        if len(sources_df) > 0:
            type_counts = sources_df.groupby('type')['total'].sum().reset_index()
            type_counts['label'] = type_counts['type'].map({
                'client': f'🟢 {config.get("url_cible", "Votre site")}',
                'partenaire': '🔵 Partenaires',
                'concurrent': '🔴 Concurrents'
            })
            
            fig_pie = px.pie(
                type_counts, 
                values='total', 
                names='label',
                color='type',
                color_discrete_map={
                    'client': '#10b981',
                    'partenaire': '#3b82f6',
                    'concurrent': '#ef4444'
                },
                hole=0.45
            )
            fig_pie.update_layout(
                height=350,
                margin=dict(l=20, r=20, t=30, b=20),
                showlegend=True,
                legend=dict(orientation="h", y=-0.1),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#1e293b')
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
            
            st.caption("💡 Ce graphique montre la proportion de citations entre votre écosystème et vos concurrents.")
        else:
            st.info("Aucune source détectée sur cette période")
    
    with col_right:
        st.markdown('<div class="section-header">🏆 Top 10 Sources Citées</div>', unsafe_allow_html=True)
        
        if len(sources_df) > 0:
            top10 = sources_df.head(10)
            colors_list = ['#10b981' if t == 'client' else '#3b82f6' if t == 'partenaire' else '#ef4444' for t in top10['type']]
            
            fig_bar = go.Figure(go.Bar(
                x=top10['total'],
                y=top10['source'],
                orientation='h',
                marker_color=colors_list,
                text=top10['total'],
                textposition='auto'
            ))
            fig_bar.update_layout(
                height=350,
                margin=dict(l=20, r=20, t=10, b=20),
                yaxis=dict(autorange="reversed"),
                xaxis_title="Nombre de citations",
                showlegend=False,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#1e293b')
            )
            st.plotly_chart(fig_bar, use_container_width=True)
            
            st.caption("💡 Les barres vertes représentent votre site ou partenaires, les rouges vos concurrents.")
    
    # Tableau complet des sources
    st.markdown('<div class="section-header">📋 Tableau Détaillé des Sources</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box" style="background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border-left-color: #64748b;">
        <p style="margin:0; color: #475569; font-size: 13px;">
        <strong>Comment lire ce tableau :</strong> Chaque ligne représente un site web cité par les IA. 
        "Total" = nombre total de citations, "PPLX" = citations par Perplexity, "GEM" = citations par Gemini.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    if len(sources_df) > 0:
        display_df = sources_df.copy()
        display_df['Type'] = display_df['type'].map({
            'client': '🟢 Votre site',
            'partenaire': '🔵 Partenaire', 
            'concurrent': '🔴 Concurrent'
        })
        
        max_total = int(display_df['total'].max()) if len(display_df) > 0 else 10
        st.dataframe(
            display_df[['source', 'total', 'pplx', 'gem', 'Type']].head(20),
            use_container_width=True,
            hide_index=True,
            column_config={
                "source": st.column_config.TextColumn("🌐 Source", width="large"),
                "total": st.column_config.ProgressColumn("📊 Total", min_value=0, max_value=max_total, format="%d"),
                "pplx": st.column_config.NumberColumn("⚡ PPLX", format="%d", help="Citations par Perplexity"),
                "gem": st.column_config.NumberColumn("♊ GEM", format="%d", help="Citations par Gemini"),
                "Type": st.column_config.TextColumn("🏷️ Type")
            }
        )
    
    # Recommandations
    recommendations = generate_recommendations(visibility_metrics, sources_df, config)
    if recommendations:
        st.markdown('<div class="section-header">💡 Recommandations</div>', unsafe_allow_html=True)
        
        for reco in recommendations:
            st.markdown(f"""
            <div class="reco-card">
                <div class="reco-title">{reco['icon']} {reco['title']}</div>
                <div class="reco-content">{reco['content']}</div>
            </div>
            """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# ONGLET 2 : ÉVOLUTION
# -----------------------------------------------------------------------------
with tab2:
    st.markdown("""
    <div class="info-box">
        <div class="info-box-title">📈 Suivi de l'évolution</div>
        <p style="margin:0; color: #1e40af;">
        Ce graphique montre comment vos scores de visibilité évoluent dans le temps. 
        Un score élevé signifie que les IA vous citent plus souvent.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # KPIs scores
    col1, col2, col3, col4 = st.columns(4)
    
    avg_score = df_client['Score_Global'].mean() if len(df_client) > 0 else 0
    avg_pplx = df_client['Score_PPLX'].mean() if len(df_client) > 0 else 0
    avg_gem = df_client['Score_GEM'].mean() if len(df_client) > 0 else 0
    avg_reco = df_client['Note_Recommandation'].astype(float).mean() if len(df_client) > 0 and 'Note_Recommandation' in df_client.columns else 0
    
    with col1:
        st.metric("Score GEO Global", f"{avg_score:.0f}%", help="Moyenne des scores de visibilité sur toutes les requêtes")
    with col2:
        st.metric("Score Perplexity", f"{avg_pplx:.0f}%", help="Score moyen sur Perplexity")
    with col3:
        st.metric("Score Gemini", f"{avg_gem:.0f}%", help="Score moyen sur Gemini")
    with col4:
        stars = "⭐" * int(round(avg_reco))
        st.metric("Recommandation", stars if stars else "—", help="Note moyenne de recommandation (1-5)")
    
    st.markdown('<div class="section-header">📈 Évolution Temporelle</div>', unsafe_allow_html=True)
    
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
            mode='lines+markers', name='⚡ Perplexity',
            line=dict(color='#8B5CF6', width=2, dash='dot')
        ))
        fig.add_trace(go.Scatter(
            x=df_evolution['Periode'], y=df_evolution['Score_GEM'],
            mode='lines+markers', name='♊ Gemini',
            line=dict(color='#10B981', width=2, dash='dot')
        ))
        fig.update_layout(
            template="plotly_white",
            height=400,
            legend=dict(orientation="h", y=1.1),
            hovermode='x unified',
            yaxis_title="Score (%)",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='white',
            font=dict(color='#1e293b'),
            xaxis_title="Période"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.caption("💡 La ligne pleine représente le score global, les lignes pointillées les scores par moteur IA.")
    else:
        st.info("Pas assez de données pour afficher l'évolution")
    
    # Performance par requête
    st.markdown('<div class="section-header">🎯 Détail par Requête</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box" style="background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border-left-color: #64748b;">
        <p style="margin:0; color: #475569; font-size: 13px;">
        <strong>Score GEO :</strong> Un score de 100% signifie que vous êtes parfaitement cité. 
        Un score < 50% indique que vous n'apparaissez pas ou peu dans la réponse.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    if len(df_client) > 0:
        st.dataframe(
            df_client[['Mot_Cle', 'Score_Global', 'Score_PPLX', 'Score_GEM', 'Note_Recommandation', 'Concurrent_Principal']].sort_values('Score_Global', ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Mot_Cle": st.column_config.TextColumn("📝 Requête", width="large"),
                "Score_Global": st.column_config.ProgressColumn("🎯 Score", min_value=0, max_value=100, format="%d%%"),
                "Score_PPLX": st.column_config.ProgressColumn("⚡ PPLX", min_value=0, max_value=100, format="%d%%"),
                "Score_GEM": st.column_config.ProgressColumn("♊ GEM", min_value=0, max_value=100, format="%d%%"),
                "Note_Recommandation": st.column_config.NumberColumn("⭐ Reco", format="%d"),
                "Concurrent_Principal": st.column_config.TextColumn("🥊 Concurrent")
            }
        )

# -----------------------------------------------------------------------------
# ONGLET 3 : CONCURRENCE
# -----------------------------------------------------------------------------
with tab3:
    st.markdown("""
    <div class="info-box">
        <div class="info-box-title">🥊 Analyse de la concurrence</div>
        <p style="margin:0; color: #1e40af;">
        Découvrez quels sont vos principaux concurrents dans les réponses IA et sur quelles requêtes ils vous devancent.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    if len(sources_df) > 0:
        concurrents_df = sources_df[sources_df['type'] == 'concurrent'].head(10)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('<div class="section-header">🏴‍☠️ Top Concurrents</div>', unsafe_allow_html=True)
            
            if len(concurrents_df) > 0:
                fig_conc = go.Figure(go.Bar(
                    x=concurrents_df['total'],
                    y=concurrents_df['source'],
                    orientation='h',
                    marker_color='#ef4444',
                    text=concurrents_df['total'],
                    textposition='auto'
                ))
                fig_conc.update_layout(
                    height=400,
                    yaxis=dict(autorange="reversed"),
                    xaxis_title="Nombre de citations",
                    margin=dict(l=20, r=20, t=10, b=40),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#1e293b')
                )
                st.plotly_chart(fig_conc, use_container_width=True)
                
                st.caption("💡 Ces sites sont vos principaux concurrents dans les réponses IA.")
            else:
                st.success("🎉 Aucun concurrent majeur détecté !")
        
        with col2:
            st.markdown('<div class="section-header">⚡ vs ♊ Par Concurrent</div>', unsafe_allow_html=True)
            
            if len(concurrents_df) > 0:
                fig_compare = go.Figure()
                fig_compare.add_trace(go.Bar(
                    name='⚡ Perplexity',
                    x=concurrents_df['source'],
                    y=concurrents_df['pplx'],
                    marker_color='#8B5CF6'
                ))
                fig_compare.add_trace(go.Bar(
                    name='♊ Gemini',
                    x=concurrents_df['source'],
                    y=concurrents_df['gem'],
                    marker_color='#10B981'
                ))
                fig_compare.update_layout(
                    barmode='group',
                    height=400,
                    xaxis_tickangle=-45,
                    margin=dict(l=20, r=20, t=10, b=100),
                    legend=dict(orientation="h", y=1.1),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#1e293b')
                )
                st.plotly_chart(fig_compare, use_container_width=True)
                
                st.caption("💡 Comparez la présence de chaque concurrent sur les deux moteurs IA.")
    
    # Tableau concurrents par requête
    st.markdown('<div class="section-header">🎯 Concurrent Principal par Requête</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box" style="background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border-left-color: #ef4444;">
        <p style="margin:0; color: #991b1b; font-size: 13px;">
        <strong>Concurrent Principal :</strong> Le site le plus visible dans la réponse IA pour chaque requête. 
        Si votre score est bas, c'est ce concurrent qui capte l'attention.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    if 'Concurrent_Principal' in df_client.columns and len(df_client) > 0:
        conc_data = df_client[['Mot_Cle', 'Score_Global', 'Concurrent_Principal']].copy()
        conc_data['Statut'] = conc_data['Score_Global'].apply(
            lambda x: '🏆 Vous gagnez' if x >= 50 else '⚠️ Concurrent devant'
        )
        
        st.dataframe(
            conc_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Mot_Cle": st.column_config.TextColumn("📝 Requête", width="large"),
                "Score_Global": st.column_config.ProgressColumn("🎯 Votre Score", min_value=0, max_value=100, format="%d%%"),
                "Concurrent_Principal": st.column_config.TextColumn("🏴‍☠️ Concurrent"),
                "Statut": st.column_config.TextColumn("📊 Résultat")
            }
        )

# -----------------------------------------------------------------------------
# ONGLET 4 : PREUVES
# -----------------------------------------------------------------------------
with tab4:
    st.markdown("""
    <div class="info-box">
        <div class="info-box-title">🔍 Explorateur de Preuves</div>
        <p style="margin:0; color: #1e40af;">
        Consultez les réponses brutes des IA pour chaque requête. 
        Le surlignage vous aide à repérer rapidement les éléments importants.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Légende du surlignage
    st.markdown("""
    <div class="legend-box">
        <div class="legend-item"><span class="highlight-client">Votre site</span> = URL cible ou partenaire détecté</div>
        <div class="legend-item"><span class="highlight-keyword">Mot-clé</span> = Terme signature de votre marque</div>
        <div class="legend-item"><span class="highlight-concurrent">Concurrent</span> = Site concurrent cité</div>
    </div>
    """, unsafe_allow_html=True)
    
    if len(df_client) > 0:
        # Sélection de la requête
        requetes = df_client['Mot_Cle'].unique().tolist()
        selected_query = st.selectbox("📝 Sélectionner une requête à analyser :", requetes)
        
        entry = df_client[df_client['Mot_Cle'] == selected_query].iloc[0]
        parsed_sources = parse_sources(entry.get('Sources_Detectees', ''))
        
        # Résumé de la requête
        col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
        with col_sum1:
            score_class = "high" if entry['Score_Global'] >= 50 else "medium" if entry['Score_Global'] >= 30 else "low"
            st.markdown(f"<div style='text-align:center;'><span class='badge badge-score-{score_class}' style='font-size:16px;'>{entry['Score_Global']}%</span><br><small>Score Global</small></div>", unsafe_allow_html=True)
        with col_sum2:
            is_pplx = entry['Score_PPLX'] >= 50
            st.markdown(f"<div style='text-align:center;'><span class='{'citation-yes' if is_pplx else 'citation-no'}'>{'✅ Cité' if is_pplx else '❌ Non cité'}</span><br><small>Perplexity</small></div>", unsafe_allow_html=True)
        with col_sum3:
            is_gem = entry['Score_GEM'] >= 50
            st.markdown(f"<div style='text-align:center;'><span class='{'citation-yes' if is_gem else 'citation-no'}'>{'✅ Cité' if is_gem else '❌ Non cité'}</span><br><small>Gemini</small></div>", unsafe_allow_html=True)
        with col_sum4:
            conc = entry.get('Concurrent_Principal', 'N/A')
            st.markdown(f"<div style='text-align:center;'><span class='badge badge-concurrent'>{conc if conc != 'N/A' else '—'}</span><br><small>Concurrent</small></div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Sources détectées
        st.markdown("##### 📋 Sources citées dans les réponses")
        col_src1, col_src2 = st.columns(2)
        
        with col_src1:
            st.markdown("**⚡ Perplexity**")
            if parsed_sources['PPLX']:
                for src in parsed_sources['PPLX']:
                    src_type = classify_source(src, config)
                    st.markdown(f"<span class='badge badge-{src_type}'>{src}</span>", unsafe_allow_html=True)
            else:
                st.caption("Aucune source détectée")
        
        with col_src2:
            st.markdown("**♊ Gemini**")
            if parsed_sources['GEM']:
                for src in parsed_sources['GEM']:
                    src_type = classify_source(src, config)
                    st.markdown(f"<span class='badge badge-{src_type}'>{src}</span>", unsafe_allow_html=True)
            else:
                st.caption("Aucune source détectée")
        
        st.markdown("---")
        
        # Réponses complètes
        st.markdown("##### 📄 Réponses complètes des IA")
        
        all_sources = parsed_sources['PPLX'] + parsed_sources['GEM']
        
        col_pplx, col_gem = st.columns(2)
        
        with col_pplx:
            st.markdown(f"""
            <div class="motor-header pplx">
                <span>⚡ Perplexity</span>
                <span>Score : {entry['Score_PPLX']}%</span>
            </div>
            """, unsafe_allow_html=True)
            
            text = highlight_text_advanced(entry.get('Texte_PPLX', ''), config, all_sources)
            st.markdown(f'<div class="reponse-ia">{text if text else "<em>Aucune réponse disponible</em>"}</div>', unsafe_allow_html=True)
        
        with col_gem:
            st.markdown(f"""
            <div class="motor-header gem">
                <span>♊ Gemini</span>
                <span>Score : {entry['Score_GEM']}%</span>
            </div>
            """, unsafe_allow_html=True)
            
            text_g = highlight_text_advanced(entry.get('Texte_GEM', ''), config, all_sources)
            st.markdown(f'<div class="reponse-ia">{text_g if text_g else "<em>Aucune réponse disponible</em>"}</div>', unsafe_allow_html=True)
    else:
        st.warning("Aucune donnée disponible pour cette période")

# -----------------------------------------------------------------------------
# ONGLET 5 : EXPORT
# -----------------------------------------------------------------------------
with tab5:
    st.markdown("""
    <div class="info-box">
        <div class="info-box-title">📥 Export des données</div>
        <p style="margin:0; color: #1e40af;">
        Téléchargez vos données pour les analyser dans Excel, les partager avec votre équipe ou les intégrer dans vos rapports.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="section-header">📄 Rapport PDF</div>', unsafe_allow_html=True)
        
        st.markdown("""
        Le rapport PDF inclut :
        - ✅ Métriques de visibilité
        - ✅ Interprétation automatique
        - ✅ Top 15 sources citées
        - ✅ Graphiques et tableaux
        """)
        
        if st.button("🔄 Générer le rapport PDF", type="primary", use_container_width=True):
            with st.spinner("Génération en cours..."):
                try:
                    pdf = generate_pdf_report(
                        df_client, selected_client, config,
                        visibility_metrics, sources_df,
                        start_date, end_date
                    )
                    st.download_button(
                        "📥 Télécharger le PDF",
                        data=pdf,
                        file_name=f"GEO-Radar_{selected_client}_{start_date}_{end_date}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    st.success("✅ Rapport généré !")
                except ImportError:
                    st.error("⚠️ Installez `reportlab` : `pip install reportlab`")
                except Exception as e:
                    st.error(f"❌ Erreur : {e}")
    
    with col2:
        st.markdown('<div class="section-header">📊 Export CSV</div>', unsafe_allow_html=True)
        
        st.markdown("Téléchargez les données brutes pour analyse avancée :")
        
        if len(df_client) > 0:
            csv_data = df_client.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Données complètes",
                data=csv_data,
                file_name=f"GEO-Radar_data_{selected_client}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        if len(sources_df) > 0:
            csv_sources = sources_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Analyse des sources",
                data=csv_sources,
                file_name=f"GEO-Radar_sources_{selected_client}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        st.markdown("---")
        st.caption("💡 Les fichiers CSV s'ouvrent dans Excel, Google Sheets ou tout tableur.")

# =============================================================================
# FOOTER
# =============================================================================
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns([1, 2, 1])
with col_f2:
    st.markdown(f"""
    <div style="text-align: center; color: #94a3b8; font-size: 12px;">
        📡 <strong>GEO-Radar Pro</strong> — Audit de Visibilité IA<br>
        Dernière MAJ : {df['Timestamp'].max().strftime('%d/%m/%Y %H:%M')}
    </div>
    """, unsafe_allow_html=True)

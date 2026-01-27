# CLAUDE.md - Guide du Projet GEO-Radar

## Aperçu du Projet

GEO-Radar est un **Outil d'Audit de Visibilité IA** qui surveille comment les sites web sont cités par les moteurs IA (Perplexity et Google Gemini) en réponse aux requêtes de recherche. Il aide les clients à suivre leur visibilité en ligne dans les réponses générées par l'IA, mesurer la fréquence des citations, analyser le positionnement concurrentiel et générer des rapports détaillés.

**Cas d'usage principal** : Professionnels du SEO, stratèges de contenu et équipes marketing suivant comment les systèmes IA référencent leurs sites web.

**Langue** : L'interface utilisateur et les commentaires du code sont principalement en français.

## Structure du Code

```
GEO-Radar/
├── app.py                 # Application principale du tableau de bord Streamlit (~1500 lignes)
├── monitor.py             # Script de surveillance/scan automatisé (~125 lignes)
├── requirements.txt       # Dépendances Python
├── README.md              # Description basique du projet
├── .gitignore             # Configuration Git ignore
├── .devcontainer/
│   └── devcontainer.json  # Config GitHub Codespaces/VS Code dev container
└── .github/
    └── workflows/
        └── daily.yml      # Workflow GitHub Actions pour scan quotidien
```

## Fichiers Clés

### app.py - Application Tableau de Bord
L'application web Streamlit principale fournissant :
- **Interface multi-onglets** : Sources & Visibilité, Évolution, Concurrence, Preuves, Export
- **Visualisation des données** : Cartes KPI, graphiques via Plotly
- **Configuration clients** : Configs codées en dur pour les clients SPF, Conforama, IKEA
- **Génération de rapports PDF** : Utilise ReportLab pour l'export
- **Intégration Google Sheets** : Lecture depuis le classeur `GEO-Radar_DATA`

**Fonctions Clés** :
- `get_data()` : Récupère et met en cache les données Google Sheets (TTL 10 min)
- `analyze_all_sources()` : Classifie les sources citées comme client/partenaire/concurrent
- `calculate_visibility_metrics()` : Calcule les taux de citation et part de voix
- `generate_recommendations()` : Génère automatiquement des recommandations stratégiques
- `generate_pdf_report()` : Crée des rapports PDF exportables
- `highlight_text_advanced()` : Surlignage HTML pour l'analyse de texte

### monitor.py - Scanner Automatisé
Script léger pour les scans programmés :
- Interroge l'API Perplexity (modèle `sonar`) et l'API Google Gemini (`gemini-1.5-flash`)
- Calcule les scores de visibilité GEO (échelle 0-100)
- Enregistre les résultats dans la feuille Google Sheets `LOGS_RESULTATS`

**Fonctions Clés** :
- `connect_sheets()` : Authentification OAuth2 vers Google Sheets
- `ask_ai_advanced()` : Interroge les moteurs IA avec des prompts structurés
- `parse_metadata()` : Extrait sources, scores de recommandation, concurrents
- `calculate_geo_score()` : Score basé sur mention officielle (50pts), partenaire (20pts), mots-clés (jusqu'à 30pts)

## Stack Technologique

| Technologie | Utilisation |
|-------------|-------------|
| Streamlit | Framework UI web |
| Pandas | Manipulation de données |
| Plotly | Visualisations interactives |
| gspread | Client API Google Sheets |
| google-generativeai | SDK API Gemini |
| ReportLab | Génération PDF |
| requests | Client HTTP (API Perplexity) |

## Services Externes

- **API Google Sheets** : Stockage des données (classeur `GEO-Radar_DATA`)
- **API Google Drive** : Permissions des fichiers
- **API Perplexity AI** : Réponses IA via modèle Sonar
- **API Google Gemini** : Réponses IA via gemini-1.5-flash

## Workflows de Développement

### Développement Local
```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le tableau de bord
streamlit run app.py --server.port 8501

# Lancer le monitor manuellement (nécessite les secrets configurés)
python monitor.py
```

### GitHub Codespaces / Dev Container
Le fichier `.devcontainer/devcontainer.json` configure :
- Environnement Python 3.11
- Installation automatique des requirements
- Démarrage automatique de Streamlit sur le port 8501
- CORS/CSRF désactivés pour le développement

### Scan Automatisé
Le workflow GitHub Actions (`.github/workflows/daily.yml`) :
- S'exécute quotidiennement à 08:00 UTC
- Peut être déclenché manuellement via workflow_dispatch
- Exécute `monitor.py` avec les secrets GitHub

## Secrets/Variables d'Environnement Requis

| Secret | Description |
|--------|-------------|
| `GOOGLE_JSON_KEY` | JSON du compte de service pour API Google Sheets/Drive |
| `PERPLEXITY_API_KEY` | Clé API Perplexity AI |
| `GEMINI_API_KEY` | Clé API Google Gemini |
| `MISTRAL_API_KEY` | Clé API Mistral (configurée mais pas utilisée activement) |

Les secrets sont accessibles via `st.secrets` (gestion des secrets Streamlit) ou variables d'environnement dans GitHub Actions.

## Architecture du Flux de Données

```
┌─────────────────────┐
│  GitHub Actions     │ (Quotidien à 08:00 UTC)
│  exécute monitor.py │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │             │
┌───▼───┐   ┌────▼────┐
│Perplexity  │ Gemini  │
│   API │   │  API    │
└───┬───┘   └────┬────┘
    │            │
    └─────┬──────┘
          │
    ┌─────▼─────────┐
    │ Google Sheets │ (feuille LOGS_RESULTATS)
    └─────┬─────────┘
          │
    ┌─────▼─────────┐
    │  Streamlit    │ (Tableau de bord app.py)
    │  Dashboard    │
    └───────────────┘
```

## Conventions Clés

### Style de Code
- **Langue** : Français pour les textes UI, commentaires et noms de variables liés à la logique métier
- **Imports** : Bibliothèque standard d'abord, puis packages tiers
- **Configuration** : Configs clients codées en dur dans le dict `CONFIG_CLIENTS` en haut de app.py
- **Gestion d'erreurs** : Blocs try/except avec valeurs de repli (ex: "Erreur Perplexity")
- **Cache** : Utiliser `@st.cache_data(ttl=600)` pour les fonctions de récupération de données

### Patterns Streamlit
- Layout large : `st.set_page_config(layout="wide")`
- CSS personnalisé via `st.markdown()` avec balises `<style>`
- Sidebar pour sélection client/filtres
- Onglets via `st.tabs()` pour la navigation
- Session state pour les sélections persistantes

### Conventions de Nommage
- `url_cible` : URL cible (site web du client)
- `urls_partenaires` : URLs des partenaires/alliés
- `mots_signatures` : Mots-clés signatures pour l'analyse sémantique
- `concurrent` : Concurrent
- `GEO score` : Métrique de visibilité (0-100)

### Structure Google Sheets
- Classeur : `GEO-Radar_DATA`
- Feuilles :
  - `CONFIG_CIBLES` : Configuration clients (Mot_Cle, URL_Cible, URLs_Partenaires, Mots_Signatures)
  - `LOGS_RESULTATS` : Résultats des scans avec horodatages, scores, réponses IA

## Tâches Courantes

### Ajouter un Nouveau Client
1. Ajouter la config client au dict `CONFIG_CLIENTS` dans `app.py` :
```python
"NouveauClient": {
    "url_cible": "nouveauclient.com",
    "urls_partenaires": ["partenaire1.com", "partenaire2.com"],
    "mots_signatures": ["motcle1", "motcle2"],
    "couleur": "#HEXCOLOR"
}
```
2. Ajouter les lignes correspondantes à la feuille `CONFIG_CIBLES` dans Google Sheets

### Modifier les Prompts IA
Éditer le template `prompt` dans la fonction `ask_ai_advanced()` dans `monitor.py`

### Ajouter de Nouvelles Métriques/Graphiques
- Ajouter les nouveaux calculs de métriques dans les fonctions concernées de `app.py`
- Créer les visualisations avec Plotly (`px.line()`, `px.bar()`, `px.pie()`, etc.)
- Ajouter à la section d'onglet appropriée

### Changer la Programmation des Scans
Éditer l'expression cron dans `.github/workflows/daily.yml` :
```yaml
schedule:
  - cron: '0 8 * * *'  # Format: minute heure jour mois jour_semaine
```

## Considérations de Test

- Pas de tests automatisés actuellement dans le codebase
- Tests manuels via l'UI Streamlit
- Surveiller les logs dans GitHub Actions pour les exécutions programmées
- Google Sheets sert de piste d'audit des données

## Points d'Attention et Notes

1. **Accès aux secrets** : Dans Streamlit, utiliser `st.secrets["KEY"]` ; dans GitHub Actions, les secrets sont des variables d'environnement
2. **Limitation de débit** : Délai de 2 secondes entre les requêtes dans monitor.py (`time.sleep(2)`)
3. **Calcul du score** : Score max de 100 (plafonné dans `calculate_geo_score()`)
4. **Génération PDF** : Utilise ReportLab avec style personnalisé ; inclut les graphiques Plotly en images
5. **Cache des données** : Le tableau de bord met en cache les données pendant 10 minutes pour réduire les appels API
6. **Localisation française** : Tous les textes destinés aux utilisateurs sont en français

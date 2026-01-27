# CLAUDE.md - GEO-Radar Project Guide

## Project Overview

GEO-Radar is an **AI Visibility Audit Tool** that monitors how websites are cited by AI engines (Perplexity and Google Gemini) in response to search queries. It helps clients track their online visibility in AI-generated responses, measure citation frequency, analyze competitive positioning, and generate detailed reports.

**Primary Use Case**: SEO professionals, content strategists, and marketing teams tracking how AI systems reference their websites.

**Language**: The application UI and code comments are primarily in French.

## Codebase Structure

```
GEO-Radar/
├── app.py                 # Main Streamlit dashboard application (~1500 lines)
├── monitor.py             # Automated monitoring/scanning script (~125 lines)
├── requirements.txt       # Python dependencies
├── README.md              # Basic project description
├── .gitignore             # Git ignore configuration
├── .devcontainer/
│   └── devcontainer.json  # GitHub Codespaces/VS Code dev container config
└── .github/
    └── workflows/
        └── daily.yml      # GitHub Actions daily scan workflow
```

## Key Files

### app.py - Dashboard Application
The main Streamlit web application providing:
- **Multi-tab interface**: Sources & Visibility, Evolution, Competition, Evidence, Export
- **Data visualization**: KPI cards, charts via Plotly
- **Client configuration**: Hard-coded configs for SPF, Conforama, IKEA clients
- **PDF report generation**: Uses ReportLab for export functionality
- **Google Sheets integration**: Reads from `GEO-Radar_DATA` spreadsheet

**Key Functions**:
- `get_data()`: Fetches and caches Google Sheets data (10-min TTL)
- `analyze_all_sources()`: Classifies cited sources as client/partner/competitor
- `calculate_visibility_metrics()`: Computes citation rates and voice share
- `generate_recommendations()`: Auto-generates strategic recommendations
- `generate_pdf_report()`: Creates exportable PDF reports
- `highlight_text_advanced()`: HTML highlighting for text analysis

### monitor.py - Automated Scanner
Lightweight script for scheduled scans:
- Queries Perplexity API (`sonar` model) and Google Gemini API (`gemini-1.5-flash`)
- Calculates GEO visibility scores (0-100 scale)
- Logs results to Google Sheets `LOGS_RESULTATS` worksheet

**Key Functions**:
- `connect_sheets()`: OAuth2 authentication to Google Sheets
- `ask_ai_advanced()`: Queries AI engines with structured prompts
- `parse_metadata()`: Extracts sources, recommendation scores, competitors
- `calculate_geo_score()`: Scores based on official mention (50pts), partner (20pts), keywords (up to 30pts)

## Technology Stack

| Technology | Purpose |
|------------|---------|
| Streamlit | Web UI framework |
| Pandas | Data manipulation |
| Plotly | Interactive visualizations |
| gspread | Google Sheets API client |
| google-generativeai | Gemini API SDK |
| ReportLab | PDF generation |
| requests | HTTP client (Perplexity API) |

## External Services

- **Google Sheets API**: Data storage (`GEO-Radar_DATA` spreadsheet)
- **Google Drive API**: File permissions
- **Perplexity AI API**: AI responses via Sonar model
- **Google Gemini API**: AI responses via gemini-1.5-flash

## Development Workflows

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard
streamlit run app.py --server.port 8501

# Run the monitor manually (requires secrets configured)
python monitor.py
```

### GitHub Codespaces / Dev Container
The `.devcontainer/devcontainer.json` configures:
- Python 3.11 environment
- Auto-installs requirements
- Starts Streamlit on port 8501 automatically
- CORS/CSRF disabled for development

### Automated Scanning
The GitHub Actions workflow (`.github/workflows/daily.yml`):
- Runs daily at 08:00 UTC
- Can be triggered manually via workflow_dispatch
- Executes `monitor.py` with secrets from GitHub

## Required Secrets/Environment Variables

| Secret | Description |
|--------|-------------|
| `GOOGLE_JSON_KEY` | Service account JSON for Google Sheets/Drive API |
| `PERPLEXITY_API_KEY` | Perplexity AI API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `MISTRAL_API_KEY` | Mistral API key (configured but not actively used) |

Secrets are accessed via `st.secrets` (Streamlit secrets management) or environment variables in GitHub Actions.

## Data Flow Architecture

```
┌─────────────────────┐
│  GitHub Actions     │ (Daily at 08:00 UTC)
│  runs monitor.py    │
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
    │ Google Sheets │ (LOGS_RESULTATS worksheet)
    └─────┬─────────┘
          │
    ┌─────▼─────────┐
    │  Streamlit    │ (app.py Dashboard)
    │  Dashboard    │
    └───────────────┘
```

## Key Conventions

### Code Style
- **Language**: French for UI text, comments, and variable names related to business logic
- **Imports**: Standard library first, then third-party packages
- **Configuration**: Hard-coded client configs in `CONFIG_CLIENTS` dict at top of app.py
- **Error handling**: Try/except blocks with fallback values (e.g., "Erreur Perplexity")
- **Caching**: Use `@st.cache_data(ttl=600)` for data fetching functions

### Streamlit Patterns
- Wide layout: `st.set_page_config(layout="wide")`
- Custom CSS via `st.markdown()` with `<style>` tags
- Sidebar for client/filter selection
- Tabs via `st.tabs()` for navigation
- Session state for persistent selections

### Naming Conventions
- `url_cible`: Target URL (client's website)
- `urls_partenaires`: Partner/ally URLs
- `mots_signatures`: Signature keywords for semantic analysis
- `concurrent`: Competitor
- `GEO score`: Visibility metric (0-100)

### Google Sheets Structure
- Spreadsheet: `GEO-Radar_DATA`
- Worksheets:
  - `CONFIG_CIBLES`: Client configuration (Mot_Cle, URL_Cible, URLs_Partenaires, Mots_Signatures)
  - `LOGS_RESULTATS`: Scan results with timestamps, scores, AI responses

## Common Tasks

### Adding a New Client
1. Add client config to `CONFIG_CLIENTS` dict in `app.py`:
```python
"NewClient": {
    "url_cible": "newclient.com",
    "urls_partenaires": ["partner1.com", "partner2.com"],
    "mots_signatures": ["keyword1", "keyword2"],
    "couleur": "#HEXCOLOR"
}
```
2. Add corresponding rows to `CONFIG_CIBLES` worksheet in Google Sheets

### Modifying AI Prompts
Edit the `prompt` template in `ask_ai_advanced()` function in `monitor.py`

### Adding New Metrics/Charts
- Add new metric calculations in relevant functions in `app.py`
- Create visualizations using Plotly (`px.line()`, `px.bar()`, `px.pie()`, etc.)
- Add to appropriate tab section

### Changing Scan Schedule
Edit cron expression in `.github/workflows/daily.yml`:
```yaml
schedule:
  - cron: '0 8 * * *'  # Format: minute hour day month weekday
```

## Testing Considerations

- No automated tests currently in the codebase
- Manual testing via Streamlit UI
- Monitor logs in GitHub Actions for scheduled runs
- Google Sheets serves as data audit trail

## Gotchas and Notes

1. **Secrets access**: In Streamlit, use `st.secrets["KEY"]`; in GitHub Actions, secrets are environment variables
2. **Rate limiting**: 2-second delay between queries in monitor.py (`time.sleep(2)`)
3. **Score calculation**: Max score is 100 (capped in `calculate_geo_score()`)
4. **PDF generation**: Uses ReportLab with custom styling; includes Plotly charts as images
5. **Data caching**: Dashboard caches data for 10 minutes to reduce API calls
6. **French localization**: All user-facing text is in French

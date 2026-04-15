# Alpha Agent

AI-powered freelance job auto-apply agent. Scans job platforms, scores offers against your profile using AI, generates personalized proposals, and submits applications automatically.

## How It Works

```
Scan job platforms  -->  AI scores relevance  -->  Generate proposal  -->  Auto-apply
      |                       |                        |                      |
  Freework API          Gemini 2.5 Flash        Personalized message     Playwright
  (+ more platforms)    via Vertex AI            based on your CV         headless browser
```

1. **Scan** - Queries job platforms via API using your configured search terms
2. **Score** - AI evaluates each job against your profile (skills, experience, preferences) and assigns a relevance score (0-100)
3. **Generate** - For qualified jobs (score >= threshold), AI writes a personalized application message
4. **Apply** - Submits the application via headless browser automation
5. **Track** - Logs everything to Google Sheets and a local SQLite database

## Supported Platforms

| Platform | Scraper | Auto-Apply |
|----------|---------|------------|
| Free-Work | Yes | Yes |
| LinkedIn | Yes | Planned |
| HelloWork | Yes | Planned |
| Collective | Yes | Planned |

## Quick Start

### Prerequisites

- Python 3.11+
- Google Chrome installed
- A Free-Work account with a completed profile (CV uploaded)

### Installation

```bash
git clone https://github.com/Alphabii/Alpha-Agent.git
cd Alpha-Agent

python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt
playwright install chromium
```

### Configuration

```bash
cp .env.example .env
```

Edit `.env` with your credentials, profile info, and preferences. See [Configuration](#configuration-details) below.

Add your CV/profile in `profile.md` at the project root (markdown format).

### Usage

**Single scan** - Find and apply to recent jobs:
```bash
python -m src.main scan --platform freework --freshness 24h
```

**Continuous watch** - Scan on an interval:
```bash
python -m src.main watch
```

**Check status** - View stats and configuration:
```bash
python -m src.main status
```

**Web dashboard** - Launch the monitoring UI:
```bash
python -m src.main web --port 5050
```

**Manual login** - Save browser session interactively:
```bash
python -m src.main login freework
```

**Extract cookies** - Export session cookies for headless deployment:
```bash
python -m src.main extract-cookies freework
```

### CLI Options

```bash
python -m src.main scan [OPTIONS]

Options:
  -p, --platform TEXT     Scan a specific platform only (e.g., freework)
  -q, --query TEXT        Search keywords (overrides SEARCH_QUERIES)
  -c, --contracts TEXT    Contract types, comma-separated: freelance,cdi,cdd
  -f, --freshness TEXT    Publication date filter: 24h, 7d, 14d, 30d
  -r, --remote TEXT       Remote filter: full, partial, no
  -l, --location TEXT     Location filter
  --max-pages INTEGER     Max pages to scrape per query (default: 3)
```

## Configuration Details

### AI Provider

The agent uses AI for job scoring and proposal generation. Three providers are supported:

| Provider | Model | Config |
|----------|-------|--------|
| Vertex AI | Gemini 2.5 Flash | `AI_PROVIDER=vertex` + GCP service account |
| Google Gemini | Gemini | `AI_PROVIDER=gemini` + API key |
| OpenAI | GPT-4.1 Mini | `AI_PROVIDER=openai` + API key |

### Search Queries

Configure multiple search terms in `.env` to run separate queries per scan:

```
SEARCH_QUERIES=["Data Analyst","BI Consultant","Analytics Engineer","Power BI Developer"]
```

### Authentication

The agent authenticates to Free-Work via a REST API call (fully headless). No visible browser window is needed. On first run, it logs in automatically using `FREEWORK_EMAIL` and `FREEWORK_PASSWORD`.

For cloud/remote deployment, you can pre-fill session cookies in `.env`:
```
FREEWORK_JWT_HP=eyJ...
FREEWORK_JWT_S=abc...
FREEWORK_REFRESH_TOKEN=def...
```

Use `python -m src.main extract-cookies freework` to export cookies from an existing session.

### Google Sheets Tracking

To enable Google Sheets tracking:

1. Create a GCP service account with Sheets API enabled
2. Share your Google Sheet with the service account email
3. Set `GOOGLE_SERVICE_ACCOUNT_PATH` in `.env`

## Project Structure

```
Alpha-Agent/
  src/
    ai/              # AI scoring & proposal generation
      analyzer.py    # Job relevance scoring
      generator.py   # Application message generation
      prompts.py     # AI prompt templates
    applicator/      # Platform-specific auto-apply logic
      freework.py    # Free-Work applicator (API login + Playwright)
    scrapers/        # Platform-specific job scrapers
      freework.py    # Free-Work API scraper
    web/             # Flask web dashboard
    scheduler/       # Continuous scan runner
    utils/
      browser.py     # Playwright browser manager (stealth mode)
    config.py        # Settings from .env
    pipeline.py      # Scan -> Score -> Generate -> Apply pipeline
    db.py            # SQLite database operations
    sheets.py        # Google Sheets integration
    main.py          # CLI entry point (Typer)
  profile.md         # Your CV in markdown format
  .env               # Credentials & config (not committed)
  .env.example       # Template for .env
```

## License

Private repository. All rights reserved.

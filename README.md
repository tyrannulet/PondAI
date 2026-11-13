# PondWatch AI

PondWatch AI is a Streamlit app for exploring Czech ponds, reservoirs, and other mapped water bodies using satellite data. It accepts natural-language requests in English or Czech, searches RÚIAN and ZABAGED, and provides a plain-language report by default. Charts and measurement tables are optional.

## Features

- Search ponds, reservoirs, lakes, or all mapped water bodies in a Czech municipality.
- Analyze Sentinel-2 water-surface and optical indicators (NDWI, NDTI, and NDCI).
- Screen for possible ice or snow using Sentinel-2 scene classification. This is not confirmation that a water surface was frozen.
- Select among multiple candidates using a map and a descriptive list.
- Use Featherless AI for request interpretation and tool calling.
- Run in demo mode with simulated values when API credentials are unavailable.

## Agent architecture

- `scripts/config.py` loads configuration from `api/` and checks for placeholders.
- `scripts/geo_sources.py` searches municipalities and water bodies through RÚIAN and ZABAGED.
- `scripts/satellite.py` analyzes Sentinel-2 data and provides algae and possible-ice screening.
- `scripts/agent.py` interprets requests and calls `find_ponds()` and `analyze_pond()`.
- `scripts/app.py` renders the Streamlit interface.
- `scripts/demo_data.py` provides simulated values when real API credentials are unavailable.

## Install dependencies

1. Create a virtual environment:

```bash
python -m venv .venv
```

2. Activate it:

```bash
.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Getting API credentials

### Featherless
- Visit https://featherless.ai.
- Create an account and API key.
- Use the `Qwen/Qwen3-32B` model.

### Copernicus / Sentinel Hub
- Visit https://dataspace.copernicus.eu/.
- Create an account and obtain a `Client ID` and `Client Secret`.
- Add the credentials to `api/copernicus.txt`.

## Where to add credentials

- `api/featherless.txt`
- `api/copernicus.txt`

Environment variables override values from these files. Placeholder values beginning with `PASTE_` are not treated as valid credentials.

## Run the app

From the project root, run:

```bash
streamlit run scripts/app.py
```

## Using the app

- Enter a natural-language request, for example:
  - “Analyze the ponds in Řitka for 2025.”
  - “Find reservoirs in Prague.”
  - “Show charts for this analysis.”
- The app identifies the municipality, water-body type, and date range.
- If multiple candidates are found, select one from the map and list.
- A plain-language report is shown by default; opt into charts and measurements using the checkbox or by asking for charts.

## Demo mode

If real API credentials are unavailable, the app starts in demo mode:

- A warning identifies simulated values; they are not a real satellite analysis.
- The app does not call APIs with fake credentials.
- Demo data do not include ice observations or laboratory water-quality measurements.

## Interpreting results

- NDWI is a spectral indicator of water; classified pixel share is not water depth or volume.
- NDTI and NDCI are optical screening indicators, not laboratory measurements.
- The snow/ice class can flag possible surface ice, but cannot confirm that a water body was frozen.
- Treat all satellite-derived results as screening, not as a health or water-safety assessment.

## Windows launcher

1. Double-click `Spustit PondWatch.bat`.
2. On first run, the script installs missing dependencies from `requirements.txt`.
3. The app opens at [http://localhost:8502](http://localhost:8502). Keep the terminal window open while using the app; closing it stops the server.

Python 3 must be installed.

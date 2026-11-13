# PondWatch AI

PondWatch AI je jednoduchá MVP aplikace pro monitoring českých rybníků ze satelitních dat. Aplikace umí rozpoznat obec a rybník z přirozeného českého dotazu, vyhledat kandidáty v geodatabázích RÚIAN a ZABAGED, zpracovat satelitní signály (NDWI, NDTI a NDCI) a prezentovat výsledky v grafu, tabulce a mapě. Celé rozhraní je v češtině a v demo režimu funguje i bez API klíčů.

## Co aplikace dělá

- rozumí přirozenému českému požadavku,
- hledá obec a rybník v ní,
- analyzuje vodní plochu, optické indikátory vody a biologickou kvalitu,
- zobrazuje výsledky v Streamlit dashboardu,
- používá Featherless AI pro základní agentní logiku a tool calling,
- umožňuje demo režim s realisticky vypadajícími simulovanými daty.

## Architektura agenta

Aplikace je navržena jako jednoduchý MVP bez zbytečných služeb:

- `scripts/config.py` načítá konfigurační soubory z `api/` a kontroluje placeholdery.
- `scripts/geo_sources.py` vyhledává obce a rybníky přes RÚIAN a ZABAGED.
- `scripts/satellite.py` připravuje analýzu Sentinel-2 a experimentální indikaci algální biomasy.
- `scripts/agent.py` interpretuje přirozený prompt a volá lokalní nástroje `find_ponds()` a `analyze_pond()`.
- `scripts/app.py` zobrazuje UI v Streamlit.
- `scripts/demo_data.py` poskytuje simulovaná data, pokud chybí skutečné API klíče.

## Instalace závislostí

1. Vytvořte virtuální prostředí:

```bash
python -m venv .venv
```

2. Aktivujte prostředí:

```bash
.venv\Scripts\activate
```

3. Nainstalujte závislosti:

```bash
pip install -r requirements.txt
```

## Kde získat API klíče

### Featherless
- Otevřete: https://featherless.ai
- Vytvořte účet a API klíč
- Použijte model `Qwen/Qwen3-32B`

### Copernicus / Sentinel Hub
- Otevřete: https://dataspace.copernicus.eu/
- Vytvořte účet a získejte `Client ID` a `Client Secret`
- Poté přidejte údaje do souboru `api/copernicus.txt`

## Kam doplnit klíče

- `api/featherless.txt`
- `api/copernicus.txt`

Přepíše se do proměnných prostředí, pokud je aplikace spouští. Při konfiguraci nesmí být ve hodnotách placeholdery začínající na `PASTE_`.

## Spuštění aplikace

Z kořenové složky projektu spusťte:

```bash
streamlit run scripts/app.py
```

## Ovládání aplikace

- Zadejte přirozený dotaz ve větě, například:
  - „Analyzuj rybník v Řitce za celý rok 2025.“
  - „Jaké jsou optické indikátory vody pro rybník v Řitce?“
- Aplikace rozpozná obec, rybník a časové období.
- Pokud je nalezeno více kandidátů, vyberte konkrétní rybník.
- Výsledky se zobrazí v grafu, mapě a tabulce.

## Demo režim

Pokud nejsou nastavena skutečná API data, aplikace se spustí v demo režimu:

- zobrazuje se varování „DEMO REŽIM – zobrazená data jsou simulovaná, nejde o skutečnou satelitní analýzu“,
- grafy a mapa se načtou z realistických simulovaných dat,
- aplikace nevolá žádné skutečné API s falešnými klíči,
- výsledky jsou označené jako demonstrační a ne jako skutečné měření.

## Bezpečnost a správnost výsledků

- NDWI slouží k odhadu vodní plochy a orientaci při zobrazení vody.
- NDTI je orientační indikátor optických změn souvisejících s suspendovanými látkami.
- NDCI je experimentální indikátor chlorofylu-a a fytoplanktonové biomasy.
- NDCI a NDTI nikdy neznamenají přímé laboratorní měření ani potvrzení cyanotoxinů, patogenů nebo chemické bezpečnosti vody.
- Všechny výsledky je třeba interpretovat jako satelitní screening, nikoli jako zdravotní závěr.

## Rozšíření projektu

PondWatch AI je navržen tak, aby bylo snadné rozšířit o další analýzu biologické kvality vody, zalednění a zlepšené AI interpretace beze změny základní jednoduché architektury.
## Spuštění aplikace ve Windows

1. Dvakrát klikněte na `Spustit PondWatch.bat`.
2. Při prvním spuštění skript nainstaluje chybějící závislosti z `requirements.txt`.
3. Otevře se aplikace v prohlížeči na [http://localhost:8502](http://localhost:8502). Okno terminálu ponechte otevřené, dokud aplikaci používáte; zavřením ji ukončíte.

Skript vyžaduje nainstalovaný Python 3 a spouští se ze složky projektu.

# PondWatch AI

PondWatch AI is a Streamlit app for exploring Czech ponds, reservoirs, and other mapped water bodies using satellite data. It accepts natural-language requests in English or Czech, searches RÚIAN and ZABAGED, and discusses the results in a conversational chat. Charts and measurement tables are optional.

## Features

- Search ponds, reservoirs, lakes, or all mapped water bodies in a Czech municipality.
- Analyze Sentinel-2 water-surface and optical indicators (NDWI, NDTI, and NDCI).
- Screen for possible ice or snow using Sentinel-2 scene classification. This is not confirmation that a water surface was frozen.
- Select among multiple candidates using a map and a descriptive list.
- Use Featherless AI to understand requests in context and write answers based on the actual results, in the user's language.
- Ask follow-up questions, choose a candidate naturally ("take the larger one"), or change the period without repeating the location.
- Run in demo mode with simulated values when API credentials are unavailable.

## Agent architecture

- `scripts/config.py` loads configuration from `api/` and checks for placeholders.
- `scripts/geo_sources.py` searches municipalities and water bodies through RÚIAN and ZABAGED.
- `scripts/satellite.py` analyzes Sentinel-2 data and provides algae and possible-ice screening.
- `scripts/conversation.py` passes recent chat history, the selected water body, candidates, and measurements to Featherless for structured request understanding and conversational replies.
- `scripts/agent.py` validates the requested action, calls `find_ponds()` and `analyze_pond()`, and keeps the conversation's selection and period.
- `scripts/app.py` renders the Streamlit interface.
- `scripts/demo_data.py` provides simulated values when real API credentials are unavailable.

## Conversational analysis

Start with a request such as "Analyze ponds in Řitka for last summer." After choosing a water body, you can continue with "Why do NDWI and water percentage differ?", "Explain it more simply", or "And for 2024?" The model receives the recent conversation and measured values, so an explanation uses existing results; a request for another period runs a new analysis for the selected water body. Asking to show or hide charts updates the display without fetching satellite data again.

The model first returns a structured intent, and the application executes the corresponding search, selection, or analysis once. A second model call writes the answer using the result and available observations. Context is bounded to 12 recent messages, 60 candidates, and 72 representative observations, with statistics computed over the full series. Numerical claims are checked against the supplied context; unsupported numbers trigger one correction attempt. If the model is unavailable or its answer is rejected, the interface explicitly labels the automatic fallback. This check does not validate every possible verbal interpretation of the measurements.

## Install dependencies

1. Create a virtual environment:

```bash
python -m venv .venv
```

2. Activate it on macOS / Linux:

```bash
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
```

3. Install dependencies:

```bash
python -m pip install -r requirements.txt
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
python -m streamlit run scripts/app.py
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

On macOS / Linux, you can also run without activating the environment:

```bash
.venv/bin/python -m streamlit run scripts/app.py
```

The default address is http://localhost:8501; the Windows launcher uses port 8502.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

On Windows, use `.venv\Scripts\python.exe -m unittest discover -s tests -v`.

The default suite uses controlled API responses without making external requests.
It covers request parsing, conversation state, invalid credentials and dates,
satellite errors and missing measurements, reliability, ice screening, demo
identity and period coverage, map geometry, and four Streamlit interface flows.

An optional live integration test searches RÚIAN/ZABAGED, analyzes one water body
for June 2025 with Copernicus, and checks a Featherless follow-up without fetching
the observations again. It requires valid credentials, network access, and uses
API quota. Enable it explicitly on macOS / Linux with:

```bash
PONDAI_LIVE_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_live_integration.py -v
```

On Windows PowerShell, set `$env:PONDAI_LIVE_TESTS = '1'`, run the same unittest
arguments using `.venv\Scripts\python.exe`, then remove the variable with
`Remove-Item Env:PONDAI_LIVE_TESTS`.

## Loading icons

Both loading indicators cycle through 🎣 🐟 🚣 🏊 🛶 🏄 ⛵ 🏖️ 💧 every 1.2 seconds. Reduced-motion preferences show a static icon.

## Historická dokumentace ze starší lokální verze

Následující přílohy zachovávají celé původní README a pracovní kontext. Jde o historii před sloučením, nikoli popis současného kódu. Platný popis aktuálního chování je výše: anglické UI, české i anglické dotazy, slovní report, volitelné grafy a screening možného sněhu/ledu. Starší lokální opravy a testy zde zmíněné nebyly při sloučení převzaty.

<details>
<summary>Původní README</summary>

# PondWatch AI

PondWatch AI je jednoduchá MVP aplikace pro monitoring českých rybníků ze satelitních dat. Aplikace umí rozpoznat obec a rybník z přirozeného českého dotazu, vyhledat kandidáty v geodatabázích RÚIAN a ZABAGED, zpracovat satelitní signály (NDWI, NDTI a NDCI) a prezentovat výsledky v grafu, tabulce a mapě. Celé rozhraní je v češtině a v demo režimu funguje i bez API klíčů.

## Co aplikace dělá

- rozumí přirozenému českému požadavku,
- hledá obec a rybník v ní,
- analyzuje vodní plochu, optické indikátory vody a biologickou kvalitu,
- zobrazuje výsledky v Streamlit dashboardu,
- používá Featherless AI pro rozpoznání obce a interpretaci satelitních grafů,
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

Proměnné prostředí mají přednost před hodnotami v souborech. Prázdné hodnoty, `AAAA` a placeholdery začínající na `PASTE_` se nepovažují za skutečné přihlašovací údaje.

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

## Testování

Z kořene projektu na macOS / Linux spusťte:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Ve Windows použijte `.venv\Scripts\python.exe -m unittest discover -s tests -v`.
Testy pokrývají konfiguraci, parsování data a obce, výběr rybníka, chyby API, statistiky, demo data, geometrii a průchod Streamlit rozhraním.
Používají řízené odpovědi externích služeb a neodesílají API klíče ani nečerpají API kvótu. Živé ověření služeb je samostatný krok.

</details>

<details>
<summary>Původní CONTEXT.md</summary>

# PondWatch AI — pracovní kontext

Záznam významných změn a důvodů jejich provedení. Při dalších úpravách tento soubor průběžně doplňovat. API klíče a tokeny sem nikdy nekopírovat.

## 2026-11-13 — ikonky při přemýšlení

- Oba načítací indikátory (chat i potvrzení rybníka) používají společnou animaci. Po uživatelském zúžení seznamu jsou povolené pouze tyto ikonky: 🎣 🐟 🚣 🏊 🛶 🏄 ⛵ 🏖️ 💧. Odstraněny byly bota, kolo, pták, větvička, košík, stan a pes (původní položky 9–15).
- Ikonky se střídají po 1,2 sekundy pomocí CSS během běžného volání agenta. Indikátor se odstraní i při výjimce; při systémovém omezení animací zůstane první ikonka a text.
- Ověření: všech 6 existujících testů rozhraní v `test_app.py` prošlo; `git diff --check` bez chyb. Testy neověřují časování animace v prohlížeči.

## 2026-11-13 — kontrola chyb a regresní testy

- `AAAA` a prázdné řetězce se rozpoznávají jako placeholdery, aby neaktivovaly volání s neplatnými údaji.
- Přidána společná validace kalendářních dat a pořadí intervalu. Neplatné datum a nepřiměřený relativní počet měsíců vyvolají žádost o opravu místo pádu; samostatné ISO datum označuje jeden den.
- Zrušena duplicitní modelová smyčka, která spouštěla nástroje a jejich výsledky zahazovala. Featherless dál normalizuje obce a interpretuje grafy; výběr a analýzu řídí místní kód. NDCI využívá stejnou satelitní odpověď jako ostatní grafy.
- Chyba Sentinel Hub se předává jako chyba analýzy, ne jako dokončený výsledek. Chybějící hodnoty neprodukují nulový průměr, interval s nulou platných pixelů nemá platné indexy a součet mnoha málo spolehlivých intervalů nezvyšuje spolehlivost. Průměr NDCI už nepoužívá jen první pozorování.
- Výběr kandidáta se odlišuje od zadání data; neplatné číslo zachovává nabídku. Nové hledání ruší starý filtr a staré grafy, včetně hledání jiného rybníka ve stejné obci.
- Demo zachovává identitu a polygon vybraného rybníka, pokrývá celé období a u krátkého období zachová oba konce. Neznámé ID se nenahrazuje jiným demo rybníkem.
- ArcGIS prstence jsou rozlišeny na samostatné polygony a otvory. Mapy podporují MultiPolygon i otvory a přibližné značky leží uvnitř geometrie. ID v ArcGIS dotazu je escapováno.
- Ověření: všech 48 automatických testů prošlo, včetně 6 průchodů UI přes Streamlit AppTest; `compileall`, `pip check` a `git diff --check` bez chyb. Testy externí služby nahrazují a nečerpají kvótu. Příkaz je v README.
- Samostatný živý test: Featherless normalizoval „v Řitce“ na „Řitka“, RÚIAN/ZABAGED vrátily 2 rybníky a analýza největšího za červen 2025 vrátila 2 intervaly včetně interpretace grafů. Jde o ověření integrace, nikoli laboratorní validaci indexů.
- Server na `http://localhost:8502` odpovídá na kontrolu dostupnosti. Konfigurační soubory s API údaji nebyly při testování měněny.

## 2026-11-13 — MVP projektu

- Vytvořena základní struktura `scripts/`, `api/` a `data/` s konfigurací, geodatovými zdroji, satelitní analýzou, agentem, Streamlit UI a simulovanými demo daty. Důvod: dodat spustitelné MVP podle zadání, které funguje i bez API údajů.
- Přidány šablony API konfigurace a `.gitignore` pro skutečné soubory s klíči. Konfigurace kontroluje placeholdery `PASTE_`, aby se neposílaly falešné přihlašovací údaje.
- Implementováno hledání obcí v RÚIAN a rybníků v ZABAGED; více nalezených rybníků se nabízí k výběru, místo náhodného výběru.
- Přidán Sentinel Hub Statistical API, Featherless tool calling, grafy, mapa a tabulka. Demo hodnoty jsou označeny jako simulované.

## 2026-11-13 — ověření skutečných API

- Ověřeno, že Featherless přijímá tool-calling požadavky a Copernicus OAuth vydává token. Tajné hodnoty nebyly vypisovány ani zaznamenány.
- Opraven RÚIAN/ZABAGED dotaz: ArcGIS REST požadavky se posílají přes POST, geometrii obce předáváme v původním EPSG:5514 a geometrii rybníka vracíme v EPSG:4326 pro mapu a Sentinel Hub.
- Podle skutečné odpovědi ZABAGED se název čte z atributu `jmeno` a plocha z `Shape_Area`; bez jména se použije „Bezejmenný rybník“.
- Opraven požadavek Sentinel Hub Statistical API podle oficiální dokumentace: `aggregationInterval`, evalscript ve `aggregation`, intervaly v UTC a samostatný výstup `dataMask`. Statistiky se žádají v nativním rozlišení 20 m, aby výpočet NDCI nepředstíral rozlišení 10 m.
- Živá analýza Řiteckého rybníka v červnu 2025 vrátila pouze 2 platné pixely. Výsledek je proto označen jako málo spolehlivý a není interpretován jako spolehlivá biologická indikace.
- Zalednění z produktu WIC není implementováno. Aplikace na tuto skutečnost upozorňuje a nemá tvrdit, zda byl rybník zamrzlý.

## 2026-11-13 — rozpoznávání dotazů a UI

- Rozšířeno rozpoznávání obce na české předložky `v` i `ve`, doplněny běžné aliasy včetně „Valmez“ a inflektovaného „Valašském Meziříčí“. Důvod: původní parser hledal pouze `v ` a požadavek z konverzace proto nepoznal.
- Zastavuje se zachycení názvu obce před navazující částí věty, například „a řekni…“.
- Relativní období „poslední měsíc“ se převádí na rozsah od stejného dne předchozího měsíce do dneška. Pokud je rybníků víc, systém si vyžádá výběr jednoho.
- Přidán Streamlit spinner „Přemýšlím a připravuji analýzu…“, aby uživatel viděl, že se dotaz zpracovává.
- Pokud je nastaven Copernicus, UI už nepředvyplňuje simulované grafy ani demo rybník. Tím se brání záměně simulovaných hodnot za živá měření.

## 2026-11-13 — výběr rybníka na mapě

- Bezejmenné rybníky se v chatu i seznamu popisují plochou v m² a ha a přibližnými souřadnicemi; souřadnice jsou odvozeny z polygonu a označeny jako přibližné.
- Při více kandidátech se zobrazí mapa polygonů a značek s popisky a dropdown s odpovídajícími popisy. Tlačítko umožní vybrat rybník a navázat analýzou bez psaní pořadového čísla do chatu.
- Relativní intervaly podporují počty měsíců, např. „poslední 3 měsíce“. Kontrola testovacího dotazu určila pro dnešní datum interval 2026-08-13 až 2026-11-13.
- Odpověď výslovně rozlišuje podíl vodní plochy od výšky hladiny a objemu vody; tyto veličiny aplikace přímo neměří.
- Živý test pro Valmez našel čtyři rybníky s polygonem. Ověřen také výběr kandidáta a pokračování analýzou pomocí testovacích návratových dat.

## 2026-11-13 — modelová normalizace obcí

- Před tool-calling krokem Featherless dostane samostatný požadavek na převod vytaženého názvu obce do úředního základního tvaru RÚIAN. Odpověď je strukturovaná jako JSON; například „Řitce“ se převádí na „Řitka“.
- Normalizovaný název se vynutí v argumentech `find_ponds` i v místní záložní cestě, aby model nemohl omylem vyhledávat pouze skloňovaný tvar.
- Při selhání normalizačního API se použije místní parser a zaznamená se pouze typ chyby, nikdy klíč nebo token. Odpověď v chatu zobrazí rozpoznaný základní tvar obce.
- Ověřeno na živém hledání: „rybník v Řitce“ → „Řitka“ → dva rybníky v RÚIAN/ZABAGED.
- Doplněno zpracování celého promptu před tool-callingem. Důvod: věta „v Řitce v roce 2025“ předchozím parserem zachytila chybně jako „Řitce v“ a odpověděla, že obec nezná.
- Parser nyní odděluje i tvary „v roce“ a „v roce 2025“. Živě ověřen přesný požadavek na analýzu rybníku v Řitce za rok 2025: obec normalizována na „Řitka“, rok zachován a nalezeny dva rybníky.

## Ověření a spuštění

- Ověření syntaxe: `python -m compileall -q scripts`.
- Ověření živého vyhledávání: Valašské Meziříčí vrací několik kandidátů z RÚIAN/ZABAGED; pro testovací požadavek „Valmez“ aplikace nabídla 4 rybníky.
- Lokální aplikace byla testována na `http://localhost:8502`.
- API konfigurační soubory jsou v `api/featherless.txt` a `api/copernicus.txt`; do tohoto záznamu se jejich obsah neukládá.

## 2026-11-13 — parsování číselných statistik Sentinel Hub

- Pád při analýze Řiteckého rybníka způsobila textová hodnota statistiky (např. `"0.42"`) v odpovědi Sentinel Hub, kterou kód před zaokrouhlením nepřevedl na číslo.
- Přidán bezpečný převod číselných hodnot i řetězců; nečíselné a nekonečné hodnoty se považují za nedostupná měření. Převod se používá pro indexy, medián, podíl vody i počet pixelů.
- Přidány regresní testy pro číselné řetězce a neplatné hodnoty.

## 2026-11-13 — výpočet podílu vodní plochy

- Živá odpověď Sentinel Hub pro Řitecký rybník uváděla `geometryPixelCount: 1`: polygon byl posílán v EPSG:4326 (stupně), zatímco rozlišení `resx/resy` je v metrech. Jediný pixel způsobil, že průměr binárního příznaku vody mohl být jen 0 % nebo 100 %.
- Geometrie se před statistickým požadavkem převádí do metrického EPSG:3035 a pracuje se v nativním rozlišení 10 m. Přidána závislost `pyproj`.
- Opraven výpočet platných pixelů jako `sampleCount - noDataCount`, v souladu se strukturou odpovědi Statistical API; období bez platných pixelů už nevykazuje falešných 0 %.
- Živé ověření Řiteckého rybníka za 2026-08-13 až 2026-11-13: geometrie pokrývá 89 pixelů místo 1; podíly jsou většinou průběžné hodnoty přibližně 20–38 %, jedno období 0 % a období bez dat je `n/a`.
- Přidán regresní test převodu polygonu do metrického souřadnicového systému a odečítání pixelů v `noDataCount`.

## 2026-11-13 — odborná interpretace satelitních grafů

- Featherless dostává při dokončení analýzy geospaciální kontext rybníka, období, kvality a počtu pixelů i hodnoty časových řad vodního podílu, NDWI, NDTI a NDCI.
- Systémový prompt vymezuje interpretaci jako orientační screening: mísení vody a břehu v 10m pixelech, vliv oblačnosti/stínů/vegetace/sezóny, rozdíl mezi průměrným NDWI a podílem klasifikovaných vodních pixelů a omezení NDTI/NDCI.
- Model má na konci odpovědi projít každý graf, komentovat trend a chybějící data a nevyvozovat nepodložené příčiny, laboratorní kvalitu vody ani zalednění. Interpretace se zobrazuje v chatové odpovědi i pod grafy.
- Pokud AI není nakonfigurována nebo její volání selže, zobrazí se automatické shrnutí číselných trendů místo prázdné sekce; dostupnost AI či její chybu sděluje UI.
- Přidány testy ověřující, že model obdrží geospaciální omezení a měření a že záložní shrnutí projde všechny grafy včetně chybějících dat.
- Živý test Qwen3 odhalil, že výchozí režim přemýšlení spotřeboval limit odpovědi a vracel useknutý text. Pro interpretaci je vypnut přes `chat_template_kwargs.enable_thinking=false`, limit odpovědi zvýšen a neúplný výstup se odmítne ve prospěch úplného datového shrnutí.
- Upřesněno rozlišení mezi 0 % při kladném počtu validních pixelů a chybějícími daty; model nesmí vysvětlovat konkrétní trendy nepodloženými příčinami.
- Do kontextu modelu jsou přidány předpočítané přesné rozsahy a směry. Neúplný nebo spekulativní výstup se nahrazuje datovým shrnutím všech grafů. Živý test Qwen3 vrátil čtyři dokončené části pro vodní podíl, NDWI, NDTI a NDCI.

## 2026-11-13 — oprava filtrů při hledání rybníků

- Příčina falešných výsledků „nenalezen žádný rybník“: stav chatu přenášel název rybníka z předchozího hledání do nové obce, takže ZABAGED výsledky odfiltroval podle starého názvu. Při novém městě nebo požadavku na více/všechny rybníky se nyní ruší starý výběr, filtr i období.
- Parser názvu rybníka zaměňoval větu „rybník ve městě Řitka“ za filtr s názvem „ve městě Řitka“. Rozpoznává nyní jen skutečný název po slově „rybník“ a nepovažuje množné „rybníky“ za jméno; výslovný název (např. „rybník Brčálník v Řitce“) zůstává podporován.
- Doplněny lokální převody „v Praze“ → „Praha“, „v Mníšku pod Brdy“ → „Mníšek pod Brdy“ a rozpoznání „ve městě Řitka“ i bez AI.
- Živě ověřeny všechny tři hlášené dotazy bez Featherless: Praha vrací 245 kandidátů, Mníšek pod Brdy 18 a Řitka 2. U všech je filtr rybníka `None`; rok 2025 se zachová u dotazů, které jej obsahují.
- Přidány regresní testy parseru, výběru obce a zrušení starého filtru při nové lokalitě.

</details>

# PondWatch AI — pracovní kontext

Záznam významných změn a důvodů jejich provedení. Při dalších úpravách tento soubor průběžně doplňovat. API klíče a tokeny sem nikdy nekopírovat.

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
- „Poslední měsíc“ se interpretuje jako klouzavých 30 dní do dnešního data. Pokud je rybníků víc, systém si vyžádá výběr jednoho.
- Přidán Streamlit spinner „Přemýšlím a připravuji analýzu…“, aby uživatel viděl, že se dotaz zpracovává.
- Pokud je nastaven Copernicus, UI už nepředvyplňuje simulované grafy ani demo rybník. Tím se brání záměně simulovaných hodnot za živá měření.

## Ověření a spuštění

- Ověření syntaxe: `python -m compileall -q scripts`.
- Ověření živého vyhledávání: Valašské Meziříčí vrací několik kandidátů z RÚIAN/ZABAGED; pro testovací požadavek „Valmez“ aplikace nabídla 4 rybníky.
- Lokální aplikace byla testována na `http://localhost:8502`.
- API konfigurační soubory jsou v `api/featherless.txt` a `api/copernicus.txt`; do tohoto záznamu se jejich obsah neukládá.

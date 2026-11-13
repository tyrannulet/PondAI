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

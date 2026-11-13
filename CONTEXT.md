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

## 2026-11-13 — oprava filtrů při hledání rybníků

- Příčina falešných výsledků „nenalezen žádný rybník“: stav chatu přenášel název rybníka z předchozího hledání do nové obce, takže ZABAGED výsledky odfiltroval podle starého názvu. Při novém městě nebo požadavku na více/všechny rybníky se nyní ruší starý výběr, filtr i období.
- Parser názvu rybníka zaměňoval větu „rybník ve městě Řitka“ za filtr s názvem „ve městě Řitka“. Rozpoznává nyní jen skutečný název po slově „rybník“ a nepovažuje množné „rybníky“ za jméno; výslovný název (např. „rybník Brčálník v Řitce“) zůstává podporován.
- Doplněny lokální převody „v Praze“ → „Praha“, „v Mníšku pod Brdy“ → „Mníšek pod Brdy“ a rozpoznání „ve městě Řitka“ i bez AI.
- Živě ověřeny všechny tři hlášené dotazy bez Featherless: Praha vrací 245 kandidátů, Mníšek pod Brdy 18 a Řitka 2. U všech je filtr rybníka `None`; rok 2025 se zachová u dotazů, které jej obsahují.
- Přidány regresní testy parseru, výběru obce a zrušení starého filtru při nové lokalitě.

## 2026-11-13 — oprava spouštěcího skriptu a prostředí

- Aktualizován `.gitignore`: přidány `venv/`, `.venv/` a `.idea/`.
- Přidána konfigurace Streamlit (`.streamlit/credentials.toml` a `config.toml`) potlačující interaktivní dotaz na e-mail při prvním spuštění a vypínající telemetrii.
- Upraven dávkový skript `Spustit PondWatch.bat`: přednostně detekuje a používá lokální virtuální prostředí `venv`/`.venv` namísto systémového Pythonu a v případě potřeby automaticky vytvoří `.venv`. Tím se brání selhání instalace závislostí z PyPI.

## 2026-11-13 — English reports, optional charts, water types, and ice screening

- Přeloženo uživatelské rozhraní Streamlitu, výchozí odpovědi a demo texty do angličtiny; parser dál přijímá české dotazy a nově rozumí i běžným anglickým formulacím a období „last N months“.
- Výchozím výsledkem je srozumitelný slovní report s odhadem pokrytí vodou, srovnáním měsíčních NDCI signálů a jasným upozorněním, že satelitní indikátory nejsou laboratorní měření kvality vody. Grafy a tabulka se zobrazí pouze po zapnutí volby nebo žádosti o grafy.
- Ověřený dotaz na ZABAGED vrstvu „Vodní plocha“ našel tyto kódy `typ_vp_k`: 1 přehradní nádrž, 2 rybník, 3 antropogenní jezero, 4 přírodní jezero, 5 výhonová tůně, 6 koupaliště, 7 rybniční sádka, 8 sedimentační nádrž, 9 ostatní vodní plocha a 10 neurčená vodní plocha. Vyhledávání nyní podporuje rybníky, nádrže, jezera a všechny mapované typy; výsledky zobrazují typ vodního útvaru.
- Nakonfigurovaná WIC BYOC kolekce při ověření vrátila HTTP 403, proto aplikace netvrdí, že ji může číst. Pro screening možného ledu používá místo toho třídu „snow/ice“ (SCL 11) v Sentinel-2 a započítá jen intervaly s alespoň 10 platnými pixely a konzervativním prahem 15 % a dvou pixelů. Výsledek výslovně označuje jako možný sníh/led, nikoli potvrzené zamrznutí; žádné zjištění také nedokazuje, že plocha nikdy nezamrzla.
- Živá kontrola Sentinel Hub pro jeden rybník v Řitce (leden 2025) úspěšně vrátila tři intervaly včetně nového `ice_percent`; první interval měl 76 platných pixelů a 0 % klasifikovaných jako sníh/led. Streamlit na portu 8502 odpovídal HTTP 200.
- Přidány cílené regresní testy pro vodní typy, anglické parsování a data, volitelnost grafů, měsíční report a detekci možného ledu včetně případů s nedostatkem pixelů.

## 2026-11-13 — sloučení verzí

- Základ kódu a testů je `fe5d439` (`update 7`). Ze starších lokálních změn byla převzata pouze animace ikonek. README obsahuje původní dokumentaci i pracovní kontext jako historickou přílohu; historické záznamy nepopisují nutně současné chování.

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

## 2026-11-13 — modernizace analytických grafů a widgetů

- Implementován nový card-based analytický přehled (`_render_analytics_widget`): kompaktní karty pro jednotlivé metriky (vodní plocha, NDWI, NDTI, NDCI a případný led) s minimalistickými sparkline křivkami bez rušivých os a popisků.
- Pod každým sparkline grafem jsou agregované statistiky (průměr, trend Δ se směrovou šipkou a barevným zvýrazněním, rozsah hodnot / screeningová kategorie).
- Rozklikávací interaktivní detailní graf (`st.expander`) pro každou měřenou veličinu s posuvníkem časového rozsahu (rangeslider), hover popisky, zobrazením min/max bodů a referenčními pásmy (např. limity NDCI pro algální biomasu).

## 2026-11-13 — zapojení modelu do porozumění a rozhovoru

- Nahrazena původní normalizace obce a duplicitní tool-calling smyčka dvojicí modelových kroků: porozumění celému požadavku ve strukturovaném JSON a vytvoření odpovědi podle skutečného výsledku akce. Modelová odpověď se už nezahazuje a běžný report se při dostupném modelu nepřebírá z pevné šablony.
- Nový `scripts/conversation.py` předává historii ze skutečného UI klíče `messages` ve správném pořadí, aktuální dotaz právě jednou, vybraný rybník, kandidáty, období, kvalitu a měření. Kontext je omezen na 12 zpráv, 60 kandidátů a 72 rovnoměrně vybraných pozorování; statistiky používají celou řadu.
- Model rozlišuje hledání, výběr, analýzu jiného období, doplňující otázku a potřebu upřesnění. Odpovídá jazykem uživatele a zohledňuje žádosti o stručnost. Otázky k výsledkům neprovádějí nové vyhledávání ani satelitní výpočet. Výběr z mapy/číslem dál funguje přímo; přirozený výběr je omezen na skutečné kandidáty.
- Výpadek modelu je viditelný v rozhraní. Neplatné datum nebo neexistující volba nespustí analýzu. Čísla v generované odpovědi se porovnávají s předaným kontextem včetně statistik a zaokrouhlení; nepodložená čísla vyvolají jeden opravný pokus, potom označené automatické shrnutí. Kontrola čísel sama o sobě neověřuje všechny slovní závěry modelu.
- Změna viditelnosti grafů funguje i přes chat. Algae screening znovu používá právě načtenou satelitní odpověď; chyba měření se neoznačí jako dokončená analýza.
- Ověření: všech 46 testů prošlo, včetně dvou testů rozhraní Streamlit. `compileall`, `pip check` a `git diff --check` bez chyb. Skutečný Featherless zvládl tříkrokový český rozhovor nad testovacími daty: hledání za loňské léto → výběr většího rybníka → vysvětlení NDWI. Nástroje v tomto živém testu byly nahrazeny řízenými daty; proběhlo právě jedno hledání a jedna analýza. API údaje nebyly měněny ani vypisovány.

## 2026-11-13 — nové ověření a opravy regresí

- Doplněno 21 automatických testů: neplatné přihlašovací údaje a období, celé i krátké demo období, zachování identity a polygonu v demo analýze, chyby Sentinel Hub, chybějící a nulová měření, spolehlivost jednotlivých intervalů, nejednoznačný led, polygony s otvory a oddělenými částmi, změna typu vodní plochy a odstranění starých grafů po chybě. Rozhraní se nově ověřuje čtyřmi průchody AppTest včetně mapového výběru a demo grafů/tabulky; tabulka zahrnuje i NDCI.
- Opraveno zaměňování neznámého demo ID za první rybník, zkrácení ročního dema na deset záznamů a ztráta prvního dne krátkého období. Analýza simulovaných hodnot zachovává vybranou geometrii a screening znovu používá stejnou časovou řadu.
- Data se validují před externím voláním; chybová odpověď satelitní služby není úspěch, chybějící index nemá nulový průměr a nulový počet platných pixelů zneplatní indexy. Mnoho intervalů s několika pixely nezvyšuje spolehlivost; algae screening vyžaduje dostupné NDCI z dostatečně pokrytých intervalů. Nejednoznačný sníh/led se nehlásí jako absence ledu.
- ArcGIS prstence se převádějí na Polygon/MultiPolygon podle vnoření; mapy zachovávají otvory i samostatné části a značky používají bod uvnitř geometrie. ID v dotazu se escapuje. Po chybě nové analýzy se skryjí staré výsledky; změna vodního typu vyvolá nové hledání.
- Přidán samostatně zapínaný `tests/test_live_integration.py` a návod v README. Výchozí sada obsahuje 67 automatických testů a jeden vynechaný živý test. Živé ověření služeb v této relaci neproběhlo: síťový pokus selhal a automatická kontrola oprávnění následně zamítla spuštění mimo sandbox kvůli externím požadavkům a spotřebě API kvóty. Pro další živý běh je potřeba výslovné schválení uživatele.

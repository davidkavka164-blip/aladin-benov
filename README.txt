ALADIN METEOGRAM – BEŇOV
Lokalita: 49.417362 N, 17.501343 E.

ZDROJE PŘEDPOVĚDI
- 0–72 hodin: ČHMÚ ALADIN, česká doména CZ_1km (GRIB2).
- 72–168 hodin: ECMWF IFS HRES, rozlišení 0,25° (GRIB2).
- Data se získávají přímo z otevřených dat ČHMÚ a ECMWF. Open-Meteo se nepoužívá.
- Licenční podmínky a atribuce: ČHMÚ CC BY 4.0, ECMWF CC BY 4.0.

ZPRACOVÁNÍ
- GitHub Actions stahuje a dekóduje GRIB2 soubory, vybírá nejbližší výpočetní bod k Beňovu a vytváří data/forecast.json.
- Automatické sestavení předpovědi je plánováno přibližně dvakrát denně.
- Časové řady modelu ECMWF jsou převedeny na hodinové body interpolací; srážky jsou přepočítány z kumulativních úhrnů na hodinový průměr.
- Webová aplikace načítá hotový JSON soubor. Při výpadku připojení zobrazí poslední uloženou předpověď s upozorněním.

ZOBRAZENÍ
Pět grafů: teplota; vítr; srážky a relativní vlhkost; tlak; oblačnost.
Aplikace kontroluje nová data každých 30 minut a umožňuje ruční aktualizaci.
Hostování přes HTTPS. Android: Chrome > Instalovat aplikaci. iPhone: Safari > Sdílet > Přidat na plochu.

Neoficiální nezávislé zobrazení meteorologických dat.

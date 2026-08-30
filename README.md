# SARKA SPORTS FORECAST — NFL v0.1

SARKA on nflverse-dataan perustuva NFL-ennustejärjestelmä. Se arvioi otteluiden voittotodennäköisyyksiä ja simuloi kautta 100 000 kertaa. Malli ei ennusta varmoja lopputuloksia, eikä se ole vedonlyöntiohje.

Jokainen virallinen ennuste muodostetaan vain ennen määriteltyä katkaisuaikaa saatavilla olleesta tiedosta. Hyväksytty ennuste saa malliversion ja tallennetaan muuttumattomaan ennustehistoriaan. Malli ja v0.1.1-kalibrointi on jäädytetty ennen kautta 2026.

- [Julkinen SARKA-sivusto](https://toivooskarilaitinen-cloud.github.io/vaimea-nfl-forecast/)
- [Laajempi tuotantokäytön ohje](docs/KAYTTOOHJE.md)
- [Havaintojen kirjoitusohje](content/havainnot/_OHJE.md)

## Näin järjestelmä toimii kauden aikana

GitHub hakee nflverse-datan automaattisesti joka päivä klo **13.17 Suomen kesäaikaa** eli klo 10.17 UTC. Päivittäinen ajo:

1. hakee uuden datan
2. tarkistaa datan tuoreuden ja kattavuuden
3. pysäyttää julkaisun, jos olennaista tietoa puuttuu
4. päivittää sivuston tavalliset, uudelleen rakennettavat näkymät
5. tarkistaa, että lukittu ennustehistoria voidaan palauttaa muuttumattomana
6. arkistoi muuttuneen kausisimulaation Probability History -käyrää varten

Päivittäinen ajo ei saa yksin luoda virallista ennustetta. Virallinen ennuste syntyy vasta erillisessä hyväksyntäajossa, jossa aloittavat QB:t ja ottelulista tarkistetaan ihmisen toimesta.

Automaattisten ajojen tila näkyy GitHubin [Actions-näkymässä](https://github.com/toivooskarilaitinen-cloud/vaimea-nfl-forecast/actions).

## Virallisen ennusteen hyväksyminen

Ennen viikon ennusteiden lukitsemista:

1. Tarkista otteluohjelma ja katkaisuajat.
2. Tarkista järjestelmän ehdottamat aloittavat QB:t.
3. Korjaa QB tarvittaessa ja merkitse molemmat aloittajat hyväksytyiksi.
4. Tarkista datan tuoreus, laatuvaroitukset ja neutral-site-merkinnät.
5. Käynnistä GitHub Actionsissa **Approve official forecast**.
6. Valitse **Run workflow** ja anna pyydetyt draft-, starter- ja hyväksyjätiedot.
7. Hyväksy tuotantoympäristön ajo GitHubissa.

Hyväksynnän jälkeen ennuste lisätään append-only-ledgeriin. Vanhaa virallista riviä ei korvata tai kirjoiteta uudelleen. Sivuston `latest.json` on vain viimeisin näkymä; `history.json` on tarkistettava ennustehistoria.

## QB-aloittajan käsittely

Depth chart auttaa ehdottamaan aloittajaa, mutta v0.1 ei hyväksy QB:ta automaattisesti. Ihminen vahvistaa aloittajan ennen virallista julkaisua. Jos hyväksytty pelaajatunnus ei vastaa ehdotettua tai korjattua tunnusta, julkaisu pysähtyy.

Loukkantumisia ei automatisoida v0.1:ssä, koska riittävän luotettavaa, vakaata ja aikaleimattua ilmaista lähdettä ei ole lukittu järjestelmään.

## Preseason-ennuste ennen kauden alkua

Preseason-ennuste muodostetaan edellisen kauden tiedosta ja jäädytetystä mallista. Ennen ensimmäistä virallista ajoa:

1. varmista, että tarvittavat nflverse-kaudet on ladattu
2. tarkista edellisen kauden lopun joukkuevahvuudet
3. käy läpi QB-aloittajat ja offseasonin olennaiset muutokset
4. aja preseason-tarkistuslista
5. tarkista walk-forward-backtest ja vertailutasot
6. tee kaksi kuivaharjoitusta ilman ledgeriin kirjoittamista
7. hyväksy vasta sen jälkeen virallinen preseason-ennuste

Preseason-prosessi ei sovita mallia uudelleen. Se tarkistaa lähtötiedot ja sen, että jäädytetty malli voidaan ottaa turvallisesti käyttöön.

## Hälytykset

Jos päivittäinen datahaku, laatuportti, ennusteajo tai Pages-julkaisu epäonnistuu, työnkulku luo tai päivittää GitHub Issue -hälytyksen ja osoittaa sen repon omistajalle.

Hälytyksen näkee:

- GitHubin ilmoituskellossa
- repon [Issues-näkymässä](https://github.com/toivooskarilaitinen-cloud/vaimea-nfl-forecast/issues)
- sähköpostissa, jos Issues-ilmoitukset on sallittu kohdassa **GitHub Settings → Notifications**

## Sivuston tekstien muokkaaminen

Voit muokata näkyviä tekstejä suoraan GitHubissa:

1. avaa haluamasi HTML-tiedosto
2. paina kynäkuvaketta **Edit this file**
3. muuta tekstiä HTML-tagien välistä
4. paina **Commit changes**

Keskeiset tiedostot:

- `index.html` — etusivu
- `ennusteet.html` — ennusteet ja tuotannon tila
- `menetelma.html` — mallin menetelmä
- `mallin-jalki.html` — backtest ja aito ennustehistoria
- `joukkueet.html` — joukkueet
- `havainnot.html` — havaintojen etusivu

Älä muuta `class="..."`, `id="..."`, JavaScript-koodia tai HTML-tageja, ellet tiedä niiden tehtävää. GitHub Pages julkaisee tallennetun muutoksen yleensä muutamassa minuutissa.

## Uuden Havainnon julkaiseminen

Havainnot kirjoitetaan Markdown-tiedostoina kansioon `content/havainnot`.

1. Kopioi olemassa oleva artikkeli.
2. Nimeä tiedosto muodossa `VVVV-KK-PP-lyhyt-otsikko.md`.
3. Vaihda tiedoston alusta otsikko, päiväys ja tiivistelmä.
4. Kirjoita teksti Markdownina.
5. Tallenna muutos `main`-haaraan.

Sivusto rakentaa artikkelille automaattisesti kortin ja oman sivun. Tarkempi pikaohje löytyy tiedostosta [`content/havainnot/_OHJE.md`](content/havainnot/_OHJE.md).

## Mitä malli ottaa huomioon?

### Joukkuevahvuus

Hyökkäys ja puolustus arvioidaan erikseen EPA/play-luvulla. Uusimmat ottelut painavat enemmän kuin vanhat. Luvut vastustajakorjataan ja vedetään pienillä otoksilla kohti liigan keskiarvoa.

### QB-vahvuus

QB-malli yhdistää EPA/dropbackin ja CPOE:n. Pienen otoksen suorituksia hillitään 180 dropbackin priorilla, jotta muutama poikkeuksellinen peli ei tee arviosta liian varmaa.

### Ottelun olosuhteet

Malli käyttää kotietua ja lepoeroa. Neutral-site-otteluissa kotietu on nolla, mutta ottelun hyökkäys-, puolustus- ja QB-data käytetään normaalisti.

### Ottelutodennäköisyys

Joukkuevahvuudet, QB-ero, kotietu ja lepoero yhdistetään regularisoidulla logistisella mallilla. v0.1.1 käyttää jäädytettyä yhden parametrin lämpötilakalibrointia, joka hillitsee liiallista varmuutta muuttamatta suosikkien järjestystä.

### Kausisimulaatio

Jäljellä oleva kausi simuloidaan 100 000 kertaa jäädytetyillä ottelutodennäköisyyksillä. Pudotuspelipaikat ratkaistaan konferensseittain. Tiebreaker-käsittely sisältää luotettavasti toteutettavan ydinosan, mutta kaikkia NFL:n monen joukkueen sääntöjä ei vielä väitetä täydellisiksi. Tulokset merkitään `tiebreaker_mode: approximation_v0.1`.

Jokainen muuttunut kausisimulaatio tallennetaan erillisenä pisteenä `data/season-forecast-ledger`-kansioon. Identtistä ajoa ei tallenneta kahdesti, eikä vanhoja pisteitä kirjoiteta yli. Playoff- ja divisioonatodennäköisyydet ovat käytössä heti. Konferenssi- ja Super Bowl -todennäköisyydet aktivoidaan vasta luotettavan pudotuspelikaavion ottelumallin valmistuttua.

## Backtest ja seuranta

Walk-forward-backtest harjoittelee mallin vain testikautta edeltävillä kausilla. Kauden 2025 julkaistu testi sisältää 284 ottelua. Sivulla näytetään Brier, log loss, kalibraatio sekä yksinkertainen kotivoittoprosentin vertailutaso.

Backtest ei ole sama asia kuin ennen otteluita lukittu ennustehistoria. Kauden 2026 viralliset ennusteet raportoidaan erikseen eikä mallia säädetä kesken kauden lyhyiden tulosjaksojen perusteella.

## Datarakenne ja toistettavuus

```text
nflverse
  → data/raw/<UTC-aikaleima>/        alkuperäinen data, ei ylikirjoiteta
  → data/clean/<UTC-aikaleima>/      tarkistetut ja tyypitetyt rivit
  → data/features/<malli>/<cutoff>/  vain katkaisuhetkellä saatavilla ollut tieto
  → data/forecast-ledger/            muuttumattomat viralliset ennusteet
  → public/data/                     sivuston JSON-näkymät
```

Virallisesta ajosta tallennetaan vähintään malliversio, katkaisuaika, asetukset, lähtötiedostojen SHA-256-tiivisteet, ohjelmistoversio, satunnaissiemen, QB-lähde ja varoitukset. Raakadata säilytetään, koska nflverse voi tehdä tilastokorjauksia jälkikäteen.

## Kehittäjän pika-aloitus

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
vaimea download --season 2024 --season 2025
vaimea publish
```

Mallin asetukset ovat tiedostossa `config/model.yaml`.

## Datalähteet ja lisenssit

- [nflverse-data](https://github.com/nflverse/nflverse-data) — otteluohjelma, play-by-play ja johdetut kentät. Tarkista aina käytetyn julkaisun lisenssi; nflverse julkaisee suuren osan datasta CC BY 4.0 -lisenssillä.
- NFL-joukkueiden nimet ja tunnukset kuuluvat niiden omistajille. SARKA ei ole NFL:n virallinen tuote.
- Repon oma koodi on MIT-lisensoitu. MIT-lisenssi ei muuta kolmannen osapuolen datan lisenssiä.

## Seuraavat kehitysvaiheet

- tarkat graafipohjaiset NFL-tiebreakerit ja pudotuspelikaavio
- aikaleimattu markkinaennuste vain vertailutasoksi
- sää- ja matkustusdata luotettavista aikaleimatuista lähteistä
- kauden jälkeinen ablaatiotesti mallikomponenteille
- lisensoitu ja ihmisen tarkistama loukkantumisprosessi
- MLB-malli omana erillisenä kokonaisuutenaan

## Vastuullinen käyttö

Todennäköisyydet ovat arvioita, eivät lupauksia. Onnistumiset, epäonnistumiset ja kaikki viralliset ennusteet julkaistaan samassa historiassa.

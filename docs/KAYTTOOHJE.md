# SARKA NFL — tuotantokäytön muistilista

Mallin v0.1.1-matematiikka ja kalibrointi pysyvät jäädytettyinä. Tämä prosessi tarkistaa lähtötiedot, hyväksyy aloittavat QB:t ja lukitsee ennusteen muuttamatta mallia.

## Ennen kauden alkua

1. Vie edellisen kauden lopun joukkuevahvuudet sovittuun tiedostoon.
2. Luo QB-tarkistuslista ajankohdan depth chartista komennolla `vaimea starter-sheet`.
3. Aja `vaimea preseason-check`. Tarkistus ei estimoi uusia kertoimia, vaan varmistaa, että lähtötilan aineisto ja QB-katselmus ovat olemassa.
4. Tarkista, että malliversio on `0.1.1`, kalibrointikerroin on jäädytetty ja injury-automaatio on pois käytöstä.

## Viikoittainen hyväksyntä

1. Päivittäinen GitHub-ajo hakee datan ja suorittaa laatuportit.
2. `vaimea draft` paketoi mallin jo laskemat todennäköisyydet tarkistettavaksi muuttamatta niitä.
3. QB-listaan tulevat automaattiset ehdotukset. Jokainen ottelu alkaa tilassa `needs_review`.
4. Tarkista vain muuttuneet tai puuttuvat QB:t ja merkitse ottelu hyväksytyksi.
5. Aja `vaimea review`. Se tarkistaa datan iän, ottelumäärän, päällekkäisyydet, EPA-rivimäärän, joukkuepeiton, katkaisuajat, todennäköisyydet, input-hashit ja molemmat QB:t.
6. GitHubissa avaa **Actions → Approve official forecast → Run workflow**. Anna oma nimesi ja hyväksy ajo.
7. Onnistunut ajo lisää uuden tiedoston muuttumattomaan ledgeriin ja päivittää sivuston. Vanhaa ennustetta ei korvata.

## Mitä sivustolla näkyy

- datan hakuaika ja lähdeviikko
- malliversio ja ennusteen katkaisuaika
- QB- ja datavaroitukset
- neutral-site-merkintä ja nollattu kotietu
- tiebreaker-approksimaation varoitus
- ottelukohtainen muutos ja tekninen muutossyy
- Brier, log loss, 100 ottelun liukuva seuranta ja vertailutasot
- kaikkien joukkueiden Playoff- ja divisioonatodennäköisyyksien kehityskäyrä
- konferenssi- ja Super Bowl -käyrät, kun pudotuspelikaavion ottelumalli on valmis

Suorituskykyraportti on vain seurantaa. Se ei muuta mallia kesken kauden.

## Hälytykset

Epäonnistunut päivittäinen ajo näkyy kahdessa paikassa:

1. **GitHub → Actions → Update forecasts** näyttää epäonnistuneen vaiheen ja lokin.
2. Automaattinen Issue nimeltä **SARKA operational alert: forecast update failed** avataan tai sitä päivitetään. Issue osoitetaan repon omistajalle.

GitHub lähettää tästä ilmoituksen ilmoituskelloon. Sähköposti tulee, jos GitHubin **Settings → Notifications → Issues** -sähköposti-ilmoitukset ovat käytössä. Ulkoista sähköposti-, SMS- tai Slack-palvelua ei tarvita.

## Palautus

Komento `vaimea recover` tarkistaa ledgerin päällekkäisyydet ja tiedostotiivisteet sekä rakentaa `latest.json`, `history.json`, `movers.json` ja tilatiedoston uudelleen. Se ei kirjoita ledger-tiedostoja uudelleen.

## Kausiennusteen historia

Hyväksytty kausisimulaation syöte tallennetaan tiedostoon `data/season-runs/input.json`. Se sisältää kauden, viikon, aikaleiman, malliversion, jäljellä olevien otteluiden jäädytetyt todennäköisyydet ja joukkueiden konferenssi- sekä divisioonatiedot.

Päivittäinen ajo suorittaa tämän jälkeen:

1. `vaimea season-run` — ajaa 100 000 kautta ja kirjoittaa uusimman tuloksen
2. `vaimea archive-season` — vertaa tulosta aiempiin ja arkistoi vain muuttuneen ennusteen
3. rakentaa `public/data/season-history.json`-tiedoston sivuston graafeille

Jokainen arkistoitu piste saa aikaleiman ja sisältötiivisteen. Identtistä ajoa ei lisätä kahdesti. `vaimea recover` tarkistaa myös kausiennustehistorian tiivisteet ja pysäyttää julkaisun, jos vanhaa pistettä on muutettu.

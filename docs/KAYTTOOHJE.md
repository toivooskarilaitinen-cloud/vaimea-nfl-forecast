# SARKA NFL — tuotantokäytön muistilista

Mallin v0.1.1-matematiikka ja kalibrointi pysyvät jäädytettyinä. Tämä prosessi tarkistaa lähtötiedot, hyväksyy aloittavat QB:t ja lukitsee ennustesnapshotit muuttamatta mallia jälkikäteen.

## Ennen kauden alkua

1. Vie edellisen kauden lopun joukkuevahvuudet sovittuun tiedostoon.
2. Luo preseason-QB-tarkistus ja varmista, että jokaisen todennäköisyyden QB-provenienssi on tallessa.
3. Aja `vaimea preseason-check`.
4. Tarkista, että malliversio on `0.1.1`, kalibrointikerroin on jäädytetty ja injury-automaatio on pois käytöstä.

## Automaattinen viikkoprosessi

1. Päivittäinen **Update forecasts** hakee datan ja ajaa laatuportit.
2. `vaimea prepare-review` yhdistää jo lasketut todennäköisyydet nflverse/nfldata-aikatauluun, kickoff-aikoihin ja tämänhetkisiin QB-tietoihin.
3. Jokaiselle ottelulle lasketaan **FINAL LOCK = kickoff − 90 min**.
4. Ottelut, joiden final lock on jo ohitettu, eivät voi enää tulla uuteen draftiin.
5. Jos uusinta virallista snapshotia vastaava todennäköisyys ja QB:t eivät ole muuttuneet, uutta hyväksyntää ei pyydetä.
6. Kun hyväksyntää tarvitaan, GitHub avaa omistajalle Issuen **SARKA QB review required: Week N**. GitHubin ilmoituskello ja haluttaessa sähköposti toimivat ilmoituksena.
7. Issue näyttää ottelun, molemmat QB:t, nykyisen todennäköisyyden sekä tiedon siitä, vastaavatko QB:t niitä QB:ita, joilla todennäköisyys laskettiin.

## Ihmisen hyväksyntä

1. Avaa Issue ja tarkista QB-rivit.
2. Jos jokainen rivi on kunnossa, avaa **Actions → Approve official forecast → Run workflow**.
3. Anna oma nimesi ja kirjoita vahvistukseksi täsmälleen `APPROVE`.
4. Workflow merkitsee juuri generoituun starter-review-tiedostoon QB:t hyväksytyiksi.
5. `vaimea review` tarkistaa vielä datan iän, ottelumäärän, cutoffit, todennäköisyydet, QB:t, draftin ja starter-sheetin yhteensopivuuden sekä final-lock-portin.
6. `vaimea approve` lisää hyväksytyn snapshotin append-only-ledgeriin.
7. `vaimea publish` päivittää sivuston automaattisesti ja QB review -Issue suljetaan.

## Snapshot vs. FINAL LOCK

**Hyväksyntä ei tarkoita, ettei ennuste voisi enää koskaan muuttua.**

Jokainen hyväksyntä luo muuttumattoman snapshotin. Jos sallittu lähtötieto muuttuu myöhemmin ennen final lockia, SARKA voi luoda uuden draftin ja uuden snapshotin. Vanha snapshot jää historiaan.

Esimerkki:

- T−3 vrk: SEA 59,9 % → official snapshot
- T−1 vrk: uusi sallittu signaali → SEA 57,2 % → uusi official snapshot
- T−90 min: FINAL LOCK
- kickoffin jälkeen uusia snapshotteja ei hyväksytä

Pisteytyksessä käytetään ottelun **viimeistä hyväksyttyä snapshotia ennen FINAL LOCKia**. Koska järjestelmä teknisesti estää hyväksynnät final lockin jälkeen, jälkikäteistä valikointia ei voi tehdä.

## QB-muutos

QB-kuittaus ei saa liimata uutta QB:ta vanhaan prosenttiin.

Jos tämänhetkinen aloittava QB poikkeaa QB:sta, jolla kyseinen todennäköisyys laskettiin, review-gate pysäyttää julkaisun virheeseen:

`probability must be recomputed`

Tällöin todennäköisyys on ensin laskettava uudelleen uuden QB:n tiedolla ja vasta sen jälkeen pyydetään uusi ihmisen hyväksyntä.

## Mitä sivustolla näkyy

- datan hakuaika ja lähdeviikko
- malliversio ja snapshotin cutoff
- ottelukohtainen kickoff ja final-lock-aika
- `updateable` / `final`-tila
- QB- ja datavaroitukset
- neutral-site-merkintä
- tiebreaker-approksimaation varoitus
- ottelukohtainen muutos edelliseen snapshotiin
- Brier, log loss, 100 ottelun liukuva seuranta ja vertailutasot
- kausiennusteen historiakäyrät

Suorituskykyraportti on vain seurantaa. Se ei muuta mallia kesken kauden.

## Hälytykset

Epäonnistunut automaattinen ajo näkyy kahdessa paikassa:

1. **GitHub → Actions** näyttää epäonnistuneen vaiheen ja lokin.
2. Automaattinen Issue **SARKA operational alert: ... failed** avataan tai sitä päivitetään.

GitHub lähettää Issuesta ilmoituksen ilmoituskelloon. Sähköposti tulee, jos GitHubin **Settings → Notifications → Issues** -sähköposti-ilmoitukset ovat käytössä.

## Palautus

`vaimea recover` tarkistaa ledgerin päällekkäisyydet ja tiivisteet sekä rakentaa julkiset näkymät uudelleen. Se ei kirjoita vanhoja ledger-snapshotteja uudelleen.

## Kausiennusteen historia

Hyväksytty kausisimulaation syöte tallennetaan tiedostoon `data/season-runs/input.json`. Päivittäinen ajo suorittaa edelleen `vaimea season-run` ja `vaimea archive-season` -vaiheet. Otteluennusteiden snapshot-ledger ja kausiennusteen snapshot-ledger säilyvät erillisinä auditoitavina historioina.

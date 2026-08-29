from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "havainnot"
OUTPUT = ROOT / "havainnot"

NAV = """<header class="topbar"><a class="wordmark" href="{root}index.html"><span class="signal"></span>SARKA <b>NFL</b></a><nav aria-label="Päänavigaatio"><a href="{root}ennusteet.html">Ennusteet</a><a class="active-nav" href="{root}havainnot.html">Havainnot</a><a href="{root}joukkueet.html">Joukkueet</a><a href="{root}mallin-jalki.html">Mallin jälki</a><a href="{root}menetelma.html">Menetelmä</a></nav></header>"""

FOOTER = """<footer><div class="wordmark"><span class="signal"></span>SARKA <b>NFL</b></div><p>Havaintoja numeroista — ei melua numeroiden ympärillä.</p><span>© 2026 SARKA</span></footer>"""


@dataclass(frozen=True)
class Post:
    title: str
    published: date
    summary: str
    eyebrow: str
    slug: str
    body: str

    @property
    def date_fi(self) -> str:
        months = (
            "tammikuuta", "helmikuuta", "maaliskuuta", "huhtikuuta", "toukokuuta",
            "kesäkuuta", "heinäkuuta", "elokuuta", "syyskuuta", "lokakuuta",
            "marraskuuta", "joulukuuta",
        )
        return f"{self.published.day}. {months[self.published.month - 1]} {self.published.year}"


def inline(text: str) -> str:
    value = html.escape(text, quote=False)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(
        r"\[([^]]+)]\((https?://[^)]+)\)",
        r'<a href="\2" rel="noopener noreferrer">\1</a>',
        value,
    )
    return value


def markdown(text: str) -> str:
    lines = text.strip().splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            output.append("<ul>" + "".join(f"<li>{inline(item)}</li>" for item in list_items) + "</ul>")
            list_items.clear()

    for raw in lines + [""]:
        line = raw.strip()
        if not line:
            flush_paragraph()
            flush_list()
        elif line.startswith("### "):
            flush_paragraph(); flush_list(); output.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            flush_paragraph(); flush_list(); output.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("> "):
            flush_paragraph(); flush_list(); output.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line.startswith("- "):
            flush_paragraph(); list_items.append(line[2:])
        else:
            flush_list(); paragraph.append(line)
    return "".join(output)


def read_post(path: Path) -> Post:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n") or "\n---\n" not in raw[4:]:
        raise ValueError(f"{path.name}: YAML-otsake puuttuu")
    front, body = raw[4:].split("\n---\n", 1)
    meta: dict[str, str] = {}
    for line in front.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"{path.name}: virheellinen otsakerivi: {line}")
        meta[key.strip()] = value.strip().strip('"')
    required = {"title", "date", "summary"}
    missing = required - meta.keys()
    if missing:
        raise ValueError(f"{path.name}: puuttuvat kentät: {', '.join(sorted(missing))}")
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError(f"{path.name}: tiedostonimen slug saa sisältää vain a-z, 0-9 ja -")
    return Post(
        title=meta["title"],
        published=date.fromisoformat(meta["date"]),
        summary=meta["summary"],
        eyebrow=meta.get("eyebrow", "HAVAINTO"),
        slug=slug,
        body=body,
    )


def page(title: str, description: str, content: str, root: str = "") -> str:
    return f"""<!doctype html><html lang="fi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{html.escape(description, quote=True)}"><meta property="og:title" content="{html.escape(title, quote=True)}"><meta property="og:description" content="{html.escape(description, quote=True)}"><meta property="og:type" content="article"><title>{html.escape(title)} — SARKA NFL</title><link rel="stylesheet" href="{root}styles.css"></head><body><div class="grain" aria-hidden="true"></div>{NAV.format(root=root)}{content}{FOOTER}</body></html>\n"""


def build() -> list[Path]:
    posts = sorted(
        (read_post(path) for path in CONTENT.glob("*.md") if not path.name.startswith("_")),
        key=lambda post: (post.published, post.slug),
        reverse=True,
    )
    if not posts:
        raise ValueError("Lisää vähintään yksi Markdown-tiedosto content/havainnot-kansioon")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    cards = "".join(
        f"""<a class="content-card" href="havainnot/{post.slug}.html"><span class="meta">{html.escape(post.eyebrow)} · {html.escape(post.date_fi.upper())}</span><h2>{html.escape(post.title)}</h2><p>{html.escape(post.summary)}</p><span class="arrow">Lue →</span></a>"""
        for post in posts
    )
    index_content = f"""<main><section class="page-hero"><span class="kicker">VÄHEMMÄN MELUA</span><h1>Havainnot</h1><p>Kirjoitan tänne siitä, mitä luvut kertovat ja mikä niissä on vielä epäselvää. Tarkoitus ei ole selittää jokaista sunnuntaita jälkikäteen, vaan löytää asioita, joilla voi olla merkitystä myös ensi viikolla.</p></section><section class="page-content"><div class="content-cards">{cards}</div></section></main>"""
    index_path = ROOT / "havainnot.html"
    index_path.write_text(
        page("Havainnot", "SARKA NFL:n havainnot mallista, joukkueista ja kaudesta.", index_content),
        encoding="utf-8",
    )
    written = [index_path]

    for post in posts:
        article = f"""<main><section class="page-hero article-hero"><span class="kicker">{html.escape(post.eyebrow)} · {html.escape(post.date_fi.upper())}</span><h1>{html.escape(post.title)}</h1><p>{html.escape(post.summary)}</p></section><section class="page-content"><div class="page-grid"><article class="prose article-body">{markdown(post.body)}</article><aside class="side-card"><strong>HAVAINTOJEN LINJA</strong><ul><li>Havainto ja tulkinta erotetaan toisistaan.</li><li>Yhdestä ottelusta ei tehdä trendiä.</li><li>Epävarmuus sanotaan ääneen.</li><li>Vanhaa ennustetta ei korjata.</li></ul><a class="text-link" href="../havainnot.html">← Kaikki havainnot</a></aside></div></section></main>"""
        target = OUTPUT / f"{post.slug}.html"
        target.write_text(page(post.title, post.summary, article, root="../"), encoding="utf-8")
        written.append(target)
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rakenna Havainnot Markdown-tiedostoista")
    parser.parse_args()
    for generated in build():
        print(generated.relative_to(ROOT))

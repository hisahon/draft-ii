# bib2html_li.py
from pybtex.database.input.bibtex import Parser
import re, html, sys

BOLD_LAST = {"Astafyeva", "Maletckii", "Kherani", "Sanchez", "Honda", "Ouar",  "Ravanelli"}
LINK_TEXT = "Open Access"

DROP_FIELDS = {
    "abstract", "file", "keywords", "urldate", "issn", "langid", "shortjournal",
    "shorttitle", "publisher"
}

def strip_braces(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("{", "").replace("}", "")).strip()

def year_from(entry) -> str:
    y = entry.fields.get("year", "").strip()
    if y:
        return y
    d = entry.fields.get("date", "").strip()
    m = re.search(r"\b(\d{4})\b", d)
    return m.group(1) if m else "n.d."

def initials(parts):
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        out.append(p if p.endswith(".") else (p[0].upper() + "."))
    return " ".join(out)

def fmt_person(p) -> str:
    last = " ".join(list(p.prelast_names) + list(p.last_names)).strip()
    ini = " ".join(x for x in [initials(p.first_names), initials(p.middle_names)] if x).strip()
    s = html.escape(f"{last}, {ini}".strip().rstrip(","))
    if last.split() and last.split()[-1] in BOLD_LAST:
        s = f"<b>{s}</b>"
    return s

def fmt_authors(persons) -> str:
    a = [fmt_person(p) for p in persons]
    if not a:
        return ""
    return a[0] if len(a) == 1 else ", ".join(a[:-1]) + ", &amp; " + a[-1]

def doi_or_url(entry) -> str:
    doi = entry.fields.get("doi", "").strip()
    if doi:
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
        return f"https://doi.org/{doi}"
    return entry.fields.get("url", "").strip()

def preprocess_biblatex_author(text: str) -> str:
    # Converte "family=Paula, given=E. R., prefix=de, useprefix=true"
    # em "de Paula, E. R." (formato que o pybtex entende)
    def repl(m):
        family = m.group("family").strip()
        given  = m.group("given").strip()
        prefix = (m.group("prefix") or "").strip()
        name = f"{prefix} {family}".strip()
        return f"{name}, {given}"
    return re.sub(
        r"family=(?P<family>[^,}]+),\s*given=(?P<given>[^,}]+)(?:,\s*prefix=(?P<prefix>[^,}]+))?(?:,[^}]*)?",
        repl,
        text
    )

def drop_fields_bibtex(raw: str, fields_to_drop: set[str]) -> str:
    # Remove campos do tipo:  field = {...},  ou field = "..."
    # com contagem de chaves/aspas, para aguentar multiline + nested braces
    i = 0
    n = len(raw)
    out = []
    # regex para detectar "  fieldname   ="
    field_re = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*=\s*", re.ASCII)

    while i < n:
        if raw[i] in " \t\r\n":
            out.append(raw[i]); i += 1; continue

        m = field_re.match(raw, i)
        if not m:
            out.append(raw[i]); i += 1; continue

        name = m.group(1).lower()
        j = m.end()  # posição após '=' e espaços

        if name not in fields_to_drop:
            # mantém normalmente
            out.append(raw[i:j])
            i = j
            continue

        # pula o valor desse campo
        if j >= n:
            break

        if raw[j] == "{":
            depth = 1
            j += 1
            while j < n and depth > 0:
                c = raw[j]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                j += 1
        elif raw[j] == '"':
            j += 1
            while j < n:
                c = raw[j]
                if c == '"' and raw[j-1] != "\\":
                    j += 1
                    break
                j += 1
        else:
            # valor "simples" até vírgula/linha
            while j < n and raw[j] not in ",\n\r":
                j += 1

        # consome vírgula e espaços após o valor
        while j < n and raw[j] in " \t\r\n":
            j += 1
        if j < n and raw[j] == ",":
            j += 1
        # também consome espaços/linhas depois da vírgula
        while j < n and raw[j] in " \t\r\n":
            j += 1

        # efetivamente remove [i, j)
        i = j

    return "".join(out)

def main(bib_path: str):
    raw = open(bib_path, "r", encoding="utf-8").read()
    raw = drop_fields_bibtex(raw, DROP_FIELDS)
    raw = preprocess_biblatex_author(raw)

    bib = Parser().parse_string(raw)

    keys = list(bib.entries.keys())
    keys.sort(key=lambda k: year_from(bib.entries[k]), reverse=True)

    for k in keys:
        e = bib.entries[k]
        authors = fmt_authors(e.persons.get("author", []))
        year = html.escape(year_from(e))
        title = html.escape(strip_braces(e.fields.get("title", "")))

        journal = e.fields.get("journal", e.fields.get("journaltitle", e.fields.get("booktitle", "")))
        journal = html.escape(strip_braces(journal))

        vol = strip_braces(e.fields.get("volume", ""))
        num = strip_braces(e.fields.get("number", e.fields.get("issue", "")))
        pages = strip_braces(e.fields.get("pages", ""))

        vip = ""
        if vol:
            vip = f"{vol}({num})" if num else vol

        link = doi_or_url(e)
        link_html = f'<a href="{html.escape(link, quote=True)}">{html.escape(LINK_TEXT)}</a>' if link else ""

        parts = []
        parts.append(f"{authors} ({year}).\n" if authors else f"({year}).")
        if title:
            parts.append(f"                       {title}.\n")
        if journal:
            tail = []
            if vip: tail.append(html.escape(vip))
            if pages: tail.append(html.escape(pages))
            parts.append(f"                       <i>{journal}</i>, " + ", ".join(tail) + ("," if (tail or link_html) else ""))
        if link_html:
            parts.append(link_html)

        line = " ".join(parts).strip()
        line = re.sub(r"\s+,", ",", line).rstrip(",").strip()

        print("                    <li>")
        print(f"                        {line}")
        print("                    </li>\n")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ref.bib")

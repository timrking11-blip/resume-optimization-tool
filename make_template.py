#!/usr/bin/env python3
"""Resume Optimization Tool · template builder.

Reads the source template (TIM KING SOURCE RESUME.docx) and writes templates/docx_template.json:
the Word package parts every generated resume reuses (styles, numbering, theme, settings, fonts table),
the page setup, and one paragraph definition per resume element. rot.py (CLI builds and sync PDFs) and
the Resume Match Desk (Word download, PDF layout, preview) all render from this one file.

  python make_template.py                      rebuild from sources/TIM KING SOURCE RESUME.docx
  python make_template.py "path/to/new.docx"   copy an updated source into sources/, then rebuild
  python make_template.py --source X.docx --layout core/layouts/neutral-1.json --out hub/template/docx_template.json
                                               build another template from another source docx and layout (rot-layout/1)

The yellow "Section A:"…"Section D:" labels in the source are annotations and never reach a resume.
Normalized on purpose: one heading spacing everywhere, one bullet style per section, and a right tab
stop for role dates instead of runs of tab characters.
"""
import argparse, datetime as dt, hashlib, json, re, shutil, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "sources" / "TIM KING SOURCE RESUME.docx"
OUT = ROOT / "templates" / "docx_template.json"
LAYOUT = ROOT / "core" / "layouts" / "source-2026-09.json"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def attr(xml, tag, name):
    m = re.search(rf"<w:{tag}\b[^>]*\bw:{name}=\"([^\"]*)\"", xml)
    return m.group(1) if m else None


def paragraphs(doc):
    body = doc.split("<w:body>", 1)[1]
    return re.findall(r"<w:p[ >].*?</w:p>", body, re.S)


def ptext(p):
    return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", p))


def num_id(p):
    m = re.search(r'<w:numId w:val="(\d+)"/>', p)
    return m.group(1) if m else None


def build(src, layout):
    z = zipfile.ZipFile(src)
    part = lambda n: z.read(n).decode("utf-8")
    doc = part("word/document.xml")
    paras = paragraphs(doc)

    # which list definition each section uses in the source
    section, used = None, {}
    for p in paras:
        t = re.sub(r"^Section [A-D]:\s*", "", ptext(p)).strip().lower()
        if 'w:val="Heading1"' in p:
            section = t
            continue
        n = num_id(p)
        if n:
            used.setdefault(section, []).append(n)
    common = lambda s, d: max(set(used.get(s, [d])), key=used.get(s, [d]).count)
    heads = {s["kind"]: s["heading"].lower() for s in layout["sections"] if s.get("heading")}   # the layout names each section
    nums = {"experience": common(heads.get("experience", "professional experience"), "1"),
            "certs": common(heads.get("certifications", "credentialing & certifications"), "5"),
            "engagements": common(heads.get("engagements", "business consulting engagements"), "5"),
            "competencies": common(heads.get("core_competencies", "core competencies"), "2")}

    numbering = part("word/numbering.xml")
    abstract_of = dict(re.findall(r'<w:num w:numId="(\d+)"[^>]*>\s*<w:abstractNumId w:val="(\d+)"/>', numbering))
    indents = {}
    for key, nid in nums.items():
        a = re.search(r'<w:abstractNum [^>]*w:abstractNumId="%s".*?</w:abstractNum>' % abstract_of[nid], numbering, re.S).group(0)
        lvl0 = re.search(r'<w:lvl w:ilvl="0".*?</w:lvl>', a, re.S).group(0)
        indents[key] = {"left": int(attr(lvl0, "ind", "left") or 360), "hanging": int(attr(lvl0, "ind", "hanging") or 360),
                        "glyph": attr(lvl0, "lvlText", "val") or "•"}

    sect = re.search(r"<w:sectPr\b.*?</w:sectPr>", doc, re.S).group(0)
    sect = re.sub(r' w:rsid\w*="[^"]*"', "", sect)
    page = {"width": int(attr(sect, "pgSz", "w")), "height": int(attr(sect, "pgSz", "h")),
            "top": int(attr(sect, "pgMar", "top")), "bottom": int(attr(sect, "pgMar", "bottom")),
            "left": int(attr(sect, "pgMar", "left")), "right": int(attr(sect, "pgMar", "right"))}
    content_w = page["width"] - page["left"] - page["right"]
    theme = part("word/theme/theme1.xml")
    hl = re.search(r"<a:hlink>\s*<a:srgbClr val=\"([0-9A-Fa-f]{6})\"", theme)
    major = re.search(r"<a:majorFont>\s*<a:latin typeface=\"([^\"]+)\"", theme)

    # ---- package parts (no embedded fonts: Calibri ships with Office; saves ~3.8 MB per resume)
    ct = part("[Content_Types].xml")
    ct = re.sub(r'<Default Extension="odttf"[^>]*/>', "", ct)
    ct = re.sub(r'<Override PartName="/customXml/[^"]*"[^>]*/>', "", ct)
    settings = part("word/settings.xml")
    settings = re.sub(r"<w:embedTrueTypeFonts/>|<w:embedSystemFonts/>|<w:saveSubsetFonts/>", "", settings)
    settings = re.sub(r"<w:rsids>.*?</w:rsids>", "", settings, flags=re.S)
    settings = re.sub(r"<w1[45]:docId [^>]*/>", "", settings)
    font_table = re.sub(r"<w:embed(Regular|Bold|Italic|BoldItalic) [^>]*/>", "", part("word/fontTable.xml"))
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
           'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Template>Normal</Template>'
           '<Application>Resume Optimization Tool</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>'
           '<LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged>'
           '<AppVersion>16.0000</AppVersion></Properties>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>{title}</dc:title><dc:creator>{author}</dc:creator><cp:lastModifiedBy>{author}</cp:lastModifiedBy>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified></cp:coreProperties>')
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    doc_rels = [f'<Relationship Id="rId1" Type="{rel}styles" Target="styles.xml"/>',
                f'<Relationship Id="rId2" Type="{rel}numbering" Target="numbering.xml"/>',
                f'<Relationship Id="rId3" Type="{rel}settings" Target="settings.xml"/>',
                f'<Relationship Id="rId4" Type="{rel}webSettings" Target="webSettings.xml"/>',
                f'<Relationship Id="rId5" Type="{rel}fontTable" Target="fontTable.xml"/>',
                f'<Relationship Id="rId6" Type="{rel}theme" Target="theme/theme1.xml"/>']
    root = re.search(r"<w:document\b[^>]*>", doc).group(0)

    # ---- paragraph definitions (pPr), values from the source's paragraphs; spacing in twips
    npr = lambda key: f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{nums[key]}"/></w:numPr>'
    rule = '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="999999"/></w:pBdr>'
    date_tab = f'<w:tabs><w:tab w:val="right" w:pos="{content_w}"/></w:tabs>'
    ppr = {
        "name": '<w:pPr><w:spacing w:after="40"/><w:jc w:val="center"/></w:pPr>',
        "contact": '<w:pPr><w:spacing w:after="200"/><w:jc w:val="center"/></w:pPr>',
        "heading": f'<w:pPr><w:pStyle w:val="Heading1"/><w:keepNext/>{rule}<w:spacing w:before="240" w:after="100"/></w:pPr>',
        "summary": '<w:pPr><w:spacing w:after="100"/><w:jc w:val="both"/></w:pPr>',
        "tagline": '<w:pPr><w:spacing w:after="100"/><w:jc w:val="center"/></w:pPr>',
        "expertise": '<w:pPr><w:spacing w:after="100"/><w:jc w:val="center"/></w:pPr>',
        "tech_label": '<w:pPr><w:keepNext/><w:jc w:val="center"/></w:pPr>',
        "tech_line": '<w:pPr><w:jc w:val="center"/></w:pPr>',
        "school": '<w:pPr><w:keepNext/><w:spacing w:after="20"/></w:pPr>',
        "degree": '<w:pPr><w:spacing w:after="100"/></w:pPr>',
        "role_header": f'<w:pPr><w:keepNext/>{date_tab}</w:pPr>',
        "role_context": '<w:pPr><w:keepNext/><w:spacing w:after="100" w:line="276" w:lineRule="auto"/></w:pPr>',
        "bullet": f'<w:pPr><w:pStyle w:val="ListParagraph"/>{npr("experience")}<w:spacing w:after="80"/></w:pPr>',
        "bullet_last": f'<w:pPr><w:pStyle w:val="ListParagraph"/>{npr("experience")}<w:spacing w:after="240"/></w:pPr>',
        "cert": f'<w:pPr>{npr("certs")}<w:spacing w:after="40" w:line="250" w:lineRule="auto"/></w:pPr>',
        "eng_header": '<w:pPr><w:keepNext/><w:spacing w:after="80"/></w:pPr>',
        "eng_subtitle": '<w:pPr><w:keepNext/><w:spacing w:after="80"/></w:pPr>',
        "eng_bullet": f'<w:pPr><w:pStyle w:val="ListParagraph"/>{npr("engagements")}<w:spacing w:after="40" w:line="250" w:lineRule="auto"/><w:contextualSpacing w:val="0"/></w:pPr>',
        "eng_bullet_last": f'<w:pPr><w:pStyle w:val="ListParagraph"/>{npr("engagements")}<w:spacing w:after="160" w:line="250" w:lineRule="auto"/><w:contextualSpacing w:val="0"/></w:pPr>',
        "comp": f'<w:pPr><w:pStyle w:val="ListParagraph"/>{npr("competencies")}<w:spacing w:after="70" w:line="250" w:lineRule="auto"/></w:pPr>',
    }
    # run styles: rPr is composed in schema order (rStyle, rFonts, b, i, color, sz, u) by both renderers
    styles = {
        "plain": {}, "bold": {"b": 1}, "italic": {"i": 1}, "bold_italic": {"b": 1, "i": 1}, "bold_u": {"b": 1, "u": 1},
        "name": {"b": 1, "color": "1F3864"}, "contact": {"color": "444444"}, "link": {"link": 1},
        "heading": {"b": 1, "color": "1F3864", "sz": 20}, "degree": {"i": 1, "color": "444444"},
        "context": {"color": "808080", "sz": 16}, "cert_note": {"i": 1, "color": "404040"},
    }
    # spacing and line rules restated for the HTML and jsPDF renderers (points; line = multiple of single spacing)
    tw = lambda v: round(v / 20, 2)
    metrics = {
        "font": (major.group(1) if major else "Calibri"), "fallback_font": "Carlito", "size": 10, "single": 1.2207,
        "ascent": 0.9521, "hyperlink": "#" + (hl.group(1) if hl else "0000FF"),
        "page": {k: tw(v) for k, v in page.items()},
        "space": {"name": tw(40), "contact": tw(200), "heading_before": tw(240), "heading_after": tw(100), "rule_gap": 2,
                  "rule_width": 0.75, "tagline": tw(100), "school": tw(20), "degree": tw(100), "context": tw(100),
                  "bullet_last": tw(240), "cert": tw(40), "eng_header": tw(80), "eng_subtitle": tw(80), "eng_bullet": tw(40),
                  "eng_bullet_last": tw(160)},
        "line": {"context": 276 / 240, "list": 250 / 240},
        "indent": {k: {"left": tw(v["left"]), "hanging": tw(v["hanging"]), "glyph": v["glyph"] if len(v["glyph"]) == 1 and ord(v["glyph"]) < 0xF000 else "•"}
                   for k, v in indents.items()},
        "colors": {"navy": "#1F3864", "contact": "#444444", "rule": "#999999", "context": "#808080", "degree": "#444444",
                   "cert_note": "#404040", "ink": "#000000"},
        "context_size": 8,
    }
    return {
        "schema": "rot-docx-template/1",
        "source": {"file": src.name, "md5": hashlib.md5(src.read_bytes()).hexdigest(),
                   "made_at": dt.datetime.now().isoformat(timespec="seconds")},
        "parts": {"[Content_Types].xml": ct, "_rels/.rels": part("_rels/.rels"), "word/styles.xml": part("word/styles.xml"),
                  "word/numbering.xml": numbering, "word/settings.xml": settings, "word/webSettings.xml": part("word/webSettings.xml"),
                  "word/fontTable.xml": font_table, "word/theme/theme1.xml": theme, "docProps/app.xml": app},
        "core_xml": core,
        "doc_open": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + root + "<w:body>",
        "doc_close": sect + "</w:body></w:document>",
        "rels_open": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        "rels_base": doc_rels,
        "rel_hyperlink": f'<Relationship Id="{{id}}" Type="{rel}hyperlink" Target="{{url}}" TargetMode="External"/>',
        "rels_close": "</Relationships>",
        "ppr": ppr, "styles": styles, "metrics": metrics, "numbering": nums,
        "layout": {k: v for k, v in layout.items() if not k.startswith("_")},
    }


def main():
    ap = argparse.ArgumentParser(description="Build a docx template JSON from a source .docx and a layout.")
    ap.add_argument("new_source", nargs="?", help="copy this .docx over the source template first (legacy form)")
    ap.add_argument("--source", default=str(SRC), help="the source .docx (default: the source template)")
    ap.add_argument("--layout", default=str(LAYOUT), help="a rot-layout/1 JSON (default: core/layouts/source-2026-09.json)")
    ap.add_argument("--out", default=str(OUT), help="where to write the template JSON")
    a = ap.parse_args()
    src, out = Path(a.source).expanduser().resolve(), Path(a.out)
    if a.new_source:
        new = Path(a.new_source).expanduser().resolve()
        if not new.exists():
            sys.exit(f"missing: {new}")
        if new != SRC.resolve():
            shutil.copy2(new, SRC)
            print(f"copied {new.name} -> sources/")
        src = SRC.resolve()
    if not src.exists():
        sys.exit(f"missing source template: {src}")
    layout = json.loads(Path(a.layout).read_text(encoding="utf-8"))
    t = build(src, layout)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(t, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} ({out.stat().st_size // 1024} KB) from {src.name} with layout {layout.get('id')}; "
          f"lists: {t['numbering']}; page {t['metrics']['page']}")
    print("next: python extract.py && python rot.py ingest && python rot.py build --version vN")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Resume Optimization Tool · source extractor.

Reads every resume version (docx + pdf), the Liminal work summary, and the LinkedIn
capture, and writes sources/raw_extract.json: one record per source with every bullet
(verbatim, tagged with role + section), summary paragraphs, competency lines, systems
lines, and certification lines. Nothing is rewritten here — curation happens in
curation/achievements.json, and rot.py refuses to build if any raw bullet is unassigned.

usage: python extract.py
"""
import hashlib, json, re, sys, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
CAREER = ROOT.parent
BAS = CAREER.parent / "Business Advisory Services"

# id, path, target role, kind, date written (file mtime used if None)
SOURCES = [
    ("R1_base_2026", CAREER / "Tim King Resume 2026 .docx", "General baseline (Resume 1 — bullet standard)", "docx"),
    ("R2_base_2026_preliminal", CAREER / "Resumes/Tim King Resume 2026 .docx", "General baseline (pre-Liminal)", "docx"),
    ("R3_fundraising", CAREER / "Resumes/Tim King Fundraising Resume 2026 .docx", "Educational & nonprofit fundraising / advancement", "docx"),
    ("R4_openai_client_partner_me", CAREER / "Resumes/Tim_King_Resume_OpenAI_Client_Partner_Media & Entertainment-TK.docx", "OpenAI — Client Partner, Media & Entertainment", "docx"),
    ("R5_luminance_commercial_director", CAREER / "Resumes/Tim_King_Resume_Luminance_Commercial_Director.docx", "Luminance — Commercial Director (enterprise AI sales leadership)", "docx"),
    ("R6_admarketplace_director", CAREER / "Resumes/Tim_King_Resume_adMarketplace_Director_Advertiser_Sales.docx", "adMarketplace — Director, Advertiser Sales", "docx"),
    ("R7_fox_weather_director", CAREER / "Resumes/Tim_King_Resume_FOX_Weather_Director_Ad_Sales.pdf", "FOX Weather — Director, Ad Sales", "pdf_resume"),
    ("R8_bairesdev_vp_sales", BAS / "Timothy King Resume - BairesDev VP Sales.docx", "BairesDev — VP Sales (IT services)", "docx"),
    ("R9_knit_growth_marketing", BAS / "Timothy King Resume - Knit Growth Marketing.docx", "Knit — Growth Marketing", "docx"),
    ("R10_mri_simmons_audience", BAS / "Timothy King Resume - MRI-Simmons Audience Activation.docx", "MRI-Simmons — Audience Activation (data sales)", "docx"),
    ("R11_magellan_measurement", BAS / "Timothy King Resume - Magellan AI Measurement Growth.docx", "Magellan AI — Measurement Growth", "docx"),
    ("R12_meridian_gtm", BAS / "Timothy King Resume - Meridian GTM.docx", "Meridian — GTM", "docx"),
    ("R13_samba_platform_sales", BAS / "Timothy King Resume - Samba Platform Sales.docx", "Samba TV — Platform / Data Partnerships Sales", "docx"),
    ("R14_smartly_agency_partnerships", BAS / "Timothy King Resume - Smartly Agency Partnerships.docx", "Smartly — Agency Partnerships (player-coach)", "docx"),
    ("R15_versant_transformation", BAS / "Timothy King Resume - Versant Transformation Enablement.docx", "Versant — Transformation & Enablement", "docx"),
    ("R16_admarketplace_adv_success", BAS / "Timothy King Resume - adMarketplace Advertiser Success.docx", "adMarketplace — Advertiser Success", "docx"),
    ("S17_liminal_summary", CAREER / "Liminal_Chief_of_Strategy_Summary.md.pdf", "Liminal work summary (pre-written bullets)", "pdf_liminal"),
    ("S18_linkedin", ROOT / "sources/linkedin_2026-09-25.md", "LinkedIn public profile (captured 2026-09-25)", "linkedin_md"),
]

ROLE_PATTERNS = [
    ("liminal", r"Liminal|Healthcare (AI|FinTech|Tech)|Chief Strategy|Chief of Strategy|Strategy Consultant"),
    ("psp", r"Professional Sports Publications|PSP Sports|Ad(vertising)? Sales Director"),
    ("nyl", r"New York Life"),
    ("tek_lead", r"Specialized Lead"),
    ("tek_recruiter", r"(Enterprise|National) Recruiter"),
    ("demanddrive", r"demandDrive|Amazon Business|Inside Sales Representative|Sales Development Representative"),
    ("yri", r"YRI Custom"),
    ("massdot", r"EZ Pass|Department of Transportation"),
]
SECTION_PATTERNS = [
    ("summary", r"^(PROFESSIONAL SUMMARY|Professional Summary)$"),
    ("competencies", r"^(CORE COMPETENCIES|ADVANCEMENT COMPETENCIES|Core Expertise)$"),
    ("experience", r"^(PROFESSIONAL EXPERIENCE|Professional Experience|Work Experience|Consulting Projects)$"),
    ("portfolio", r"^SELECTED .*(WORK|PORTFOLIO)$"),
    ("education", r"^(EDUCATION|Education)$"),
    ("certifications", r"^Certifications"),
    ("skills", r"^Core Skills$"),
]
SEP = re.compile(r"\s[·•�|]\s")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def clean(t):
    t = t.replace(" ", " ").replace("\t", " ")
    return re.sub(r"\s+", " ", t).strip()


def role_of(line):
    for key, pat in ROLE_PATTERNS:
        if re.search(pat, line):
            return key
    return None


def section_of(line):
    for key, pat in SECTION_PATTERNS:
        if re.search(pat, line.strip()):
            return key
    return None


def docx_paragraphs(path):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("word/document.xml"))
    for p in root.iter(W + "p"):
        ppr = p.find(W + "pPr")
        is_list = False
        if ppr is not None:
            if ppr.find(W + "numPr") is not None:
                is_list = True
            st = ppr.find(W + "pStyle")
            if st is not None and "List" in (st.get(W + "val") or ""):
                is_list = True
        txt = clean("".join(t.text or "" for t in p.iter(W + "t")))
        if txt:
            yield txt, is_list


def new_record(sid, path, target, kind):
    return {"id": sid, "file": str(path.relative_to(CAREER.parent)), "md5": md5(path),
            "target_role": target, "kind": kind, "headline": None, "bullets": [],
            "summary": [], "competency_lines": [], "systems_lines": [], "skills_lines": [],
            "cert_lines": [], "portfolio": [], "role_headers": []}


def parse_docx(rec, path):
    section, role, n = "header", None, 0
    for txt, is_list in docx_paragraphs(path):
        n += 1
        sec = section_of(txt)
        if sec:
            section = sec
            if sec == "experience":
                role = None
            continue
        if n == 2 and txt.isupper():
            rec["headline"] = txt
            continue
        if txt.startswith(("Systems:", "Technologies:")):
            rec["systems_lines"].append(txt)
            continue
        if section in ("header", "summary", "competencies") and not is_list:
            if len(SEP.findall(txt)) >= 4 and len(txt) < 900 and "@" not in txt:
                rec["competency_lines"].append(txt)
            elif len(txt) > 180:
                rec["summary"].append(txt)
            continue
        if section == "experience" and not is_list:
            r = role_of(txt)
            if r and len(txt) < 200:
                role = r
                rec["role_headers"].append({"role": r, "text": txt})
            elif role and len(txt) < 120:
                rec["role_headers"].append({"role": role, "text": txt})  # date/location line
            elif len(txt) >= 120 and role:
                rec["bullets"].append({"role": role, "section": "experience", "text": txt})
            continue
        if section == "experience" and is_list:
            rec["bullets"].append({"role": role or "UNKNOWN", "section": "experience", "text": txt})
            continue
        if section == "education":
            if is_list or txt.startswith("Senior Capstone"):
                rec["bullets"].append({"role": "education", "section": "education", "text": txt})
            else:
                rec["role_headers"].append({"role": "education", "text": txt})
            continue
        if section == "certifications":
            rec["cert_lines"].append(txt)
            continue
        if section == "skills":
            rec["skills_lines"].append(txt)
            continue
        if section == "portfolio":
            rec["portfolio"].append(txt)
            continue


def pdf_text(path):
    from pypdf import PdfReader
    return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(path)).pages)


def parse_fox(rec, path):
    from pypdf import PdfReader
    raw = "\n".join(p.extract_text(extraction_mode="layout") or "" for p in PdfReader(str(path)).pages)
    lines = [clean(l) for l in raw.splitlines()]
    heads = {"CORE COMPETENCIES": "competencies", "PROFESSIONAL EXPERIENCE": "experience",
             "SELECTED PROPOSAL PORTFOLIO": "portfolio", "EDUCATION": "education"}
    section, role, buf, para, comp, sysl = "header", None, None, [], [], []

    def flush():
        nonlocal buf
        if buf is not None:
            rec["bullets"].append({"role": role or "UNKNOWN",
                                   "section": "education" if section == "education" else "experience",
                                   "text": clean(buf)})
            buf = None

    nonblank = 0
    for s in lines:
        if not s:
            continue
        nonblank += 1
        if s in heads:
            flush(); section = heads[s]; continue
        if nonblank == 2:
            rec["headline"] = s; continue
        if section == "header":
            if nonblank > 3:
                para.append(s)
            continue
        if section == "competencies":
            (sysl if (sysl or s.startswith("Systems:")) else comp).append(s); continue
        if section == "portfolio":
            rec["portfolio"].append(s); continue
        if s.startswith("•"):
            flush(); buf = s.lstrip("• ").strip(); continue
        if " | " in s and (role_of(s) or section == "education"):
            flush()
            role = "education" if section == "education" else role_of(s)
            rec["role_headers"].append({"role": role, "text": s}); continue
        if re.match(r"^[A-Z][a-z]+(,| [A-Z][a-z]+,) [A-Z]{2} \|", s):
            flush(); rec["role_headers"].append({"role": role, "text": s}); continue
        if buf is not None:
            buf += " " + s
    flush()
    if para:
        rec["summary"].append(clean(" ".join(para)))
    if comp:
        rec["competency_lines"].append(clean(" ".join(comp)))
    if sysl:
        rec["systems_lines"].append(clean(" ".join(sysl)))
    rec["portfolio"] = [clean(" ".join(rec["portfolio"]))] if rec["portfolio"] else []


def parse_liminal(rec, path):
    t = clean(pdf_text(path))
    block = t.split("6. Resume Bullets", 1)[1].split("If you need a shorter set", 1)[0]
    block = block.split("Present", 1)[1]  # drop the role header line
    items = [clean(b) for b in block.split("•")[1:]]
    items = [re.sub(r"one-engineer-plus- fractional", "one-engineer-plus-fractional", b) for b in items]
    for b in items:
        rec["bullets"].append({"role": "liminal", "section": "experience", "text": b})
    rec["role_headers"].append({"role": "liminal", "text": "Chief of Strategy — Liminal (behavioral-health AI) · 2026–Present"})


def parse_linkedin(rec, path):
    role, section = None, "experience"
    for l in path.read_text(encoding="utf-8").splitlines():
        s = l.strip()
        if s.startswith("## "):
            section = {"## Experience": "experience", "## Projects": "experience", "## Headline": "header",
                       "## Licenses & certifications": "certifications", "## Education": "education"}.get(s, "other")
            continue
        if s.startswith("#"):
            r = role_of(s)
            if r:
                role = r
            rec["role_headers"].append({"role": role, "text": s.lstrip("# ")})
            continue
        if section == "header" and s and not s.startswith("Location"):
            rec["headline"] = s
        if section == "experience" and s.startswith("- "):
            rec["bullets"].append({"role": role, "section": "experience", "text": clean(s[2:])})
        elif section == "certifications" and s.startswith("- "):
            rec["cert_lines"].append(s[2:])
        elif section == "education" and s.startswith("- "):
            rec["role_headers"].append({"role": "education", "text": s[2:]})


def main():
    out = []
    for sid, path, target, kind in SOURCES:
        if not path.exists():
            sys.exit(f"missing source: {path}")
        rec = new_record(sid, path, target, kind)
        {"docx": parse_docx, "pdf_resume": parse_fox, "pdf_liminal": parse_liminal,
         "linkedin_md": parse_linkedin}[kind](rec, path)
        out.append(rec)
    (ROOT / "sources/raw_extract.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    total = 0
    for r in out:
        by_role = {}
        for b in r["bullets"]:
            by_role[b["role"]] = by_role.get(b["role"], 0) + 1
        total += len(r["bullets"])
        print(f"{r['id']:34s} bullets={len(r['bullets']):3d} summary={len(r['summary'])} comp={len(r['competency_lines'])} "
              f"sys={len(r['systems_lines'])} skills={len(r['skills_lines'])} certs={len(r['cert_lines'])}  {by_role}")
    print("TOTAL raw bullets:", total)


if __name__ == "__main__":
    main()

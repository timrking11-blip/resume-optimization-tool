"""Riley Mahoney: a fictional test person for the shared core and Career Companion Hub.

Every person, company, date and number here is invented. The fixture exists so that the core, the intake pipeline
and the public edition can be tested without touching Tim's own data. Deliberate features (see persona.json,
"deliberate"): the same accomplishment worded differently across documents, a role end date that differs between
a resume and LinkedIn, a title that differs between two resumes, a metric that differs between two resumes (must
never print until resolved), a number written in words, a first-person bullet, a bullet over the Resume 1 ceiling,
an early role that only two sources mention, and a consulting engagement that only the newest sources mention.

Regenerate:  python tests/fixtures/persona/build_persona.py           (docx, txt, md, postings, persona.json)
             python tests/fixtures/persona/build_persona.py --pdf     (also PDFs through tools/docx2pdf.ps1 and Word)
"""
import json, subprocess, sys, zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

# ------------------------------------------------------------------ a minimal .docx writer (no dependencies)
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                 '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                 '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '</Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            '</Relationships>')
STYLES = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
          '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:rPrDefault>'
          '<w:pPrDefault><w:pPr><w:spacing w:after="60" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
          '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
          '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:after="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="34"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="60"/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="808080"/></w:pBdr></w:pPr><w:rPr><w:b/><w:caps/><w:sz w:val="22"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="140" w:after="20"/></w:pPr><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360"/><w:contextualSpacing/></w:pPr></w:style>'
          '</w:styles>')
NUMBERING = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {W}>'
             '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
             '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="&#8226;"/><w:lvlJc w:val="left"/>'
             '<w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr><w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/></w:rPr></w:lvl>'
             '</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>')


def core_xml(title, author, stamp):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(title)}</dc:title><dc:creator>{escape(author)}</dc:creator><cp:lastModifiedBy>{escape(author)}</cp:lastModifiedBy>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified>'
            '</cp:coreProperties>')


def run(text, b=False, i=False, sz=None):
    rpr = ("<w:b/>" if b else "") + ("<w:i/>" if i else "") + (f'<w:sz w:val="{sz}"/>' if sz else "")
    return f'<w:r>{"<w:rPr>" + rpr + "</w:rPr>" if rpr else ""}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(runs, style=None, num=False, jc=None, tab_right=None):
    if isinstance(runs, str):
        runs = [run(runs)]
    ppr = ""
    if style: ppr += f'<w:pStyle w:val="{style}"/>'
    if num: ppr += '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    if tab_right: ppr += f'<w:tabs><w:tab w:val="right" w:pos="{tab_right}"/></w:tabs>'
    if jc: ppr += f'<w:jc w:val="{jc}"/>'
    return f'<w:p>{"<w:pPr>" + ppr + "</w:pPr>" if ppr else ""}{"".join(runs)}</w:p>'


TAB = "<w:r><w:tab/></w:r>"


def table(rows, widths):
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    trs = ""
    for r in rows:
        tcs = "".join(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/></w:tcPr>{para(c)}</w:tc>' for c, w in zip(r, widths))
        trs += f"<w:tr>{tcs}</w:tr>"
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblBorders><w:insideH w:val="single" w:sz="4" w:color="BFBFBF"/></w:tblBorders></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{trs}</w:tbl>')


def write_docx(path, body_xml, title, author, stamp):
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{body_xml}'
           '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1008" w:right="1080" w:bottom="1008" w:left="1080" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
           '</w:body></w:document>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", NUMBERING)
        z.writestr("docProps/core.xml", core_xml(title, author, stamp))


# ------------------------------------------------------------------ the person
NAME = "Riley Mahoney"
CONTACT = "Denver, CO | (555) 010-0199 | riley.mahoney@example.com | linkedin.com/in/rileymahoney-example"

# accomplishment id -> wording per document (v1 classic, v2 media/partnerships, v3 revops, li LinkedIn)
A = {
    "hal-forecast": {"v1": "Rebuilt the weekly forecast process across three regions, lifting forecast accuracy from 71% to 93% within two quarters.",
                     "v3": "Redesigned forecasting cadence and stage definitions; forecast accuracy rose from 71% to 93% in two quarters.",
                     "li": "Improved forecast accuracy to 93% by rebuilding the weekly forecast process."},
    "hal-crm": {"v1": "Consolidated three CRMs into a single Salesforce instance shared by sales, customer success and marketing.",
                "v2": "Merged 3 CRMs into one Salesforce org, giving sales, CS and marketing one customer record.",
                "v3": "Led the consolidation of 3 CRMs into one Salesforce instance across sales, customer success and marketing, retiring two legacy tools."},
    "hal-routing": {"v1": "Designed lead routing rules and an SLA that cut speed-to-lead from 26 hours to under 2 hours and lifted SQL-to-opportunity conversion by 18 points.",
                    "v3": "Introduced routing and SLA rules that took speed-to-lead from 26 hours to under 2 hours; SQL-to-opportunity conversion improved 18 points."},
    "hal-pricing": {"v1": "Built the pricing and packaging model for a new mid-market tier that reached $1.2M ARR in its first year.",
                    "v3": "Owned pricing and packaging for the mid-market tier, which reached $1,200,000 in ARR in year one.",
                    "li": "Launched a mid-market pricing tier that passed $1M ARR in its first year."},
    "hal-team": {"v3": "Manage a team of 4 (two analysts and two Salesforce administrators) supporting a 60-person revenue organization."},
    "hal-pipeline": {"v1": "Grew qualified pipeline to $6.1M through territory redesign and a rebuilt SDR-to-AE handoff.",
                     "v3": "Grew qualified pipeline to $6.8M through territory redesign and a new SDR-to-AE handoff."},
    "kes-quota": {"v1": "Closed $2.4M in new business in FY2023 at 128% of quota, the top result on a team of nine.",
                  "v2": "Delivered $2.4M in new business in FY2023 (128% of quota), first of nine on the team.",
                  "li": "128% of quota in FY2023 with $2.4M in new business."},
    "kes-grocery": {"v2": "Won the retail media network's first three grocery accounts, including a $600K annual commitment from a regional chain."},
    "kes-cases": {"v1": "Built ROAS and CPM business cases for CMO and CFO buyers, raising average deal size 35%.",
                  "v2": "Wrote the ROAS/CPM business case template used with CMO and CFO buyers; average deal size grew 35%."},
    "kes-committee": {"v2": "Ran discovery-led cycles with buying committees of 6 to 8 stakeholders across brand, agency and finance teams."},
    "kes-agencies": {"v1": "I partnered with agency holding companies to expand the network into 12 new brands over 18 months.",
                     "v2": "Expanded the network into 12 new brands in 18 months through agency holding-company partnerships."},
    "pin-newsletter": {"v1": "Grew newsletter subscribers from 40K to 110K in 18 months while holding a 38% open rate.",
                       "v2": "Grew the newsletter from 40,000 to 110,000 subscribers in 18 months at a 38% open rate."},
    "pin-sponsored": {"v1": "Launched a sponsored-content product that produced $850K in first-year revenue.",
                      "v2": "Created and sold a sponsored-content product: $850,000 in revenue in its first year."},
    "pin-budget": {"v2": "Managed a $1.1M annual media budget; paid social returned 3.2x ROAS.",
                   "li": "Owned a $1.1M media budget and delivered 3.2x ROAS on paid social."},
    "pin-rebrand": {"v1": "Led the rebrand of three regional sports properties, coordinating design, editorial, sales collateral and a 14-market launch calendar, while keeping the combined program within 4% of budget."},
    "qui-meetings": {"v1": "Booked 140 qualified meetings in a year and finished #1 of 12 SDRs.",
                     "li": "Top SDR of 12 with 140 qualified meetings booked in one year."},
    "qui-sequences": {"v1": "Wrote outbound sequences adopted team-wide, lifting reply rates from 9% to 14%."},
    "lark-icp": {"v3": "Defined the ideal customer profile and three pricing tiers for a digital health startup; the first 5 pilot clinics signed within 4 months.",
                 "li": "Defined ICP and pricing tiers; first 5 pilot clinics signed within 4 months."},
    "lark-discovery": {"v3": "Built the sales narrative and a 30-interview customer discovery plan the founders ran before raising their seed round."},
}
ROLES = {
    "hal": dict(title="Director of Revenue Operations", employer="Halcyon Metrics", loc="Denver, CO", start="2024-01", end=None),
    "kes": dict(title="Senior Account Executive", employer="Kestrel Adtech", loc="Remote", start="2021-03", end="2023-11"),
    "pin": dict(title="Marketing Manager", employer="Pinecrest Sports Media", loc="Boulder, CO", start="2018-06", end="2021-02"),
    "qui": dict(title="Sales Development Representative", employer="Quillstone Software", loc="Denver, CO", start="2016-08", end="2018-05"),
    "lark": dict(title="Fractional GTM Advisor", employer="Larkspur Health", loc="Remote", start="2023-02", end="2023-08"),
}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
fmt = lambda v, short=False: "Present" if not v else f"{(MONTHS[int(v[5:]) - 1][:3] if short else MONTHS[int(v[5:]) - 1])} {v[:4]}"


def bullets_for(role, doc):
    return [A[k][doc] for k in A if k.startswith(role) and doc in A[k]]


# ------------------------------------------------------------------ resume v1: classic layout, "•" characters, date on its own line
def resume_v1():
    body, txt = [], []
    def add(x, t=None): body.append(x); txt.append(t if t is not None else "")
    add(para([run(NAME)], "Title"), NAME)
    add(para([run(CONTACT)], jc="center"), CONTACT)
    add(para([run("Professional Summary")], "Heading1"), "PROFESSIONAL SUMMARY")
    summ = ("Revenue operations and sales professional with eight years across B2B SaaS, retail media and sports publishing. "
            "Builds forecasting, pipeline and pricing systems that revenue teams actually use, and has carried a quota.")
    add(para(summ), summ)
    add(para([run("Experience")], "Heading1"), "EXPERIENCE")
    for key, dates in (("hal", "January 2024 – Present"), ("kes", "2021 – 2024"), ("pin", "June 2018 – February 2021"), ("qui", "August 2016 – May 2018")):
        r = ROLES[key]; title = r["title"]
        head = f"{title} | {r['employer']} | {r['loc']}"
        add(para([run(head, b=True)], "Heading2"), head)
        add(para([run(dates, i=True)]), dates)
        for b in bullets_for(key, "v1"):
            add(para("• " + b), "• " + b)
    add(para([run("Education")], "Heading1"), "EDUCATION")
    add(para([run("Lakeside State University", b=True), run(" — B.A., Communication, 2016")]), "Lakeside State University — B.A., Communication, 2016")
    add(para([run("Certifications & Tools")], "Heading1"), "CERTIFICATIONS & TOOLS")
    add(para("HubSpot Revenue Operations Certification (2023)"), "HubSpot Revenue Operations Certification (2023)")
    tools = "Salesforce, HubSpot, Outreach, Gong, Clari, Looker, ZoomInfo, Excel, Notion"
    add(para("Tools: " + tools), "Tools: " + tools)
    return "".join(body), "\n".join(txt)


# ------------------------------------------------------------------ resume v2: media and partnerships angle, real Word bullets, one-line role headers
def resume_v2():
    body, txt = [], []
    def add(x, t=None): body.append(x); txt.append(t if t is not None else "")
    add(para([run(NAME, b=True, sz=32)]), NAME)
    add(para([run("Media Sales & Partnerships | Retail Media | Growth Marketing", i=True)]), "Media Sales & Partnerships | Retail Media | Growth Marketing")
    add(para(CONTACT), CONTACT)
    add(para([run("Summary")], "Heading1"), "SUMMARY")
    summ = ("Media seller and marketer who has built sponsored products, sold retail media to CPG brands and agencies, and run "
            "seven-figure budgets. Comfortable in front of CMOs and CFOs with a ROAS case.")
    add(para(summ), summ)
    add(para([run("Core Skills")], "Heading1"), "CORE SKILLS")
    skills = "Retail media networks • Agency partnerships • ROAS and CPM business cases • Discovery and multi-stakeholder selling • Newsletter and lifecycle marketing • Paid social • Budget ownership • Salesforce, HubSpot, The Trade Desk, Google Analytics"
    add(para(skills), skills)
    add(para([run("Professional Experience")], "Heading1"), "PROFESSIONAL EXPERIENCE")
    heads = (("hal", "Director of Revenue Operations", "Jan 2024 – Present"), ("kes", "Senior Account Executive", "Mar 2021 – Nov 2023"),
             ("pin", "Senior Marketing Manager", "Jun 2018 – Feb 2021"))
    for key, title, dates in heads:
        r = ROLES[key]
        head = f"{r['employer']} — {title} ({r['loc']}) · {dates}"
        add(para([run(r["employer"] + " — ", b=True), run(title, b=True), run(f" ({r['loc']}) · {dates}")], "Heading2"), head)
        for b in bullets_for(key, "v2"):
            add(para(b, "ListParagraph", num=True), "- " + b)
    add(para([run("Education & Certifications")], "Heading1"), "EDUCATION & CERTIFICATIONS")
    add(para("B.A., Communication — Lakeside State University (2016)"), "B.A., Communication — Lakeside State University (2016)")
    add(para("HubSpot Revenue Operations Certification, 2023"), "HubSpot Revenue Operations Certification, 2023")
    add(para("Google Analytics Individual Qualification, 2020"), "Google Analytics Individual Qualification, 2020")
    return "".join(body), "\n".join(txt)


# ------------------------------------------------------------------ resume v3: revops angle, dashes, a skills table, the advisory engagement
def resume_v3():
    body, txt = [], []
    def add(x, t=None): body.append(x); txt.append(t if t is not None else "")
    add(para([run(NAME)], "Title"), NAME)
    add(para([run("Revenue Operations Leader")], jc="center"), "Revenue Operations Leader")
    add(para([run(CONTACT)], jc="center"), CONTACT)
    add(para([run("Experience")], "Heading1"), "EXPERIENCE")
    heads = (("hal", "Director of Revenue Operations", "January 2024 – Present"), ("lark", "Fractional GTM Advisor (part-time)", "February 2023 – August 2023"),
             ("kes", "Senior Account Executive", "March 2021 – November 2023"), ("pin", "Marketing Manager", "June 2018 – February 2021"))
    for key, title, dates in heads:
        r = ROLES[key]
        add(para([run(f"{title}, {r['employer']}", b=True), TAB, run(dates)], "Heading2", tab_right=10080), f"{title}, {r['employer']}\t{dates}")
        add(para([run(r["loc"], i=True)]), r["loc"])
        bl = bullets_for(key, "v3")
        if key == "pin":
            bl = ["Ran audience growth, sponsored content and a $1.1M media budget for three regional sports properties."]
        for b in bl:
            add(para("– " + b), "- " + b)
    add(para([run("Skills")], "Heading1"), "SKILLS")
    rows = [["Systems", "Salesforce (admin), HubSpot, Outreach, Gong, Looker, Tableau, ZoomInfo"],
            ["Revenue operations", "Forecasting, territory design, lead routing, pricing and packaging, CRM consolidation"],
            ["Go-to-market", "ICP definition, discovery interviews, pricing tiers, sales narrative, pilot programs"]]
    add(table(rows, [2400, 7680]), "\n".join(f"{a}: {b}" for a, b in rows))
    add(para([run("Education & Certifications")], "Heading1"), "EDUCATION & CERTIFICATIONS")
    add(para("Lakeside State University — B.A., Communication (2016)"), "Lakeside State University — B.A., Communication (2016)")
    add(para("HubSpot Revenue Operations Certification (2023)"), "HubSpot Revenue Operations Certification (2023)")
    return "".join(body), "\n".join(txt)


# ------------------------------------------------------------------ LinkedIn "Save to PDF" style export (docx for the PDF, md for the paste path)
def linkedin():
    lines = [
        ("h", NAME), ("p", "Director of Revenue Operations at Halcyon Metrics"), ("p", "Denver, Colorado, United States"),
        ("h2", "Contact"), ("p", "riley.mahoney@example.com"), ("p", "linkedin.com/in/rileymahoney-example"),
        ("h2", "Top Skills"), ("p", "Revenue Operations"), ("p", "Salesforce"), ("p", "Sales Forecasting"),
        ("h2", "Certifications"), ("p", "HubSpot Revenue Operations Certification"), ("p", "Salesforce Trailhead: Sales Cloud Basics"),
        ("h2", "Summary"),
        ("p", "I build the systems revenue teams run on: forecasts people trust, routing that gets leads to a human fast, and pricing that "
              "matches how customers buy. Eight years across B2B SaaS, retail media and sports publishing, including quota-carrying years."),
        ("h2", "Experience"),
        ("h3", "Halcyon Metrics"), ("p", "Director of Revenue Operations"), ("p", "January 2024 - Present (2 years 9 months)"), ("p", "Denver, Colorado, United States"),
        ("p", A["hal-forecast"]["li"]), ("p", A["hal-pricing"]["li"]),
        ("h3", "Larkspur Health"), ("p", "Fractional GTM Advisor"), ("p", "February 2023 - August 2023 (7 months)"), ("p", "Remote"),
        ("p", A["lark-icp"]["li"]),
        ("h3", "Kestrel Adtech"), ("p", "Senior Account Executive"), ("p", "March 2021 - November 2023 (2 years 9 months)"), ("p", "Remote"),
        ("p", A["kes-quota"]["li"]),
        ("h3", "Pinecrest Sports Media"), ("p", "Senior Marketing Manager"), ("p", "June 2018 - February 2021 (2 years 9 months)"), ("p", "Boulder, Colorado, United States"),
        ("p", A["pin-budget"]["li"]),
        ("h3", "Quillstone Software"), ("p", "Sales Development Representative"), ("p", "August 2016 - May 2018 (1 year 10 months)"), ("p", "Denver, Colorado, United States"),
        ("p", A["qui-meetings"]["li"]),
        ("h2", "Education"), ("h3", "Lakeside State University"), ("p", "Bachelor of Arts - BA, Communication · (2012 - 2016)"),
    ]
    body, md = [], []
    for kind, t in lines:
        if kind == "h": body.append(para([run(t, b=True, sz=32)])); md.append(f"# {t}")
        elif kind == "h2": body.append(para([run(t)], "Heading1")); md.append(f"\n## {t}")
        elif kind == "h3": body.append(para([run(t, b=True)], "Heading2")); md.append(f"\n### {t}")
        else: body.append(para(t)); md.append(t)
    return "".join(body), "\n".join(md) + "\n"


POSTINGS = {
    "01_director_revenue_operations": """Director, Revenue Operations
Northgate Software · Denver, CO (hybrid) · Full-time

About Northgate
Northgate makes planning software for mid-market manufacturers. We are a Series C company with 400 employees and a 90-person go-to-market team.

What you'll do
- Own the revenue forecast: stage definitions, weekly cadence, and the accuracy the executive team and board rely on.
- Run our Salesforce instance and the systems around it (HubSpot, Outreach, Gong, Looker), including the roadmap for consolidating tools acquired through two acquisitions.
- Design territories, lead routing and SLAs for SDR and AE teams; measure speed-to-lead and conversion at every stage.
- Partner with product marketing and finance on pricing and packaging changes, including the launch of a mid-market tier.
- Build the dashboards and pipeline reviews the CRO uses every week; report on pipeline coverage and win rates.
- Lead and grow a team of analysts and administrators.

What you bring
- 6+ years in revenue operations, sales operations or a related role at a B2B SaaS company.
- Proven forecasting accuracy improvements and CRM consolidation experience.
- Salesforce administration depth; Looker or Tableau fluency; comfortable with SQL basics.
- Experience presenting to C-suite stakeholders and aligning sales, customer success and marketing.
- Bonus: pricing and packaging work, or a quota-carrying background.
""",
    "02_senior_account_executive_retail_media": """Senior Account Executive, Retail Media
Cobalt Commerce Media · New York, NY or Remote (US) · Full-time

The role
Cobalt runs the retail media network for a group of regional grocery and specialty retailers. You will sell sponsored products, onsite display and offsite audiences to CPG brands and their agencies.

Responsibilities
- Own full-cycle new business with brands and agency teams: prospecting, discovery, business case, negotiation and close.
- Build ROAS and CPM business cases that a CMO and a CFO can both defend; explain measurement and incrementality clearly.
- Navigate buying committees of six or more stakeholders across brand, shopper marketing, agency and finance.
- Land the network's first accounts in new categories and expand them into annual commitments.
- Keep Salesforce accurate and forecast your book weekly.

Requirements
- 5+ years in media sales, retail media or ad tech with a record of exceeding quota.
- Experience selling to CPG brands and agency holding companies.
- Working knowledge of retail media networks, programmatic buying (The Trade Desk or similar) and first-party data.
- Strong discovery skills; you sell with questions before slides.
""",
    "03_head_of_growth_marketing": """Head of Growth Marketing
Fernwood · Remote (US) · Full-time

About Fernwood
Fernwood is a direct-to-consumer subscription for home gardening kits with 120,000 active subscribers.

What you'll own
- Growth across paid social, search, email and partnerships, with a seven-figure annual budget and clear ROAS targets.
- The newsletter and lifecycle program: subscriber growth, open and click rates, and win-back flows.
- Segmentation and positioning for three product lines and a rebrand launching next spring across 20 markets.
- Analytics: GA4, attribution, cohort reporting and a weekly growth review with the founders.
- A team of three (paid media, lifecycle, content) and agency partners.

What we're looking for
- 6+ years in growth or performance marketing for a consumer subscription or media brand.
- Track record of growing an audience (newsletter or subscriber base) and of managing a media budget over $1M.
- Comfort building sponsored or partner revenue products is a plus.
- Hands-on with Google Analytics, Klaviyo or a similar ESP, and paid social platforms.
- You use generative AI tools (ChatGPT, Claude) in your daily workflow and can show the judgment you apply to their output.
""",
    "04_partnerships_manager_agency_channel": """Partnerships Manager, Agency & Channel
Sable Signals · Chicago, IL (hybrid) · Full-time

About the role
Sable Signals provides measurement for retail media and CTV campaigns. This role builds our agency and channel partnerships so that partners bring us into their clients' plans.

You will
- Recruit and enable agency holding-company teams and independent agencies; run quarterly business reviews with each partner.
- Build co-marketing programs and partner enablement content; certify partner teams on our measurement methodology.
- Source and qualify pipeline through partners and hand qualified opportunities to account executives with clean discovery notes.
- Negotiate partnership terms, referral structures and joint go-to-market plans.
- Work with product marketing on positioning for the DSP and retail media network ecosystem (The Trade Desk, retailer networks).

You have
- 5+ years in partnerships, channel sales or agency sales in ad tech or marketing technology.
- Experience expanding a product into new brands through agency relationships.
- Comfort presenting to senior agency and brand stakeholders; strong written business cases.
- Salesforce or HubSpot discipline; you keep partner pipeline visible and forecastable.
""",
    "05_gtm_strategy_lead_ai_startup": """GTM Strategy Lead
Orbit Labs · San Francisco, CA or Remote · Full-time

About Orbit Labs
Orbit Labs (Series A, 35 people) builds an AI assistant for clinic operations teams. We have twelve paying customers and need a repeatable go-to-market motion.

What you'll do
- Define the ideal customer profile, segmentation and positioning for our first two verticals.
- Design pricing tiers and packaging with the founders; run the pilot program and convert pilots to paid.
- Run customer discovery interviews (30+ in the first quarter) and turn them into a sales narrative and playbook.
- Build the first forecast, pipeline stages and CRM setup (HubSpot) for a team of two AEs.
- Prepare board updates on GTM progress and lead the weekly go-to-market review.
- Stand up channel partnerships where a direct motion cannot carry the CAC.

What you bring
- 5+ years across go-to-market strategy, revenue operations or early-stage sales leadership.
- Experience defining ICP and pricing for a new product; you have taken something from zero to first customers.
- Structured discovery and stakeholder alignment skills; experience presenting to founders, boards or executives.
- Comfort with ambiguity and with generative AI tools as part of your daily workflow.
- Healthcare or clinic-operations experience is a bonus.
""",
}

PERSONA = {
    "fixture": "riley-mahoney/1", "fictional": True,
    "note": "Every person, company, date and number is invented. Built by build_persona.py; edit that file, not these outputs.",
    "identity": {"name": NAME, "location": "Denver, CO", "phone": "(555) 010-0199", "email": "riley.mahoney@example.com", "linkedin": "linkedin.com/in/rileymahoney-example"},
    "documents": {
        "resume_v1_classic.docx": {"kind": "resume", "authored_at": "2026-03-02", "layout": "classic: date line under the header, bullets as • characters", "roles": ["hal", "kes", "pin", "qui"]},
        "resume_v2_media_partnerships.docx": {"kind": "resume", "authored_at": "2025-11-14", "layout": "one-line role headers, real Word bullets, skills line", "roles": ["hal", "kes", "pin"]},
        "resume_v3_revops.docx": {"kind": "resume", "authored_at": "2026-08-20", "layout": "right-tab dates, dash bullets, a two-column skills table, the advisory engagement", "roles": ["hal", "lark", "kes", "pin"]},
        "linkedin_profile.docx": {"kind": "linkedin", "authored_at": "2026-09-20", "layout": "LinkedIn Save-to-PDF order: headline, contact, skills, certifications, summary, experience with durations", "roles": ["hal", "lark", "kes", "pin", "qui"]},
    },
    "roles": {k: {**v, "titles_by_source": {}} for k, v in ROLES.items()},
    "education": [{"school": "Lakeside State University", "degree": "B.A., Communication", "year": 2016}],
    "certifications": [{"name": "HubSpot Revenue Operations Certification", "year": 2023, "sources": ["v1", "v2", "v3", "li"]},
                       {"name": "Google Analytics Individual Qualification", "year": 2020, "sources": ["v2"]},
                       {"name": "Salesforce Trailhead: Sales Cloud Basics", "year": None, "sources": ["li"]}],
    "tools_by_source": {"v1": ["Salesforce", "HubSpot", "Outreach", "Gong", "Clari", "Looker", "ZoomInfo", "Excel", "Notion"],
                        "v2": ["Salesforce", "HubSpot", "The Trade Desk", "Google Analytics"],
                        "v3": ["Salesforce", "HubSpot", "Outreach", "Gong", "Looker", "Tableau", "ZoomInfo"],
                        "li": ["Salesforce"]},
    "accomplishments": {k: {"role": k.split("-")[0], "sources": sorted(v.keys()), "texts": v} for k, v in A.items()},
    "deliberate": {
        "same_fact_different_wording": ["hal-forecast", "hal-crm", "hal-routing", "kes-quota", "kes-cases", "pin-newsletter", "pin-sponsored", "qui-meetings"],
        "number_formats_same_fact": {"hal-pricing": ["$1.2M (v1)", "$1,200,000 (v3)", "over $1M (li, a lower bound, not a contradiction)"],
                                     "pin-sponsored": ["$850K (v1)", "$850,000 (v2)"], "hal-crm": ["three (v1)", "3 (v2, v3)"]},
        "metric_conflict_must_not_print": {"hal-pipeline": {"v1": 6100000, "v3": 6800000}},
        "date_conflict": {"kes.end": {"v1": "2024", "v2": "2023-11", "v3": "2023-11", "li": "2023-11", "expected_resolution": "2023-11 (three sources, newer documents)"}},
        "title_conflict": {"pin.title": {"v1": "Marketing Manager", "v3": "Marketing Manager", "v2": "Senior Marketing Manager", "li": "Senior Marketing Manager"}},
        "first_person_line": "kes-agencies (v1) starts with \"I partnered\"",
        "over_ceiling_line": "pin-rebrand (v1) is longer than 170 characters",
        "early_role_two_sources_only": "qui (v1 and LinkedIn): a hidden-by-default candidate",
        "engagement_newest_sources_only": "lark (v3 and LinkedIn): consulting engagement, part-time, 7 months",
        "number_words": ["three CRMs (v1)", "first three grocery accounts (v2)", "team of nine (v1)"],
    },
    "postings": {
        "01_director_revenue_operations": {"expect_strong": ["forecasting", "crm-discipline", "pipeline-management", "pricing-packaging"], "expect_role_focus": ["hal"]},
        "02_senior_account_executive_retail_media": {"expect_strong": ["executive-selling", "discovery", "media-sales", "qualification"], "expect_role_focus": ["kes"]},
        "03_head_of_growth_marketing": {"expect_strong": ["marketing", "audience-growth", "budget"], "expect_role_focus": ["pin"]},
        "04_partnerships_manager_agency_channel": {"expect_strong": ["channel-strategy", "partnerships"], "expect_role_focus": ["kes"]},
        "05_gtm_strategy_lead_ai_startup": {"expect_strong": ["gtm-strategy", "customer-discovery", "pricing-packaging", "stakeholder-alignment"], "expect_role_focus": ["lark", "hal"]},
        "_note": "expect_strong names taxonomy families or tags loosely; the Phase 1 tests pin exact ids once the GTM taxonomy v1 is fixed.",
    },
}
for k, src in (("v1", {"hal": "Director of Revenue Operations", "kes": "Senior Account Executive", "pin": "Marketing Manager", "qui": "Sales Development Representative"}),
               ("v2", {"hal": "Director of Revenue Operations", "kes": "Senior Account Executive", "pin": "Senior Marketing Manager"}),
               ("v3", {"hal": "Director of Revenue Operations", "lark": "Fractional GTM Advisor", "kes": "Senior Account Executive", "pin": "Marketing Manager"}),
               ("li", {"hal": "Director of Revenue Operations", "lark": "Fractional GTM Advisor", "kes": "Senior Account Executive", "pin": "Senior Marketing Manager", "qui": "Sales Development Representative"})):
    for role, title in src.items():
        PERSONA["roles"][role]["titles_by_source"][k] = title


def main():
    out = HERE
    (out / "postings").mkdir(parents=True, exist_ok=True)
    docs = [("resume_v1_classic", resume_v1, "2026-03-02T15:00:00Z", "Riley Mahoney Resume"),
            ("resume_v2_media_partnerships", resume_v2, "2025-11-14T21:30:00Z", "Riley Mahoney - Media & Partnerships"),
            ("resume_v3_revops", resume_v3, "2026-08-20T13:05:00Z", "Riley Mahoney - Revenue Operations")]
    for name, fn, stamp, title in docs:
        body, txt = fn()
        write_docx(out / f"{name}.docx", body, title, NAME, stamp)
        (out / f"{name}.txt").write_text(txt + "\n", encoding="utf-8")
    body, md = linkedin()
    write_docx(out / "linkedin_profile.docx", body, "Profile", NAME, "2026-09-20T18:00:00Z")
    (out / "linkedin_profile.md").write_text(md, encoding="utf-8")
    for k, v in POSTINGS.items():
        (out / "postings" / f"{k}.txt").write_text(v, encoding="utf-8")
    (out / "persona.json").write_text(json.dumps(PERSONA, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(docs)} resumes, LinkedIn export, {len(POSTINGS)} postings, persona.json in {out}")
    if "--pdf" in sys.argv:
        ps = ROOT / "tools" / "docx2pdf.ps1"
        for name in [d[0] for d in docs] + ["linkedin_profile"]:
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps), str(out / f"{name}.docx"), str(out / f"{name}.pdf")],
                               capture_output=True, text=True)
            print(name, r.stdout.strip() or r.stderr.strip())


if __name__ == "__main__":
    main()

"""A small, dependency-free Word (.docx) writer.

Builds a valid document from paragraph XML, with the package parts make_template.py reads (styles, numbering,
settings, webSettings, fontTable, theme). Generic Office parts can be supplied through `base_parts` (for example the
parts stored in templates/docx_template.json), otherwise minimal built-in ones are used. Output is deterministic when
`stamp` is fixed: entries are written in a fixed order with fixed zip timestamps, so the file's md5 is stable.

    from tools.docx_writer import Doc
    d = Doc(title="Resume", author="Name", stamp="2026-01-01T00:00:00Z")
    d.p("Name", style="Title"); d.p("Heading", style="Heading1"); d.bullet("A bullet", num=1)
    d.write("out.docx")
"""
import zipfile
from xml.sax.saxutils import escape

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"

CONTENT_TYPES = XML + ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
    '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
    '<Override PartName="/word/webSettings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml"/>'
    '<Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>'
    '<Override PartName="/word/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    '</Types>')
ROOT_RELS = XML + ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Id="rId1" Type="{REL}officeDocument" Target="word/document.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    f'<Relationship Id="rId3" Type="{REL}extended-properties" Target="docProps/app.xml"/>'
    '</Relationships>')
DOC_RELS = XML + ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Id="rId1" Type="{REL}styles" Target="styles.xml"/>'
    f'<Relationship Id="rId2" Type="{REL}numbering" Target="numbering.xml"/>'
    f'<Relationship Id="rId3" Type="{REL}settings" Target="settings.xml"/>'
    f'<Relationship Id="rId4" Type="{REL}webSettings" Target="webSettings.xml"/>'
    f'<Relationship Id="rId5" Type="{REL}fontTable" Target="fontTable.xml"/>'
    f'<Relationship Id="rId6" Type="{REL}theme" Target="theme/theme1.xml"/>'
    '</Relationships>')
STYLES = XML + (f'<w:styles {W}>'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi" w:cstheme="majorHAnsi"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="60" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="100"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="20"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360"/><w:contextualSpacing/></w:pPr></w:style>'
    '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>'
    '</w:styles>')
SETTINGS = XML + f'<w:settings {W}><w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/><w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat></w:settings>'
WEB_SETTINGS = XML + f'<w:webSettings {W}><w:optimizeForBrowser/><w:allowPNG/></w:webSettings>'
FONT_TABLE = XML + (f'<w:fonts {W}><w:font w:name="Calibri"><w:panose1 w:val="020F0502020204030204"/><w:charset w:val="00"/><w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>'
    '<w:font w:name="Symbol"><w:panose1 w:val="05050102010706020507"/><w:charset w:val="02"/><w:family w:val="roman"/><w:pitch w:val="variable"/></w:font></w:fonts>')


def theme_xml(major="Calibri", minor="Calibri", hlink="0563C1"):
    """A complete Office theme (colours, fonts, the three format lists Word insists on) with the given fonts."""
    fills = ('<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
             '<a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
             '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
             '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>')
    return XML + ('<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Neutral"><a:themeElements>'
        '<a:clrScheme name="Neutral"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
        '<a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2><a:accent1><a:srgbClr val="4472C4"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2>'
        '<a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4><a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6>'
        f'<a:hlink><a:srgbClr val="{hlink}"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
        f'<a:fontScheme name="Neutral"><a:majorFont><a:latin typeface="{major}"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="{minor}"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
        f'<a:fmtScheme name="Neutral">{fills}</a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>')


def numbering_xml(nums):
    """One bullet list per numId: {numId: {"glyph": "•", "left": 360, "hanging": 360}}."""
    abstracts, instances = [], []
    for k, (nid, spec) in enumerate(sorted(nums.items())):
        abstracts.append(f'<w:abstractNum w:abstractNumId="{k}"><w:multiLevelType w:val="hybridMultilevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
                         f'<w:lvlText w:val="{escape(spec.get("glyph", "•"))}"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{spec.get("left", 360)}" w:hanging="{spec.get("hanging", 360)}"/></w:pPr>'
                         # a real U+2022 in the text font: Word prints it, PDF text and ATS parsers read it as "•" (a Symbol-font
                         # bullet would come out as a private-use code point)
                         '</w:lvl></w:abstractNum>')
        instances.append(f'<w:num w:numId="{nid}"><w:abstractNumId w:val="{k}"/></w:num>')
    return XML + f'<w:numbering {W}>' + "".join(abstracts) + "".join(instances) + "</w:numbering>"


def core_xml(title, author, stamp):
    return XML + ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<dc:title>{escape(title)}</dc:title><dc:creator>{escape(author)}</dc:creator><cp:lastModifiedBy>{escape(author)}</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified></cp:coreProperties>')


APP_XML = XML + ('<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
    '<Template>Normal</Template><Application>Career Companion Hub</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop><LinksUpToDate>false</LinksUpToDate>'
    '<SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion></Properties>')


def run(text, b=False, i=False, u=False, sz=None, color=None):
    rpr = "".join(x for x in ["<w:b/>" if b else "", "<w:i/>" if i else "", '<w:u w:val="single"/>' if u else "",
                              f'<w:color w:val="{color}"/>' if color else "", f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>' if sz else ""])
    return f'<w:r>{"<w:rPr>" + rpr + "</w:rPr>" if rpr else ""}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


class Doc:
    def __init__(self, title="Document", author="Career Companion Hub", stamp="2026-01-01T00:00:00Z", base_parts=None, nums=None,
                 page=(12240, 15840), margins=(1008, 1080, 1008, 1080), fonts=("Calibri", "Calibri")):
        self.title, self.author, self.stamp = title, author, stamp
        self.base = base_parts or {}
        self.nums = nums or {1: {"glyph": "•"}, 2: {"glyph": "•"}, 5: {"glyph": "•"}}
        self.page, self.margins, self.fonts = page, margins, fonts
        self.body = []

    def raw(self, xml):
        self.body.append(xml)

    def p(self, runs, style=None, jc=None, num=None, tab_right=None, keep_next=False, after=None, before=None):
        if isinstance(runs, str):
            runs = [run(runs)]
        ppr = ""
        if style: ppr += f'<w:pStyle w:val="{style}"/>'
        if keep_next: ppr += "<w:keepNext/>"
        if num is not None: ppr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
        if tab_right: ppr += f'<w:tabs><w:tab w:val="right" w:pos="{tab_right}"/></w:tabs>'
        if after is not None or before is not None:
            ppr += "<w:spacing" + (f' w:before="{before}"' if before is not None else "") + (f' w:after="{after}"' if after is not None else "") + "/>"
        if jc: ppr += f'<w:jc w:val="{jc}"/>'
        self.body.append(f'<w:p>{"<w:pPr>" + ppr + "</w:pPr>" if ppr else ""}{"".join(runs)}</w:p>')

    def bullet(self, text, num=1, style="ListParagraph", after=None):
        self.p(text, style=style, num=num, after=after)

    @property
    def content_width(self):
        return self.page[0] - self.margins[1] - self.margins[3]

    def parts(self):
        top, right, bottom, left = self.margins
        sect = (f'<w:sectPr><w:pgSz w:w="{self.page[0]}" w:h="{self.page[1]}"/><w:pgMar w:top="{top}" w:right="{right}" w:bottom="{bottom}" w:left="{left}" '
                'w:header="708" w:footer="708" w:gutter="0"/><w:cols w:space="708"/><w:docGrid w:linePitch="360"/></w:sectPr>')
        document = XML + f'<w:document {W}><w:body>{"".join(self.body)}{sect}</w:body></w:document>'
        b = self.base
        return {
            "[Content_Types].xml": b.get("[Content_Types].xml", CONTENT_TYPES),
            "_rels/.rels": b.get("_rels/.rels", ROOT_RELS),
            "word/_rels/document.xml.rels": DOC_RELS,
            "word/document.xml": document,
            "word/styles.xml": b.get("word/styles.xml", STYLES),
            "word/numbering.xml": numbering_xml(self.nums),
            "word/settings.xml": b.get("word/settings.xml", SETTINGS),
            "word/webSettings.xml": b.get("word/webSettings.xml", WEB_SETTINGS),
            "word/fontTable.xml": b.get("word/fontTable.xml", FONT_TABLE),
            "word/theme/theme1.xml": b.get("word/theme/theme1.xml", theme_xml(*self.fonts)),
            "docProps/core.xml": core_xml(self.title, self.author, self.stamp),
            "docProps/app.xml": b.get("docProps/app.xml", APP_XML),
        }

    def write(self, path):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in self.parts().items():
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, data)
        return path

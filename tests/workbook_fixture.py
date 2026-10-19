"""Small fictional OOXML workbook for tests; contains no business records."""
from datetime import datetime, timedelta
from io import BytesIO
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZipFile, ZIP_DEFLATED

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def column(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def sheet_xml(rows):
    root = Element("worksheet", xmlns=NS)
    data = SubElement(root, "sheetData")
    for row_number, cells in rows.items():
        row = SubElement(data, "row", r=str(row_number))
        for address, value, style, formula in cells:
            attributes = {"r": address, "s": str(style)}
            if isinstance(value, str):
                attributes["t"] = "inlineStr"
                cell = SubElement(row, "c", attributes)
                SubElement(SubElement(cell, "is"), "t").text = value
            else:
                cell = SubElement(row, "c", attributes)
                if formula:
                    SubElement(cell, "f").text = formula
                SubElement(cell, "v").text = str(value)
    return tostring(root, encoding="utf-8", xml_declaration=True)


def sample_workbook():
    dates = [datetime(2026, 10, 17) - timedelta(days=index) for index in range(24)]
    summary = {1: [("A1", "姓名", 0, None)]}
    source = {1: [("D1", "姓名", 0, None)]}
    for index, day in enumerate(dates):
        summary[1].append((f"{column(index + 2)}1", f"{day.month}月{day.day}日总流水", 0, None))
        serial = (day - datetime(1899, 12, 30)).days
        source[1].append((f"{column(index + 6)}1", serial, 0, None))
    for row, name, style in [(2, "司机甲", 0), (3, "司机乙", 0), (4, "司机丙", 1), (5, "司机丁", 2)]:
        summary[row] = [(f"A{row}", name, style, None)]
        source[row] = [(f"D{row}", name, 0, None)]
        if row not in (2, 3):
            continue
        for index in range(24 if row == 2 else 10):
            amount = index if row == 2 else 5
            source_col = column(index + 6)
            source[row].append((f"{source_col}{row}", amount, 0, None))
            formula = f"SUMIF(流水表!$D:$D,$A{row},流水表!{source_col}:{source_col})"
            summary[row].append((f"{column(index + 2)}{row}", amount, 0, formula))
    summary[6] = [("A6", 0, 0, None)]
    files = {
        "[Content_Types].xml": '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>''',
        "_rels/.rels": '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''',
        "xl/workbook.xml": f'''<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="流水表" sheetId="1" r:id="rId1"/><sheet name="Sheet2" sheetId="2" r:id="rId2"/></sheets></workbook>''',
        "xl/_rels/workbook.xml.rels": '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/></Relationships>''',
        "xl/styles.xml": f'''<styleSheet xmlns="{NS}"><fonts count="3"><font><name val="Arial"/><sz val="11"/><color theme="1"/></font><font><name val="Arial"/><sz val="11"/><color rgb="FFFF0000"/></font><font><name val="Arial"/><sz val="11"/><color theme="9" tint="-0.25"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''',
        "xl/theme/theme1.xml": '''<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Test"><a:themeElements><a:clrScheme name="Test"><a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2><a:accent1><a:srgbClr val="4472C4"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2><a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4><a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="E54C5E"/></a:accent6></a:clrScheme></a:themeElements></a:theme>''',
        "xl/worksheets/sheet1.xml": sheet_xml(source),
        "xl/worksheets/sheet2.xml": sheet_xml(summary),
    }
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()

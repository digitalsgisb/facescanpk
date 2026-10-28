"""Native Excel employee shift reports using only the Python standard library."""
import io
import re
from datetime import timedelta
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
HEADERS = ['Work date', 'Employee ID', 'Name', 'Nickname', 'Plant / location',
           'Company', 'Department', 'Office department', 'Production section', 'Line',
           'Team', 'Position', 'Job type', 'Employee status', 'Shift',
           'Shift start (Malaysia)', 'Shift end (Malaysia)', 'Overtime']


def roster_rows(store, db, employees, start, end):
    """Resolve saved shift rules for every selected employee and work date."""
    rows = []
    current = start
    employees = sorted(employees, key=lambda e: tuple((e.get(k) or '').casefold()
                       for k in ('base','department','line','team','name','id')))
    while current <= end:
        for e in employees:
            schedule = store.resolve_schedule(db, e, current)
            planned = store.planned(schedule, current) if schedule else None
            production = (e.get('department') or '').strip().upper() == 'PRODUCTION'
            section = (e.get('production_section') or ('ROLL MAKING' if
                       (e.get('line') or '').strip().upper() == 'ROLL MAKING' else 'CONVERSION')) if production else ''
            rows.append([str(current), e['id'], e['name'], e.get('nickname'),
                         e.get('base') or 'Location unassigned', e.get('company'),
                         e.get('department'), e.get('office_department'), section,
                         e.get('line'), e.get('team'), e.get('position'), e.get('job_type'),
                         'Active' if e['active'] else 'Archived',
                         schedule['name'] if schedule else 'Unassigned',
                         planned[0].strftime('%Y-%m-%d %H:%M') if planned else '',
                         planned[1].strftime('%Y-%m-%d %H:%M') if planned else '',
                         ('Yes' if schedule['ot'] else 'No') if schedule else ''])
        current += timedelta(days=1)
    return rows


def workbook(data):
    """Write text as inline strings so employee input never becomes a formula."""
    rows = [HEADERS, *data]
    if len(rows) > 1048576:
        raise ValueError('Too many rows for Excel. Choose a shorter date range.')
    sheet = ['<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
             '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews>',
             '<cols><col min="1" max="6" width="24" customWidth="1"/><col min="7" max="18" width="25" customWidth="1"/></cols><sheetData>']
    for index, row in enumerate(rows, 1):
        sheet.append(f'<row r="{index}">')
        for col, value in enumerate(row):
            ref = f'{chr(65 + col)}{index}'
            if isinstance(value, (int, float)):
                sheet.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value or ''))[:32767]
                sheet.append(f'<c r="{ref}" t="inlineStr" s="{1 if index == 1 else 0}"><is><t xml:space="preserve">{escape(text)}</t></is></c>')
        sheet.append('</row>')
    sheet.append(f'</sheetData><autoFilter ref="A1:R{len(rows)}"/></worksheet>')
    output = io.BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>''')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Employee shifts" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" xfId="0"/><xf fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        archive.writestr('xl/worksheets/sheet1.xml', ''.join(sheet))
    return output.getvalue()

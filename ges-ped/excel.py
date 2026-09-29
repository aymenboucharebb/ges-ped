"""Échanges XLSX sans dépendance externe, chaînes explicites (jamais de formule)."""
import io,zipfile,xml.etree.ElementTree as ET,posixpath
from xml.sax.saxutils import escape
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def col(i):
    s=''
    while i:i,n=divmod(i-1,26);s=chr(65+n)+s
    return s
def export(headers,rows):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="ENSF" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        parts=['<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols>']
        for i,h in enumerate(headers,1):parts.append(f'<col min="{i}" max="{i}" width="{max(18,min(50,len(h)+5))}" customWidth="1"/>')
        parts.append('</cols><sheetData>')
        for i,row in enumerate([headers]+rows,1):
            parts.append(f'<row r="{i}">')
            for j,v in enumerate(row,1):
                p=f'{col(j)}{i}'
                if isinstance(v,(float,int)):parts.append(f'<c r="{p}"><v>{v}</v></c>')
                else:parts.append(f'<c r="{p}" t="inlineStr"><is><t xml:space="preserve">{escape(str(v or ""))}</t></is></c>')
            parts.append('</row>')
        parts.append(f'</sheetData><autoFilter ref="A1:{col(len(headers))}{len(rows)+1}"/></worksheet>')
        z.writestr('xl/worksheets/sheet1.xml',''.join(parts))
    return out.getvalue()
def read(content):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        if sum(i.file_size for i in z.infolist())>40_000_000:raise ValueError('Classeur trop volumineux.')
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        wb=ET.fromstring(z.read('xl/workbook.xml'));sheet=wb.find('s:sheets/s:sheet',NS)
        rid=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        target=next(x.attrib['Target'] for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')) if x.attrib['Id']==rid)
        path=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        result=[]
        for row in ET.fromstring(z.read(path)).findall('s:sheetData/s:row',NS):
            values={}
            for c in row.findall('s:c',NS):
                if c.find('s:f',NS) is not None:raise ValueError('Les formules ne sont pas acceptées à l’import. Collez les valeurs dans un nouveau classeur.')
                letters=''.join(x for x in c.attrib.get('r','A') if x.isalpha());i=0
                for x in letters:i=i*26+ord(x)-64
                typ=c.attrib.get('t');v=c.find('s:v',NS)
                value=v.text if v is not None else ''
                if typ=='s':value=strings[int(value)]
                elif typ=='inlineStr':value=''.join(c.find('s:is',NS).itertext())
                values[i-1]=value
            if values:result.append([values.get(i,'') for i in range(max(values)+1)])
        if len(result)>2001:raise ValueError('Import limité à 2 000 lignes par fichier.')
        return result

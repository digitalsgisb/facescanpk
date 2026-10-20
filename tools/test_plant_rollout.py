import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from install_code_update import install
from prepare_employee_update import extract

TEST_ROOT=Path(__file__).resolve().parents[1]/'ai-pc/runtime/tests'
TEST_ROOT.mkdir(parents=True,exist_ok=True)


class RolloutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.root=Path(self.temp.name)
        self.target=self.root/'plant'
        self.target.mkdir()

    def tearDown(self): self.temp.cleanup()

    def bundle(self,files,corrupt=False):
        path=self.root/'update.zip'
        with zipfile.ZipFile(path,'w') as z:
            manifest={'format':'sgi-code-update-v1','files':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}}
            if corrupt: manifest['files'][next(iter(files))]='0'*64
            z.writestr('update-manifest.json',json.dumps(manifest))
            for name,raw in files.items(): z.writestr(name,raw)
        return path

    def test_preview_and_apply_preserve_database_config_and_backup_old_code(self):
        (self.target/'server.py').write_bytes(b'old code')
        (self.target/'.env').write_bytes(b'private configuration sentinel')
        (self.target/'runtime').mkdir()
        (self.target/'runtime/attendance.sqlite3').write_bytes(b'live database sentinel')
        archive=self.bundle({'server.py':b'new code','testing_operations.py':b'new module'})
        self.assertFalse(install(archive,self.target)['applied'])
        self.assertEqual((self.target/'server.py').read_bytes(),b'old code')
        result=install(archive,self.target,True)
        self.assertTrue(result['applied'])
        self.assertEqual((self.target/'server.py').read_bytes(),b'new code')
        self.assertEqual((self.target/'.env').read_bytes(),b'private configuration sentinel')
        self.assertEqual((self.target/'runtime/attendance.sqlite3').read_bytes(),b'live database sentinel')
        with zipfile.ZipFile(result['code_backup']) as z: self.assertEqual(z.read('server.py'),b'old code')
        self.assertEqual(install(archive,self.target,True)['files_to_update'],0)

    def test_forbidden_paths_and_corrupted_updates_are_rejected_before_writing(self):
        for name in ('../server.py','runtime/attendance.sqlite3','.env','compose.yaml','data/employees.json','database/face.npy'):
            with self.subTest(name=name), self.assertRaises(ValueError): install(self.bundle({name:b'bad'}),self.target,True)
        with self.assertRaises(ValueError): install(self.bundle({'server.py':b'bad'},True),self.target,True)
        self.assertFalse((self.target/'server.py').exists())

    def workbook(self,formula=False):
        path=self.root/'employees.xlsx'
        headers=['Employee#','Name','Company','Base','Department','Job Type']
        rows=[headers,['000123','Test Name','Company','SENDAYAN','PRODUCTION','SPR, PROD']]
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        from xml.sax.saxutils import escape
        xml=f'<worksheet xmlns="{ns}"><sheetData>'
        for n,row in enumerate(rows,1):
            xml+=f'<row r="{n}">'+''.join(f'<c r="{chr(65+i)}{n}" t="inlineStr"><is><t>{escape(value)}</t></is></c>' for i,value in enumerate(row))+'</row>'
        if formula: xml+='<row r="3"><c r="A3"><f>1+1</f><v>2</v></c></row>'
        xml+='</sheetData></worksheet>'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Employment Details" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml',xml)
        return path

    def test_workbook_values_preserve_ids_exact_positions_and_locations(self):
        row=extract(self.workbook())[0]
        self.assertEqual(row['id'],'000123')
        self.assertEqual(row['job_type'],'SPR, PROD')
        self.assertEqual(row['base'],'SENDAYAN')

    def test_formulas_in_employee_fields_are_not_treated_as_instructions_or_data(self):
        with self.assertRaises(ValueError): extract(self.workbook(True))


if __name__=='__main__': unittest.main()

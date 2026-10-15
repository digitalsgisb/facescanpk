"""Exercise the actual registration widgets without loading camera/AI libraries."""
import ast
import string
import tkinter as tk
import unittest
from pathlib import Path
from kiosk_keyboard import TouchKeyboard


class RegistrationLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.attributes('-alpha', 0)
        source = ast.parse((Path(__file__).parent/'face.py').read_text(encoding='utf-8'))
        cls = next(node for node in source.body if isinstance(node,ast.ClassDef) and node.name=='SmartAttendanceSystem')
        methods = {'setup_register','build_keyboard','_set_active','_active','_kb_normalize','_kb_insert','_kb_backspace','_kb_clear'}
        cls.body = [node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name in methods]
        namespace = {'tk':tk, 'TouchKeyboard':TouchKeyboard, 'GUI_BG':'#000', 'GUI_PANEL':'#1e1e1e'}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'face.py','exec'),namespace)
        self.app = namespace['SmartAttendanceSystem']()
        self.app.root = self.root
        self.app.display_width, self.app.display_height = 270, 480
        self.app.save_face_data = lambda:None
        self.app.show_frame = lambda mode:None
        self.app.setup_register()
        self.app.frame_register.pack(fill='both',expand=True)

    def tearDown(self):
        self.root.destroy()

    def test_all_keys_and_actions_fit_registration_screen(self):
        self.root.deiconify()
        for width,height,scaling in [(800,480,1.33),(800,480,2),(1024,600,1.33)]:
            with self.subTest(size=(width,height),scaling=scaling):
                self.root.tk.call('tk','scaling',scaling)
                self.root.geometry(f'{width}x{height}')
                self.root.update()
                keys=self.app.keyboard.keys
                self.assertTrue(set(string.digits+string.ascii_uppercase).issubset(keys))
                for widget in [*keys.values(),self.app.entry_id,self.app.entry_name,*self.app.btn_capture.master.winfo_children()]:
                    x=widget.winfo_rootx()-self.root.winfo_rootx()
                    y=widget.winfo_rooty()-self.root.winfo_rooty()
                    self.assertGreaterEqual(x,0)
                    self.assertGreaterEqual(y,0)
                    self.assertLessEqual(x+widget.winfo_width(),width)
                    self.assertLessEqual(y+widget.winfo_height(),height)
                    self.assertGreater(widget.winfo_width(),25)
                    self.assertGreater(widget.winfo_height(),20)

    def test_previously_clipped_keys_and_editing_work_on_selected_field(self):
        self.app._set_active(self.app.entry_id)
        for key in '90OPL-':
            self.app.keyboard.keys[key].invoke()
        self.assertEqual(self.app.entry_id.get().upper(),'90OPL-')
        self.app._set_active(self.app.entry_name)
        for key in ['O','SPACE','P']:
            self.app.keyboard.keys[key].invoke()
        self.assertEqual(self.app.entry_name.get(),'O P')
        self.app.keyboard.keys['DEL'].invoke()
        self.assertEqual(self.app.entry_name.get(),'O ')
        self.app.keyboard.keys['CLEAR'].invoke()
        self.assertEqual(self.app.entry_name.get(),'')
        self.assertEqual(self.app.entry_id.get().upper(),'90OPL-')


if __name__=='__main__':
    unittest.main(verbosity=2)

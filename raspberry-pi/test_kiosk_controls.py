"""Check real Tk navigation and hit targets without camera/AI imports."""
import ast
import tkinter as tk
import unittest
from pathlib import Path
from kiosk_keyboard import TouchKeyboard


class KioskControlTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk()
        self.root.withdraw()
        # Fully transparent Windows windows are excluded from native hit testing.
        self.root.attributes('-alpha',0.01)
        self.root.attributes('-topmost',True)
        self.root.geometry('800x480')
        source=ast.parse((Path(__file__).parent/'face.py').read_text(encoding='utf-8'))
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='SmartAttendanceSystem')
        names={'setup_menu','setup_register','setup_attendance','build_keyboard','_set_active','_active',
               '_kb_normalize','_kb_insert','_kb_backspace','_kb_clear','return_to_menu','show_frame'}
        cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
        namespace={'tk':tk,'TouchKeyboard':TouchKeyboard,'GUI_BG':'#000','GUI_PANEL':'#1e1e1e',
                   'GUI_ACCENT':'#0f0','GUI_WARN':'#fc0'}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'face.py','exec'),namespace)
        self.app=namespace['SmartAttendanceSystem']()
        self.app.root=self.root
        self.app.display_width,self.app.display_height=270,480
        self.app.get_logo_image=lambda *args:tk.PhotoImage(master=self.root,width=54,height=48)
        self.app.update_clock=lambda:None
        self.app.reload_database=lambda:None
        self.app.on_shutdown=lambda:None
        self.app.save_face_data=lambda:None
        self.app.active_entry=None
        self.app._threads_running=True
        self.app.setup_menu()
        self.app.setup_register()
        self.app.setup_attendance()
        self.app.show_frame('ATTENDANCE')
        self.root.deiconify()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_stop_tap_returns_to_menu_and_registration_without_exiting(self):
        button=self.app.btn_stop
        x=button.winfo_width()//2
        y=button.winfo_height()//2
        self.assertIs(self.root.winfo_containing(button.winfo_rootx()+x,button.winfo_rooty()+y),button)
        button.event_generate('<Enter>',x=x,y=y)
        button.event_generate('<ButtonPress-1>',x=x,y=y)
        button.event_generate('<ButtonRelease-1>',x=x,y=y)
        self.root.update()
        self.assertEqual(self.app.mode,'MENU')
        self.assertTrue(self.app.frame_menu.winfo_ismapped())
        self.assertFalse(self.app.frame_attendance.winfo_ismapped())
        self.assertTrue(self.app._threads_running)
        register=next(w for w in self.app.frame_menu.winfo_children() if isinstance(w,tk.Button) and w.cget('text')=='REGISTER NEW USER')
        register.invoke()
        self.root.update()
        self.assertEqual(self.app.mode,'REGISTER')
        self.assertTrue(self.app.frame_register.winfo_ismapped())

    def test_stop_stays_visible_with_large_status_text_and_scaling(self):
        for scaling in [1.33,2]:
            self.root.tk.call('tk','scaling',scaling)
            self.app.lbl_status_main.config(text='CLOCK-IN CONFIRMED')
            self.app.lbl_current_status.config(text='Waiting for attendance confirmation',wraplength=400)
            self.app.lbl_next_window.config(text='Working hours not assigned; scan kept for review')
            self.root.update()
            button=self.app.btn_stop
            x=button.winfo_rootx()-self.root.winfo_rootx()
            y=button.winfo_rooty()-self.root.winfo_rooty()
            self.assertGreaterEqual(x,0)
            self.assertGreaterEqual(y,0)
            self.assertLessEqual(x+button.winfo_width(),800)
            self.assertLessEqual(y+button.winfo_height(),480)
            self.assertGreaterEqual(button.winfo_height(),48)
            self.assertGreaterEqual(button.winfo_width(),130)
            self.assertIs(self.root.winfo_containing(button.winfo_rootx()+button.winfo_width()//2,
                                                    button.winfo_rooty()+button.winfo_height()//2),button)


if __name__=='__main__':
    unittest.main(verbosity=2)

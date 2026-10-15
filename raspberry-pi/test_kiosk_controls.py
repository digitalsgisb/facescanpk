"""Check real Tk navigation and hit targets without camera/AI imports."""
import ast
import tkinter as tk
import unittest
from pathlib import Path
from kiosk_keyboard import TouchKeyboard
from kiosk_touch import enable_touch_buttons


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
        self.app.get_logo_image=lambda width,height,*args:tk.PhotoImage(master=self.root,width=width,height=height)
        self.app.update_clock=lambda:None
        self.app.reload_database=lambda:None
        self.app.on_shutdown=lambda:None
        self.app.save_face_data=lambda:None
        self.app.active_entry=None
        self.app._threads_running=True
        self.app.setup_menu()
        self.app.setup_register()
        self.app.setup_attendance()
        enable_touch_buttons(self.root)
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
        register=self.app.btn_menu_register
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

    def test_stop_without_hover_and_single_invocation(self):
        button = self.app.btn_stop
        calls = []
        button.configure(command=lambda: calls.append('stop'))
        button.event_generate('<Leave>')
        button.configure(state='normal')
        button.event_generate('<ButtonPress-1>', x=5, y=5)
        button.event_generate('<ButtonRelease-1>', x=5, y=5)
        self.root.update()
        self.assertEqual(calls, ['stop'])
        button.event_generate('<ButtonRelease-1>', x=5, y=5)
        self.assertEqual(calls, ['stop'])

    def test_cancelled_or_disabled_tap_does_not_invoke(self):
        button = self.app.btn_stop
        calls = []
        button.configure(command=lambda: calls.append('stop'))
        button.event_generate('<ButtonPress-1>', x=5, y=5)
        button.event_generate('<ButtonRelease-1>', x=-3, y=5)
        button.configure(state='disabled')
        button.event_generate('<ButtonPress-1>', x=5, y=5)
        button.event_generate('<ButtonRelease-1>', x=5, y=5)
        self.assertEqual(calls, [])

    def test_keyboard_tap_without_hover_inserts_once(self):
        self.app.show_frame('REGISTER')
        self.root.update()
        key = self.app.keyboard.keys['A']
        key.event_generate('<Leave>')
        key.configure(state='normal')
        key.event_generate('<ButtonPress-1>', x=5, y=5)
        key.event_generate('<ButtonRelease-1>', x=5, y=5)
        self.assertEqual(self.app.entry_id.get(), 'A')

    def test_controls_fit_compact_touchscreen_window(self):
        self.root.geometry('780x400')
        self.app.show_frame('ATTENDANCE')
        self.root.update()
        stop = self.app.btn_stop
        self.assertGreater(stop.winfo_rooty() - self.root.winfo_rooty(), 250)
        self.app.show_frame('REGISTER')
        self.root.update()
        for widget in [self.app.entry_id, self.app.entry_name, self.app.btn_capture,
                       *self.app.keyboard.keys.values()]:
            x = widget.winfo_rootx() - self.root.winfo_rootx()
            y = widget.winfo_rooty() - self.root.winfo_rooty()
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + widget.winfo_width(), 780)
            self.assertLessEqual(y + widget.winfo_height(), 400)
            self.assertGreaterEqual(widget.winfo_height(), 20)

    def test_footer_has_larger_logo_and_bottom_aligned_stop(self):
        self.root.geometry('800x480')
        self.root.update()
        stop = self.app.btn_stop
        logo = self.app.lbl_attendance_logo
        stop_center = stop.winfo_rooty() + stop.winfo_height() / 2
        logo_center = logo.winfo_rooty() + logo.winfo_height() / 2
        self.assertLessEqual(abs(stop_center - logo_center), 1)
        self.assertEqual(logo.winfo_width(), 84)
        self.assertEqual(logo.winfo_height(), 84)
        self.assertGreater(stop.winfo_rooty() - self.root.winfo_rooty(), 350)
        self.assertLess(stop.winfo_rootx() + stop.winfo_width(), logo.winfo_rootx())


if __name__=='__main__':
    unittest.main(verbosity=2)

"""Check real Tk navigation and hit targets without camera/AI imports."""
import ast
import tkinter as tk
import unittest
import threading
import time
import tempfile
import os
import re
import numpy as np
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
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
        names={'setup_menu','setup_register','setup_attendance','return_to_menu','show_frame',
               'registration_employees','refresh_registration','select_registration_employee',
               'toggle_registration_filter','change_registration_page','update_registration_capture',
               'save_face_data','reload_database','process_register'}
        cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
        namespace={'tk':tk,'time':time,'np':np,'os':os,'re':re,'Path':Path,'messagebox':Mock(),'CV_GREEN':(0,255,0),'GUI_BG':'#faf7f5','GUI_PANEL':'#faf7f5',
                   'GUI_ACCENT':'#177245','GUI_WARN':'#9a5a12', 'GUI_INK':'#302428',
                   'GUI_MUTED':'#7f6c70', 'GUI_BRAND':'#781b28', 'GUI_BORDER':'#dfc9cc'}
        for node in source.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id.startswith('GUI_'):
                namespace[node.targets[0].id] = ast.literal_eval(node.value)
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'face.py','exec'),namespace)
        self.namespace=namespace
        self.app=namespace['SmartAttendanceSystem']()
        self.app.root=self.root
        self.app.display_width,self.app.display_height=270,480
        self.app.get_logo_image=lambda width,height,*args:tk.PhotoImage(master=self.root,width=width,height=height)
        self.app.update_clock=lambda:None
        self.app.reload_database=lambda:None
        self.app.on_shutdown=lambda:None
        self.app.save_face_data=lambda:None
        self.app.transport=Mock()
        self.app.transport.workers.return_value={
            'EMP001': {'name': 'Test One', 'active': True},
            'EMP002': {'name': 'Test Two', 'active': True},
            'OLD': {'name': 'Inactive', 'active': False}}
        self.app.database_lock=threading.Lock()
        self.app.known_ids=['EMP002']
        self.app.reg_face_detected=False
        self.app.reg_face_embedding=None
        self.app.reg_embedding_time=0
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

    def test_card_tap_without_hover_selects_employee_and_waits_for_fresh_face(self):
        self.app.show_frame('REGISTER')
        self.root.update()
        card = self.app.registration_cards[0]
        self.assertIn('EMP001', card.cget('text'))
        self.assertNotIn('EMP002', card.cget('text'))
        card.event_generate('<Leave>')
        card.event_generate('<ButtonPress-1>', x=5, y=5)
        card.event_generate('<ButtonRelease-1>', x=5, y=5)
        self.assertEqual(self.app.registration_selected, 'EMP001')
        self.assertEqual(self.app.btn_capture.cget('state'), 'disabled')
        self.app.reg_face_detected=True
        self.app.reg_face_embedding=object()
        self.app.reg_embedding_time=time.monotonic()
        self.app.registration_selected_at=self.app.reg_embedding_time - .01
        self.app.update_registration_capture()
        self.assertEqual(self.app.btn_capture.cget('state'), 'normal')
        self.app.reg_embedding_time-=2
        self.app.update_registration_capture()
        self.assertEqual(self.app.btn_capture.cget('state'), 'disabled')

    def test_employee_sync_removes_inactive_selection_and_adds_new_cards(self):
        self.app.show_frame('REGISTER')
        self.app.select_registration_employee('EMP001')
        self.app.transport.workers.return_value={'NEW': {'name': 'New Employee', 'active': True}}
        self.app.refresh_registration()
        self.assertIsNone(self.app.registration_selected)
        self.assertIn('NEW', self.app.registration_cards[0].cget('text'))
        self.assertEqual(self.app.btn_capture.cget('state'), 'disabled')

    def test_registered_filter_and_local_enrollment_remove_pending_card(self):
        self.app.show_frame('REGISTER')
        self.app.known_ids.append('EMP001')
        self.app.refresh_registration()
        self.assertIn('No employees waiting', self.app.registration_cards[0].cget('text'))
        self.app.toggle_registration_filter()
        self.assertIn('Registered - tap to recapture', self.app.registration_cards[0].cget('text'))
        self.app.select_registration_employee('EMP002')
        self.assertEqual(self.app.registration_selected, 'EMP002')

    def test_pagination_and_cached_offline_list(self):
        self.app.transport.workers.return_value={str(i): {'name': f'Worker {i}', 'active': True} for i in range(8)}
        self.app.network_state='Offline'
        self.app.show_frame('REGISTER')
        self.assertIn('last synced', self.app.lbl_registration_sync.cget('text'))
        self.app.change_registration_page(2)
        self.assertEqual(self.app.lbl_registration_page.cget('text'), '3 / 3')
        self.assertEqual(self.app.registration_cards[2].cget('state'), 'disabled')
        self.app.transport.request.assert_not_called()

    def test_save_uses_card_identity_and_updates_pending_list(self):
        test_root=Path(__file__).parent/'runtime/tests'
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            self.namespace['DB_PATH']=directory
            self.app.reload_database=self.app.__class__.reload_database.__get__(self.app)
            self.app.show_frame('REGISTER')
            self.app.select_registration_employee('EMP001')
            self.app.reg_face_embedding=np.ones(512)
            self.app.reg_face_detected=True
            self.app.reg_embedding_time=time.monotonic()
            self.app.registration_selected_at=self.app.reg_embedding_time - .01
            self.app.__class__.save_face_data(self.app)
            saved=list(Path(directory).glob('*.npy'))
            self.assertEqual([p.name for p in saved], ['EMP001_Test One.npy'])
            np.testing.assert_array_equal(np.load(saved[0]), np.ones(512))
            self.assertIn('EMP001', self.app.known_ids)
            self.assertIsNone(self.app.registration_selected)
            self.assertIn('EMP002', self.app.registration_cards[0].cget('text'))
            self.namespace['messagebox'].showinfo.assert_called_once()

    def test_save_rechecks_employee_active_and_capture_predates_selection(self):
        self.app.show_frame('REGISTER')
        self.app.select_registration_employee('EMP001')
        self.app.reg_face_detected=True
        self.app.reg_face_embedding=np.ones(512)
        self.app.reg_embedding_time=self.app.registration_selected_at - .1
        self.app.__class__.save_face_data(self.app)
        self.assertEqual(self.namespace['messagebox'].showwarning.call_args.args[0], 'LOOK AT CAMERA')
        self.app.transport.workers.return_value['EMP001']['active']=False
        self.app.__class__.save_face_data(self.app)
        self.assertEqual(self.namespace['messagebox'].showwarning.call_args.args[0], 'EMPLOYEE NOT FOUND')
        self.namespace['messagebox'].showinfo.assert_not_called()

    def test_inference_started_before_selection_cannot_enable_capture(self):
        self.app.show_frame('REGISTER')
        self.app.select_registration_employee('EMP001')
        self.app.ui=lambda fn: fn()
        face=SimpleNamespace(embedding=np.ones(512), bbox=np.array([0, 0, 10, 10]))
        self.app.process_register([face], self.app.registration_selected_at - .1)
        self.assertIsNone(self.app.reg_face_embedding)
        self.assertEqual(self.app.btn_capture.cget('state'), 'disabled')

    def test_fresh_inference_after_selection_enables_capture(self):
        self.app.show_frame('REGISTER')
        self.app.select_registration_employee('EMP001')
        self.app.registration_selected_at-=.01
        self.app.ui=lambda fn: fn()
        face=SimpleNamespace(embedding=np.ones(512), bbox=np.array([0, 0, 10, 10]))
        self.app.process_register([face], time.monotonic())
        self.assertEqual(self.app.btn_capture.cget('state'), 'normal')
        self.app.process_register([])
        self.assertEqual(self.app.btn_capture.cget('state'), 'disabled')

    def test_controls_fit_compact_touchscreen_window(self):
        self.root.geometry('780x400')
        self.app.transport.workers.return_value={str(i): {'name':'Long Employee Name ' * 5, 'active':True} for i in range(5)}
        self.app.show_frame('ATTENDANCE')
        self.root.update()
        stop = self.app.btn_stop
        self.assertGreater(stop.winfo_rooty() - self.root.winfo_rooty(), 250)
        self.app.show_frame('REGISTER')
        self.root.update()
        for widget in [self.app.btn_capture, self.app.btn_registration_filter,
                       self.app.btn_registration_previous, self.app.btn_registration_next,
                       *self.app.registration_cards]:
            x = widget.winfo_rootx() - self.root.winfo_rootx()
            y = widget.winfo_rooty() - self.root.winfo_rooty()
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + widget.winfo_width(), 780)
            self.assertLessEqual(y + widget.winfo_height(), 400)
            self.assertGreaterEqual(widget.winfo_height(), 20)

    def test_registration_cards_fit_fullscreen_with_larger_fonts(self):
        self.app.show_frame('REGISTER')
        for scaling in [1.33, 2]:
            self.root.tk.call('tk', 'scaling', scaling)
            self.root.geometry('800x480')
            self.root.update()
            for widget in [*self.app.registration_cards, self.app.btn_capture,
                           self.app.btn_registration_next, self.app.btn_registration_filter]:
                self.assertLessEqual(widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height(), 480)
                self.assertGreaterEqual(widget.winfo_height(), 35)

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

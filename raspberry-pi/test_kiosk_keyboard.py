"""Keep the reusable touch keyboard covered independently of card registration."""
import string
import tkinter as tk
import unittest
from kiosk_keyboard import TouchKeyboard


class TouchKeyboardTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.attributes('-alpha', 0)
        self.entry = tk.Entry(self.root)
        self.entry.pack(fill='x')
        self.keyboard = TouchKeyboard(self.root, lambda value: self.entry.insert(tk.END, value),
                                     lambda: self.entry.delete(max(0, len(self.entry.get()) - 1), tk.END),
                                     lambda: self.entry.delete(0, tk.END))
        self.keyboard.pack(fill='both', expand=True)

    def tearDown(self):
        self.root.destroy()

    def test_all_keys_fit_available_space(self):
        self.root.deiconify()
        for width,height,scaling in [(500,300,1.33),(500,300,2)]:
            self.root.tk.call('tk', 'scaling', scaling)
            self.root.geometry(f'{width}x{height}')
            self.root.update()
            self.assertTrue(set(string.digits + string.ascii_uppercase).issubset(self.keyboard.keys))
            for widget in self.keyboard.keys.values():
                self.assertLessEqual(widget.winfo_rootx() - self.root.winfo_rootx() + widget.winfo_width(), width)
                self.assertLessEqual(widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height(), height)

    def test_insertion_and_edit_actions(self):
        for key in ['9', '0', 'O', 'SPACE', 'P', '-']:
            self.keyboard.keys[key].invoke()
        self.assertEqual(self.entry.get(), '90O P-')
        self.keyboard.keys['DEL'].invoke()
        self.assertEqual(self.entry.get(), '90O P')
        self.keyboard.keys['CLEAR'].invoke()
        self.assertEqual(self.entry.get(), '')


if __name__ == '__main__':
    unittest.main()

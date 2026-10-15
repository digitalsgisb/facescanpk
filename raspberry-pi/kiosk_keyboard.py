"""A touchscreen keyboard that shares its available width across all keys."""
import tkinter as tk


class TouchKeyboard(tk.Frame):
    def __init__(self, parent, on_insert, on_backspace, on_clear, background='#1e1e1e'):
        super().__init__(parent, bg=background)
        self.keys = {}
        for column in range(20):
            self.columnconfigure(column, weight=1, uniform='key')
        for row in range(5):
            self.rowconfigure(row, weight=1, uniform='key')
        rows = ['1234567890', 'QWERTYUIOP', "ASDFGHJKL'", 'ZXCVBNM-']
        for row, letters in enumerate(rows):
            offset = (20 - len(letters) * 2) // 2
            for index, letter in enumerate(letters):
                button = self.make_key(letter, lambda value=letter: on_insert(value))
                button.grid(row=row, column=offset+index*2, columnspan=2, sticky='nsew', padx=1, pady=1)
        for label, column, span, command, color in [
            ('SPACE', 0, 10, lambda: on_insert(' '), '#333'),
            ('DEL', 10, 5, on_backspace, '#665500'),
            ('CLEAR', 15, 5, on_clear, '#660000'),
        ]:
            button = self.make_key(label, command, color)
            button.grid(row=4, column=column, columnspan=span, sticky='nsew', padx=1, pady=1)

    def make_key(self, label, command, color='#333'):
        button = tk.Button(self, text=label, command=command, font=('Arial', 13, 'bold'),
                           bg=color, fg='white', activebackground='#831b1c', activeforeground='white',
                           width=1, height=1, padx=0, pady=0, bd=1, takefocus=False)
        self.keys[label] = button
        return button

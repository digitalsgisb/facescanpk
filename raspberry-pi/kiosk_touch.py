"""Tk button taps that do not depend on mouse-hover Enter events."""
import os
import tkinter as tk


def trace_input(event, phase):
    if os.environ.get('KIOSK_DEBUG_TOUCH') == '1':
        print(f'[TOUCH] {phase} widget={event.widget.winfo_class()} '
              f'local={event.x},{event.y} screen={event.x_root},{event.y_root}', flush=True)


def enable_touch_buttons(parent):
    """Install once on existing buttons; preserve keyboard and invoke() behavior."""
    for widget in parent.winfo_children():
        if isinstance(widget, tk.Button) and not getattr(widget, '_kiosk_touch_bound', False):
            widget._kiosk_touch_bound = True
            widget._kiosk_touch_armed = False
            widget._kiosk_touch_relief = widget.cget('relief')

            def press(event, button=widget):
                trace_input(event, 'press')
                button._kiosk_touch_armed = button.cget('state') != 'disabled'
                if button._kiosk_touch_armed:
                    button.configure(relief='sunken')
                return 'break'

            def release(event, button=widget):
                trace_input(event, 'release')
                armed = button._kiosk_touch_armed
                button._kiosk_touch_armed = False
                button.configure(relief=button._kiosk_touch_relief)
                inside = 0 <= event.x < button.winfo_width() and 0 <= event.y < button.winfo_height()
                if armed and inside and button.cget('state') != 'disabled':
                    button.invoke()
                # Prevent the Tk class binding from invoking the command again.
                return 'break'

            widget.bind('<ButtonPress-1>', press)
            widget.bind('<ButtonRelease-1>', release)
        enable_touch_buttons(widget)

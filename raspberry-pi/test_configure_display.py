import unittest
from configure_display import pin_window


class DisplayConfigTests(unittest.TestCase):
    def test_preserves_touch_output_settings_comments_and_existing_rules(self):
        original = ('# Desktop\n[core]\nplugins = move resize\n'
                    '[input-device:10-0038 generic ft5x06 (79)]\noutput = DSI-1\n'
                    '[output:HDMI-A-2]\nposition = 800,0\n'
                    '[window-rules]\nother = on created then maximize\n')
        result = pin_window(original, 'DSI-1')
        self.assertIn('# Desktop\n', result)
        self.assertIn('[input-device:10-0038 generic ft5x06 (79)]\noutput = DSI-1\n', result)
        self.assertIn('[output:HDMI-A-2]\nposition = 800,0\n', result)
        self.assertIn('other = on created then maximize\n', result)
        self.assertIn('plugins = move resize window-rules\n', result)
        self.assertIn('start_on_output "DSI-1"', result)
        self.assertEqual(pin_window(result, 'DSI-1'), result)

    def test_uses_inherited_plugins_without_removing_them(self):
        result = pin_window('[input]\nxkb_layout = us', 'DSI-1', '[core]\nplugins = move resize')
        self.assertIn('plugins = move resize window-rules', result)
        self.assertIn('xkb_layout = us\n', result)

    def test_preserves_unknown_inherited_plugins(self):
        original = '[input]\nxkb_layout = us\n'
        result = pin_window(original, 'DSI-1')
        self.assertTrue(result.startswith(original))
        self.assertNotIn('[core]', result)
        self.assertIn('start_on_output "DSI-1"', result)

    def test_refuses_rule_injection(self):
        with self.assertRaises(ValueError):
            pin_window('[core]\nplugins = move', 'DSI-1" then maximize')


if __name__ == '__main__':
    unittest.main()

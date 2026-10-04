import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('menu', pathlib.Path(__file__).resolve().parents[1] / 'scripts/menu.py')
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)

class Menu(unittest.TestCase):
    def test_fresh_system(self):
        result = menu.update('{}\n')
        self.assertEqual(menu.parse(result)[0][menu.KEY]['label'], 'System Cleaner')

    def test_preserves_comments_and_unrelated_entries(self):
        text = '{\n// keep me\n"other": {"url":"https://example.org", "action":"unchanged"}, // trailing\n}\n'
        installed = menu.update(text)
        self.assertIn('// keep me', installed)
        self.assertIn('// trailing', installed)
        self.assertEqual(menu.parse(installed)[0]['other'], menu.parse(text)[0]['other'])
        self.assertEqual(menu.update(installed), installed)
        removed = menu.update(installed, True)
        self.assertEqual(menu.parse(removed)[0], menu.parse(text)[0])
        self.assertIn('// keep me', removed)

    def test_entry_conflict_stops_install(self):
        with self.assertRaises(ValueError):
            menu.update('{"setup.cleanmacaci":{"action":"another-app"}}')

    def test_remove_only_owned_entry(self):
        text = '{"setup.cleanmacaci":{"action":"another-app"}}'
        with self.assertRaises(ValueError):
            menu.update(text, True)

    def test_empty_remove_and_install_remove(self):
        self.assertEqual(menu.update('{}', True), '{}')
        self.assertEqual(menu.parse(menu.update(menu.update('{}'), True))[0], {})

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            menu.parse('{"x":1,"x":2}')

if __name__ == '__main__':
    unittest.main()

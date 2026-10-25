"""Offline tests for SynthWave's Neon Dreams activation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('neon', ROOT / 'roles/dev/files/enable_neon_dreams.py')
NEON = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NEON)


class NeonDreamsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.extension = self.root / 'extension'
        (self.extension / 'src/js').mkdir(parents=True)
        (self.extension / 'src/css').mkdir()
        (self.extension / 'src/js/theme_template.js').write_text('[DISABLE_GLOW];[CHROME_STYLES];[NEON_BRIGHTNESS]')
        (self.extension / 'src/css/editor_chrome.css').write_text('.editor { color: pink; }')
        self.installation = self.root / 'code'

    def workbench(self, directory, filename):
        path = self.installation / 'resources/app/out/vs/code' / directory / 'workbench' / filename
        path.parent.mkdir(parents=True)
        path.write_text('<html><body>VS Code</body></html>')
        return path

    def test_supported_layouts_enable_once_and_refresh_settings(self):
        for directory in ('electron-browser', 'electron-sandbox'):
            for filename in ('workbench.esm.html', 'workbench.html'):
                with self.subTest(directory=directory, filename=filename):
                    self.installation = self.root / f'{directory}-{filename}'
                    html = self.workbench(directory, filename)
                    self.assertTrue(NEON.enable_neon_dreams(self.extension, self.installation, {}))
                    self.assertEqual(html.read_text().count('src="neondreams.js"'), 1)
                    self.assertTrue(html.read_text().endswith('</html>'))
                    theme = html.with_name('neondreams.js')
                    self.assertEqual(theme.read_text(), 'false;.editor { color: pink; };72')
                    self.assertFalse(NEON.enable_neon_dreams(self.extension, self.installation, {}))
                    settings = {'synthwave84.brightness': 0.8, 'synthwave84.disableGlow': True}
                    self.assertTrue(NEON.enable_neon_dreams(self.extension, self.installation, settings))
                    self.assertEqual(theme.read_text(), 'true;.editor { color: pink; };CC')
                    self.assertEqual(html.read_text().count('src="neondreams.js"'), 1)

    def test_reapplies_after_vscode_is_replaced(self):
        html = self.workbench('electron-browser', 'workbench.html')
        NEON.enable_neon_dreams(self.extension, self.installation, {})
        html.write_text('<html>New VS Code version</html>')
        self.assertTrue(NEON.enable_neon_dreams(self.extension, self.installation, {}))
        self.assertIn('New VS Code version', html.read_text())
        self.assertEqual(html.read_text().count('src="neondreams.js"'), 1)

    def test_jsonc_settings_preserve_strings(self):
        settings = self.root / 'settings.json'
        settings.write_text('''{
            // Neon settings
            "synthwave84.brightness": 0.8,
            "synthwave84.disableGlow": false, /* keep glow */
            "url": "https://example.org/*literal*/",
            "text": "comma,} and escaped quote \\\" // literal",
            "array": [1, 2,],
        }''')
        parsed = NEON.read_settings(settings)
        self.assertEqual(parsed['synthwave84.brightness'], 0.8)
        self.assertFalse(parsed['synthwave84.disableGlow'])
        self.assertEqual(parsed['url'], 'https://example.org/*literal*/')
        self.assertEqual(parsed['text'], 'comma,} and escaped quote " // literal')
        self.assertEqual(parsed['array'], [1, 2])

    def test_missing_workbench_fails_explicitly(self):
        with self.assertRaisesRegex(RuntimeError, 'workbench HTML not found'):
            NEON.enable_neon_dreams(self.extension, self.installation, {})


if __name__ == '__main__':
    unittest.main()

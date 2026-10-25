"""Apply SynthWave '84's enableNeon file changes without launching VS Code."""
import json
import math
from pathlib import Path
import re
import sys


def read_settings(path):
    # VS Code settings are JSONC: preserve strings while removing comments
    # and trailing commas.
    text = path.read_text()
    text = re.sub(
        r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/',
        lambda match: match[0] if match[0].startswith('"') else ' ',
        text,
    )
    text = re.sub(
        r'"(?:\\.|[^"\\])*"|,\s*(?=[}\]])',
        lambda match: match[0] if match[0].startswith('"') else '',
        text,
    )
    return json.loads(text)


def enable_neon_dreams(extension, installation, settings):
    base = installation / 'resources/app/out/vs/code'
    # These are the layouts supported by SynthWave's enableNeon command.
    workbench = next((
        base / directory / 'workbench' / filename
        for directory in ('electron-browser', 'electron-sandbox')
        for filename in ('workbench.esm.html', 'workbench.html')
        if (base / directory / 'workbench' / filename).is_file()
    ), None)
    if workbench is None:
        raise RuntimeError('SynthWave: VS Code workbench HTML not found')

    try:
        brightness = float(settings.get('synthwave84.brightness', 0.45))
    except (ValueError, TypeError):
        brightness = 0.45
    if math.isnan(brightness):
        brightness = 0.45
    brightness = min(1, max(0, brightness))
    glow_disabled = bool(settings.get('synthwave84.disableGlow', False))

    theme = (extension / 'src/js/theme_template.js').read_text()
    chrome = (extension / 'src/css/editor_chrome.css').read_text()
    theme = theme.replace('[DISABLE_GLOW]', str(glow_disabled).lower())
    theme = theme.replace('[CHROME_STYLES]', chrome)
    theme = theme.replace('[NEON_BRIGHTNESS]', format(math.floor(brightness * 255), 'X'))

    html = workbench.read_text()
    if 'neondreams.js' not in html:
        if '</html>' not in html:
            raise RuntimeError('SynthWave: closing HTML tag not found')
        html = html.replace('</html>', '\t<!-- SYNTHWAVE 84 --><script src="neondreams.js"></script><!-- NEON DREAMS -->\n</html>')

    changed = False
    for path, content in ((workbench.with_name('neondreams.js'), theme), (workbench, html)):
        if not path.exists() or path.read_text() != content:
            path.write_text(content)
            changed = True
    return changed


if __name__ == '__main__':
    extension, installation, settings = map(Path, sys.argv[1:])
    if not extension.is_dir() or not (extension / 'src/js/theme_template.js').is_file():
        raise RuntimeError('SynthWave extension is not installed or its template is missing')
    changed = enable_neon_dreams(extension, installation, read_settings(settings))
    print('changed' if changed else 'ok')

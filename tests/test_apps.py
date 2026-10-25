"""Offline checks for Chromium, Chrome and desktop applications."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / 'roles/desktop/tasks'


class DesktopApplicationsTests(unittest.TestCase):
    def test_standard_desktop_packages_are_installed(self):
        packages = yaml.safe_load((TASKS / 'packages.yml').read_text())[1]['ansible.builtin.apt']['name']
        for package in [
            'chromium', 'gimp', 'audacity', 'keepassxc', 'kdeconnect',
            'syncthing', 'thunderbird', 'thunderbird-l10n-fr', 'libnss3-tools',
            'wireguard-tools', 'firmware-amd-graphics', 'mesa-vulkan-drivers',
            'mesa-va-drivers', 'mesa-vdpau-drivers', 'libglx-mesa0',
            'mesa-utils', 'vulkan-tools', 'radeontop',
        ]:
            self.assertIn(package, packages)

    def test_chromium_and_chrome_share_the_oxlabs_nss_trust(self):
        tasks = yaml.safe_load((TASKS / 'browsers.yml').read_text())
        nss = next(task for task in tasks if task['name'].startswith('Initialize the shared'))
        self.assertIn('sql:/home/{{ desktop_user }}/.pki/nssdb', nss['ansible.builtin.command']['argv'])
        import_task = next(task for task in tasks if task['name'].startswith('Import the Oxlabs'))
        self.assertIn('/usr/local/share/ca-certificates/oxlabs-root.crt', import_task['ansible.builtin.command']['argv'])
        self.assertIn('C,,', import_task['ansible.builtin.command']['argv'])
        self.assertFalse(any('mimeapps.list' in str(task) for task in tasks))

    def test_google_chrome_is_installed_from_the_official_package(self):
        defaults = yaml.safe_load((ROOT / 'roles/desktop/defaults/main.yml').read_text())
        self.assertEqual(
            defaults['google_chrome_apt_uri'],
            'https://dl.google.com/linux/chrome/deb/',
        )
        tasks = yaml.safe_load((TASKS / 'browsers.yml').read_text())
        archive = next(task for task in tasks if task['name'].startswith('Require the x86_64'))
        self.assertIn('x86_64', archive['ansible.builtin.assert']['that'])
        repository = next(task for task in tasks if task['name'].startswith('Configure the official Google'))
        self.assertEqual(repository['ansible.builtin.deb822_repository']['name'], 'google-chrome')
        self.assertEqual(repository['ansible.builtin.deb822_repository']['signed_by'], '{{ google_chrome_apt_key_url }}')
        install = next(task for task in tasks if task['name'].startswith('Install Google Chrome'))
        self.assertEqual(install['ansible.builtin.apt']['name'], 'google-chrome-stable')

    def test_sway_portal_preferences_select_gtk_wlr_and_keyring(self):
        tasks = yaml.safe_load((TASKS / 'portals.yml').read_text())
        config = next(task for task in tasks if task['name'].startswith('Select the Wayland portal'))
        self.assertEqual(config['ansible.builtin.copy']['dest'], '/etc/xdg-desktop-portal/sway-portals.conf')
        content = config['ansible.builtin.copy']['content']
        self.assertIn('default=gtk', content)
        self.assertIn('org.freedesktop.impl.portal.ScreenCast=wlr', content)
        self.assertIn('org.freedesktop.impl.portal.Screenshot=wlr', content)
        self.assertIn('org.freedesktop.impl.portal.Secret=gnome-keyring', content)

    def test_signal_is_installed_from_flathub_system_wide(self):
        tasks = yaml.safe_load((ROOT / 'roles/flatpak/tasks/main.yml').read_text())
        task = next(task for task in tasks if task['name'] == 'Install apps via system Flatpak')
        self.assertIn('org.signal.Signal', task['loop'])
        flatpak = task['community.general.flatpak']
        self.assertEqual(flatpak['remote'], 'flathub')
        self.assertEqual(flatpak['method'], 'system')
        self.assertEqual(flatpak['state'], 'present')

    def test_signal_has_system_wide_host_filesystem_access(self):
        tasks = yaml.safe_load((ROOT / 'roles/flatpak/tasks/main.yml').read_text())
        directory = next(task for task in tasks if task['name'] == 'Create the system Flatpak overrides directory')
        self.assertEqual(directory['ansible.builtin.file']['path'], '/var/lib/flatpak/overrides')
        self.assertEqual(directory['ansible.builtin.file']['state'], 'directory')
        task = next(task for task in tasks if task['name'] == 'Allow Signal to access host files')
        override = task['community.general.ini_file']
        self.assertEqual(override['path'], '/var/lib/flatpak/overrides/org.signal.Signal')
        self.assertEqual(override['section'], 'Context')
        self.assertEqual(override['option'], 'filesystems')
        self.assertEqual(override['value'], 'host;')
        self.assertTrue(override['no_extra_spaces'])
        self.assertEqual(override['owner'], 'root')
        self.assertEqual(override['mode'], '0644')

    def test_browser_tasks_are_imported(self):
        tasks = yaml.safe_load((TASKS / 'main.yml').read_text())
        imported = {task.get('ansible.builtin.import_tasks'): task for task in tasks if 'ansible.builtin.import_tasks' in task}
        self.assertIn('browsers.yml', imported)
        self.assertIn('chrome', imported['browsers.yml']['tags'])


if __name__ == '__main__':
    unittest.main()

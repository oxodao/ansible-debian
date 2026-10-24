"""Offline checks for Firefox policies, preferences and AutoConfig."""
import json
from pathlib import Path
import unittest

from ansible.plugins.filter.core import FilterModule
from jinja2 import Environment, FileSystemLoader, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/firefox'


class FirefoxTests(unittest.TestCase):
    def setUp(self):
        self.defaults = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())
        self.tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        self.env = Environment(
            loader=FileSystemLoader(ROLE / 'templates'),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            trim_blocks=True,
        )
        self.env.filters.update(FilterModule().filters())

    def test_policies_include_every_supported_preference(self):
        task = next(
            task for task in self.tasks
            if task.get('ansible.builtin.copy', {}).get('dest') == '/etc/firefox/policies/policies.json'
        )
        rendered = self.env.from_string(task['ansible.builtin.copy']['content']).render(
            firefox_policies=self.defaults['firefox_policies'],
            firefox_preferences=self.defaults['firefox_preferences'],
            firefox_extensions=self.defaults['firefox_extensions'],
        )
        policies = json.loads(rendered)['policies']
        self.assertEqual(policies['Preferences'], self.defaults['firefox_preferences'])
        self.assertNotIn('findbar.highlightAll', policies['Preferences'])
        self.assertEqual(policies['RequestedLocales'], ['fr'])
        self.assertEqual(policies['Certificates']['Install'], ['/usr/local/share/ca-certificates/oxlabs-root.crt'])
        self.assertEqual(policies['AIControls']['SidebarChatbot']['Value'], 'blocked')
        self.assertTrue(policies['DisableProfileImport'])
        self.assertEqual(policies['OverrideFirstRunPage'], '')
        self.assertEqual(policies['OverridePostUpdatePage'], '')
        self.assertFalse(policies['Preferences']['browser.aboutwelcome.enabled']['Value'])
        self.assertEqual(policies['Preferences']['intl.locale.requested']['Value'], 'fr')
        self.assertEqual(policies['Preferences']['intl.accept_languages']['Value'], 'fr-FR, fr, en-US, en')
        self.assertEqual(policies['ExtensionSettings'], self.defaults['firefox_extensions'])
        self.assertEqual(len(policies['ExtensionSettings']), 9)
        theme = '{7d275064-ec2e-4a96-b0cf-a774c506d22d}'
        self.assertIn(theme, policies['ExtensionSettings'])
        self.assertIn('{74145f27-f039-47ce-a470-a662b129930a}', policies['ExtensionSettings'])
        for extension_id, extension in policies['ExtensionSettings'].items():
            self.assertEqual(extension['installation_mode'], 'normal_installed')
            self.assertTrue(extension['install_url'].startswith('https://addons.mozilla.org/'))
            self.assertTrue(extension['install_url'].endswith('/latest.xpi'))
            if extension_id != theme:
                self.assertTrue(extension['private_browsing'])
        self.assertNotIn('Cookie-Editor', json.dumps(policies))
        self.assertNotIn('Video Download Helper', json.dumps(policies))

    def test_unsupported_preferences_use_autoconfig(self):
        config = self.env.get_template('firefox.cfg.j2').render(
            firefox_autoconfig_preferences=self.defaults['firefox_autoconfig_preferences'],
        )
        self.assertTrue(config.startswith('// The first line'))
        self.assertIn('defaultPref("findbar.highlightAll", true);', config)
        entrypoint = self.env.get_template('autoconfig.js.j2').render()
        self.assertIn('pref("general.config.filename", "firefox.cfg");', entrypoint)
        destinations = {
            task.get('ansible.builtin.copy', {}).get('dest'): task
            for task in self.tasks if 'ansible.builtin.copy' in task
        }
        destinations.update({
            task.get('ansible.builtin.template', {}).get('dest'): task
            for task in self.tasks if 'ansible.builtin.template' in task
        })
        self.assertIn('/etc/firefox/defaults/pref/autoconfig.js', destinations)
        self.assertIn('/etc/firefox/firefox.cfg', destinations)

    def test_firefox_requires_the_oxlabs_root_ca(self):
        check = next(task for task in self.tasks if task['name'].startswith('Check the Oxlabs root CA'))
        self.assertEqual(check['ansible.builtin.stat']['path'], '/usr/local/share/ca-certificates/oxlabs-root.crt')
        requirement = next(task for task in self.tasks if task['name'].startswith('Require the Oxlabs root CA'))
        self.assertEqual(requirement['ansible.builtin.assert']['that'], 'firefox_root_ca.stat.exists')
        self.assertIn('root_ca', requirement['ansible.builtin.assert']['fail_msg'])

    def test_all_firefox_management_files_are_written_as_root(self):
        tasks = [
            task for task in self.tasks
            if task.get('ansible.builtin.copy', {}).get('dest', '').startswith('/etc/firefox/')
            or task.get('ansible.builtin.template', {}).get('dest', '').startswith('/etc/firefox/')
        ]
        self.assertEqual(len(tasks), 3)
        for task in tasks:
            module = task.get('ansible.builtin.copy') or task.get('ansible.builtin.template')
            self.assertEqual(module['owner'], 'root')
            self.assertEqual(module['group'], 'root')
            self.assertEqual(module['mode'], '0644')


if __name__ == '__main__':
    unittest.main()

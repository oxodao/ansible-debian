"""Offline checks for installation from the latest miniscr Debian package."""
from pathlib import Path
import re
import unittest

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]


class MiniscrTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load((ROOT / 'roles/desktop/tasks/miniscr.yml').read_text())

    def test_resolves_the_latest_release_and_verifies_the_download(self):
        self.assertEqual(
            self.tasks[0]['ansible.builtin.uri']['url'],
            'https://api.github.com/repos/oxodao/miniscr/releases/latest',
        )
        download = next(task['ansible.builtin.get_url'] for task in self.tasks if 'ansible.builtin.get_url' in task)
        self.assertEqual(download['url'], '{{ miniscr_assets[0].browser_download_url }}')
        self.assertIn('miniscr_assets[0].digest', download['checksum'])
        self.assertEqual(download['mode'], '0644')

    def test_selects_only_the_architecture_independent_deb(self):
        env = Environment(undefined=StrictUndefined)
        env.tests['match'] = lambda value, pattern: re.match(pattern, value) is not None
        expression = self.tasks[1]['ansible.builtin.set_fact']['miniscr_assets']
        select = env.compile_expression(expression[2:-2].strip())
        assets = [
            {'name': 'miniscr_0.1.0_all.deb'},
            {'name': 'miniscr_0.1.0_amd64.deb'},
            {'name': 'miniscr_0.1.0_all.deb.sha256'},
            {'name': 'miniscr_0.1.0_allXdeb'},
            {'name': 'other_0.1.0_all.deb'},
        ]
        self.assertEqual(select(miniscr_release={'json': {'assets': assets}}), assets[:1])
        self.assertEqual(select(miniscr_release={'json': {'assets': []}}), [])
        require = next(task['ansible.builtin.assert'] for task in self.tasks if 'ansible.builtin.assert' in task)
        self.assertEqual(require['that'], 'miniscr_assets | length == 1')

    def test_installs_the_downloaded_package_with_apt_for_dependencies(self):
        download = next(task['ansible.builtin.get_url'] for task in self.tasks if 'ansible.builtin.get_url' in task)
        install = self.tasks[-1]['ansible.builtin.apt']
        self.assertEqual(install['deb'], download['dest'])
        self.assertEqual(install['state'], 'present')
        self.assertTrue(install['update_cache'])
        self.assertFalse(any('ansible.builtin.command' in task or 'ansible.builtin.shell' in task for task in self.tasks))

    def test_is_part_of_the_terminal_tasks_without_a_dedicated_tag(self):
        tasks = yaml.safe_load((ROOT / 'roles/desktop/tasks/terminal.yml').read_text())
        task = next(task for task in tasks if task.get('ansible.builtin.import_tasks') == 'miniscr.yml')
        self.assertNotIn('tags', task)


if __name__ == '__main__':
    unittest.main()

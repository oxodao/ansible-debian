"""Offline checks for installation from published GitHub binaries."""
from pathlib import Path
import re
import unittest

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]


class MetaprintTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load((ROOT / 'roles/desktop/tasks/metaprint.yml').read_text())

    def test_installs_a_release_binary_without_compilation(self):
        self.assertEqual(
            self.tasks[0]['ansible.builtin.uri']['url'],
            'https://api.github.com/repos/oxodao/metaprint/releases/latest',
        )
        self.assertFalse(any('ansible.builtin.command' in task or 'ansible.builtin.git' in task for task in self.tasks))
        install = self.tasks[-1]['ansible.builtin.get_url']
        self.assertEqual(install['dest'], '/usr/local/bin/metaprint')
        self.assertEqual(install['owner'], 'root')
        self.assertEqual(install['mode'], '0755')

    def test_selects_only_the_matching_linux_architecture(self):
        env = Environment(undefined=StrictUndefined)
        env.tests['match'] = lambda value, pattern: re.match(pattern, value) is not None
        expression = self.tasks[1]['ansible.builtin.set_fact']['metaprint_assets']
        select = env.compile_expression(expression[2:-2].strip())
        assets = [
            {'name': 'metaprint-v0.5-linux-x86_64'},
            {'name': 'metaprint-v0.5-linux-aarch64'},
            {'name': 'metaprint-v0.5-darwin-x86_64'},
        ]
        for architecture, expected in [('x86_64', assets[:1]), ('aarch64', assets[1:2]), ('armv7l', [])]:
            with self.subTest(architecture=architecture):
                self.assertEqual(select(
                    metaprint_release={'json': {'assets': assets}},
                    ansible_facts={'architecture': architecture},
                ), expected)

    def test_is_part_of_the_terminal_tasks_and_keeps_its_tag(self):
        tasks = yaml.safe_load((ROOT / 'roles/desktop/tasks/terminal.yml').read_text())
        task = next(task for task in tasks if task.get('ansible.builtin.import_tasks') == 'metaprint.yml')
        self.assertEqual(task['tags'], ['metaprint'])
        play = yaml.safe_load((ROOT / 'site.yml').read_text())[0]
        self.assertNotIn('metaprint', [role['role'] for role in play['roles']])


if __name__ == '__main__':
    unittest.main()

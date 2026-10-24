"""Offline checks for the games role."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/games'


class GamesTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())

    def test_steam_is_installed_with_gaming_support(self):
        install = next(task for task in self.tasks if task['name'].startswith('Install Steam'))
        packages = install['ansible.builtin.apt']['name']
        for package in ['steam-installer', 'steam-devices', 'gamemode', 'mangohud']:
            self.assertIn(package, packages)
        for package in ['libgl1-mesa-dri:i386', 'libglx-mesa0:i386', 'mesa-vulkan-drivers:i386']:
            self.assertIn(package, packages)
        self.assertNotIn('steam', packages)

    def test_i386_is_enabled_before_steam(self):
        check = self.tasks[0]
        self.assertEqual(check['ansible.builtin.command'], 'dpkg --print-foreign-architectures')
        add = self.tasks[1]
        self.assertEqual(add['ansible.builtin.command'], 'dpkg --add-architecture i386')
        self.assertEqual(add['when'], '"i386" not in games_foreign_architectures.stdout_lines')

    def test_games_role_is_in_the_playbook(self):
        site = yaml.safe_load((ROOT / 'site.yml').read_text())[0]
        role = next(role for role in site['roles'] if role['role'] == 'games')
        self.assertEqual(role['tags'], ['games'])


if __name__ == '__main__':
    unittest.main()

"""Offline checks for the explicitly requested configuration replacement."""
from pathlib import Path
import unittest

from jinja2 import Environment
import yaml


ROOT = Path(__file__).resolve().parents[1]


class DotfilesTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load((ROOT / 'roles/dotfiles/tasks/main.yml').read_text())

    def test_dotfiles_run_before_desktop_including_with_desktop_tag(self):
        roles = yaml.safe_load((ROOT / 'site.yml').read_text())[0]['roles']
        names = [role['role'] for role in roles]
        self.assertLess(names.index('dotfiles'), names.index('desktop'))
        self.assertIn('desktop', roles[names.index('dotfiles')]['tags'])

    def test_opt_ownership_is_not_recursive_and_clone_runs_as_user(self):
        opt = next(task['ansible.builtin.file'] for task in self.tasks if task.get('ansible.builtin.file', {}).get('path') == '/opt')
        self.assertEqual(opt['owner'], '{{ desktop_user }}')
        self.assertNotIn('recurse', opt)
        clone = next(task for task in self.tasks if 'ansible.builtin.git' in task)
        self.assertEqual(clone['become_user'], '{{ desktop_user }}')
        self.assertEqual(clone['ansible.builtin.git']['dest'], '/opt/dotfiles')
        self.assertEqual(clone['ansible.builtin.git']['repo'], 'https://github.com/oxodao/dotfiles.git')
        self.assertNotIn('force', clone['ansible.builtin.git'])
        self.assertTrue(clone['ansible.builtin.git']['update'])

    def test_only_non_symlinks_are_removed_and_replaced(self):
        stat = next(task['ansible.builtin.stat'] for task in self.tasks if 'ansible.builtin.stat' in task)
        self.assertFalse(stat['follow'])
        remove, link = self.tasks[-2:]
        self.assertEqual(remove['ansible.builtin.file']['state'], 'absent')
        self.assertEqual(link['ansible.builtin.file']['src'], '/opt/dotfiles/config')
        self.assertEqual(link['ansible.builtin.file']['dest'], '/home/{{ desktop_user }}/.config')
        for task in (remove, link):
            condition = Environment().compile_expression(task['when'])
            self.assertFalse(condition(dotfiles_config={'stat': {'islnk': True}}))
            self.assertTrue(condition(dotfiles_config={'stat': {'islnk': False}}))
            self.assertTrue(condition(dotfiles_config={'stat': {'exists': False}}))

    def test_origin_switches_to_ssh_directly_after_the_https_clone(self):
        index = next(index for index, task in enumerate(self.tasks) if 'ansible.builtin.git' in task)
        task = self.tasks[index + 1]
        self.assertEqual(task['become_user'], '{{ desktop_user }}')
        self.assertEqual(task['ansible.builtin.command']['argv'], [
            'git', '-C', '/opt/dotfiles', 'remote', 'set-url', 'origin',
            'git@github.com:oxodao/dotfiles.git',
        ])
        self.assertNotIn('when', task)

    def test_session_does_not_generate_user_or_fallback_configurations(self):
        tasks = yaml.safe_load((ROOT / 'roles/desktop/tasks/session.yml').read_text())
        self.assertFalse(any(task.get('ansible.builtin.template', {}).get('dest', '').startswith('/home/') for task in tasks))
        fallback = next(task['ansible.builtin.file'] for task in tasks if task.get('ansible.builtin.file', {}).get('path') == '/usr/local/etc/sway/config')
        self.assertEqual(fallback['state'], 'absent')
        launcher = (ROOT / 'roles/desktop/templates/start-sway.sh.j2').read_text()
        self.assertIn("--config '/home/{{ desktop_user }}/.config/sway/config'", launcher)


if __name__ == '__main__':
    unittest.main()

"""Offline checks for system-wide custom fonts and Nerd Fonts."""
from pathlib import Path
import unittest

from jinja2 import Environment
import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/desktop'


class FontsTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load((ROLE / 'tasks/fonts.yml').read_text())

    def test_custom_fonts_are_copied_recursively_system_wide(self):
        task = next(task for task in self.tasks if 'ansible.builtin.copy' in task)
        copy = task['ansible.builtin.copy']
        self.assertEqual(copy['src'], 'fonts/')
        self.assertEqual(copy['dest'], '/usr/local/share/fonts/custom/')
        self.assertEqual(copy['owner'], 'root')
        self.assertEqual(copy['group'], 'root')
        self.assertEqual(copy['mode'], '0644')
        self.assertEqual(copy['directory_mode'], '0755')
        self.assertEqual(task['notify'], 'Refresh the font cache')
        self.assertTrue((ROLE / 'files/fonts').is_dir())

    def test_hack_remains_the_default_without_reinstalling_existing_fonts(self):
        defaults = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())
        self.assertEqual(defaults['nerd_fonts'], [{'name': 'Hack', 'font_file': 'HackNerdFont-Regular.ttf'}])
        task = next(task for task in self.tasks if 'ansible.builtin.unarchive' in task)
        archive = task['ansible.builtin.unarchive']
        environment = Environment()
        render = lambda value: environment.from_string(value).render(item=defaults['nerd_fonts'][0])
        self.assertEqual(render(archive['src']), 'https://github.com/ryanoasis/nerd-fonts/releases/latest/download/Hack.tar.xz')
        self.assertEqual(render(archive['dest']), '/usr/local/share/fonts/HackNerdFont')
        self.assertEqual(render(archive['creates']), '/usr/local/share/fonts/HackNerdFont/HackNerdFont-Regular.ttf')
        self.assertTrue(archive['remote_src'])
        self.assertEqual(task['notify'], 'Refresh the font cache')

    def test_nerd_font_tasks_loop_over_the_configured_fonts(self):
        environment = Environment()
        item = {'name': 'CascadiaCode', 'font_file': 'CaskaydiaCoveNerdFont-Regular.ttf'}
        for module in ('ansible.builtin.file', 'ansible.builtin.unarchive'):
            task = next(task for task in self.tasks if module in task)
            self.assertEqual(task['loop'], '{{ nerd_fonts }}')
            self.assertEqual(task['loop_control']['label'], '{{ item.name }}')
        archive = next(task['ansible.builtin.unarchive'] for task in self.tasks if 'ansible.builtin.unarchive' in task)
        self.assertEqual(environment.from_string(archive['src']).render(item=item), 'https://github.com/ryanoasis/nerd-fonts/releases/latest/download/CascadiaCode.tar.xz')
        self.assertEqual(environment.from_string(archive['creates']).render(item=item), '/usr/local/share/fonts/CascadiaCodeNerdFont/CaskaydiaCoveNerdFont-Regular.ttf')

    def test_common_configuration_includes_the_requested_nerd_fonts(self):
        variables = yaml.safe_load((ROOT / 'group_vars/all.yml').read_text())
        fonts = variables['nerd_fonts']
        self.assertEqual({font['name']: font['font_file'] for font in fonts}, {
            'Hack': 'HackNerdFont-Regular.ttf',
            'AdwaitaMono': 'AdwaitaMonoNerdFont-Regular.ttf',
            'DepartureMono': 'DepartureMonoNerdFont-Regular.otf',
            'FiraCode': 'FiraCodeNerdFont-Regular.ttf',
            'FiraMono': 'FiraMonoNerdFont-Regular.otf',
            'Iosevka': 'IosevkaNerdFont-Regular.ttf',
            'IosevkaTerm': 'IosevkaTermNerdFont-Regular.ttf',
            'JetBrainsMono': 'JetBrainsMonoNerdFont-Regular.ttf',
            'Noto': 'NotoMonoNerdFont-Regular.ttf',
            'RobotoMono': 'RobotoMonoNerdFont-Regular.ttf',
            'SourceCodePro': 'SauceCodeProNerdFont-Regular.ttf',
            'Ubuntu': 'UbuntuNerdFont-Regular.ttf',
            'UbuntuMono': 'UbuntuMonoNerdFont-Regular.ttf',
            'UbuntuSans': 'UbuntuSansMonoNerdFont-Regular.ttf',
        })
        self.assertEqual(len(fonts), 14)

    def test_fonts_can_be_run_with_the_fonts_tag(self):
        tasks = yaml.safe_load((ROLE / 'tasks/terminal.yml').read_text())
        fonts = next(task for task in tasks if task.get('ansible.builtin.import_tasks') == 'fonts.yml')
        self.assertIn('fonts', fonts['tags'])

    def test_interface_font_is_configured_after_font_installation(self):
        task = self.tasks[-1]
        self.assertEqual(task['become_user'], '{{ desktop_user }}')
        self.assertEqual(task['community.general.dconf'], {
            'key': '/org/gnome/desktop/interface/font-name',
            'value': "'DepartureMono Nerd Font 11'",
            'state': 'present',
        })
        gtk_tasks = yaml.safe_load((ROLE / 'tasks/gtk.yml').read_text())
        self.assertFalse(any(task['community.general.dconf']['key'].endswith('/font-name') for task in gtk_tasks))


if __name__ == '__main__':
    unittest.main()

"""Offline checks for the development tools role."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/dev'


class DevTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        self.defaults = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())

    def test_vscode_role_was_renamed_to_dev(self):
        self.assertTrue(ROLE.is_dir())
        self.assertFalse((ROOT / 'roles/vscode').exists())
        site = yaml.safe_load((ROOT / 'site.yml').read_text())[0]
        role = next(role for role in site['roles'] if role['role'] == 'dev')
        self.assertEqual(role['tags'], ['dev'])

    def test_ansible_and_repository_checks_come_from_debian(self):
        imported = next(task for task in self.tasks if task.get('ansible.builtin.import_tasks') == 'ansible.yml')
        self.assertEqual(imported['tags'], ['ansible'])
        tasks = yaml.safe_load((ROLE / 'tasks/ansible.yml').read_text())
        packages = tasks[0]['ansible.builtin.apt']['name']
        self.assertEqual(packages, ['ansible', 'python-is-python3', 'ssh-askpass', 'yamllint'])

    def test_docker_uses_debian_packages_and_activates_the_service(self):
        tasks = yaml.safe_load((ROLE / 'tasks/docker.yml').read_text())
        packages = tasks[0]['ansible.builtin.apt']['name']
        self.assertEqual(packages, ['docker.io', 'docker-compose', 'docker-buildx'])
        account = tasks[1]['ansible.builtin.user']
        self.assertEqual(account['name'], '{{ desktop_user }}')
        self.assertEqual(account['groups'], 'docker')
        self.assertTrue(account['append'])
        service = tasks[2]['ansible.builtin.systemd_service']
        self.assertEqual(service['name'], 'docker.service')
        self.assertTrue(service['enabled'])
        self.assertEqual(service['state'], 'started')

    def test_sdkman_installs_without_touching_the_user_zshrc(self):
        tasks = yaml.safe_load((ROLE / 'tasks/sdkman.yml').read_text())
        install = next(task for task in tasks if task['name'].startswith('Install SDKMAN'))
        self.assertEqual(install['become_user'], '{{ desktop_user }}')
        self.assertEqual(install['environment']['SDKMAN_DIR'], '{{ sdkman_directory }}')
        self.assertEqual(install['environment']['HOME'], '{{ sdkman_temporary_home }}')
        self.assertEqual(install['environment']['ZDOTDIR'], '{{ sdkman_temporary_home }}')
        self.assertFalse(any('lineinfile' in task or '.zshrc' in str(task) for task in tasks))

    def test_nvm_installs_without_touching_the_user_zshrc(self):
        tasks = yaml.safe_load((ROLE / 'tasks/nvm.yml').read_text())
        install = next(task for task in tasks if task['name'].startswith('Install NVM'))
        self.assertEqual(install['become_user'], '{{ desktop_user }}')
        self.assertEqual(install['environment']['NVM_DIR'], '{{ nvm_directory }}')
        self.assertEqual(install['environment']['PROFILE'], '/dev/null')
        self.assertFalse(any('lineinfile' in task or '.zshrc' in str(task) for task in tasks))

    def test_vscode_uses_a_versioned_install_and_skips_existing_versions(self):
        self.assertEqual(self.defaults['vscode_architectures'], {
            'x86_64': 'x64', 'aarch64': 'arm64', 'armv7l': 'armhf',
        })
        self.assertEqual(self.defaults['vscode_directory'], '/opt/vscode')
        tasks = yaml.safe_load((ROLE / 'tasks/vscode.yml').read_text())
        release = next(task for task in tasks if task['name'].startswith('Resolve the latest stable'))
        self.assertIn('/api/update/linux-', release['ansible.builtin.uri']['url'])
        check = next(task for task in tasks if task['name'].startswith('Check whether the latest VS Code'))
        self.assertEqual(check['ansible.builtin.stat']['path'], '{{ vscode_directory }}/{{ vscode_release.json.productVersion }}/bin/code')
        download = next(task for task in tasks if task['name'].startswith('Download the missing VS Code'))
        self.assertIn('sha256:', download['ansible.builtin.get_url']['checksum'])
        self.assertEqual(download['when'], 'not vscode_installed.stat.exists')
        version_dir = next(task for task in tasks if task['name'].startswith('Create the missing VS Code'))
        self.assertEqual(version_dir['ansible.builtin.file']['state'], 'directory')
        extract = next(task for task in tasks if task['name'].startswith('Extract the missing VS Code'))
        self.assertEqual(extract['ansible.builtin.unarchive']['dest'], '{{ vscode_directory }}/{{ vscode_release.json.productVersion }}')
        self.assertEqual(extract['ansible.builtin.unarchive']['extra_opts'], ['--strip-components=1'])
        stable = next(task for task in tasks if task['name'].startswith('Expose the current VS Code'))
        self.assertEqual(stable['ansible.builtin.file']['dest'], '/opt/code')
        self.assertEqual(stable['ansible.builtin.file']['state'], 'link')
        find_old = next(task for task in tasks if task['name'].startswith('Find obsolete VS Code'))
        self.assertEqual(find_old['ansible.builtin.find']['excludes'], '{{ vscode_release.json.productVersion }}')
        remove_old = next(task for task in tasks if task['name'].startswith('Remove obsolete VS Code'))
        self.assertEqual(remove_old['ansible.builtin.file']['state'], 'absent')
        self.assertFalse(any(task['name'].startswith('Explain how') for task in tasks))

    def test_vscode_installs_only_missing_extensions_from_remote_dotfiles(self):
        tasks = yaml.safe_load((ROLE / 'tasks/vscode.yml').read_text())
        read = next(task for task in tasks if task['name'].startswith('Read the VS Code extension'))
        self.assertEqual(read['ansible.builtin.slurp']['src'], '/opt/dotfiles/vscode_extensions.txt')
        self.assertEqual(read['register'], 'vscode_extensions')
        installed = next(task for task in tasks if task['name'].startswith('List installed VS Code extensions'))
        self.assertEqual(installed['ansible.builtin.command']['argv'], ['/opt/code/bin/code', '--list-extensions'])
        self.assertFalse(installed['changed_when'])
        install = next(task for task in tasks if task['name'].startswith('Install missing VS Code extensions'))
        self.assertEqual(install['ansible.builtin.command']['argv'], ['/opt/code/bin/code', '--install-extension', '{{ item }}'])
        self.assertIn('vscode_extensions.content | b64decode', install['loop'])
        self.assertIn('splitlines()', install['loop'])
        self.assertIn("reject('equalto', '')", install['loop'])
        self.assertIn('unique', install['loop'])
        self.assertEqual(install['when'], "item | lower not in (vscode_installed_extensions.stdout_lines | default([]) | map('lower') | list)")
        for task in (read, installed, install):
            self.assertEqual(task['become_user'], '{{ desktop_user }}')
        for task in (installed, install):
            self.assertEqual(task['environment']['HOME'], '/home/{{ desktop_user }}')
        self.assertFalse(any('--uninstall-extension' in str(task) for task in tasks))

    def test_neon_dreams_is_checked_on_every_vscode_run(self):
        tasks = yaml.safe_load((ROLE / 'tasks/vscode.yml').read_text())
        locate = next(task for task in tasks if task['name'].startswith('Locate the installed SynthWave'))
        self.assertEqual(locate['ansible.builtin.command']['argv'], ['/opt/code/bin/code', '--locate-extension', 'robbowen.synthwave-vscode'])
        self.assertEqual(locate['become_user'], '{{ desktop_user }}')
        self.assertFalse(locate['changed_when'])
        enable = next(task for task in tasks if task['name'].startswith('Enable Neon Dreams'))
        self.assertIn('files/enable_neon_dreams.py', enable['ansible.builtin.script']['cmd'])
        self.assertIn('/opt/code', enable['ansible.builtin.script']['cmd'])
        self.assertIn('/.config/Code/User/settings.json', enable['ansible.builtin.script']['cmd'])
        self.assertEqual(enable['ansible.builtin.script']['executable'], '/usr/bin/python3')
        self.assertEqual(enable['changed_when'], "'changed' in vscode_neon_dreams.stdout_lines")
        self.assertNotIn('when', enable)
        self.assertNotIn('creates', enable['ansible.builtin.script'])

    def test_jetbrains_products_and_installation_layout(self):
        products = {product['code']: product for product in self.defaults['jetbrains_products']}
        self.assertEqual(set(products), {'PS', 'DG', 'IIU'})
        self.assertEqual(products['IIU']['name'], 'idea')
        self.assertEqual(products['IIU']['command'], 'idea')
        tasks = yaml.safe_load((ROLE / 'tasks/jetbrains.yml').read_text())
        releases = next(task for task in tasks if task['name'].startswith('Resolve the latest'))
        self.assertIn('data.services.jetbrains.com', releases['ansible.builtin.uri']['url'])
        checksums = next(task for task in tasks if task['name'].startswith('Fetch the latest'))
        self.assertIn('checksumLink', checksums['ansible.builtin.uri']['url'])
        download = next(task for task in tasks if task['name'].startswith('Download missing'))
        self.assertIn('sha256:', download['ansible.builtin.get_url']['checksum'])
        extract = next(task for task in tasks if task['name'].startswith('Extract missing'))
        self.assertEqual(extract['ansible.builtin.unarchive']['extra_opts'], ['--strip-components=1'])
        opt_link = next(task for task in tasks if task['name'].startswith('Expose the current'))
        self.assertEqual(opt_link['ansible.builtin.file']['dest'], '/opt/{{ item.item.name }}')
        command_link = next(task for task in tasks if task['name'].startswith('Create the JetBrains command'))
        self.assertEqual(command_link['ansible.builtin.file']['dest'], '/usr/bin/{{ item.item.command }}')
        find_old = next(task for task in tasks if task['name'].startswith('Find obsolete JetBrains'))
        self.assertIn('excludes', find_old['ansible.builtin.find'])
        remove_old = next(task for task in tasks if task['name'].startswith('Remove obsolete JetBrains'))
        self.assertEqual(remove_old['ansible.builtin.file']['state'], 'absent')
        launcher = next(task for task in tasks if task['name'].startswith('Create the JetBrains desktop'))
        self.assertIn('Exec=/opt/{{ item.item.name }}/bin/{{ item.item.script }} %f', launcher['ansible.builtin.copy']['content'])

    def test_jetbrains_reuses_already_installed_versions(self):
        tasks = yaml.safe_load((ROLE / 'tasks/jetbrains.yml').read_text())
        check = next(task for task in tasks if task['name'].startswith('Check whether the latest'))
        self.assertIn('/product-info.json', check['ansible.builtin.stat']['path'])
        download = next(task for task in tasks if task['name'].startswith('Download missing'))
        self.assertEqual(download['when'], 'not jetbrains_installed.results[jetbrains_index].stat.exists')

    def test_bruno_is_installed_from_flathub_with_dev_tag(self):
        tasks = yaml.safe_load((ROOT / 'roles/flatpak/tasks/main.yml').read_text())
        bruno = next(task for task in tasks if task['name'].startswith('Install Bruno'))
        self.assertEqual(bruno['community.general.flatpak']['name'], 'com.usebruno.Bruno')
        self.assertEqual(bruno['community.general.flatpak']['remote'], 'flathub')
        self.assertIn('dev', bruno['tags'])

    def test_vesktop_is_installed_from_flathub(self):
        tasks = yaml.safe_load((ROOT / 'roles/flatpak/tasks/main.yml').read_text())
        apps = next(task for task in tasks if task['name'].startswith('Install apps via'))
        self.assertIn('dev.vencord.Vesktop', apps['loop'])
        self.assertNotIn('io.github.crealityofficial.CrealityPrint', apps['loop'])
        self.assertNotIn('org.kde.Platform', apps['loop'])
        self.assertNotIn('org.kde.KStyle.Adwaita', apps['loop'])
        self.assertNotIn('org.gnome.Platform', apps['loop'])

    def test_crealityprint_uses_the_official_flatpak_bundle(self):
        tasks = yaml.safe_load((ROOT / 'roles/flatpak/tasks/main.yml').read_text())
        release = next(task for task in tasks if task['name'].startswith('Resolve the latest Creality'))
        self.assertIn('CrealityOfficial/CrealityPrint/releases/latest', release['ansible.builtin.uri']['url'])
        download = next(task for task in tasks if task['name'].startswith('Download the Creality'))
        self.assertEqual(download['ansible.builtin.get_url']['checksum'], '{{ crealityprint_asset.digest }}')
        install = next(task for task in tasks if task['name'].startswith('Install Creality Print'))
        self.assertEqual(install['ansible.builtin.command']['argv'], [
            'flatpak', 'install', '--system', '--noninteractive', '-y',
            '/tmp/crealityprint.flatpak',
        ])
        defaults = yaml.safe_load((ROOT / 'roles/flatpak/defaults/main.yml').read_text())
        self.assertEqual(set(defaults['crealityprint_asset_patterns']), {'x86_64', 'aarch64'})


if __name__ == '__main__':
    unittest.main()

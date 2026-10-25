"""Offline checks for terminal tools, Rofi plugins and GCR keyring integration."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / 'roles/desktop/tasks'


class DesktopToolsTests(unittest.TestCase):
    def test_terminal_packages_cover_the_core_dotfiles_commands(self):
        tasks = yaml.safe_load((TASKS / 'terminal.yml').read_text())
        packages = tasks[0]['ansible.builtin.apt']['name']
        for package in ['alacritty', 'tmux', 'jq', 'zsh', 'neovim', 'eza', 'direnv', 'git-delta', 'git-lfs', 'openssh-client', 'rsync', 'curl', 'ripgrep', 'fd-find']:
            self.assertIn(package, packages)
        self.assertTrue(any(task.get('ansible.builtin.git', {}).get('dest') == '/home/{{ desktop_user }}/.oh-my-zsh' for task in tasks))

    def test_existing_zsh_startup_files_are_not_overwritten(self):
        tasks = yaml.safe_load((TASKS / 'terminal.yml').read_text())
        link = next(task for task in tasks if task.get('ansible.builtin.file', {}).get('dest') == '/home/{{ desktop_user }}/.zshrc')
        self.assertEqual(link['ansible.builtin.file']['src'], '/opt/dotfiles/zshrc')
        self.assertNotIn('force', link['ansible.builtin.file'])
        self.assertIn('not terminal_zshrc.stat.exists', link['when'])

    def test_opencode_uses_the_official_installer_without_editing_dotfiles(self):
        tasks = yaml.safe_load((TASKS / 'terminal.yml').read_text())
        install = next(task for task in tasks if task['name'].startswith('Install OpenCode'))
        self.assertEqual(install['become_user'], '{{ desktop_user }}')
        self.assertIn('https://opencode.ai/install', install['ansible.builtin.shell'])
        self.assertIn('--no-modify-path', install['ansible.builtin.shell'])
        self.assertEqual(install['args']['creates'], '/home/{{ desktop_user }}/.opencode/bin/opencode')
        self.assertEqual(install['environment']['HOME'], '/home/{{ desktop_user }}')

    def test_custom_zsh_theme_is_installed_after_cloning_oh_my_zsh(self):
        tasks = yaml.safe_load((TASKS / 'terminal.yml').read_text())
        clone = next(index for index, task in enumerate(tasks) if task.get('ansible.builtin.git', {}).get('dest') == '/home/{{ desktop_user }}/.oh-my-zsh')
        index = next(index for index, task in enumerate(tasks) if task.get('ansible.builtin.copy', {}).get('src') == 'mattboll.zsh-theme')
        self.assertGreater(index, clone)
        theme = tasks[index]['ansible.builtin.copy']
        self.assertEqual(theme['dest'], '/home/{{ desktop_user }}/.oh-my-zsh/custom/themes/mattboll.zsh-theme')
        self.assertEqual(theme['owner'], '{{ desktop_user }}')
        source = (ROOT / 'roles/desktop/files/mattboll.zsh-theme').read_text()
        self.assertIn('${#p}', source)

    def test_uses_packaged_gcr_and_keyring_units_without_creating_ssh_keys(self):
        tasks = yaml.safe_load((TASKS / 'keyring.yml').read_text())
        packages = tasks[0]['ansible.builtin.apt']['name']
        for package in ['gcr4', 'gnome-keyring', 'seahorse']:
            self.assertIn(package, packages)
        units = next(task for task in tasks if task.get('ansible.builtin.systemd_service', {}).get('scope') == 'global')
        self.assertEqual(units['ansible.builtin.systemd_service']['scope'], 'global')
        self.assertEqual(units['loop'], ['gnome-keyring-daemon.service', 'gcr-ssh-agent.socket'])
        runtime = next(task for task in tasks if 'block' in task)
        self.assertEqual(runtime['become_user'], '{{ desktop_user }}')
        self.assertEqual(runtime['when'], 'keyring_user_bus.stat.exists')
        stop = next(task for task in runtime['block'] if task.get('ansible.builtin.systemd_service', {}).get('name') == 'ssh-agent.service')
        self.assertEqual(stop['ansible.builtin.systemd_service']['state'], 'stopped')
        self.assertNotIn('enabled', stop['ansible.builtin.systemd_service'])
        launcher = (ROOT / 'roles/desktop/templates/start-sway.sh.j2').read_text()
        self.assertIn('export SSH_AUTH_SOCK="${XDG_RUNTIME_DIR}/gcr/ssh"', launcher)
        self.assertIn('/var/lib/flatpak/exports/share', launcher)
        self.assertIn('${HOME}/.local/share/flatpak/exports/share', launcher)
        self.assertFalse(any('ansible.builtin.shell' in task for task in tasks))
        for command in ['ssh-keygen', 'ssh-add', 'enable-linger', '--unlock']:
            self.assertNotIn(command, str(tasks))

    def test_keyring_removes_pam_password_synchronization_on_existing_hosts(self):
        tasks = yaml.safe_load((TASKS / 'keyring.yml').read_text())
        self.assertNotIn('libpam-gnome-keyring', tasks[0]['ansible.builtin.apt']['name'])
        pin = tasks[1]['ansible.builtin.copy']
        self.assertEqual(pin['dest'], '/etc/apt/preferences.d/no-libpam-gnome-keyring')
        self.assertIn('Package: libpam-gnome-keyring\nPin: release *\nPin-Priority: -1\n', pin['content'])
        removal = tasks[2]['ansible.builtin.apt']
        self.assertEqual(removal, {'name': 'libpam-gnome-keyring', 'state': 'absent', 'purge': True})

    def test_keyring_initialization_never_overwrites_existing_secrets(self):
        tasks = yaml.safe_load((TASKS / 'keyring.yml').read_text())
        copies = [task['ansible.builtin.copy'] for task in tasks if '/.local/share/keyrings/' in task.get('ansible.builtin.copy', {}).get('dest', '')]
        self.assertEqual(len(copies), 2)
        for task in copies:
            self.assertFalse(task['force'])
            self.assertEqual(task['mode'], '0600')
            self.assertEqual(task['owner'], '{{ desktop_user }}')
        self.assertTrue(copies[0]['dest'].endswith('/login.keyring'))
        self.assertIn('[keyring]\ndisplay-name=Login', copies[0]['content'])
        self.assertTrue(copies[1]['dest'].endswith('/default'))
        self.assertEqual(copies[1]['content'], 'login')

    def test_glow_uses_debian_go_and_the_path_expected_by_the_dotfiles(self):
        tasks = yaml.safe_load((TASKS / 'terminal.yml').read_text())
        self.assertIn('golang-go', tasks[0]['ansible.builtin.apt']['name'])
        glow = next(task for task in tasks if task.get('ansible.builtin.command', {}).get('argv') == ['go', 'install', 'charm.land/glow/v3@latest'])
        self.assertEqual(glow['become_user'], '{{ desktop_user }}')
        self.assertEqual(glow['environment']['GOPATH'], '/home/{{ desktop_user }}/.go')
        self.assertEqual(glow['environment']['GOBIN'], '/home/{{ desktop_user }}/.go/bin')

    def test_polkit_uses_the_current_mate_agent_not_removed_gnome_agent(self):
        tasks = yaml.safe_load((TASKS / 'packages.yml').read_text())
        packages = tasks[1]['ansible.builtin.apt']['name']
        self.assertIn('polkitd', packages)
        self.assertIn('mate-polkit', packages)
        self.assertNotIn('policykit-1-gnome', packages)

    def test_rofi_uses_real_calc_and_emoji_release_plugins(self):
        tasks = yaml.safe_load((TASKS / 'rofi.yml').read_text())
        packages = tasks[0]['ansible.builtin.apt']['name']
        self.assertIn('rofi', packages)
        self.assertIn('rofi-dev', packages)
        self.assertIn('qalc', packages)
        self.assertIn('wl-clipboard', packages)
        self.assertIn('wtype', packages)
        self.assertNotIn('rofimoji', packages)
        releases = next(task for task in tasks if 'ansible.builtin.uri' in task)
        self.assertEqual({plugin['repository'] for plugin in releases['loop']}, {
            'svenstaro/rofi-calc', 'Mange/rofi-emoji',
        })
        self.assertTrue(releases['ansible.builtin.uri']['url'].endswith('/releases/latest'))
        self.assertFalse(any('ansible.builtin.include_tasks' in task for task in tasks))
        self.assertFalse((TASKS / 'rofi-plugin.yml').exists())
        for block in (task for task in tasks if 'block' in task):
            for task in block['block'][:-1]:
                if 'ansible.builtin.command' in task or 'ansible.builtin.git' in task:
                    self.assertEqual(task['become_user'], '{{ desktop_user }}')

    def test_optional_desktop_tools_are_installed_with_tlp_instead_of_ppd(self):
        tasks = yaml.safe_load((TASKS / 'packages.yml').read_text())
        packages = tasks[1]['ansible.builtin.apt']['name']
        for package in [
            'qtwayland5', 'qt6-wayland', 'cups', 'cups-pk-helper',
            'system-config-printer', 'fwupd', 'powertop',
            'tlp', 'tlp-pd', 'tlp-rdw',
        ]:
            self.assertIn(package, packages)
        self.assertNotIn('gnome-disk-utility', packages)
        self.assertNotIn('power-profiles-daemon', packages)
        removal = tasks[0]['ansible.builtin.apt']
        self.assertEqual(removal, {'name': 'power-profiles-daemon', 'state': 'absent'})
        service = next(task for task in tasks if task.get('ansible.builtin.systemd_service', {}).get('name') == 'tlp.service')
        self.assertTrue(service['ansible.builtin.systemd_service']['enabled'])
        self.assertEqual(service['ansible.builtin.systemd_service']['state'], 'started')

    def test_root_ca_is_bootstrapped_without_tls_then_trusted(self):
        tasks = yaml.safe_load((TASKS / 'root_ca.yml').read_text())
        download = tasks[1]['ansible.builtin.get_url']
        self.assertEqual(download['url'], 'https://ca.lan/root.crt')
        self.assertEqual(download['dest'], '/usr/local/share/ca-certificates/oxlabs-root.crt')
        self.assertEqual(download['mode'], '0644')
        self.assertTrue(download['validate_certs'] is False)
        self.assertFalse(download['force'])
        self.assertEqual(tasks[1]['notify'], 'Update CA certificates')
        handlers = yaml.safe_load((ROOT / 'roles/desktop/handlers/main.yml').read_text())
        update = next(handler for handler in handlers if handler['name'] == 'Update CA certificates')
        self.assertEqual(update['ansible.builtin.command'], 'update-ca-certificates')

    def test_french_locale_is_generated_and_selected(self):
        tasks = yaml.safe_load((TASKS / 'locale.yml').read_text())
        self.assertEqual(tasks[0]['community.general.locale_gen']['name'], 'fr_FR.UTF-8')
        self.assertEqual(tasks[1]['ansible.builtin.copy']['dest'], '/etc/default/locale')
        self.assertIn('LANG=fr_FR.UTF-8', tasks[1]['ansible.builtin.copy']['content'])

    def test_xdg_user_directories_are_created_without_rewriting_the_dotfiles(self):
        tasks = yaml.safe_load((TASKS / 'session.yml').read_text())
        task = next(task for task in tasks if task['name'].startswith('Create the XDG user directories'))
        self.assertEqual(task['loop'], ['Bureau', 'Documents', 'Images', 'Téléchargements'])
        self.assertEqual(task['ansible.builtin.file']['state'], 'directory')
        self.assertFalse(any('xdg-user-dirs-update' in str(task) for task in tasks))

    def test_file_manager_and_wayland_integration_are_installed(self):
        tasks = yaml.safe_load((TASKS / 'packages.yml').read_text())
        packages = tasks[1]['ansible.builtin.apt']['name']
        for package in [
            'nemo', 'nemo-fileroller', 'tumbler',
            'gvfs', 'gvfs-backends', 'gvfs-fuse', 'file-roller',
            'libgdk-pixbuf2.0-bin', 'heif-gdk-pixbuf', 'libjxl-gdk-pixbuf',
            'gedit', 'mpv', 'mupdf', 'vlc',
            'gstreamer1.0-libav', 'gstreamer1.0-plugins-good',
            'xdg-user-dirs', 'xdg-utils', 'libglib2.0-bin',
            'swaylock',
            'xdg-desktop-portal', 'xdg-desktop-portal-gtk', 'xdg-desktop-portal-wlr',
            'lm-sensors', 'upower', 'alsa-utils',
        ]:
            self.assertIn(package, packages)

    def test_dark_theme_is_applied_in_the_desktop_user_dconf(self):
        tasks = yaml.safe_load((TASKS / 'gtk.yml').read_text())
        self.assertEqual([task['community.general.dconf']['key'] for task in tasks], [
            '/org/gnome/desktop/interface/gtk-theme',
            '/org/gnome/desktop/interface/color-scheme',
        ])
        self.assertEqual([task['community.general.dconf']['value'] for task in tasks], [
            "'Adwaita-dark'", "'prefer-dark'",
        ])
        for task in tasks:
            self.assertEqual(task['become_user'], '{{ desktop_user }}')
        packages = yaml.safe_load((TASKS / 'packages.yml').read_text())[1]['ansible.builtin.apt']['name']
        self.assertIn('dconf-cli', packages)
        self.assertIn('python3-psutil', packages)

    def test_capture_menu_dependencies_are_installed(self):
        tasks = yaml.safe_load((TASKS / 'packages.yml').read_text())
        packages = tasks[1]['ansible.builtin.apt']['name']
        for package in ['grim', 'slurp', 'python3-gi', 'gir1.2-gtk-3.0', 'gir1.2-gtklayershell-0.1', 'wl-clipboard', 'libnotify-bin']:
            self.assertIn(package, packages)

    def test_uses_current_sid_networkmanager_applet_packages(self):
        tasks = yaml.safe_load((TASKS / 'packages.yml').read_text())
        packages = tasks[1]['ansible.builtin.apt']['name']
        self.assertIn('network-manager-applet', packages)
        self.assertIn('nm-connection-editor', packages)
        self.assertNotIn('network-manager-gnome', packages)


if __name__ == '__main__':
    unittest.main()

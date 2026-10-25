"""Offline checks; never execute the provisioning playbooks."""
import datetime
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

from ansible.plugins.filter.core import FilterModule
from jinja2 import Environment, FileSystemLoader, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "roles/desktop/templates"


def installation_tasks():
    play = yaml.safe_load((ROOT / "install.yml").read_text())[0]

    def flatten(tasks, inherited_when=None):
        for task in tasks:
            task = dict(task)
            if inherited_when is not None:
                task.setdefault("when", inherited_when)
            yield task
            yield from flatten(task.get("block", []), task.get("when"))

    return list(flatten(play["tasks"]))


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.env = Environment(
            loader=FileSystemLoader(TEMPLATES),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            trim_blocks=True,
        )
        self.env.filters.update(FilterModule().filters())
        self.vars = {
            "desktop_user": "testuser",
            "inventory_hostname": "testhost",
        }

    def render(self, name):
        return self.env.get_template(name).render(self.vars)

    def test_all_yaml_is_valid(self):
        for path in ROOT.rglob("*.yml"):
            with self.subTest(path=str(path)):
                yaml.safe_load(path.read_text())

    def test_all_desktop_templates_render(self):
        for path in TEMPLATES.glob("*.j2"):
            with self.subTest(template=path.name):
                self.assertTrue(self.render(path.name).strip())

    def test_greetd_autologin_matches_debian(self):
        config = tomllib.loads(self.render("greetd.toml.j2"))
        self.assertEqual(config["terminal"]["vt"], 7)
        self.assertEqual(config["default_session"]["user"], "_greetd")
        self.assertEqual(config["default_session"]["command"], "/usr/sbin/agreety --cmd /usr/local/bin/start-sway")
        self.assertEqual(config["initial_session"]["user"], "testuser")
        self.assertEqual(config["initial_session"]["command"], "/usr/local/bin/start-sway")

    def test_launcher_runs_the_compiled_swayfx(self):
        subprocess.run(["sh", "-n"], input=self.render("start-sway.sh.j2"), text=True, check=True)
        with tempfile.TemporaryDirectory() as directory:
            fake_sway = Path(directory) / "sway"
            fake_sway.write_text("#!/bin/sh\nexit 7\n")
            fake_sway.chmod(0o755)
            script = self.render("start-sway.sh.j2").replace("/usr/local/bin/sway", str(fake_sway))
            result = subprocess.run(["sh"], input=script, text=True)
            self.assertEqual(result.returncode, 7)

    def test_swayfx_is_built_without_root(self):
        defaults = yaml.safe_load((ROOT / "roles/desktop/defaults/main.yml").read_text())
        self.assertTrue(defaults["swayfx_source_directory"].startswith("/tmp/"))
        tasks = yaml.safe_load((ROOT / "roles/desktop/tasks/swayfx.yml").read_text())
        for task in tasks:
            if "ansible.builtin.git" in task or task["name"].startswith(("Configure the SwayFX", "Compile SwayFX")):
                self.assertEqual(task["become_user"], "{{ desktop_user }}")
        packages = yaml.safe_load((ROOT / "roles/desktop/tasks/packages.yml").read_text())
        self.assertNotIn("sway", packages[1]["ansible.builtin.apt"]["name"])
        self.assertIn("greetd", packages[1]["ansible.builtin.apt"]["name"])

    def test_desktop_does_not_restart_a_running_session(self):
        tasks = yaml.safe_load((ROOT / "roles/desktop/tasks/session.yml").read_text())
        service = next(task["ansible.builtin.systemd_service"] for task in tasks if "ansible.builtin.systemd_service" in task)
        self.assertTrue(service["enabled"])
        self.assertNotIn("state", service)

    def test_desktop_imports_terminal_and_rofi_before_build_and_session(self):
        tasks = yaml.safe_load((ROOT / "roles/desktop/tasks/main.yml").read_text())
        self.assertEqual([task["ansible.builtin.import_tasks"] for task in tasks], [
            "packages.yml", "root_ca.yml", "locale.yml", "gtk.yml",
            "portals.yml", "browsers.yml", "plymouth.yml", "terminal.yml",
            "rofi.yml", "swayfx.yml", "session.yml",
        ])

    def test_ethernet_is_left_to_networkmanager(self):
        profiles = [task["ansible.builtin.template"]["src"] for task in installation_tasks() if "ansible.builtin.template" in task]
        self.assertEqual(profiles, ["wifi.nmconnection.j2"])

    def test_wifi_fallback_uses_dhcp_with_lower_route_priority(self):
        env = self.env.overlay(loader=FileSystemLoader(ROOT / "templates"))
        profile = env.get_template("wifi.nmconnection.j2").render(
            self.vars,
            network_wifi={"interface": "wlp2s0", "ssid": "Test Wi-Fi", "password": "secret-pass"},
        )
        self.assertIn("interface-name=wlp2s0", profile)
        self.assertIn("ssid=Test Wi-Fi", profile)
        self.assertIn("psk=secret-pass", profile)
        self.assertIn("autoconnect=true", profile)
        self.assertEqual(profile.count("method=auto\nroute-metric=600"), 2)

    def test_wifi_profile_is_optional_and_secrets_are_protected(self):
        wifi = next(task for task in installation_tasks() if task.get("ansible.builtin.template", {}).get("src") == "wifi.nmconnection.j2")
        self.assertEqual(wifi["when"], "network_wifi is defined")
        self.assertTrue(wifi["no_log"])
        self.assertEqual(wifi["ansible.builtin.template"]["mode"], "0600")
        self.assertEqual(wifi["ansible.builtin.template"]["owner"], "root")
        self.assertNotIn("backup", wifi["ansible.builtin.template"])

    def test_initial_install_is_separate_from_desktop_setup(self):
        site = yaml.safe_load((ROOT / "site.yml").read_text())[0]
        self.assertNotIn("sid", [role["role"] for role in site["roles"]])
        self.assertNotIn("network", [role["role"] for role in site["roles"]])
        install = yaml.safe_load((ROOT / "install.yml").read_text())[0]
        self.assertNotIn("roles", install)
        self.assertFalse(any("ansible.builtin.include_tasks" in task for task in installation_tasks()))
        self.assertTrue(any(task.get("ansible.builtin.apt", {}).get("upgrade") == "dist" for task in installation_tasks()))
        self.assertEqual(install["become_method"], "su")
        self.assertEqual(site["hosts"], install["hosts"])
        self.assertTrue(any("ansible.builtin.reboot" in task for task in install["post_tasks"]))

    def test_sudo_setup_preserves_existing_user_groups(self):
        tasks = installation_tasks()
        self.assertTrue(any(task.get("ansible.builtin.apt", {}).get("name") == "sudo" for task in tasks))
        account = next(task["ansible.builtin.user"] for task in tasks if "ansible.builtin.user" in task)
        self.assertEqual(account["name"], "{{ desktop_user }}")
        self.assertEqual(account["groups"], "sudo")
        self.assertTrue(account["append"])
        self.assertTrue(any(task.get("ansible.builtin.meta") == "reset_connection" for task in tasks))

    def test_sid_replaces_only_standard_sources_with_backups(self):
        sources = [task["ansible.builtin.copy"] for task in installation_tasks() if task.get("ansible.builtin.copy", {}).get("dest", "").startswith("/etc/apt/")]
        self.assertEqual({source["dest"] for source in sources}, {
            "/etc/apt/sources.list", "/etc/apt/sources.list.d/debian.sources",
        })
        self.assertTrue(all(source["backup"] for source in sources))
        self.assertFalse(any("ansible.builtin.shell" in task for task in installation_tasks()))

    def test_initial_install_refuses_completed_installations(self):
        play = yaml.safe_load((ROOT / "install.yml").read_text())[0]
        self.assertEqual(play["pre_tasks"][0]["ansible.builtin.stat"]["path"], "/etc/.installed_at")
        check = self.env.compile_expression(play["pre_tasks"][1]["ansible.builtin.assert"]["that"])
        self.assertFalse(check(initial_installation={"stat": {"exists": True}}))
        self.assertTrue(check(initial_installation={"stat": {"exists": False}}))
        marker = next(task["ansible.builtin.copy"] for task in play["post_tasks"] if "ansible.builtin.copy" in task)
        self.assertEqual(marker["dest"], "/etc/.installed_at")
        rendered = self.env.from_string(marker["content"]).render(
            now=lambda utc, fmt: datetime.datetime.now(datetime.timezone.utc).strftime(fmt)
        )
        self.assertRegex(rendered.strip(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_ifupdown_is_written_directly_before_reboot(self):
        play = yaml.safe_load((ROOT / "install.yml").read_text())[0]
        interfaces = play["post_tasks"][-2]["ansible.builtin.copy"]
        self.assertEqual(interfaces["dest"], "/etc/network/interfaces")
        self.assertIn("iface lo inet loopback", interfaces["content"])
        self.assertNotIn("backup", interfaces)
        self.assertIn("ansible.builtin.reboot", play["post_tasks"][-1])

    def test_network_has_no_discovery_or_migration_artifacts(self):
        tasks = installation_tasks()
        self.assertFalse(any("ansible.builtin.slurp" in task or "ansible.builtin.set_fact" in task or "ansible.builtin.find" in task for task in tasks))
        text = (ROOT / "install.yml").read_text()
        self.assertNotIn("autodebian-network-migration", text)
        self.assertNotIn("autodebian-pending", text)
        self.assertNotIn("interfaces.before-autodebian", text)

if __name__ == "__main__":
    unittest.main()

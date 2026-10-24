# Auto-Debian

Setup debian to my taste for my desktop computers

## Usage

Debian initial install:
- Add ssh
- Do not install a desktop ui

```sh
$ ssh-add # Just to be sure
$ ssh-copy-id oxodao@[COMPUTER-IP]
$ ansible-galaxy collection install -r requirements.yml
$ ansible-playbook install.yml --ask-become-pass
```

This setup the initial steps:
- sudo
- NetworkManager
- Debian unstable

This is only to be done the first time you setup the computer. It won't run again afterward. It will reboot at the end to be sure that NetworkManager takes care of the following connections.

Now the following is idempotent so it can be used again at any point in the lifetime of the debian install.

```sh
$ ansible-playbook site.yml --ask-become-pass
```
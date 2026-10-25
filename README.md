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

Here is a good time to find all the Windows fonts that can be installed. See the designated section in this readme for more info.

Now the following is idempotent so it can be used again at any point in the lifetime of the debian install.

```sh
$ ansible-playbook site.yml --ask-become-pass
```

## Extra / Windows Fonts

Just get [this](https://github.com/kenshaw/msfontextract) software and run it against the [ISO file for Windows 11](https://www.microsoft.com/fr-fr/software-download/windows11).

Put them in `roles/desktop/files/fonts/windows` alongside every other font you might want to auto-install.


```sh
$ cd /tmp && git clone https://github.com/kenshaw/msfontextract.git && cd msfontextract && go run . --dest ~/Git/ansible-debian/roles/desktop/files/fonts/windows ~/Téléchargements/Windows11_Client_x64_fr-fr_*.iso
```
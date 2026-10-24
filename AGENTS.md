# Consignes pour les agents

NE TOUCHE PAS AU README SANS LA DEMANDE EXPLICITE DE L'UTILISATEUR, ET QUAND IL LE DEMANDE FAIT LE MINIMUM DE CHANGEMENTS REQUIS.

## Objectif

Configurer une Debian minimale en poste Debian Sid avec SwayFX via Ansible.
Communiquer en français. Privilégier une configuration simple et explicite,
sans options, découvertes automatiques ou abstractions inutiles.

## Deux étapes distinctes

- `install.yml` : installation initiale avec les tâches sudo, Sid et réseau
  directement dans le playbook, sans rôles ou fichiers de tâches séparés.
  Redémarrage final avec attente de SSH. Migration des dépôts APT vers Sid,
  dist-upgrade et configuration du réseau système réservés à cette étape.
- Refuser `install.yml` dès le début si `/etc/.installed_at` existe. Ce fichier
  contient la date UTC de fin d'installation et n'est écrit qu'après le
  redémarrage réussi et le retour de SSH. En cas d'échec avant cette étape,
  permettre une reprise sans marqueur de succès prématuré.
- Pour Sid, remplacer les fichiers de sources Debian standards avec sauvegarde.
  Ne pas supprimer ou déplacer globalement les dépôts APT avec un script shell.
- L'installation initiale utilise `become_method: su` avec le mot de passe root,
  car sudo peut être absent. Le playbook installe le paquet et ajoute
  `desktop_user` au groupe sudo sans retirer ses autres groupes. Les relances de
  `site.yml` utilisent sudo avec le mot de passe utilisateur, pas `NOPASSWD`.
- `site.yml` : configuration du bureau et des applications via `dotfiles`, `desktop`,
  `firefox`, `dev`, `games` et `flatpak`. Doit pouvoir être relancé après installation,
  sans migration système/réseau, dist-upgrade ou redémarrage automatique.
- Les deux playbooks ciblent le groupe `desktops` de `inventory.ini`.

Ne pas réintroduire de procédure imposant de modifier des flags entre la première
installation et les relances. Les tâches doivent être idempotentes autant que
possible ; distinguer les changements réellement nécessaires des vérifications.

## Variables

- `host_vars/<nom-inventaire>.yml` contient explicitement `desktop_user`,
  `desktop_uid` et `desktop_gid` pour le compte existant sur chaque machine.
- Ne pas découvrir ces identifiants avec `getent`, des facts ou des commandes.
- Pas de variable `desktop_home` : utiliser `/home/{{ desktop_user }}` dans les
  chemins, ou la concaténation équivalente dans une expression Jinja.
- `group_vars/all.yml` contient les paramètres communs ; les valeurs par défaut
  propres à un rôle restent dans son dossier `defaults`.

## Réseau

- NetworkManager et DHCP uniquement : Ethernet prioritaire, Wi-Fi de secours si
  configuré dans les variables de la machine.
- Le réseau système est configuré dans `install.yml`, pas dans le setup desktop.
  L'applet graphique NetworkManager reste une dépendance du bureau.
- Laisser NetworkManager détecter Ethernet et créer sa connexion DHCP : ne pas
  générer de profil `.nmconnection` Ethernet. Seul le Wi-Fi nécessite un profil
  explicite pour ses identifiants.
- Pas de flag `migrate_network`, de scan d'interfaces ou d'analyse de l'ancien
  réseau par regex. Le setup cible une Debian minimale en DHCP et laisse
  NetworkManager détecter Ethernet. Le Wi-Fi est défini dans `network_wifi`
  (`interface`, `ssid`, `password`) dans les variables de la machine.
- Utiliser directement les variables Wi-Fi fournies, sans batterie de validations
  du SSID, du mot de passe ou de l'interface. Conserver la protection des secrets.
- Ne pas redémarrer les services réseau pendant le déploiement SSH. Écrire
  directement `/etc/network/interfaces` limité à loopback juste avant le reboot.
  Pas d'unité systemd personnalisée, de fichier temporaire de migration ou de
  sauvegarde réseau spécifique au setup laissés sur la machine.
- Ne pas gérer la migration de réseaux statiques ou complexes. L'installation
  remplace directement la configuration ifupdown par loopback. Si la machine
  dépend du Wi-Fi, ses identifiants doivent être
  renseignés dans les variables avant l'installation.
- Conserver la priorité Ethernet par défaut de NetworkManager et donner au Wi-Fi
  une métrique de routage de `600`. Le Wi-Fi peut rester connecté, mais le trafic
  passe en priorité par Ethernet.
- Renseigner directement le mot de passe Wi-Fi dans les variables de la machine,
  sans Ansible Vault. Conserver `no_log` pour les tâches concernées et un profil
  NetworkManager root en mode `0600` sans backup.
- `site.yml` ne reconfigure pas le réseau. Le marqueur `/etc/.installed_at`
  empêche de rejouer l'installation initiale.
- Configurer `/etc/xdg-desktop-portal/sway-portals.conf` pour forcer les
  backends `gtk` (fichiers, impression, notifications), `wlr` (ScreenCast et
  Screenshot) et `gnome-keyring` (Secret). Ne pas installer les portails GNOME
  ou KDE complets pour Sway.

## Bureau initial

- Le rôle `desktop` installe SwayFX, greetd avec autologin, les outils terminal,
  Rofi et les outils de capture grim/slurp. Les configurations viennent des
  dotfiles, pas de templates de secours. Utiliser `site.yml --tags desktop` pour l'isoler.
- Compiler SwayFX et ses versions compatibles de SceneFX et wlroots depuis leurs
  releases dans `/tmp`, sans privilèges root, pas dans le home utilisateur.
  Installer dans `/usr/local`, actualiser le cache
  des bibliothèques et lancer explicitement `/usr/local/bin/sway` (SwayFX).
- Le rôle `dotfiles` passe avant `desktop`, également avec `--tags desktop`.
  Donner `/opt` à `desktop_user`/`desktop_gid` sans changement récursif et cloner
  `https://github.com/oxodao/dotfiles.git` dans `/opt/dotfiles` comme cet utilisateur.
  Mettre à jour le dépôt existant en HTTPS à chaque relance (`update: true`), sans
  forcer ni écraser les modifications locales, puis remettre `origin` en SSH.
- Juste après le clonage HTTPS, exécuter directement `git remote set-url origin
  git@github.com:oxodao/dotfiles.git`, sans lecture préalable de l'URL. La clé SSH
  sera configurée par l'utilisateur ensuite.
- Si `/home/{{ desktop_user }}/.config` n'est pas un symlink, le supprimer
  entièrement sans sauvegarde puis créer un lien vers `/opt/dotfiles/config`.
  Si c'est déjà un symlink, le conserver tel quel.
- Ne pas écraser les fichiers du dépôt via ce lien. Pas de configuration initiale
  ou de fallback SwayFX/Alacritty généré par Ansible : le dépôt doit les fournir.
  Le lanceur charge explicitement `/home/{{ desktop_user }}/.config/sway/config`.
  Supprimer l'ancien fallback `/usr/local/etc/sway/config` au déploiement.
  Le portage i3 vers Sway est géré séparément dans le dépôt des dotfiles.
- `desktop/tasks/terminal.yml` regroupe Alacritty, tmux, jq, Zsh/Oh My Zsh,
  Neovim, eza, direnv, Git Delta/LFS, les utilitaires shell, Hack Nerd Font et
  OpenCode. Installer OpenCode avec le script officiel comme `desktop_user`,
  `--no-modify-path`, dans `~/.opencode/bin`, et ne pas modifier les dotfiles.
  Ne pas installer automatiquement toutes les stacks de développement évoquées
  dans les intégrations facultatives des dotfiles (Docker, Java, PHP, Node, etc.).
- `desktop/tasks/metaprint.yml`, importé par `terminal.yml`, télécharge le binaire Linux de la dernière release GitHub
  `oxodao/metaprint` pour l'architecture de la machine et l'installe dans
  `/usr/local/bin/metaprint`. Pas de compilation ni d'intégration des dotfiles.
  Il peut être lancé seul avec `site.yml --tags metaprint`.
- Installer les vrais plugins `svenstaro/rofi-calc` et `Mange/rofi-emoji` depuis
  leurs dernières releases (jamais rofimoji). Compiler comme l'utilisateur dans
  `/tmp` et installer dans le répertoire de plugins indiqué par `rofi.pc`.
  Le build est lié à la version de Rofi pour reconstruire lors de ses mises à jour.
- Installer Go depuis Debian (`golang-go`) puis `go install charm.land/glow/v3@latest`
  comme l'utilisateur, avec `GOBIN=/home/{{ desktop_user }}/.go/bin` pour conserver
  le chemin attendu par les dotfiles. Les caches de compilation restent dans `/tmp`.
- Installer `polkitd` et `mate-polkit` : l'agent de session est
  `/usr/libexec/polkit-mate-authentication-agent-1`. L'ancien agent GNOME n'est plus
  fourni par Sid. L'utilisateur adapte ses dotfiles pour lancer l'agent MATE.
- Utiliser GCR (`gcr4`) avec GNOME Keyring, libsecret et Seahorse pour mémoriser les
  passphrases SSH. Activer les unités utilisateur fournies par les paquets, sans
  service personnalisé ni linger. Exporter `SSH_AUTH_SOCK=$XDG_RUNTIME_DIR/gcr/ssh`.
- L'utilisateur remplace l'ancien export du socket et retire l'unité OpenSSH
  `ssh-agent.service` ainsi que son lien d'activation dans ses dotfiles. Arrêter
  l'ancien agent encore chargé, sans réécrire les fichiers du dépôt.
- L'autologin est associé à un trousseau login par défaut sans mot de passe,
  initialisé par Ansible au format texte natif de GNOME Keyring (`login.keyring`
  et fichier `default`), en mode `0600`, uniquement s'ils n'existent pas déjà
  (`copy` avec `force: false`). L'utilisateur accepte les secrets non chiffrés
  dans ce trousseau, le disque étant protégé par LUKS. Ne jamais effacer un keyring
  existant. S'il est protégé, demander son ancien mot de passe en saisie masquée
  via Ansible puis passer son mot de passe à vide via l'API GNOME Keyring en
  conservant tous ses secrets. Aucun mot de passe dans les arguments ou les logs :
  transmission sur stdin, `stdin_add_newline: false`, tâches `no_log: true`.
  La passphrase de la clé
  est enregistrée au premier usage avec l'option de mémorisation de GCR ; garder
  la clé privée et son `.pub` ensemble dans `~/.ssh`.
- Seuls le lanceur de session et la configuration greetd restent dans les
  templates du rôle desktop. Pas de verrouillage ni de redémarrage automatique
  du bureau : greetd est activé pour le prochain démarrage.
- Le rôle `dev` regroupe Docker, VS Code, les IDE JetBrains, SDKMAN, NVM et
  Bruno. Docker vient des paquets Debian (`docker.io`, `docker-compose`,
  `docker-buildx`), l'utilisateur est ajouté au groupe `docker` et le service
  est activé.
- Installer SDKMAN dans `~/.sdkman` et NVM dans `~/.nvm` en tant qu'utilisateur.
  Ne pas modifier `.zshrc` : les dotfiles les chargent déjà. Pour SDKMAN, utiliser
  un `HOME`/`ZDOTDIR` temporaire pendant l'installeur ; pour NVM, `PROFILE=/dev/null`.
- VS Code est résolu via l'API officielle, vérifié par SHA-256, installé dans
  `/opt/vscode/<version>` et exposé par le lien stable `/opt/code`. Le rôle
  installe la dernière version au passage du playbook et ne retélécharge pas
  celle déjà présente.
- Télécharger PhpStorm, DataGrip et IntelliJ IDEA Ultimate (code `IIU`) depuis
  l'API officielle JetBrains, vérifier le SHA-256 fourni, extraire chaque
  version dans `/opt/jetbrains/<produit>-<version>` et exposer des liens stables
  `/opt/<produit>` et `/usr/bin/<commande>`. Ne pas retélécharger une version
  déjà installée. Les lanceurs `.desktop` pointent vers ces liens.
- Bruno est installé depuis Flathub (`com.usebruno.Bruno`), avec le tag `dev`
  en plus du rôle flatpak. Les mises à jour automatiques concernent les Flatpak
  système, pas APT, JetBrains ni VS Code.
- Creality Print n'est pas sur Flathub : installer son bundle Flatpak officiel
  depuis la dernière release GitHub `CrealityOfficial/CrealityPrint`, avec
  sélection x86_64/arm64, vérification du digest GitHub et installation système.
  Ne pas ajouter son app ID à la boucle Flathub.
- Le rôle `games` active l'architecture i386 puis installe Steam via le paquet
  Debian `steam-installer`, `steam-devices`, GameMode et MangoHud. Ne pas
  ajouter de dépôt ou de paquet Steam tiers. Les pilotes i386 propriétaires
  restent spécifiques au matériel.
- Ne pas modifier le README sans demande explicite, même s'il devient obsolète.

## Style

- Suivre `.yamllint` : indentation de deux espaces et chaînes entre apostrophes.
- Aucune limite de longueur de ligne : ne pas réactiver `line-length` et ne pas
  découper les lignes uniquement pour respecter 80 caractères.
- Utiliser les noms de modules Ansible pleinement qualifiés et les conventions
  des rôles existants. Les noms de tâches sont actuellement en anglais.
- Ne pas ajouter de dépendance ou de mécanisme de secours sans nécessité.
- Espacer le code quand pertinent, par exemple avant un objet multi-lignes, entre les valeurs d'un array si il est multi-lignes etc...

## Vérifications

Depuis la racine du dépôt :

```sh
yamllint .
ansible-playbook install.yml --syntax-check
ansible-playbook site.yml --syntax-check
python -m unittest discover -s tests
```

Les tests de `tests/` vérifient hors ligne les templates et la structure des
playbooks. La configuration Sway est gérée et testée séparément dans les dotfiles.

Ne pas exécuter les playbooks de provisioning sur une machine réelle sans demande
explicite : ils modifient les dépôts, les paquets, le réseau et la session, et
`install.yml` redémarre la machine. Une validation syntaxique ou des tests hors
ligne ne prouvent pas qu'un déploiement réel fonctionne.

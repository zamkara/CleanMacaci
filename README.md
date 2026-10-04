# CleanMacaci

System Cleaner for Omarchy. The plugin page is **CleanMacaci**; its menu label is **System Cleaner**.

<img width="1920" height="1080" alt="screenshot-2026-10-04_17-42-05" src="https://github.com/user-attachments/assets/fa130907-8210-454a-a237-5441b66c02d7" />

## Install

```sh
omarchy plugin add https://github.com/zamkara/CleanMacaci.git --enable
```

Open **Omarchy Menu → Setup → System Cleaner**, or run:

```sh
omarchy-shell shell summon cleaner.zamkara.ati
```

The enabled plugin registers its own menu entries. Registration preserves unrelated entries and JSONC comments, makes a backup before changes, and refuses conflicting ownership. It does not modify `/usr/share/omarchy/`, install packages, or replace the bar or menu. No additional personal plugins or scripts in `~/.local/bin` are required.

A custom System menu can read `~/.config/omarchy/extensions/system-menu.json`. The registration uses the same **System Cleaner** label. Custom menus need to implement that extension interface; arbitrary third-party menus cannot be integrated automatically. See [custom menu integration](docs/custom-menu.md).

## What it does

- Discovers cache and diagnostic entries in XDG directories, Firefox profile locations, Flatpak data, npm/Cargo caches, Java/IcedTea/Gradle caches and recognized development projects.
- Automatically selects verified regenerable caches. Unknown caches, diagnostics, offline website data, dependencies and build output require manual review.
- Protects cookies, credentials, sessions, personal application data, tracked project files, installed runtimes, Trash and performance caches.
- Use the lock icon to queue normal application closure; confirm in the footer, then rescan. Unsaved work may prompt. No files are deleted by closing applications.
- Requires confirmation and a successful preview. The full selection is checked for changed files before deletion. Cache directories retain their identity and permissions; eligible contents are removed.
- Provides real logs, scan reports, disk usage, scan cancellation, and separate system cleanup for package versions, archived journal logs and aged temporary files.

Cleaning is permanent. Preview signatures are metadata checks, not transactional filesystem snapshots. Do not run builds or restart an application while its data is being cleaned. Deletion cancellation is intentionally unavailable; scans can be cancelled. Coverage is bounded and reports skipped or unreadable trees.

## Requirements

An Omarchy release with the Quattro plugin API, Quickshell and the stock `qs.Commons` / `qs.Ui` modules; Python 3.9+, Bash, Hyprland, procps, pacman and systemd. These are expected on supported Omarchy installations. The plugin does not support GNOME-only systems or older Omarchy menus without this shell API.

Optional tools: `pacman-contrib` for `paccache`, Git for checking tracked project output, `wl-copy` for copying reports, `xdg-open` for opening reports and `xdg-terminal-exec` for system cleanup. Missing package-cleanup support is reported rather than installed silently. Normal user cleanup needs no sudo. System cleanup runs in a terminal, previews its policy, asks for confirmation and uses sudo only for the selected operation.

## Keep paths

Optional configuration: `~/.config/omarchy/cleanmacaci.json` under `XDG_CONFIG_HOME` when set:

```json
{"keep": ["~/Projects/example/node_modules", "/absolute/path/to/important/cache"]}
```

A protected descendant protects the entire candidate parent. Invalid configuration stops cleanup. The earlier `cleaner.json` name is supported when no `cleanmacaci.json` exists.

Reports and menu backups are stored under `$XDG_STATE_HOME/CleanMacaci`, defaulting to `~/.local/state/CleanMacaci`. They can contain local paths and application names. They are not uploaded or committed to this repository.

## Update, disable and remove

```sh
omarchy plugin update cleaner.zamkara.ati
omarchy plugin disable cleaner.zamkara.ati
omarchy plugin enable cleaner.zamkara.ati
```

Use `update` for an installed ID; `plugin add` does not replace an existing plugin. Disabling hides the stock menu entry. The custom menu adapter also hides disabled entries.

To remove, unregister the owned entries before deleting the plugin:

```sh
python3 ~/.config/omarchy/plugins/cleaner.zamkara.ati/scripts/menu.py --remove
omarchy plugin remove cleaner.zamkara.ati
```

Removal leaves reports, keep-list configuration and menu backups intact. It does not delete user data or unrelated menu entries. Re-enabling a plugin registers the entries again.

## Migrate from the earlier local cleaner

Keep the old plugin for rollback. After installing and checking CleanMacaci, disable the old plugin and remove only its known menu entry:

```sh
omarchy plugin disable zam.cleaner
python3 ~/.config/omarchy/plugins/cleaner.zamkara.ati/scripts/menu.py --remove-legacy
```

The old executable and reports are not removed. CleanMacaci uses bundled scripts and its own IPC target `cleanmacaci`, so it does not rely on or overwrite those executables.

## Development

```sh
python3 -m unittest discover -s tests
bash -n scripts/system-cleaner.sh
omarchy plugin validate .
qmllint -I /usr/share/omarchy/shell CleanMacaci.qml controls/Button.qml
```

Tests use temporary homes with all XDG roots redirected. They verify private data preservation, explicit selection, changed-preview rejection, keep rules, empty directories, permissions and reversible menu ownership. A clean-machine graphical smoke test remains necessary before claiming compatibility with a particular Omarchy release. Do not run deletion tests against your real home.

## License and credits

[Almatera Incubator License](LICENSE), `LicenseRef-Almatera-Incubator`. Maintained by zamkara.

The design was studied against BleachBit's action/provider, process-check and keep-list patterns and Stacer's selection/loading behavior. Their source and cleaner definitions are not bundled or copied. CleanMacaci does not claim BleachBit compatibility, SQLite history/cookie editing, secure erasure, or superiority over those projects. Omarchy supplies the native shell controls; its license remains independent.

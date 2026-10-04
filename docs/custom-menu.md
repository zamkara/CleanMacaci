# Custom System menu integration

The plugin registers its entry in `~/.config/omarchy/extensions/system-menu.json`:

```json
{
  "cleaner.zamkara.ati": {
    "label": "System Cleaner",
    "icon": "󰃢",
    "command": ["omarchy-shell", "shell", "summon", "cleaner.zamkara.ati"],
    "plugin": "cleaner.zamkara.ati"
  }
}
```

Additional description/action/visibility fields may be present. Keep unrelated entries. Use Quickshell `FileView` with `watchChanges: true` to read this file and update the menu. Render entries through the existing menu delegate, using the command array directly with `Quickshell.execDetached`.

Read the existing `~/.config/omarchy/shell.json` and show entries only while their plugin ID is present in `plugins` and absent from `disabledPlugins`. Hide the old `zam.cleaner` entry when the new entry is enabled, so migration does not display two cleaners. Missing or invalid extension files should produce an empty extension list without breaking the base menu.

Stock Omarchy users need no custom adapter: the normal Setup menu registration is included. CleanMacaci does not rewrite third-party menu QML during installation.

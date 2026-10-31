# Board-safe launcher

`board-safe-hibernate` loads an installed, unmodified `herdr-hibernate` script
and adds a conservative exemption for herdr-projects panes. It requires the
same Python version as the plugin and adds no dependencies.

Board tasks can be waiting for a person while Herdr reports their agents as
`done`. A hibernation stub cannot accept `herdr agent prompt`, and entering
text into the stub consumes that line while waking the session. Until the
board supports wake-before-send, keep its panes running in every task stage,
including finished tasks that can receive another message.

The launcher protects `Agent`, `Agent (kind)`, `Reviewer #N`, `Coordinator`,
and coordinator titles in pane metadata, pane labels, tab labels, and terminal
titles (including older, manually started coordinators).
It also checks the board's task links and protects their whole workspaces,
plus panes running inside the board data folder. Ownership is checked again
immediately before hibernation, including `--force`. Invalid task records
prevent hibernation rather than risking a board pane. Ordinary agents retain
the plugin's existing rules.

## Install

Copy the launcher outside the plugin checkout, for example to
`~/.local/lib/herdr-hibernate/board-safe-hibernate`, and make it executable.
Write the absolute path of the installed upstream `herdr-hibernate` script
to `~/.config/herdr-hibernate/plugin-path` (one line). The launcher accepts all
upstream commands. Use it for manual hibernation too; invoking the upstream
script directly bypasses this guard.

For an existing systemd user service, add
`~/.config/systemd/user/herdr-hibernate.service.d/board-safe.conf`:

```ini
[Service]
ExecStart=
ExecStart=/absolute/home/.local/lib/herdr-hibernate/board-safe-hibernate watch
```

Preserve the service's `HERDR_SOCKET_PATH` setting so it reaches the intended
Herdr session. For a fresh installation, run the launcher with `install`
from a Herdr pane, then configure the socket in a service drop-in. Reload
systemd and restart **only** `herdr-hibernate.service`.

Use `HERDR_PROJECTS_DATA_DIR` or `HERDR_PROJECTS_HOME` in the service environment
if the board uses a nondefault data directory. Keep `AUTO_SETTLE_AFTER_DAYS=0`:
the guard prevents new hibernation; it does not change upstream auto-settling
of existing records. Review `status` and the dry-run log before setting
`DRY_RUN=0`. Existing hibernated board panes should be resumed first.

Plugin updates do not overwrite the launcher or drop-in. If reinstalling the
plugin changes its directory, update `plugin-path` and restart the watcher.
Route any manual hibernation keybinding through this launcher as well.

## Undo

Set `DRY_RUN=1` first. Restore the previous service configuration, reload
systemd, and restart the watcher. Resume existing stubs with Enter before
removing their launcher or plugin files. A machine with no previous watcher
can instead disable and stop `herdr-hibernate.service`. No Herdr server
restart is needed.

Run the regression suite with `python3 -m unittest discover -s tests`.

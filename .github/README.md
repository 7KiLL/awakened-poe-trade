# Awakened PoE Trade: Wayland layer-shell overlay

An unofficial fork of [SnosMe/awakened-poe-trade](https://github.com/SnosMe/awakened-poe-trade)
that draws the overlay as a Wayland **layer surface**, so it works on niri, sway,
Hyprland and other compositors where the stock overlay window does not.

Everything else is upstream, unchanged: the UI, the item parser, the trade logic,
the data. This branch is always *the latest upstream release plus a few commits*,
rebuilt automatically when upstream releases.

## Is this for you?

Use it if the stock AppImage does one of these on a Wayland compositor:

- the overlay opens as a normal window and gets tiled next to the game
- the overlay sits behind the game, or never shows at all
- the overlay has a black background instead of a transparent one

If stock APT already works for you (it reportedly does on KDE Plasma), you
don't need this.

| Compositor | Status |
|---|---|
| niri (with xwayland-satellite) | Tested: niri 26.04, 4K output at 1.2 scale |
| sway, Hyprland, river, labwc, COSMIC, KDE Plasma | Should work, they implement `wlr-layer-shell`. Not tested yet, reports welcome |
| GNOME | No layer shell. The app notices and falls back to the stock overlay |

This is young. It has been used on one machine. [Open an issue](../../issues) with
your compositor and what happened, working or not.

## Install

1. Install the libraries the overlay host needs. They are small and most
   desktops already have half of them.

   | Distro | Packages |
   |---|---|
   | Arch, CachyOS | `python-gobject python-cairo gtk-layer-shell webkit2gtk-4.1` |
   | Fedora (untested) | `python3-gobject python3-cairo gtk-layer-shell webkit2gtk4.1` |
   | Debian, Ubuntu (untested) | `python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 gir1.2-webkit2-4.1` |

2. Download the AppImage from [Releases](../../releases/latest), make it
   executable and run it. It updates itself from this fork's releases.

3. Run Path of Exile the usual way, through XWayland. That is Proton's default.
   `PROTON_ENABLE_WAYLAND=1` is not supported, here or upstream. On niri you need
   `xwayland-satellite` running, which you already have if the game starts.

Nothing to configure: when the compositor supports layer shell and the libraries
are there, the layer overlay is used. If something is missing the app prints why
to its terminal output and uses the stock overlay.

| Option | Effect |
|---|---|
| `--no-layer-shell` | Use the stock X11 overlay window |
| `APT_PYTHON=/path/to/python3` | Python with PyGObject, if it is not `/usr/bin/python3` (NixOS and friends) |

## Known limits

- The built-in browser for the trade site is off. Trade links open in your
  default browser instead. It is Electron's `<webview>`, which the host cannot show.
- The game is assumed to be fullscreen on its monitor. Windowed mode will put
  the widgets in the wrong place.
- The overlay UI is rendered by WebKitGTK, not Chromium. It looks the same as
  far as tested, but that is where a visual difference would come from.

## How it works

Electron cannot create a layer surface: a `BrowserWindow` on Wayland is always a
normal toplevel, and under XWayland it is a normal X11 window. Compositors like
niri treat both as windows to manage, which is exactly what an overlay must not be.

Upstream already serves its UI as a web page on a local port and talks to it
over a WebSocket. So this fork replaces only the window:

```
Electron main process (X11, as upstream)        layer-host.py (Wayland)
  hotkeys, clipboard, key presses,   ── stdin ──▶  GTK3 window on the overlay layer
  game window tracking, trade proxy  ◀─ stdout ──  WebKitGTK showing the same page
```

- [`layer-host.py`](../main/src/windowing/layer-host.py) is a ~130 line GTK3 +
  gtk-layer-shell + WebKitGTK program. It is click-through while you play, takes
  the keyboard when the overlay is opened, and gives it back on Escape.
- [`LayerHost.ts`](../main/src/windowing/LayerHost.ts) starts it, tells it when
  to hide, show or take input, and converts between X11 screen pixels and overlay
  CSS pixels (the two differ on scaled outputs).
- Upstream files carry one-line hooks, about twenty lines across five files.
  [See the whole diff against upstream](../../compare/master...wayland-layer-shell).

## Notes for upstream

Written for anyone deciding whether this approach belongs in APT itself, the
maintainer first of all. Disagreement is welcome, that is what the issue
tracker here is for.

**What it costs.** Two new files and about twenty hooked lines. No new npm
dependencies, no native code, no change to packaging: the host script is
bundled into `main.js` as text and run with the system Python. Windows, macOS
and X11 sessions never execute any of it.

**What it buys.** Compositor-agnostic overlay support on everything that
implements `wlr-layer-shell`, which is every major Wayland compositor except
GNOME. It needs no per-compositor code, unlike KWin scripting, and no portals.
It keeps the X11 path for hotkeys and input, which is the part that already
works under XWayland.

**Why not pure TypeScript.** Electron has no layer-shell API. Speaking the
Wayland protocol from Node needs file-descriptor passing, so a native addon
either way. Staying an X11 window depends on each compositor's XWayland
integration mapping override-redirect windows onto the overlay layer, which
xwayland-satellite does not do today.

**Why a separate process and why Python.** A layer surface has to be created by
the toolkit that owns the window, and Chromium's is not reachable. GTK with
gtk-layer-shell is the smallest thing that can host a web view on a layer
surface, and PyGObject needs no build step, so the AppImage stays as it is.
A compiled helper, or doing this inside `electron-overlay-window`, would be the
choice for upstreaming. The stdin/stdout protocol is six commands and would not
change.

**Honest weak points.**

- A runtime dependency on system libraries that an AppImage cannot check ahead
  of time. The app probes for them at start and falls back.
- A second web engine. The overlay runs in WebKitGTK and identifies itself as
  Electron so the renderer takes its overlay code path.
- No `<webview>`, so no built-in browser.
- While the overlay has focus, X11 sees no pointer movement. The host reports
  the pointer and `LayerHost.ts` re-emits it as a `uIOhook` event so
  `WidgetAreaTracker` keeps working. It is the least pretty line in the diff.

## How this fork stays current

[`layer-shell.yml`](workflows/layer-shell.yml) runs every six hours:

1. finds the latest upstream release tag,
2. rebases this branch onto it,
3. builds the AppImage and publishes it as `v<upstream version>-layer.<n>`.

The version and the updater's repository are set at build time, so the branch
itself never conflicts with upstream's version bumps. If a rebase or build
fails, the workflow opens an issue and nothing is published.

Because the branch is rebased, its history is rewritten on every upstream
release. Fork it rather than tracking it if you want to build on top.

## Build from source

Same as upstream, see [DEVELOPING.md](../DEVELOPING.md). The layer overlay is
picked up automatically in dev mode too.

```shell
cd renderer && npm ci && npm run build
cd ../main && npm ci && npm run build && npm run package -- --linux -p never
```

## Credits

All of Awakened PoE Trade is the work of [SnosMe](https://github.com/SnosMe) and
its contributors. If it is useful to you, [support upstream](https://github.com/SnosMe/awakened-poe-trade).
This fork is not affiliated with or endorsed by upstream or Grinding Gear Games.

MIT, same as upstream.

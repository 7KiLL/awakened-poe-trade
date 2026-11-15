"""Overlay window for Wayland compositors with wlr-layer-shell (niri, sway, Hyprland, KDE).

An X11 overlay window is just another window to those compositors, a layer
surface is not. Spawned by OverlayWindow.ts in place of the BrowserWindow:

  stdin   state hidden|passive|active      passive = shown, click-through
          key <overlay hotkey>
  stdout  size <w> <h>                     surface size, CSS px
          mouse <x> <y>                    pointer, CSS px (X11 can't see it over us)
          focus-game | toggle
"""
import json
import os
import sys

import cairo
import gi

gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gdk, Gio, GLib, Gtk, GtkLayerShell, WebKit2  # noqa: E402

if sys.argv[1] == '--probe':  # LayerHost.ts asks before it gives up the BrowserWindow
    sys.exit(0 if GtkLayerShell.is_supported() else 'the compositor has no wlr-layer-shell')

# Same keys OverlayWindow.handleExtraCommands takes from Electron's before-input-event.
KEYS_JS = """
window.__overlayKey = 'Shift + Space'
window.addEventListener('keydown', (e) => {
  let code = e.code.replace(/^(Key|Digit)/, '')
  if (e.shiftKey && e.altKey) code = `Shift + Alt + ${code}`
  else if (e.ctrlKey && e.shiftKey) code = `Ctrl + Shift + ${code}`
  else if (e.ctrlKey && e.altKey) code = `Ctrl + Alt + ${code}`
  else if (e.altKey) code = `Alt + ${code}`
  else if (e.ctrlKey) code = `Ctrl + ${code}`
  else if (e.shiftKey) code = `Shift + ${code}`

  let msg
  if (code === 'Escape' || code === 'Ctrl + W') msg = 'focus-game'
  else if (code === window.__overlayKey) msg = 'toggle'
  else return
  e.preventDefault()
  e.stopImmediatePropagation()
  window.webkit.messageHandlers.host.postMessage(msg)
}, true)
"""


def out(line):
    print(line, flush=True)


win = Gtk.Window()
win.set_app_paintable(True)
win.set_visual(win.get_screen().get_rgba_visual())
GtkLayerShell.init_for_window(win)
GtkLayerShell.set_namespace(win, 'awakened-poe-trade')
GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
    GtkLayerShell.set_anchor(win, edge, True)
GtkLayerShell.set_exclusive_zone(win, -1)  # cover the bars too, like the game does

content = WebKit2.UserContentManager()
content.add_script(WebKit2.UserScript(
    KEYS_JS, WebKit2.UserContentInjectedFrames.TOP_FRAME, WebKit2.UserScriptInjectionTime.START, None, None))
content.register_script_message_handler('host')
content.connect('script-message-received::host', lambda _m, result: out(result.get_js_value().to_string()))

view = WebKit2.WebView(user_content_manager=content)
view.set_background_color(Gdk.RGBA(0, 0, 0, 0))
# The renderer picks its overlay code path by user agent; LayerHost marks what Electron has and we lack.
view.get_settings().set_user_agent_with_application_details('Electron', 'LayerHost')


def open_external(_view, action):
    Gio.AppInfo.launch_default_for_uri(action.get_request().get_uri(), None)


view.connect('create', open_external)  # window.open(): trade links go to the real browser
view.connect('context-menu', lambda *_: True)
view.connect('motion-notify-event', lambda _w, e: out(f'mouse {e.x:.0f} {e.y:.0f}'))
win.add(view)

last_size = None


def report_size(_w, alloc):
    global last_size
    if (alloc.width, alloc.height) != last_size:
        last_size = (alloc.width, alloc.height)
        out(f'size {alloc.width} {alloc.height}')


win.connect('size-allocate', report_size)


def set_state(state):
    if state == 'hidden':
        win.hide()
        return
    active = state == 'active'
    GtkLayerShell.set_keyboard_mode(
        win, GtkLayerShell.KeyboardMode.EXCLUSIVE if active else GtkLayerShell.KeyboardMode.NONE)
    # No output is set, so each map lands on the focused one: the game's.
    win.show_all()
    win.input_shape_combine_region(None if active else cairo.Region())
    if active:
        view.grab_focus()


pending = b''


def on_stdin(fd, condition):
    global pending
    data = os.read(fd, 4096) if condition & GLib.IO_IN else b''
    if not data:  # parent is gone
        Gtk.main_quit()
        return False
    *lines, pending = (pending + data).split(b'\n')
    for line in lines:
        cmd, _, arg = line.decode().partition(' ')
        if cmd == 'state':
            set_state(arg)
        elif cmd == 'key':
            view.evaluate_javascript(f'window.__overlayKey = {json.dumps(arg)}', -1, None, None, None, None, None)
    return True


GLib.io_add_watch(sys.stdin.fileno(), GLib.IO_IN | GLib.IO_HUP, on_stdin)
view.load_uri(sys.argv[1])
Gtk.main()

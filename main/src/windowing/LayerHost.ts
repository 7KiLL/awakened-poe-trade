// Wayland layer-shell overlay. Everything the fork adds to the main process
// lives here and in layer-host.py; upstream files only carry one-line hooks.
//
// Electron cannot create a layer surface, so the renderer page is shown by a
// small GTK + WebKitGTK process instead of a BrowserWindow. Hotkeys, clipboard
// and game tracking stay in Electron on X11, where the game is.
import { spawn, spawnSync, type ChildProcess } from 'child_process'
import { createInterface } from 'readline'
import { app, screen, type Point, type Rectangle } from 'electron'
import { uIOhook, type UiohookMouseEvent } from 'uiohook-napi'
import hostSource from './layer-host.py'
import type { OverlayWindow } from './OverlayWindow'
import type { GameWindow } from './GameWindow'

// The system python is the one that has PyGObject.
const PYTHON = process.env.APT_PYTHON || '/usr/bin/python3'
const ENV = { ...process.env, GDK_BACKEND: 'wayland' }

class LayerHost {
  private proc?: ChildProcess
  private overlay?: OverlayWindow
  private poeWindow?: GameWindow
  private width = 0

  start (url: string, overlay: OverlayWindow, poeWindow: GameWindow) {
    this.overlay = overlay
    this.poeWindow = poeWindow
    this.proc = spawn(PYTHON, ['-c', hostSource, url], { stdio: ['pipe', 'pipe', 'inherit'], env: ENV })
    this.proc.on('exit', () => { app.quit() })
    createInterface({ input: this.proc.stdout! }).on('line', (line) => {
      const [cmd, x, y] = line.split(' ')
      if (cmd === 'size') {
        this.width = Number(x)
      } else if (cmd === 'mouse') {
        // X11 sees no pointer over a Wayland surface, so feed WidgetAreaTracker ourselves
        const at = this.overlayToScreen({ x: Number(x), y: Number(y), width: 0, height: 0 })
        uIOhook.emit('mousemove', { x: at.x, y: at.y, ctrlKey: false, altKey: false } as UiohookMouseEvent)
      } else if (cmd === 'focus-game') {
        overlay.assertGameActive()
      } else if (cmd === 'toggle') {
        overlay.toggleActiveState()
      }
    })
    poeWindow.on('active-change', this.sync)
    this.sync()
  }

  // Deferred: callers are in the middle of changing the state this reads.
  sync = () => {
    process.nextTick(() => {
      const state = this.overlay?.isInteractable ? 'active' : (this.poeWindow?.isActive ? 'passive' : 'hidden')
      this.proc?.stdin!.write(`state ${state}\n`)
    })
  }

  setOverlayKey (key: string) {
    this.proc?.stdin!.write(`key ${key}\n`)
  }

  // X11 screen px <-> overlay CSS px. With a BrowserWindow the renderer does
  // this itself with window.screenX, which a layer surface does not have.
  // ponytail: takes the game as fullscreen on the display under the cursor;
  // a windowed game needs poeWindow.bounds as the origin instead.
  private get geometry () {
    const { bounds } = screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
    return { x: bounds.x, y: bounds.y, scale: this.width ? bounds.width / this.width : 1 }
  }

  screenToOverlay (point: Point): Point {
    const { x, y, scale } = this.geometry
    return { x: (point.x - x) / scale, y: (point.y - y) / scale }
  }

  overlayToScreen (rect: Rectangle): Rectangle {
    const { x, y, scale } = this.geometry
    return { x: rect.x * scale + x, y: rect.y * scale + y, width: rect.width * scale, height: rect.height * scale }
  }
}

function isAvailable (): boolean {
  if (process.platform !== 'linux' || !process.env.WAYLAND_DISPLAY) return false
  if (process.argv.includes('--no-layer-shell') || process.argv.includes('--no-overlay')) return false

  const probe = spawnSync(PYTHON, ['-c', hostSource, '--probe'], { env: ENV, encoding: 'utf8', timeout: 5000 })
  if (probe.status === 0) return true
  console.warn(`[LayerHost] unavailable, falling back to the X11 overlay window:\n${probe.stderr || String(probe.error)}`)
  return false
}

export const layerHost = isAvailable() ? new LayerHost() : undefined

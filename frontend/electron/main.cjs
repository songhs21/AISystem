// electron/main.cjs
const { app, BrowserWindow, Tray, Menu, nativeImage, shell, ipcMain } = require('electron')
const path = require('path')
const { spawn } = require('child_process')

// ── 경로 설정 ─────────────────────────────────────────────
const PYTHON_PATH = 'C:\\python3.10\\python.exe'
const PROJECT_ROOT = path.join(__dirname, '../..')
const VITE_URL = 'http://localhost:5173'
const API_URL = 'http://localhost:8000'
const API_PORT = 8000
const isDev = process.env.NODE_ENV !== 'production'

let mainWindow = null
let tray = null
let apiProcess = null
let logBuffer = []


// ── 타임스탬프 ────────────────────────────────────────────
function timestamp() {
  const d = new Date()
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
}


// ── 로그 → 렌더러 전송 ───────────────────────────────────
function sendLog(entry) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('log', entry)
  }
}


// ── FastAPI 서버 시작 ─────────────────────────────────────
function startApiServer() {
  apiProcess = spawn(
    PYTHON_PATH,
    ['-m', 'uvicorn', 'api.main:app', '--host', '0.0.0.0', '--port', String(API_PORT)],
    {
      cwd: PROJECT_ROOT,
      windowsHide: true,
      detached: false,
    }
  )

  // stdout 로그 수집
  apiProcess.stdout.on('data', (data) => {
    const lines = data.toString().split('\n').filter(l => l.trim())
    lines.forEach(line => {
      const entry = { source: 'API', level: 'INFO', text: line, time: timestamp() }
      logBuffer.push(entry)
      sendLog(entry)
    })
  })

  // stderr 로그 수집 (FastAPI는 stderr에 INFO 로그 출력)
  apiProcess.stderr.on('data', (data) => {
    const lines = data.toString().split('\n').filter(l => l.trim())
    lines.forEach(line => {
      const level = /error|exception/i.test(line) ? 'ERROR' : 'INFO'
      const entry = { source: 'API', level, text: line, time: timestamp() }
      logBuffer.push(entry)
      sendLog(entry)
    })
  })

  apiProcess.on('exit', (code) => {
    const entry = { source: 'API', level: 'ERROR', text: `프로세스 종료 (code: ${code})`, time: timestamp() }
    logBuffer.push(entry)
    sendLog(entry)
  })
}


// ── IPC: 기존 로그 버퍼 요청 ─────────────────────────────
ipcMain.handle('get-logs', () => logBuffer)


// ── 메인 윈도우 생성 ──────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
    show: false,
    title: 'AISystem',
  })

  const url = isDev ? VITE_URL : `file://${path.join(__dirname, '../dist/index.html')}`
  mainWindow.loadURL(url)

  mainWindow.once('ready-to-show', () => mainWindow.show())

  // 닫기 버튼 → 트레이로 최소화
  mainWindow.on('close', (e) => {
    if (!app.isQuiting) {
      e.preventDefault()
      mainWindow.hide()
    }
  })

  // Electron 콘솔 로그 수집
  mainWindow.webContents.on('console-message', (e, level, message) => {
    const levelMap = { 0: 'INFO', 1: 'INFO', 2: 'ERROR', 3: 'ERROR' }
    const entry = { source: 'ELECTRON', level: levelMap[level] || 'INFO', text: message, time: timestamp() }
    logBuffer.push(entry)
  })
}


// ── 트레이 설정 ───────────────────────────────────────────
function createTray() {
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)

  const menu = Menu.buildFromTemplate([
    { label: '열기', click: () => { mainWindow.show(); mainWindow.focus() } },
    { label: 'API 상태', click: () => shell.openExternal(`${API_URL}/health`) },
    { type: 'separator' },
    { label: '종료', click: () => { app.isQuiting = true; app.quit() } },
  ])

  tray.setToolTip('AISystem')
  tray.setContextMenu(menu)
  tray.on('double-click', () => { mainWindow.show(); mainWindow.focus() })
}


// ── 앱 이벤트 ─────────────────────────────────────────────
app.whenReady().then(() => {
  startApiServer()
  createWindow()
  createTray()
})

app.on('window-all-closed', (e) => {
  // 트레이 상주 — 모든 창 닫혀도 앱 유지
  e.preventDefault()
})

app.on('before-quit', () => {
  if (apiProcess) apiProcess.kill()
})
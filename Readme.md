<p align="center">
  <img src="ink/assets/ink.svg" width="120" alt="Ink Logo">
</p>

# Ink

A macOS system-wide handwriting input tool — draw with a stylus or mouse, and recognized text is injected into any application.

[![Release](https://img.shields.io/github/v/release/doomsday-07/ink-app?style=flat-square)](https://github.com/doomsday-07/ink-app/releases/latest)
[![macOS](https://img.shields.io/badge/macOS-13%2B-blue?style=flat-square)](https://github.com/doomsday-07/ink-app/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

## Download

Download the latest **Ink.dmg** from [GitHub Releases](https://github.com/doomsday-07/ink-app/releases/latest).

1. Open the `.dmg` file and drag **Ink.app** to your Applications folder.
2. Right-click → **Open** (first launch only, to bypass Gatekeeper).
3. Grant Accessibility permission when prompted.

---

## Features

- **Floating panel** — always-on-top, translucent, draggable and resizable (min 220×120).
- **Auto-recognition** — text is recognized automatically after a configureable delay (default 500ms) when you finish a stroke.
- **Global shortcut** — **Cmd+Shift+I** toggles the panel from any application.
- **Text injection** — recognized text is automatically sent to the previously focused app:
  1. **Accessibility API** (primary) — directly sets the value of the focused text field.
  2. **Clipboard + Cmd+V** (fallback) — copies to clipboard, activates the target app, and simulates paste.
- **Focused app tracking** — polls `NSWorkspace` every 150ms to track the frontmost application.
- **Settings bar** — configure recognition delay (100–2000ms), auto-recognize on/off, auto-clear on/off.
- **OCR engine selection** — choose between Vision (default) or EasyOCR; pick from 11 languages.
- **Opacity control** — panel opacity 30–100%.

---

## Setup

### Requirements

- macOS 13+
- Python 3.11+

### Install

```bash
git clone https://github.com/doomsday-07/ink-app.git
cd ink-app

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Run from Source

```bash
source venv/bin/activate
cd ink
python3 main.py
```

Press **Cmd+Shift+I** anywhere in macOS to toggle the floating panel.

---

## macOS Permissions

### Accessibility

Required for:
- Text injection into other applications.
- Global keyboard shortcut (Cmd+Shift+I).

**Grant**: System Settings → Privacy & Security → Accessibility → add your terminal or `.app`.

The app checks `AXIsProcessTrusted()` on launch and will prompt you if permission is missing.

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+Shift+I` | Show/hide panel |
| Click gear icon | Open settings |
| Click close (✕) | Hide panel |

---

## Handwriting Recognition

### Engines

| Engine | Requirements | Languages | Speed | Notes |
|--------|-------------|-----------|-------|-------|
| **macOS Vision** | Built-in (pyobjc-framework-Vision) | English | Fast | Default. Uses `VNRecognizeTextRequest` with language correction. |
| **EasyOCR** | `pip install easyocr` | 80+ languages | Slow (CPU) | Multilingual support. Select from 11 languages in the toolbar. |

---

## How It Works

1. **FocusedAppTracker** polls `NSWorkspace.sharedWorkspace().frontmostApplication()` every 150ms and stores the PID of the frontmost app.
2. When you draw on the floating panel, the target UI element is captured via `AXUIElementCopyAttributeValue()`.
3. After recognition:
   - **Primary**: `AXUIElementSetAttributeValue()` sets the value directly on the focused text field.
   - **Fallback**: Copies to clipboard, activates the target app, and simulates **Cmd+V**.

---

## Architecture

```
ink-app/
├── requirements.txt                 # Dependencies
│
├── core/                            # Shared library
│   ├── __init__.py                  # Re-exports
│   ├── canvas.py                    # Pressure-sensitive DrawingCanvas + Stroke
│   ├── accessibility.py             # AX API: text injection, focused app tracking
│   ├── snipping.py                  # ScreenSnipOverlay + ScreenSnipper
│   ├── recognizer.py                # Multi-engine recognizer (Vision / EasyOCR)
│   ├── corrections.py               # CorrectionStore: CSV + image dataset
│   ├── ocr_model.py                 # CNN+BiLSTM+CTC PyTorch model architecture
│   └── ...
│
├── ink/                             # Standalone Ink.app (floating input panel)
│   ├── main.py                      # Entry point
│   ├── setup.py                     # py2app packaging config
│   ├── requirements.txt
│   └── gui/
│       └── floating_panel.py        # FloatingPanel (standalone version)
│
└── packaging/                       # Build + notarization scripts
    ├── build_ink.sh                 # py2app → codesign → DMG
    ├── notarize.sh                  # Apple notarization (xcrun notarytool + stapler)
    └── entitlements.plist           # Signing entitlements
```

---

## Configuration

| Setting | Default | Location |
|---------|---------|----------|
| Recognition delay | 500ms | `ink/gui/floating_panel.py` |
| Floating panel size | 400 × 220 | `ink/gui/floating_panel.py` |
| Floating panel opacity | 95% | `ink/gui/floating_panel.py` |
| Focused app poll interval | 150ms | `core/accessibility.py` |

### Input Mode Settings

Accessed via the gear icon on the floating panel.

- **Auto-recognize**: On/Off (recognize text automatically after each stroke)
- **Recognition delay**: 100 – 3000ms (how long to wait after stroke ends)
- **Auto-clear canvas**: On/Off (clear after successful injection)
- **Injection method**: Auto / Accessibility API / Clipboard
- **OCR Engine**: Vision / EasyOCR
- **Language**: English, German, French, Spanish, Italian, Portuguese, Dutch, Russian, Japanese, Chinese, Arabic
- **Panel opacity**: 30 – 100%
- **Panel width/height**: configurable

---

## Building from Source

### Run directly

```bash
cd ink
python3 main.py
```

### Build .app bundle

```bash
cd ink
python3 setup.py py2app
xattr -cr dist/Ink.app
```

### Build DMG

```bash
bash packaging/build_ink.sh
# Output: ink/dist/Ink.dmg
```

### Codesign + Notarize (requires Apple Developer ID)

```bash
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
bash packaging/build_ink.sh

export APPLE_ID="your@email.com"
export TEAM_ID="YOURTEAMID"
export APP_SPECIFIC_PASSWORD="xxxx-xxxx-xxxx-xxxx"
bash packaging/notarize.sh ink/dist/Ink.dmg
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'PyQt6'` | Virtual environment not activated | `source venv/bin/activate` |
| "Cannot inject text" | Accessibility permission not granted | System Settings → Privacy → Accessibility → add the app/terminal |
| Text injection pastes wrong content | Clipboard race condition | Switch to Accessibility injection method in settings |

---

## Dependencies

### Required

| Package | Purpose |
|---------|---------|
| PyQt6 | GUI framework |
| pyobjc-framework-Vision | macOS Vision OCR |
| pyobjc-framework-ApplicationServices | Accessibility API |

### Optional

| Package | Purpose | Install |
|---------|---------|---------|
| easyocr | Multilingual OCR | `pip install easyocr` |

---

## License

MIT

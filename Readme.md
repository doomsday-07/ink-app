# InkApp

A macOS alternative to Windows Ink — two integrated apps for handwriting recognition and system-wide handwriting input.

## Apps

| App | Run | Purpose |
|-----|-----|---------|
| **InkApp** | `python3 main.py` | Full GUI: drawing canvas, OCR, PDF tools, screen annotation |
| **Ink** | `cd ink && python3 main.py` | Floating handwriting panel that injects text into any app |

---

## Features

### InkApp — Full Application

- **Pressure-sensitive drawing canvas** — 6 brush types: pen, calligraphy, spray, marker, pencil, eraser. Supports tablet pressure via `QTabletEvent`.
- **Handwriting recognition** — 3 engines:
  - **macOS Vision** — built-in, fast, English (default)
  - **EasyOCR** — multilingual (80+ languages, optional `pip install easyocr`)
  - **Custom model** — CNN+BiLSTM+CTC trained on your own handwriting
- **Correction dataset** — save misrecognized text with corrected labels; retrain the custom model on your handwriting.
- **PDF signing** — open PDFs, load or draw a signature, place it on any page, save incrementally or as a new file. Cryptographic signing via `pyHanko`.
- **PDF annotation** — draw pen, highlighter, rectangle, text, and eraser directly on PDF pages. Saves as a new PDF with native annotations.
- **Screen snip** — drag-select any region of the screen to capture as an image.
- **Screen annotation** — fullscreen translucent overlay for annotating live screen content.
- **System-wide input mode** — floating handwriting panel docked to a toolbar toggle; injects recognized text into any application via Accessibility API or clipboard.

### Ink — Floating Handwriting Input

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
# Clone or cd into the project
cd ink-app

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run InkApp (Full GUI)

```bash
source venv/bin/activate
python3 main.py
```

### Run Ink (Floating Input Panel)

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
- Screen capture in InkApp (macOS 14+).

**Grant**: System Settings → Privacy & Security → Accessibility → add your terminal or `.app`.

The app checks `AXIsProcessTrusted()` on launch and will prompt you if permission is missing.

### Screen Recording

Required for screen capture on macOS 14+.

**Grant**: System Settings → Privacy & Security → Screen Recording → add your terminal or `.app`.

---

## Keyboard Shortcuts

### InkApp Main Window

| Shortcut | Action |
|----------|--------|
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `Cmd+Shift+I` | Toggle system-wide input panel |

### Floating Panel (Ink / System Input)

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
| **Custom** | `torch`, `jiwer` | Your vocabulary | Fast | CNN+BiLSTM+CTC model (~3M parameters). Must be trained first. |

### Custom Model Architecture

```
Input (grayscale, H=32, W≤600)
  └─ CNN (5 conv + ReLU + BN + MaxPool) → (256, 1, W/8)
       └─ BiLSTM (1 layer, 256 hidden) → (512)
            └─ Linear (512 → 95) + LogSoftmax → CTC greedy decode
```

- **Vocabulary**: 95 characters including space, letters (a-z, A-Z), digits, and common punctuation/symbols.
- **Preprocessing**: Grayscale → binarize (threshold = mean × 0.6) → crop to ink region → resize height to 32 (preserve aspect ratio) → normalize to [0,1].

### Training Pipeline

Two-stage training for the custom model:

#### Stage 1: Pre-train on public data

Uses the Kaggle "Handwritten Names" dataset.

```bash
# Download and extract dataset to ~/Downloads/archive/
# Then run:
source venv/bin/activate
pip install -r train/requirements.txt
python3 train_kaggle.py
```

Saves to `custom_model/pretrained.pt`. Samples up to 20,000 entries, trains for 20 epochs with early stopping (patience=5).

#### Stage 2: Fine-tune on your handwriting

1. Draw text on the InkApp canvas.
2. Click **Recognize** — correct any mistakes in the text field.
3. Click **Save Correction** — saves image + corrected text to `~/ink-app-dataset/`.
4. Repeat to build a dataset (50+ samples for decent results, 200+ for good accuracy).
5. Run:

```bash
source venv/bin/activate
pip install -r train/requirements.txt
python3 train.py --pretrained custom_model/pretrained.pt
```

Saves to `custom_model/model.pt`. CNN layers are frozen during fine-tuning. Early stopping (patience=10). Restart the app and select "Custom (fine-tuned)" engine.

### Diagnostics

```bash
python3 test_model.py                         # test fine-tuned model
python3 test_model.py --pretrained             # test pre-trained model
python3 test_model.py --image path.png         # test on single image
```

---

## Text Injection

The system-wide input mode uses a multi-strategy injection pipeline:

1. `FocusedAppTracker` polls `NSWorkspace.sharedWorkspace().frontmostApplication()` every 150ms and stores the PID of the frontmost app.
2. When the user draws on the floating panel, the target UI element is captured via `AXUIElementCopyAttributeValue()` on the tracked PID's focused element.
3. After recognition:
   - **Primary**: `AXUIElementSetAttributeValue()` sets the `AXValue` attribute directly on the focused text field.
   - **Fallback**: `NSPasteboard.generalPasteboard()` copies the text, `NSWorkspace.launchApplication()` activates the target app, then `CGEventPost()` simulates **Cmd+V** (keycode 9).

---

## Architecture

```
ink-app/
├── main.py                          # InkApp entry point (QApplication + MainWindow)
├── requirements.txt                 # Top-level dependencies
│
├── core/                            # Shared library
│   ├── __init__.py                  # Re-exports: DrawingCanvas, AnnotationOverlay, ScreenSnipper, etc.
│   ├── canvas.py                    # Pressure-sensitive DrawingCanvas + Stroke (6 brush types)
│   ├── layer.py                     # AnnotationLayer data model (strokes, shapes, text, fills)
│   ├── overlay.py                   # AnnotationOverlay: fullscreen overlay with pan/zoom, layers, tools
│   ├── snipping.py                  # ScreenSnipOverlay + ScreenSnipper (region capture)
│   ├── accessibility.py             # AX API: text injection, focused app tracking, permissions
│   ├── tablet_monitor.py            # CGEventTap for stylus proximity detection
│   ├── ocr_model.py                 # CNN+BiLSTM+CTC PyTorch model architecture
│   ├── recognizer.py                # Multi-engine recognizer (Vision / EasyOCR / Custom)
│   ├── corrections.py               # CorrectionStore: CSV + image dataset in ~/ink-app-dataset/
│   ├── pdf_signer.py                # PDF viewing, signature placement, cryptographic signing
│   └── requirements.txt
│
├── gui/                             # InkApp-specific GUI widgets
│   ├── main_window.py               # MainWindow (QSplitter: canvas | text output)
│   ├── toolbar.py                   # DrawingToolbar (15+ controls)
│   ├── drawing_overlay.py           # DrawingOverlay: transient handwriting input widget
│   ├── floating_panel.py            # FloatingPanel (used by InkApp's system input mode)
│   ├── signature_dialog.py          # PDF signing dialog with page viewer
│   ├── pdf_annotate_dialog.py       # PDF annotation dialog (pen/highlighter/rect/text)
│   └── input_mode_dialog.py         # Settings dialog for floating panel
│
├── ink/                             # Standalone Ink.app (floating input panel)
│   ├── main.py                      # Entry point
│   ├── setup.py                     # py2app packaging config
│   ├── requirements.txt
│   ├── gui/
│   │   └── floating_panel.py        # FloatingPanel (standalone version)
│   ├── build/                       # py2app build artifacts
│   └── dist/Ink.app/                # Built macOS app bundle
│
├── train/                           # Training pipeline
│   ├── main.py                      # Training GUI entry point
│   ├── train.py                     # Stage 2: fine-tune on user corrections
│   ├── train_kaggle.py              # Stage 1: pre-train on Kaggle dataset
│   ├── test_model.py                # Model diagnostic script
│   └── requirements.txt             # torch, jiwer
│
├── packaging/                       # Build + notarization scripts
│   ├── build_ink.sh                 # py2app → codesign → DMG
│   ├── notarize.sh                  # Apple notarization (xcrun notarytool + stapler)
│   └── entitlements.plist           # Unsigned executable memory, disable library validation
│
├── custom_model/                    # Trained model weights
│   └── pretrained.pt                # Stage 1 pre-trained model
│
└── venv/                            # Python virtual environment
```

---

## Configuration

| Setting | Default | Location |
|---------|---------|----------|
| Dataset directory | `~/ink-app-dataset/` | `core/corrections.py` |
| Custom model directory | `ink-app/custom_model/` | `core/recognizer.py` |
| Undo stack limit | 50 | `core/overlay.py` |
| Zoom range | 0.5 – 2.0 | `core/overlay.py` |
| Default zoom | 2.0 | `core/overlay.py`, `gui/signature_dialog.py`, `gui/pdf_annotate_dialog.py` |
| Recognition delay | 500ms | `gui/input_mode_dialog.py` |
| Floating panel size | 400 × 220 | `gui/input_mode_dialog.py` |
| Floating panel opacity | 95% | `gui/input_mode_dialog.py` |
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

## Standalone App Bundles

Build distributable `.app` bundles using py2app:

```bash
# Build Ink.app
cd ink
python3 setup.py py2app
xattr -cr dist/Ink.app
```

The build scripts in `packaging/` automate the full process including codesigning and DMG creation:

```bash
# Requires a valid Apple Developer signing identity
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
bash packaging/build_ink.sh
```

The `.app` bundle uses `LSUIElement: True` — it runs as an agent app (no Dock icon, no menu bar).

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'PyQt6'` | Virtual environment not activated | `source venv/bin/activate` |
| "Cannot inject text" | Accessibility permission not granted | System Settings → Privacy → Accessibility → add the app/terminal |
| "Screen capture returns blank" | Screen Recording permission not granted (macOS 14+) | System Settings → Privacy → Screen Recording → add the app/terminal |
| Text injection pastes wrong content | Clipboard race condition | Try reducing recognition delay or switching to Accessibility injection method |
| Custom model returns gibberish | Model not trained or wrong engine selected | Train the model first, then select "Custom (fine-tuned)" in the engine combo |
| PNG export has wrong DPI | Default is 72 DPI | Override DPI in `QImage.setDotsPerMeterX()` if needed for printing |

---

## Dependencies

### Required

| Package | Version | Purpose |
|---------|---------|---------|
| PyQt6 | ≥6.6.0 | GUI framework |
| PyMuPDF | ≥1.24.0 | PDF reading and annotation |
| pyHanko | ≥0.25.0 | Cryptographic PDF signing |
| Pillow | ≥10.0.0 | Image loading/conversion |
| numpy | ≥1.24.0 | Array operations (flood fill, image processing) |
| pyobjc-framework-Vision | — | macOS Vision OCR |
| pyobjc-framework-ApplicationServices | — | Accessibility API |
| pyobjc-framework-Cocoa | — | NSApplication, NSWorkspace, NSPasteboard |
| pyobjc-framework-Quartz | — | CoreGraphics event taps, CGEventPost |

### Optional

| Package | Purpose | Install |
|---------|---------|---------|
| easyocr | Multilingual OCR | `pip install easyocr` |
| torch | Custom model training and inference | `pip install torch` |
| jiwer | CER evaluation during training | `pip install jiwer` |
| cryptography | Certificate generation for PDF signing | Included via pyHanko |

---

## License

MIT

from setuptools import setup

APP = ["main.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "includes": ["PyQt6", "ApplicationServices", "Cocoa", "Quartz", "Vision", "PIL", "PIL.Image"],
    "excludes": ["tkinter", "matplotlib", "numpy", "torch", "easyocr", "train"],
    "plist": {
        "CFBundleName": "Ink",
        "CFBundleDisplayName": "Ink",
        "CFBundleIdentifier": "com.inkapp.ink",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleIconFile": "ink.icns",
        "LSMinimumSystemVersion": "12.0",
        "LSUIElement": True,
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

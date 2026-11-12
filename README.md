<div align="center">

# Manga Translator

**Read manga, manhwa and comics in natural, casual Hindi, right in your browser.**

Japanese · Korean · Chinese · English → हिन्दी

![version](https://img.shields.io/badge/version-v1.0.0-blue)
![python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![platform](https://img.shields.io/badge/platform-Windows%2011-0078D6?logo=windows&logoColor=white)
![firefox](https://img.shields.io/badge/Firefox-supported-FF7139?logo=firefoxbrowser&logoColor=white)
![chrome](https://img.shields.io/badge/Chrome-supported-4285F4?logo=googlechrome&logoColor=white)
![ai](https://img.shields.io/badge/AI-Gemini%20%7C%20Groq%20%7C%20NLLB-8E75B2)

[Features](#features) · [How it works](#how-it-works) · [Installation](#installation) · [Usage](#usage) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting)

</div>

---

## Overview

**Manga Translator** is a free, self-hosted tool that translates manga pages while you read them.
A browser extension sends each page to a small server running on your own PC. The server reads the text,
translates it into everyday Hindi with an AI model, erases the original text and draws the Hindi back
into the speech bubbles, so the page looks as if it had been published in Hindi.

Unlike word-for-word translators, it looks at the page image to work out **who is speaking**, so the Hindi
uses the correct gender: a girl says *"मैं थक गई"*, a boy says *"मैं थक गया"*.

## Features

| Feature | Details |
|---|---|
| **Casual Hindi** | Natural spoken Hindi like anime dubs, not formal or bookish Hindi |
| **Gender-aware** | Verbs match the speaker and the person being addressed |
| **Character memory** | Remembers each character's gender per series (`memory.json`) |
| **4 source languages** | Japanese, Korean, Chinese (Simplified / Traditional) and English, with auto-detect |
| **Bubble-aware typesetting** | Detects speech bubbles, erases the original text and fits Hindi to the bubble shape |
| **Fallback chain** | Gemini → Groq → local NLLB, so reading never stops when a free limit runs out |
| **Firefox & Chrome** | Manifest V3 extension that works on any site, with an "always on for this site" option |
| **Fast reading** | Prefetches upcoming pages, translates 3 pages in parallel and caches results |
| **Local first** | Runs on `127.0.0.1`. API keys stay on your PC and are never committed |

## How it works

```mermaid
flowchart TD
    A[Manga page<br/>Firefox / Chrome] -->|image comes into view| B[Extension<br/>content.js]
    B -->|image + page URL| C[background.js]
    C -->|canvas / fetch with Referer / screenshot| D[Local server<br/>FastAPI :7860]

    D --> E{In cache?}
    E -->|yes| R[Return translated image]
    E -->|no| F[Windows OCR<br/>text + boxes]

    F --> G{Language}
    G -->|Auto| G1[Detect Japanese / Korean / Chinese / English]
    G -->|fixed| H
    G1 --> H[Group lines]

    H --> I[Bubble detection<br/>OpenCV: closed white area + dark outline]
    I --> J{Did OCR find text?}
    J -->|no| K[Gemini finds the text itself<br/>gemini-detect]
    J -->|yes| L[Red box + number on each bubble]

    L --> M{AI translation}
    M -->|1| M1[Gemini Flash-Lite<br/>image + bubbles + character memory]
    M -->|limit / error| M2[Groq gpt-oss]
    M -->|both fail| M3[Local NLLB]
    M1 --> N
    M2 --> N
    M3 --> N
    K --> N

    N[Casual Hindi<br/>matched to speaker gender] --> O[Erase original text<br/>bubble mask / convex hull]
    O --> P[Fit Hindi to the bubble shape<br/>Noto Sans Devanagari + raqm]
    P --> Q[(memory.json<br/>character genders)]
    P --> R
    R --> S[Extension swaps the img src]
```

## Tech stack

| Layer | Technology |
|---|---|
| Browser extension | JavaScript, Manifest V3 (Firefox 128+ / Chrome) |
| Server | Python 3.13, FastAPI, Uvicorn |
| OCR | Windows 11 built-in OCR (`winrt`) |
| Bubble detection | OpenCV |
| Translation | Google Gemini Flash-Lite, Groq (`openai/gpt-oss-120b`), Meta NLLB-200 600M (offline) |
| Rendering | Pillow + libraqm / FriBiDi, Noto Sans Devanagari |

## Project structure

```
manga-translator/
├── extension/                 # Firefox / Chrome extension
│   ├── manifest.json
│   ├── background.js          # fetches images, talks to the local server
│   ├── content.js             # finds manga images on the page, swaps in translations
│   └── popup.html / popup.js  # ON/OFF, language, "always on" and server status
├── server/
│   ├── server.py              # FastAPI app (POST /translate, GET /health)
│   ├── translator.py          # pipeline: OCR -> group -> bubbles -> translate -> render
│   ├── ocr_windows.py         # Windows OCR wrapper
│   ├── render.py              # bubble detection, text erasing and Hindi typesetting
│   ├── llm.py                 # Gemini / Groq prompts, fallback, character memory
│   ├── nllb.py                # offline NLLB fallback
│   ├── config.example.json    # copy to config.json and add your keys
│   └── fonts/
├── SETUP.bat                  # one-time setup
├── START_SERVER.bat           # start the local server
└── INSTALL_OCR_LANGUAGES.bat  # install Windows OCR language packs
```

## Installation

### Requirements

- Windows 11, for the built-in OCR
- Python 3.13 with PyTorch installed. An NVIDIA GPU is optional; it is only used by the NLLB fallback.
- Firefox 128+ or Chrome
- A free [Gemini API key](https://aistudio.google.com/apikey) and/or a free [Groq API key](https://console.groq.com/keys)

### Steps

**1. Install the OCR language packs** (run as administrator)

```bat
INSTALL_OCR_LANGUAGES.bat
```

**2. Run the setup.** This creates a virtual environment, installs the dependencies and downloads the
Devanagari font, the FriBiDi DLL needed for correct Hindi shaping, and the NLLB model.

```bat
SETUP.bat
```

**3. Add your API keys.** Copy `server\config.example.json` to `server\config.json` and paste your keys:

```json
{
  "gemini": { "api_key": "AIza..." },
  "groq":   { "api_key": "gsk_..." }
}
```

> [!IMPORTANT]
> Never share your API keys. `server/config.json` is listed in `.gitignore` and is never committed.

**4. Load the extension**

- **Chrome:** open `chrome://extensions`, enable *Developer mode*, click *Load unpacked* and select the `extension` folder.
- **Firefox:** open `about:debugging#/runtime/this-firefox`, click *Load Temporary Add-on* and select `extension/manifest.json`.
  Then open the extension popup and click **"Pehle permission do"** to grant site access.

> [!NOTE]
> Firefox removes temporary add-ons when it closes. Load it again after each restart, or sign the add-on through Mozilla to install it permanently.

## Usage

1. Start the server:
   ```bat
   START_SERVER.bat
   ```
2. Open a manga chapter in your browser.
3. Click the extension icon and switch it **ON**, or press **Alt+T**.
4. Scroll normally. Pages get an orange outline while they are being translated, then the Hindi version replaces them.

**Tips**

- Tick **"Is site par hamesha ON"** to turn the translator on automatically for that site.
- Pick a fixed language instead of **Auto** to make pages translate faster.

## Configuration

`server/config.json`

| Key | Default | Description |
|---|---|---|
| `providers` | `["gemini", "groq", "nllb"]` | Order in which translators are tried |
| `gemini.api_key` | `""` | Your Gemini key (or set the `GEMINI_API_KEY` environment variable) |
| `gemini.model` | Flash-Lite models | One model or a list. The next one is tried if a model is busy |
| `groq.api_key` | `""` | Your Groq key (or set `GROQ_API_KEY`) |
| `groq.model` | `openai/gpt-oss-120b` | Groq model name |
| `groq.vision` | `false` | Send the page image to Groq (needs a vision model) |
| `image_max_side` | `1024` | Size of the image sent to the AI. Smaller uses fewer tokens |

## Troubleshooting

| Problem | Fix |
|---|---|
| Popup says the server is down | Run `START_SERVER.bat` and keep its window open |
| Hindi matras look broken | Run `SETUP.bat` again, then `check_setup.py` should show `Hindi shaping: OK (raqm)` |
| Pages stay in English | Check the server window for errors. Gemini's free daily limit may be used up; Groq is used next |
| Wrong gender for a character | Edit that character in `server/memory.json` (`"m"` or `"f"`) |
| "model not found" in the log | Change the model name in `config.json` |

To check the setup at any time:

```bat
cd server
..\manga_env\Scripts\python.exe check_setup.py
```

For debugging, the server log shows the detected language, the provider used and each bubble's
gender (`m` / `f` / `u`). The original and translated versions of the last 40 pages are saved in `server/debug/`.

## Known limitations

- Windows OCR struggles with very stylized, italic or vertical text. Gemini reads those bubbles from the image instead.
- Bubbles on dark backgrounds, or bubbles joined to other bubbles, are not always detected.
- Text drawn directly on artwork (outside bubbles) is covered with a plain patch instead of being inpainted.
- Gemini's free tier has a daily request limit, which is set per project in Google AI Studio.

## Roadmap

- [ ] ML bubble and text detector (`comic-text-and-bubble-detector`)
- [ ] Better OCR: `manga-ocr` for Japanese, PaddleOCR for English / Korean / Chinese
- [ ] LaMa inpainting for text drawn on artwork
- [ ] Several pages per AI request to stretch the free limit
- [ ] Comic-style Devanagari fonts

## Acknowledgements

- [Google Gemini](https://ai.google.dev/), [Groq](https://groq.com/) and [Meta NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) for translation
- [Noto Sans Devanagari](https://fonts.google.com/noto/specimen/Noto+Sans+Devanagari) for the Hindi font
- Inspired by [manga-image-translator](https://github.com/zyddnys/manga-image-translator), [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator) and [comic-translate](https://github.com/ogkalu2/comic-translate)

---

<div align="center">

Made by [jitendra205saini](https://github.com/jitendra205saini)

</div>

<div align="center">

<img src="extension/icons/icon128.png" width="110" alt="Manga Translator logo">

# Manga Translator

**Read manga, manhwa and comics in natural, casual Hindi, right in your browser.**

Japanese · Korean · Chinese · English → हिन्दी

<a href="https://github.com/jitendra205saini/Manga-Translator/releases/latest"><img alt="version" src="https://img.shields.io/badge/version-v2.8.0-blue"></a>
<a href="https://www.python.org/downloads/"><img alt="python" src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white"></a>
<a href="https://github.com/jitendra205saini/Manga-Translator/blob/main/README.md#requirements"><img alt="platform" src="https://img.shields.io/badge/platform-Windows%2011-0078D6?logo=windows&logoColor=white"></a>
<a href="https://github.com/jitendra205saini/Manga-Translator/blob/main/README.md#installation"><img alt="firefox" src="https://img.shields.io/badge/Firefox-supported-FF7139?logo=firefoxbrowser&logoColor=white"></a>
<a href="https://github.com/jitendra205saini/Manga-Translator/blob/main/README.md#installation"><img alt="chrome" src="https://img.shields.io/badge/Chrome-supported-4285F4?logo=googlechrome&logoColor=white"></a>
<a href="https://github.com/jitendra205saini/Manga-Translator/blob/main/README.md#tech-stack"><img alt="ai" src="https://img.shields.io/badge/AI-Gemini%20%7C%20Groq%20%7C%20NLLB-8E75B2"></a>
<a href="https://github.com/jitendra205saini/Manga-Translator/blob/main/LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-green"></a>

[`manga`](https://github.com/topics/manga) [`manga-translator`](https://github.com/topics/manga-translator) [`manhwa`](https://github.com/topics/manhwa) [`comics`](https://github.com/topics/comics) [`translation`](https://github.com/topics/translation) [`hindi`](https://github.com/topics/hindi) [`ocr`](https://github.com/topics/ocr) [`gemini`](https://github.com/topics/gemini) [`groq`](https://github.com/topics/groq) [`llm`](https://github.com/topics/llm) [`browser-extension`](https://github.com/topics/browser-extension) [`firefox-extension`](https://github.com/topics/firefox-extension) [`chrome-extension`](https://github.com/topics/chrome-extension) [`fastapi`](https://github.com/topics/fastapi) [`python`](https://github.com/topics/python) [`opencv`](https://github.com/topics/opencv)

**English** | [Hinglish](README.hinglish.md)

[Features](#features) · [How it works](#how-it-works) · [Installation](#installation) · [Usage](#usage) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting)

</div>

---

<div align="center">

| Before | After |
|---|---|
| <img src="docs/demo_before.png" width="420"> | <img src="docs/demo_after.png" width="420"> |

*Demo page made for this README. The speaker on the left is a girl ("थक गई"), on the right a boy ("छोड़ दूंगा").*

| Webtoon: split bubble, before | After |
|---|---|
| <img src="docs/webtoon_before.png" width="420"> | <img src="docs/webtoon_after.png" width="420"> |

*Demo strip made for this README, cut into two images at the red line the way webtoon sites do. The middle bubble crosses the cut; it is read whole and drawn back across both images.*

</div>


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
| **ML bubble detection** | An RT-DETR model finds bubbles, text inside bubbles and text on artwork, in about 0.1 s per page on the GPU |
| **Clean typesetting** | Erases only the text pixels, rebuilds artwork with a manga-tuned LaMa model and fits Hindi to the bubble shape in a comic-style font, in the original text colour |
| **Fallback chain** | Gemini → Groq (Qwen vision model, also sees the image) → local NLLB, so reading never stops when a free limit runs out |
| **Firefox & Chrome** | Manifest V3 extension that works on any site, with an "Always on for this site" option |
| **Fast reading** | Prefetches upcoming pages, translates 5 pages in parallel, erases text while the AI is answering, remembers each series' language and caches results on disk |
| **Saves free quota** | Sends up to 3 pages in one AI request, so the free daily limit covers about 3 times more pages |
| **Whole chapter, in order** | Translates every page from the top of the chapter to the bottom, wherever you scroll, with a loading overlay on each page that is still waiting |
| **Keeps going in the background** | Carries on when you switch to another tab |
| **Webtoon strips** | Sites that cut a long strip into many images often split a speech bubble in two. The extension sends the strips above and below too, so a split bubble is read whole and drawn back across both images |
| **Better Korean / Chinese OCR** | PaddleOCR v5 (ONNX) reads Korean and Chinese; Japanese uses manga-ocr |
| **Next chapter ready** | When a chapter is done, the first pages of the next chapter are translated in advance |
| **Translate again** | Right-click a page and choose **Translate this page again** to skip the cache |
| **Clear limit messages** | When every free AI limit is used up, each page shows when it will resume and continues on its own; the popup shows today's usage and when Google resets it |
| **Several Gemini keys** | Add more than one key, separated by commas; a key that hits its limit rests and the next one is used |
| **Original / Hindi toggle** | Press **Alt+O** to flip every page back to the original and again to Hindi |
| **Local first** | Runs on `127.0.0.1`. API keys stay on your PC and are never committed |

## How it works

The full architecture in five diagrams: the whole system first, then each part in detail. Even more detail (page journey as a sequence, page states, caches, file list) is in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

### 1. System overview

Everything runs on your PC except the calls in the Internet box.

```mermaid
flowchart LR
    subgraph PC["Your PC"]
        direction TB
        subgraph BR["Browser: Firefox / Chrome"]
            POP["Popup<br/>switches · progress · usage · versions"]
            CS["content.js<br/>finds pages · queue · overlay<br/>webtoon strips · patches"]
            BG["background.js<br/>gets image bytes · cache check<br/>right-click menu"]
            POP <--> BG
            CS <--> BG
        end
        TRAY["Tray app<br/>starts / restarts server<br/>update check"]
        subgraph SV["Local server :47391 · Python FastAPI"]
            direction TB
            S1["1 Cache"] --> S2["2 Stitch strips"] --> S3["3 Language + OCR"] --> S4["4 Detect + group"]
            S4 --> S5["5 AI translation<br/>+ series memory"]
            S4 --> S6["6 Erase + draw Hindi"]
            S5 --> S6
        end
        DISK[("config.json · memory.json<br/>usage.json · cache/ · models/<br/>never uploaded")]
        TRAY --> SV
        SV <--> DISK
    end
    subgraph NET["Internet"]
        SITE["Manga website"]
        GEM["Google Gemini"]
        GRQ["Groq"]
        BAK["Backup translator<br/>IndicTrans2, English"]
        GH["GitHub Releases"]
    end
    BG -->|"page images"| SITE
    BG -->|"POST /translate"| S1
    POP -->|"GET /health"| SV
    S5 -->|"page image + texts"| GEM
    S5 -.->|"fallback"| GRQ
    S5 -.->|"switch on, limits used"| BAK
    TRAY -.-> GH
    S6 -->|"Hindi page + patches"| CS
```

### 2. Browser extension

```mermaid
flowchart TD
    A["Chapter opens<br/>or a page scrolls into view"] --> B["Scan all images<br/>lazy data-src / loading=lazy<br/>thin webtoon strips too"]
    B --> C["Queue, sorted top to bottom<br/>wherever you scroll<br/>overlay: कतार में…"]
    C --> D{"Free slot?<br/>max 5 pages"}
    D -->|"yes"| E["Overlay: spinner<br/>अनुवाद हो रहा है…"]
    E --> F["Find strips directly above / below<br/>same width, gap under 40 px<br/>up to ~500 px"]
    F --> G{"URL already translated?<br/>cacheOnly request"}
    G -->|"no"| H["Get image bytes, in order:<br/>1 canvas<br/>2 fetch with the site as Referer<br/>3 server downloads it<br/>4 screenshot, visible tab only"]
    H --> I["POST /translate<br/>page + strips + language<br/>Fast mode + Backup switch"]
    G -->|"yes"| R
    I --> J{"Server answer"}
    J -->|"Hindi page"| R["Swap in Hindi image<br/>paste patches onto neighbour strips<br/>Alt+O flips original / Hindi"]
    J -->|"retry_after"| L["Overlay: AI ki free limit khatam,<br/>~N min baad apne aap<br/>queue paused until then"]
    J -->|"error / 3 min timeout"| T["Retry after 15 s · 45 s · 90 s<br/>then again when the page<br/>is seen or the tab returns"]
    L --> C
    T --> C
    R --> N{"Whole chapter done?"}
    N -->|"yes"| P["Prefetch the first 4 pages<br/>of the next chapter in the background"]
    N -->|"no"| D
    X["Right-click:<br/>Translate this page again"] -->|"skip all caches"| C
    Y["Tab in background"] -.->|"keeps working,<br/>no screenshots"| D
```

### 3. Server: cache, OCR and detection

```mermaid
flowchart TD
    IN["POST /translate"] --> K1{"URL cache<br/>image URL + language"}
    K1 -->|"hit"| OUT1["Return cached page"]
    K1 -->|"miss"| K2{"Content cache<br/>MD5 of image + strips"}
    K2 -->|"hit"| OUT1
    K2 -->|"miss"| K3{"Same page<br/>already in progress?"}
    K3 -->|"yes: share its result"| OUT1
    K3 -->|"no"| ST["Stitch: 500 px of strips above<br/>+ page + 500 px below"]
    ST --> L1{"Language known?<br/>chosen in popup or<br/>locked for this series"}
    L1 -->|"no"| L2["Detect with Windows OCR<br/>Japanese → Korean → Chinese → English<br/>count kana / hangul / han / latin"]
    L2 --> L2b["Lock for the series<br/>after 2 pages agree"]
    L1 -->|"yes"| L3["Windows 11 OCR<br/>in that language"]
    L2b --> L4
    L3 --> L4{"Korean or Chinese?"}
    L4 -->|"yes"| L5["PaddleOCR v5 ONNX<br/>re-reads the page"]
    L4 -->|"no"| D1
    L5 --> D1["RT-DETR-v2 detector · GPU DirectML<br/>bubble · text in bubble · free text"]
    D1 --> D2{"Japanese?"}
    D2 -->|"yes"| D3["manga-ocr ONNX reads each box<br/>vertical text, furigana"]
    D2 -->|"no"| D4
    D3 --> D4["Group OCR lines into boxes<br/>attach each box to its bubble<br/>sort in reading order<br/>Japanese right to left"]
    D4 --> D5["Keep only bubbles whose centre<br/>is on this page; neighbours<br/>handle the rest"]
    D5 --> NX["To diagrams 4 and 5,<br/>in parallel"]
```

### 4. AI translation, limits and fallbacks

```mermaid
flowchart TD
    G["Bubbles of this page"] --> M["Add series memory, memory.json<br/>character → gender · last 8 lines"]
    M --> P["Prompt: page image + numbered texts<br/>casual Hindi like anime dubs<br/>verbs follow speaker / listener gender"]
    P --> BQ["Batcher: waits 0.6 s<br/>up to 3 pages of one series<br/>max 45 bubbles = 1 request"]
    BQ --> PC["Pacing under free limits<br/>14 / min per Gemini key · 25 / min Groq"]
    PC --> FM{"Fast mode?"}
    FM -->|"no"| GM["Gemini Flash-Lite<br/>next key in rotation"]
    FM -->|"yes"| GQ["Groq vision model"]
    GM -->|"429 limit"| KR["That key rests 60 s"]
    KR -->|"other keys left"| GM
    KR -->|"all keys resting"| GQ
    GQ -.->|"Fast mode: fails"| GM
    GM --> CK{"Answer usable?<br/>every line · no Urdu script<br/>no English left"}
    GQ --> CK
    CK -->|"no"| RA["Ask again only for the bad lines<br/>last resort: Urdu → Devanagari"]
    RA --> CK
    CK -->|"yes"| MW["Save new names, genders<br/>and lines to memory"]
    MW --> OK["Hindi lines → diagram 5"]
    GQ -->|"limit / error"| WT{"Every provider back<br/>within ~70 s?"}
    WT -->|"yes: wait, retry once"| GM
    WT -->|"no"| BK{"Backup switch on<br/>and English page?"}
    BK -->|"yes"| BT["Backup translator<br/>IndicTrans2, one request per bubble<br/>formal, not cached"]
    BT --> OK
    BK -->|"no"| NL{"NLLB installed?"}
    NL -->|"yes"| NN["NLLB-200 offline<br/>not cached"] --> OK
    NL -->|"no"| RT["Error + retry_after<br/>page waits, retries by itself"]
```

### 5. Typesetting and returning the page

```mermaid
flowchart TD
    A["Bubbles from diagram 3"] --> E["Erase text pixels inside bubbles<br/>bubble outline kept<br/>runs while waiting for the AI"]
    E --> E2{"Text on artwork?"}
    E2 -->|"yes"| LM["Text mask: letters closed inside the box<br/>dark + light, Otsu<br/>manga-tuned LaMa rebuilds the background"]
    E2 -->|"no"| FT
    LM --> FT
    H["Hindi lines from diagram 4"] --> FT["Fit Hindi to the bubble shape<br/>Baloo 2 font + raqm shaping<br/>size and line breaks to fit<br/>original text colour, e.g. red stays red"]
    FT --> CT["Cut out this page from the stitched strip"]
    CT --> SP{"A bubble reaches into<br/>a neighbour strip?"}
    SP -->|"yes"| PT["Make patches: up for the strip above,<br/>down for the strip below"]
    SP -->|"no"| SV
    PT --> SV["Save: RAM 20 pages + disk cache/<br/>URL alias for prefetch<br/>usage.json counts"]
    SV --> RET["Return Hindi page + patches<br/>content.js shows it and pastes patches"]
```

## Tech stack

| Layer | Technology |
|---|---|
| Browser extension | JavaScript, Manifest V3 (Firefox 128+ / Chrome) |
| Server | Python 3.13, FastAPI, Uvicorn |
| OCR | Windows 11 built-in OCR (`winrt`), `manga-ocr` ONNX for Japanese, PaddleOCR v5 ONNX for Korean / Chinese |
| Bubble / text detection | `ogkalu/comic-text-and-bubble-detector` (RT-DETR-v2, ONNX Runtime + DirectML), OpenCV fallback |
| Inpainting | Manga-tuned LaMa (`ogkalu/lama-manga-onnx-dynamic`), OpenCV fallback |
| Translation | Google Gemini Flash-Lite, Groq (`openai/gpt-oss-120b`), Meta NLLB-200 600M (offline) |
| Rendering | Pillow + libraqm / FriBiDi, Baloo 2 (Noto Sans Devanagari fallback) |

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
│   ├── mangaocr.py            # manga-ocr (ONNX) for Japanese
│   ├── render.py              # bubble detection, text erasing and Hindi typesetting
│   ├── llm.py                 # Gemini / Groq prompts, fallback, character memory
│   ├── nllb.py                # offline NLLB fallback
│   ├── detector.py            # ML bubble / text detector (ONNX, DirectML GPU)
│   ├── inpaint.py             # LaMa inpainting for text on artwork
│   ├── config.example.json    # copy to config.json and add your keys
│   └── fonts/
├── SETUP.bat                  # one-time setup
├── START.bat                  # one-click start
├── STOP.bat                   # stop the server
└── INSTALL_OCR_LANGUAGES.bat  # install Windows OCR language packs
```

## Installation

### Windows installer (recommended)

1. Download `MangaTranslator-Setup.exe` from the [Releases](https://github.com/jitendra205saini/Manga-Translator/releases) page and run it. No admin rights are needed.
2. The installer downloads its own Python and the AI models (about 600 MB) into `%LOCALAPPDATA%\Programs\Manga Translator`. Nothing is installed system-wide.
3. At the end, a page shows how to add the extension to Chrome, Edge or Firefox.
4. Manga Translator runs in the system tray (near the clock). Right-click the icon for status, API keys, restart, log and updates. It checks GitHub for a new version once a day and can update itself in one click.
5. The first time you start **Manga Translator**, a page opens where you paste a free Gemini (and optionally Groq) API key. You can change keys later from the extension popup.

To uninstall, use *Settings > Apps > Manga Translator > Uninstall*. The server is stopped and the whole install folder (Python, models, cache, keys) is removed; no pip or model cache is left elsewhere. Remove the browser extension from the browser itself.

To build the installer yourself, install [Inno Setup 6](https://jrsoftware.org/isinfo.php) and run `installeruild.bat`.

### Manual setup (developers)

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
Devanagari fonts, the FriBiDi DLL needed for correct Hindi shaping, the ML detector and LaMa models
(about 380 MB) and the NLLB model.

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
  Then open the extension popup and click **"Grant site access first"** to grant site access.

> [!NOTE]
> Firefox removes temporary add-ons when it closes. Load it again after each restart, or sign the add-on through Mozilla to install it permanently.

## Usage

1. Double-click `START.bat` (or the **Manga Translator** desktop shortcut it creates on first run).
   It runs setup if needed, asks for an API key if none is set, and starts the server in the background.
   Run `STOP.bat` to stop it.
2. Open a manga chapter in your browser.
3. Click the extension icon and switch it **ON**, or press **Alt+T**.
4. Scroll normally. Pages get an orange outline while they are being translated, then the Hindi version replaces them.

**Tips**

- Tick **"Always on for this site"** to turn the translator on automatically for that site.
- Pick a fixed language instead of **Auto** to make pages translate faster.
- Press **Alt+O** (or the popup button) to compare with the original page.

## Configuration

`server/config.json`

| Key | Default | Description |
|---|---|---|
| `providers` | `["gemini", "groq", "nllb"]` | Order in which translators are tried |
| `gemini.api_key` | `""` | Your Gemini key (or set the `GEMINI_API_KEY` environment variable) |
| `gemini.model` | Flash-Lite models | One model or a list. The next one is tried if a model is busy |
| `groq.api_key` | `""` | Your Groq key (or set `GROQ_API_KEY`) |
| `groq.model` | `["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]` | One model or a list, tried in order |
| `groq.vision_models` | `["qwen/qwen3.8-27b"]` | Models that also receive the page image, so gender works on the fallback too |
| `image_max_side` | `1024` | Size of the image sent to the AI. Smaller uses fewer tokens |
| `batch_pages` | `3` | Up to this many pages are translated in one AI request |
| `batch_wait` | `1.5` | Seconds to wait for more pages before sending a request |

## Troubleshooting

| Problem | Fix |
|---|---|
| Popup says the server is down | Double-click `START.bat` |
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
- LaMa inpainting runs on the CPU (about 0.3 to 1.5 s per text block on artwork), because it does not run on DirectML. It runs while the AI request is in flight, so it adds little extra time.
- Very small bubbles get small Hindi text, because Hindi is usually longer than the English it replaces.
- Gemini's free tier has a daily request limit, which is set per project in Google AI Studio.

## Roadmap

- [x] ML bubble and text detector (`comic-text-and-bubble-detector`)
- [x] LaMa inpainting for text drawn on artwork
- [x] Parallel AI requests, one page each (about 5-10 s per page)
- [x] Disk cache, so re-opened chapters cost no requests
- [x] Comic-style Devanagari font (Baloo 2)
- [x] Original / Hindi toggle (Alt+O)
- [x] Windows installer and clean uninstaller
- [x] System tray app with one-click auto-update
- [x] Re-ask for bubbles the AI left empty
- [x] API key setup page (no key needed during install)
- [x] Sound effects in bold comic style (धड़ाम!, थप!)
- [x] Today's usage and Gemini quota in the popup
- [x] `manga-ocr` (ONNX, no PyTorch) for Japanese: vertical text, furigana, stylized fonts
- [x] PaddleOCR v5 for Korean / Chinese
- [x] Signed Firefox add-on (permanent install, `installer/signed/manga-translator.xpi`)

## License

Released under the [MIT License](LICENSE). The bundled fonts (Noto Sans Devanagari, Baloo 2) are under the SIL Open Font License, and the downloaded models are under Apache-2.0.

## Acknowledgements

- [Google Gemini](https://ai.google.dev/), [Groq](https://groq.com/) and [Meta NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) for translation
- [Baloo 2](https://fonts.google.com/specimen/Baloo+2) and [Noto Sans Devanagari](https://fonts.google.com/noto/specimen/Noto+Sans+Devanagari) for the Hindi fonts
- [ogkalu/comic-text-and-bubble-detector](https://huggingface.co/ogkalu/comic-text-and-bubble-detector) for bubble and text detection
- [LaMa](https://github.com/advimman/lama), using the [manga-tuned ONNX model by ogkalu](https://huggingface.co/ogkalu/lama-manga-onnx-dynamic), for inpainting
- [comic-translate](https://github.com/ogkalu2/comic-translate) (Apache-2.0) for the text mask on artwork and the text colour detection, adapted in `inpaint.py` and `render.py`
- Inspired by [manga-image-translator](https://github.com/zyddnys/manga-image-translator), [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator) and [comic-translate](https://github.com/ogkalu2/comic-translate)

---

<div align="center">

Made by [jitendra205saini](https://github.com/jitendra205saini)

</div>

<div align="center">

# Manga Translator

**Manga, manhwa aur comics ko browser mein hi natural, casual Hindi mein padho.**

Japanese · Korean · Chinese · English → हिन्दी

![version](https://img.shields.io/badge/version-v1.0.0-blue)
![python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![platform](https://img.shields.io/badge/platform-Windows%2011-0078D6?logo=windows&logoColor=white)
![firefox](https://img.shields.io/badge/Firefox-supported-FF7139?logo=firefoxbrowser&logoColor=white)
![chrome](https://img.shields.io/badge/Chrome-supported-4285F4?logo=googlechrome&logoColor=white)
![ai](https://img.shields.io/badge/AI-Gemini%20%7C%20Groq%20%7C%20NLLB-8E75B2)

[English](README.md) | **Hinglish**

[Features](#features) · [Kaise kaam karta hai](#kaise-kaam-karta-hai) · [Installation](#installation) · [Use kaise karein](#use-kaise-karein) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting)

</div>

---

## Overview

**Manga Translator** ek free tool hai jo aapke apne PC par chalta hai. Aap manga padhte ho aur ye saath-saath
pages translate karta jaata hai. Browser extension har page ko aapke PC par chal rahe ek chhote server ko bhejta hai.
Server text padhta hai, AI se roz ki bolchaal wali Hindi mein translate karta hai, purana text mitata hai aur
Hindi wapas bubble mein likh deta hai. Page aisa lagta hai jaise pehle se Hindi mein chhapa ho.

Ye shabd-ba-shabd translation nahi karta. Ye page ki image dekhkar samajhta hai ki **kaun bol raha hai**,
isliye Hindi mein gender sahi aata hai: ladki bole to *"मैं थक गई"*, ladka bole to *"मैं थक गया"*.

## Features

| Feature | Details |
|---|---|
| **Casual Hindi** | Anime dub jaisi bolchaal wali Hindi, shuddh ya kitabi Hindi nahi |
| **Gender ke hisaab se** | Verb bolne wale aur sunne wale ke gender se match karte hain |
| **Character memory** | Har series mein characters ka gender yaad rakhta hai (`memory.json`) |
| **4 languages** | Japanese, Korean, Chinese (Simplified / Traditional) aur English, Auto-detect ke saath |
| **Bubble ke andar Hindi** | Speech bubble dhoondhta hai, purana text mitata hai aur Hindi bubble ki shape mein fit karta hai |
| **Backup chain** | Gemini → Groq → local NLLB. Free limit khatam ho to bhi padhna nahi rukta |
| **Firefox aur Chrome** | Manifest V3 extension, kisi bhi site par chalta hai, "is site par hamesha ON" option ke saath |
| **Tez padhai** | Aage ke pages pehle se translate karta hai, 3 pages ek saath, aur results cache karta hai |
| **Local first** | `127.0.0.1` par chalta hai. API keys aapke PC par hi rehti hain, kabhi commit nahi hoti |

## Kaise kaam karta hai

```mermaid
flowchart TD
    A[Manga page<br/>Firefox / Chrome] -->|image screen par aayi| B[Extension<br/>content.js]
    B -->|image + page URL| C[background.js]
    C -->|canvas / Referer ke saath fetch / screenshot| D[Local server<br/>FastAPI :7860]

    D --> E{Cache mein hai?}
    E -->|haan| R[Translated image wapas]
    E -->|nahi| F[Windows OCR<br/>text + boxes]

    F --> G{Language}
    G -->|Auto| G1[Japanese / Korean / Chinese / English pehchano]
    G -->|fixed| H
    G1 --> H[Lines ko group karo]

    H --> I[Bubble detection<br/>OpenCV: band safed area + kaali outline]
    I --> J{OCR ko text mila?}
    J -->|nahi| K[Gemini khud text dhoondhe<br/>gemini-detect]
    J -->|haan| L[Har bubble par laal box + number]

    L --> M{AI translation}
    M -->|1| M1[Gemini Flash-Lite<br/>image + bubbles + character memory]
    M -->|limit / error| M2[Groq gpt-oss]
    M -->|dono fail| M3[Local NLLB]
    M1 --> N
    M2 --> N
    M3 --> N
    K --> N

    N[Casual Hindi<br/>gender ke hisaab se] --> O[Purana text mitao<br/>bubble mask / convex hull]
    O --> P[Hindi bubble ki shape mein fit<br/>Noto Sans Devanagari + raqm]
    P --> Q[(memory.json<br/>characters ka gender)]
    P --> R
    R --> S[Extension img src badal deta hai]
```

## Tech stack

| Hissa | Technology |
|---|---|
| Browser extension | JavaScript, Manifest V3 (Firefox 128+ / Chrome) |
| Server | Python 3.13, FastAPI, Uvicorn |
| OCR | Windows 11 ka built-in OCR (`winrt`) |
| Bubble detection | OpenCV |
| Translation | Google Gemini Flash-Lite, Groq (`openai/gpt-oss-120b`), Meta NLLB-200 600M (offline) |
| Hindi likhna | Pillow + libraqm / FriBiDi, Noto Sans Devanagari |

## Project structure

```
manga-translator/
├── extension/                 # Firefox / Chrome extension
│   ├── manifest.json
│   ├── background.js          # images laata hai, local server se baat karta hai
│   ├── content.js             # page par manga images dhoondhta hai, translation lagata hai
│   └── popup.html / popup.js  # ON/OFF, language, "hamesha ON" aur server status
├── server/
│   ├── server.py              # FastAPI app (POST /translate, GET /health)
│   ├── translator.py          # pipeline: OCR -> group -> bubbles -> translate -> render
│   ├── ocr_windows.py         # Windows OCR wrapper
│   ├── render.py              # bubble detection, text mitana aur Hindi likhna
│   ├── llm.py                 # Gemini / Groq prompts, backup chain, character memory
│   ├── nllb.py                # offline NLLB backup
│   ├── config.example.json    # ise config.json naam se copy karke keys daalo
│   └── fonts/
├── SETUP.bat                  # ek baar ka setup
├── START_SERVER.bat           # local server chalao
└── INSTALL_OCR_LANGUAGES.bat  # Windows OCR language packs install
```

## Installation

### Kya chahiye

- Windows 11 (built-in OCR ke liye)
- Python 3.13, PyTorch installed ke saath. NVIDIA GPU zaroori nahi, wo sirf NLLB backup mein kaam aata hai.
- Firefox 128+ ya Chrome
- Free [Gemini API key](https://aistudio.google.com/apikey) aur/ya free [Groq API key](https://console.groq.com/keys)

### Steps

**1. OCR language packs install karo** (admin ke roop mein chalao)

```bat
INSTALL_OCR_LANGUAGES.bat
```

**2. Setup chalao.** Ye virtual environment banata hai, dependencies install karta hai, aur Hindi font,
Hindi ki matras sahi jodne wali FriBiDi DLL aur NLLB model download karta hai.

```bat
SETUP.bat
```

**3. API keys daalo.** `server\config.example.json` ko `server\config.json` naam se copy karo aur keys paste karo:

```json
{
  "gemini": { "api_key": "AIza..." },
  "groq":   { "api_key": "gsk_..." }
}
```

> [!IMPORTANT]
> API keys kisi ko mat dikhana. `server/config.json` `.gitignore` mein hai, isliye kabhi commit nahi hoti.

**4. Extension load karo**

- **Chrome:** `chrome://extensions` kholo, *Developer mode* ON karo, *Load unpacked* dabao aur `extension` folder chuno.
- **Firefox:** `about:debugging#/runtime/this-firefox` kholo, *Load Temporary Add-on* dabao aur `extension/manifest.json` chuno.
  Phir extension popup kholke **"Pehle permission do"** dabao.

> [!NOTE]
> Firefox band karne par temporary add-on hat jaata hai. Har restart ke baad dobara load karo, ya Mozilla se sign karwa ke permanently install karo.

## Use kaise karein

1. Server chalao:
   ```bat
   START_SERVER.bat
   ```
2. Browser mein manga chapter kholo.
3. Extension icon dabao aur **ON** karo, ya **Alt+T** dabao.
4. Normal scroll karo. Translate hote waqt page par narangi border dikhega, phir Hindi wala page lag jaayega.

**Tips**

- **"Is site par hamesha ON"** tick karo, us site par apne aap chalega.
- **Auto** ki jagah language fix karoge to pages jaldi translate honge.

## Configuration

`server/config.json`

| Key | Default | Matlab |
|---|---|---|
| `providers` | `["gemini", "groq", "nllb"]` | Translators kis order mein try honge |
| `gemini.api_key` | `""` | Aapki Gemini key (ya `GEMINI_API_KEY` environment variable) |
| `gemini.model` | Flash-Lite models | Ek model ya list. Ek busy ho to agla try hota hai |
| `groq.api_key` | `""` | Aapki Groq key (ya `GROQ_API_KEY`) |
| `groq.model` | `openai/gpt-oss-120b` | Groq model ka naam |
| `groq.vision` | `false` | Groq ko page image bhi bhejo (vision model chahiye) |
| `image_max_side` | `1024` | AI ko bheji image ka size. Chhota = kam tokens |

## Troubleshooting

| Dikkat | Hal |
|---|---|
| Popup mein server band dikhe | `START_SERVER.bat` chalao aur uski window khuli rakho |
| Hindi ki matras tooti dikhein | `SETUP.bat` dobara chalao, phir `check_setup.py` mein `Hindi shaping: OK (raqm)` aana chahiye |
| Pages English mein reh jaayein | Server window mein error dekho. Gemini ki free limit khatam ho sakti hai, tab Groq chalega |
| Kisi character ka gender galat | `server/memory.json` mein us character ko `"m"` ya `"f"` kar do |
| Log mein "model not found" | `config.json` mein model ka naam badlo |

Setup kabhi bhi check karne ke liye:

```bat
cd server
..\manga_env\Scripts\python.exe check_setup.py
```

Debug ke liye server log mein har page ki language, kaunsa provider chala aur har bubble ka gender
(`m` / `f` / `u`) dikhta hai. Aakhri 40 pages ka original aur translated `server/debug/` mein save hota hai.

## Kamiyan (Known limitations)

- Windows OCR bahut stylish, italic ya khade (vertical) text ko theek se nahi padhta. Aisi bubbles Gemini image se padh leta hai.
- Andhere background wali ya doosri bubble se judi bubbles hamesha pakdi nahi jaati.
- Art ke upar likha text (bubble ke bahar) saada patch se dhaka jaata hai, inpainting nahi hoti.
- Gemini ki free tier mein roz ki request limit hai, jo Google AI Studio mein har project ke liye set hoti hai.

## Roadmap

- [ ] ML bubble aur text detector (`comic-text-and-bubble-detector`)
- [ ] Behtar OCR: Japanese ke liye `manga-ocr`, English / Korean / Chinese ke liye PaddleOCR
- [ ] Art ke upar text ke liye LaMa inpainting
- [ ] Ek AI request mein kai pages, taaki free limit zyaada chale
- [ ] Comic style Devanagari fonts

## Acknowledgements

- Translation ke liye [Google Gemini](https://ai.google.dev/), [Groq](https://groq.com/) aur [Meta NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M)
- Hindi font ke liye [Noto Sans Devanagari](https://fonts.google.com/noto/specimen/Noto+Sans+Devanagari)
- Inspiration: [manga-image-translator](https://github.com/zyddnys/manga-image-translator), [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator) aur [comic-translate](https://github.com/ogkalu2/comic-translate)

---

<div align="center">

Made by [jitendra205saini](https://github.com/jitendra205saini)

</div>

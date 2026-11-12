# Manga Translator (JA / KO / ZH / EN -> casual Hindi)

![version](https://img.shields.io/badge/version-v1.0.0-blue)
![python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![platform](https://img.shields.io/badge/platform-Windows%2011-0078D6?logo=windows&logoColor=white)
![firefox](https://img.shields.io/badge/Firefox-extension-FF7139?logo=firefoxbrowser&logoColor=white)
![chrome](https://img.shields.io/badge/Chrome-extension-4285F4?logo=googlechrome&logoColor=white)
![gemini](https://img.shields.io/badge/AI-Gemini%20%7C%20Groq%20%7C%20NLLB-8E75B2)
![language](https://img.shields.io/badge/output-Hindi-FF9933)

## Description

**Manga Translator** ek free, local tool hai jo browser mein manga, manhwa aur comics padhte waqt pages ko
apne aap **casual (bolchaal wali) Hindi** mein translate karke usi image par likh deta hai, jaise page pehle se Hindi mein ho.

- Japanese, Korean, Chinese aur English pages support
- Bolne wale ke **gender ke hisaab se** Hindi ("main thak gayi" / "main thak gaya")
- Shuddh Hindi nahi, roz ki bolchaal wali Hindi
- Purana text mitakar Hindi bubble ke andar fit hoti hai
- Firefox aur Chrome dono par, kisi bhi site par

Translation Gemini se hoti hai (image dekhkar, bolne wale ke gender ke hisaab se). Gemini na chale to Groq,
aur dono na chalein to local NLLB (offline backup).

**Topics / Tags:** `manga` `manga-translator` `manhwa` `comics` `translation` `hindi` `ocr` `gemini` `groq` `llm`
`browser-extension` `firefox-extension` `chrome-extension` `fastapi` `python` `opencv`

## Kaise kaam karta hai

```mermaid
flowchart TD
    A[Manga page<br/>Firefox / Chrome] -->|image dikhi| B[Extension<br/>content.js]
    B -->|image + page URL| C[background.js]
    C -->|canvas / fetch with Referer / screenshot| D[Local server<br/>FastAPI :7860]

    D --> E{Cache mein hai?}
    E -->|haan| R[Translated image wapas]
    E -->|nahi| F[Windows OCR<br/>text + boxes]

    F --> G{Language}
    G -->|Auto| G1[Japanese / Korean / Chinese / English detect]
    G -->|fixed| H
    G1 --> H[Lines ko group karo]

    H --> I[Bubble detection<br/>OpenCV: safed band area + kaali outline]
    I --> J{OCR ko text mila?}
    J -->|nahi| K[Gemini khud text dhoondhe<br/>gemini-detect]
    J -->|haan| L[Page image par laal box + number]

    L --> M{AI translation}
    M -->|1| M1[Gemini Flash-Lite<br/>image + bubbles + character memory]
    M -->|limit / fail| M2[Groq gpt-oss]
    M -->|dono fail| M3[NLLB local]
    M1 --> N
    M2 --> N
    M3 --> N
    K --> N

    N[Casual Hindi<br/>gender ke hisaab se] --> O[Purana text mitao<br/>bubble mask / convex hull]
    O --> P[Hindi bubble ki shape mein fit<br/>Noto Sans Devanagari + raqm]
    P --> Q[(memory.json<br/>characters ka gender)]
    P --> R
    R --> S[Extension img.src badal deta hai]
```

## Ek baar
1. `INSTALL_OCR_LANGUAGES.bat` (admin)
2. `SETUP.bat`
3. API keys lo (dono free) aur `server\config.example.json` ko copy karke `server\config.json` banao, usme keys daalo:
   - Gemini: https://aistudio.google.com/apikey -> Create API key
   - Groq:   https://console.groq.com/keys -> Create API Key

   Key kisi ko mat dikhana. `config.json` git mein push nahi hoti.
4. Extension load karo:
   - **Chrome:** `chrome://extensions` -> Developer mode -> Load unpacked -> `extension` folder
   - **Firefox:** `about:debugging#/runtime/this-firefox` -> Load Temporary Add-on -> `extension\manifest.json`,
     phir popup mein "Pehle permission do" dabao

## Har baar
1. `START_SERVER.bat`
2. Manga tab par extension icon -> ON (ya **Alt+T**)
   - "Is site par hamesha ON" tick karo to us site par apne aap chalega
   - Language Auto ki jagah fix karoge to page jaldi translate hoga

Server log mein har page ki language, provider (gemini/groq/nllb), har bubble ka gender (m/f/u) aur translation dikhti hai.
Characters ka gender `server\memory.json` mein yaad rehta hai (galat ho to wahan se badal sakte ho).
Aakhri 40 pages ka original + translated `server\debug\` mein save hota hai.

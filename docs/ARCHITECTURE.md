# Architecture

This page explains how Manga Translator works inside: which parts exist, how a page travels from the browser to the server and back, and what happens when the free AI limits run out. For installing and using the tool, see the [README](../README.md).

- [1. System overview](#1-system-overview)
- [2. Life of one page](#2-life-of-one-page)
- [3. Server pipeline](#3-server-pipeline)
- [4. Webtoon strips and split bubbles](#4-webtoon-strips-and-split-bubbles)
- [5. AI providers, limits and fallbacks](#5-ai-providers-limits-and-fallbacks) (including how Gemini keys and models switch)
- [6. Page states in the extension](#6-page-states-in-the-extension)
- [7. Caching](#7-caching)
- [8. Files](#8-files)
- [9. Data on disk](#9-data-on-disk)

## 1. System overview

Everything runs on your own PC except the AI calls. The browser extension finds manga pages and sends them to a local server on `127.0.0.1:47391`. The server does OCR, detection, erasing and drawing locally, and only sends text plus a small image to the AI.

```mermaid
flowchart LR
    subgraph PC[Your PC]
        subgraph FF[Firefox / Chrome]
            CS["content.js<br/>finds pages, queue, overlay,<br/>applies results"]
            BG["background.js<br/>gets image bytes,<br/>talks to the server"]
            PU["popup<br/>on/off, language, switches,<br/>usage, versions"]
            CS <--> BG
            PU <--> BG
        end

        subgraph SRV["Local server (Python, FastAPI) :47391"]
            API["server.py<br/>/translate /health /config /setup"]
            TR["translator.py<br/>pipeline"]
            OCR["OCR<br/>Windows OCR · PaddleOCR · manga-ocr"]
            DET["detector.py<br/>RT-DETR bubbles + text"]
            RND["render.py + inpaint.py<br/>erase, LaMa, draw Hindi"]
            LLM["llm.py<br/>batcher, Gemini, Groq,<br/>limits, memory"]
            API --> TR
            TR --> OCR
            TR --> DET
            TR --> RND
            TR --> LLM
        end

        TRAY["tray.py<br/>starts / restarts server,<br/>update check"]
        DISK[("cache/ · memory.json<br/>usage.json · config.json<br/>models/")]
        TRAY -->|starts| SRV
        SRV <--> DISK
    end

    subgraph CLOUD[Internet]
        GEM[Google Gemini]
        GRQ[Groq]
        BAK["Backup translator<br/>IndicTrans2 API, English only"]
        GH["GitHub Releases<br/>new installer"]
        SITE[Manga website]
    end

    BG -->|"POST /translate"| API
    PU -->|"GET /health"| API
    BG -->|"download page image<br/>with the site as Referer"| SITE
    LLM --> GEM
    LLM -.->|fallback| GRQ
    TR -.->|"switch on + all limits used"| BAK
    TRAY -.-> GH
```

## 2. Life of one page

What happens from the moment a chapter opens until a Hindi page is on screen.

```mermaid
sequenceDiagram
    autonumber
    participant P as Manga page
    participant C as content.js
    participant B as background.js
    participant S as Server
    participant A as AI (Gemini / Groq)

    P->>C: images load (or lazy URLs found)
    C->>C: queue every page, sorted top to bottom
    C->>P: overlay "कतार में…" on waiting pages
    loop up to 5 pages at a time
        C->>P: overlay "अनुवाद हो रहा है…"
        C->>B: translate {image or src, neighbour strips}
        B->>S: URL already translated? (cacheOnly)
        alt cache hit
            S-->>B: Hindi page
        else not cached
            B->>B: fetch page + neighbour strips as PNG
            B->>S: POST /translate
            S->>S: OCR, detect, group, start erasing
            S->>A: page image + numbered texts (batched with up to 2 more pages)
            A-->>S: Hindi lines
            S->>S: draw Hindi, cut out own page + patches for neighbours
            S-->>B: Hindi page, spill patches
        end
        B-->>C: result
        C->>P: swap image, paste patches onto neighbour pages
    end
    C->>C: chapter done, prefetch first 4 pages of the next chapter
```

If the server answers with `retry_after` (every AI limit is used up), the page shows the wait time and is sent again by itself when the limit opens. See [section 6](#6-page-states-in-the-extension).

## 3. Server pipeline

`translator.translate_page()` runs these steps for every page.

```mermaid
flowchart TD
    IN["POST /translate<br/>image, url, prev/next strips, lang, fast, fresh, backup"] --> C1{"URL in cache?"}
    C1 -->|yes| OUT
    C1 -->|no| C2{"Image hash in cache<br/>or same page in progress?"}
    C2 -->|yes| OUT
    C2 -->|no| ST["Stitch neighbour strips<br/>up to 500 px above and below"]

    ST --> L1{"Language known?"}
    L1 -->|chosen in popup| O1[OCR in that language]
    L1 -->|series remembered| O1
    L1 -->|no| O2["Detect: Japanese → Korean → Chinese → English<br/>by counting kana / hangul / han / latin"]
    O2 --> V["Series vote: lock language<br/>after 2 pages agree"]
    O1 --> P1
    V --> P1
    P1{"Korean / Chinese?"} -->|yes| PAD["PaddleOCR v5 re-reads the page"]
    P1 -->|no| D
    PAD --> D["RT-DETR detector<br/>bubble · text in bubble · free text"]
    D --> J{"Japanese?"}
    J -->|yes| MO["manga-ocr reads each text box<br/>vertical text, furigana"]
    J -->|no| G
    MO --> G["Group OCR lines into boxes,<br/>attach each to its bubble,<br/>sort in reading order"]
    G --> OWN["Keep only bubbles whose centre<br/>is on this page"]

    OWN --> PAR{{"in parallel"}}
    PAR --> ER["Erase text pixels<br/>LaMa inpainting on artwork"]
    PAR --> AI["Batcher → Gemini / Groq<br/>see section 5"]
    ER --> RD
    AI --> RD["Fit Hindi into each bubble<br/>Baloo 2 + raqm shaping"]
    RD --> CUT["Cut out this page,<br/>make patches for bubbles that<br/>reach into neighbour strips"]
    CUT --> SAVE["Save to RAM + disk cache<br/>(not for backup / NLLB results)"]
    SAVE --> OUT["Return Hindi page<br/>+ spill patches"]
```

Notes:

- **OCR order.** Windows OCR runs first because it is fast and already on Windows 11. PaddleOCR replaces its result for Korean and Chinese, where it is much more accurate. manga-ocr replaces it for Japanese.
- **Erasing and AI at the same time.** Erasing does not need the translation, so it runs while waiting for the AI.
- **Reading order.** Boxes are sorted in rows from top to bottom, right to left for Japanese and left to right for everything else, so the AI sees the dialogue in order.

## 4. Webtoon strips and split bubbles

Many sites cut one long webtoon into several images. A speech bubble can then be split in two, and each half alone is unreadable. The extension finds images stacked directly above and below (same width, gap under 40 px, up to about 500 px) and sends them along.

```mermaid
flowchart LR
    subgraph Browser
        A["Image A"] --- B["Image B<br/>(being translated)"] --- C["Image C"]
    end

    subgraph Server
        S1["Stitch:<br/>bottom of A + B + top of C"] --> S2["Detect and translate<br/>the whole stitched strip"]
        S2 --> S3{"Bubble centre<br/>inside B?"}
        S3 -->|yes| S4["B draws it,<br/>even the part outside B"]
        S3 -->|no| S5["Skip: A or C<br/>will draw it"]
        S4 --> S6["Return B<br/>+ patch for A (up)<br/>+ patch for C (down)"]
    end

    B --> S1
    S6 --> R["content.js pastes each patch<br/>onto A or C, only inside<br/>that bubble's box"]
```

Every bubble is owned by exactly one image (the one holding its centre), so it is translated once and never drawn twice. Patches can arrive before or after the neighbour itself is translated; `content.js` keeps them and redraws the neighbour whenever either side changes. Thin strips between pages (40 px and up) are translated too, because a bubble can sit right on them.

## 5. AI providers, limits and fallbacks

```mermaid
flowchart TD
    J["Page ready for AI"] --> BQ["Batcher<br/>waits 0.6 s, joins up to 3 pages<br/>of the same series, max 45 bubbles"]
    BQ --> F{"Fast mode?"}
    F -->|no| G1
    F -->|yes| Q1

    G1["Gemini<br/>4 keys × 5 models, see below"] --> GR{"OK?"}
    GR -->|yes| CHK
    GR -->|"every key resting"| Q1

    Q1["Groq vision model"] --> QR{"OK?"}
    QR -->|yes| CHK
    QR -->|no| W{"All providers resting<br/>less than ~70 s?"}
    W -->|yes| WAIT["Wait, retry once"] --> G1
    W -->|no| FB

    CHK{"Answer usable?"} -->|"Urdu script / still English /<br/>lines missing"| RE["Ask again for those lines"] --> CHK
    CHK -->|yes| DONE["Hindi lines → render"]

    FB{"Backup switch on<br/>and page is English?"} -->|yes| BK["Backup translator<br/>one request per bubble"] --> DONE2["Render, not cached"]
    FB -->|no| NL{"NLLB installed?"}
    NL -->|yes| NLLB["Local NLLB-200"] --> DONE2
    NL -->|no| LIM["Error with retry_after<br/>→ page waits and retries itself"]
```

The diagram shows the normal order. With **Fast mode** on, the order flips: Groq is tried first and Gemini is its backup.

Rate pacing keeps requests under the free limits: about 14 requests per minute per Gemini key and 25 per minute for Groq. The daily Gemini count in the popup follows Google's day, which resets at midnight Pacific time (around 1:30 PM in India).

Each request also carries the series memory: character names with their gender and fixed Hindi spelling, and the last 8 translated lines, so verbs keep the right gender and names are spelled the same on every page.

### How Gemini keys and models switch

Google's free limit is per project **and** model. The server keeps a state for every key (ready, resting for a minute, done for the day, not valid) and treats Gemini as available while any key is ready.

```mermaid
flowchart TD
    S["Request ready"] --> A{"Any key ready?"}
    A -->|no| GQ["Groq until the first key reopens"]
    A -->|yes| K["First ready key<br/>Key 1 → 2 → 3 → 4"]
    K --> L["Models in order, last good one first<br/>3.5-flash-lite · flash-lite-latest · 3.1-flash-lite<br/>3.5-flash · flash-latest"]
    L --> R{"Answer"}
    R -->|200| OK["Hindi lines, key count +1"]
    R -->|"429"| NM{"Another model left?"}
    NM -->|yes| L
    NM -->|no| T{"Every 429 per day?"}
    T -->|yes| DAY["Key rests until Google's daily reset"]
    T -->|no| MIN["Key rests 60 s"]
    R -->|"400 / 403 invalid key"| BAD["Key skipped 1 h, red on setup page"]
    R -->|404| GONE["Model dropped"] --> NM
    DAY --> NK{"Next key ready?"}
    MIN --> NK
    BAD --> NK
    NK -->|yes| K
    NK -->|no| GQ
    SAVE["Keys saved on setup page"] -.->|"old block cleared"| A
```

The **Check Gemini keys** button on the setup page asks Google whether each key is valid (a model list call, which does not use any translation quota).

## 6. Page states in the extension

```mermaid
stateDiagram-v2
    [*] --> Waiting: page found
    Waiting --> Working: free slot (max 5)
    Working --> Done: Hindi image received
    Working --> Limit: retry_after
    Working --> Retry: error or 3 min timeout
    Limit --> Waiting: limit opens
    Retry --> Waiting: after 15 s / 45 s / 90 s
    Retry --> GaveUp: failed 3 times
    GaveUp --> Waiting: page scrolled into view or tab shown again
    Done --> Waiting: right-click, Translate this page again
    Done --> Done: patch from a neighbour pasted
```

| State | Overlay on the page |
|---|---|
| Waiting | "कतार में…" (light shade) |
| Working | spinner + "अनुवाद हो रहा है…" (dark shade) |
| Limit | "AI ki free limit khatam — ~N min baad apne aap" |
| Done | no overlay, Hindi image shown (Alt+O shows the original) |

Pages are always taken top to bottom, wherever you scroll. A hidden tab keeps working, but never takes screenshots, because a screenshot of a hidden tab would capture the wrong page.

## 7. Caching

| Level | Key | Where | Purpose |
|---|---|---|---|
| URL | image URL + language | RAM + `server/cache/` | next chapter prefetch: the page is not even downloaded again |
| Content | MD5 of the image (+ neighbour strips) + language | RAM (20 pages) + `server/cache/` | same page from any URL |
| In progress | same as content | RAM | two requests for one page share one translation |

Results from the backup translator and from NLLB are not cached, so the AI translates those pages properly later. "Translate this page again" skips all caches.

## 8. Files

| File | Role |
|---|---|
| `extension/content.js` | Finds pages (including lazy ones), queue in reading order, overlays, webtoon neighbours and patches, retries, next-chapter prefetch, Alt+O |
| `extension/background.js` | Downloads images with the right Referer, screenshot fallback, talks to the server, right-click menu |
| `extension/popup.html`, `popup.js` | On/off, language, Fast mode, Backup switch, progress, usage, versions |
| `server/server.py` | FastAPI app: `/translate`, `/health`, `/config`, `/setup`; only extensions and the setup page may call it |
| `server/translator.py` | The pipeline in section 3, stitching, ownership, caches |
| `server/ocr_windows.py` | Windows 11 OCR |
| `server/paddle_ocr.py` | PaddleOCR v5 (ONNX) for Korean and Chinese |
| `server/mangaocr.py` | manga-ocr (ONNX) for Japanese |
| `server/detector.py` | RT-DETR-v2 bubble and text detector (ONNX, DirectML GPU) |
| `server/inpaint.py` | Manga-tuned LaMa inpainting (ONNX) and text masks |
| `server/render.py` | Erasing, fitting and drawing Hindi text |
| `server/llm.py` | Prompt, batcher, Gemini / Groq calls, key rotation, pacing, limits, series memory, usage |
| `server/backup_api.py` | Backup translator (English only) |
| `server/nllb.py` | Optional offline NLLB-200 |
| `server/tray.py`, `run.py` | Tray icon, starting and restarting the server, update check |
| `installer/` | Inno Setup script, install / stop scripts, signed Firefox add-on |

## 9. Data on disk

All inside the install folder (`%LOCALAPPDATA%\Programs\Manga Translator\server`). None of it is uploaded to GitHub.

| File | Contents |
|---|---|
| `config.json` | API keys and settings |
| `memory.json` | Per series: character genders, Hindi name spellings and recent lines |
| `usage.json` | Today's page and request counts |
| `cache/` | Translated pages |
| `models/` | Detector, LaMa, manga-ocr and PaddleOCR models |
| `server.log` | Server log, for troubleshooting |

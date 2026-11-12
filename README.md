# Manga Translator (JA / KO / ZH / EN -> casual Hindi)

Translation Gemini (image dekhkar, gender ke hisaab se) se hoti hai, Gemini na chale to Groq,
aur dono na chalein to local NLLB (offline backup).

## Ek baar
1. INSTALL_OCR_LANGUAGES.bat (admin)
2. SETUP.bat
3. API keys lo (dono free) aur `server\config.json` mein daalo:
   - Gemini: https://aistudio.google.com/apikey -> Create API key
   - Groq:   https://console.groq.com/keys -> Create API Key
   ```json
   "gemini": {"api_key": "AIza...", "model": "gemini-flash-lite-latest"},
   "groq":   {"api_key": "gsk_...", "model": "llama-3.3-70b-versatile", "vision": false}
   ```
   Key kisi ko mat dikhana.
4. chrome://extensions -> Developer mode -> Load unpacked -> `extension` folder
   (pehle se load hai to Reload dabao)

## Har baar
1. START_SERVER.bat
2. Manga tab par extension icon -> ON (ya Alt+T)
   - "Is site par hamesha ON" tick karo to us site par apne aap chalega
   - Language Auto ki jagah fix karoge to page jaldi translate hoga

Server log mein har page ki language, provider (gemini/groq/nllb), har bubble ka gender (m/f/u) aur translation dikhti hai.
Characters ka gender `server\memory.json` mein yaad rehta hai (galat ho to wahan se badal sakte ho).

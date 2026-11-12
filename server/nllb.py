# NLLB-200 distilled 600M -> Hindi. GPU par fp16, warna CPU fp32.
import time

try:  # torch optional hai: installer wale setup mein nahi hota, tab sirf Gemini/Groq
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    AVAILABLE = True
except Exception:
    torch = None
    AVAILABLE = False

MODEL_NAME = "facebook/nllb-200-distilled-600M"
TARGET_LANG = "hin_Deva"
NLLB_CODES = {
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "zh_hans": "zho_Hans",
    "zh_hant": "zho_Hant",
    "en": "eng_Latn",
}

DEVICE = ("cuda" if torch.cuda.is_available() else "cpu") if AVAILABLE else "cpu"
DTYPE = (torch.float16 if DEVICE == "cuda" else torch.float32) if AVAILABLE else None

_tokenizer = None
_model = None


def load_model():
    global _tokenizer, _model
    if not AVAILABLE:
        raise RuntimeError("NLLB ke liye torch install nahi hai")
    if _model is None:
        t = time.time()
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME, torch_dtype=DTYPE).to(DEVICE)
        _model.eval()
        print(f"[nllb] loaded on {DEVICE} ({DTYPE}) in {time.time() - t:.1f}s")
    return _tokenizer, _model


def translate_texts(texts, src_lang, batch_size=16):
    if not texts:
        return []
    tokenizer, model = load_model()
    tokenizer.src_lang = NLLB_CODES.get(src_lang, src_lang)
    target_id = tokenizer.convert_tokens_to_ids(TARGET_LANG)

    outputs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        inputs = tokenizer(batch, return_tensors="pt", padding=True,
                           truncation=True, max_length=256).to(DEVICE)
        with torch.no_grad():
            generated = model.generate(**inputs, forced_bos_token_id=target_id,
                                       num_beams=2, max_length=256)
        outputs.extend(tokenizer.batch_decode(generated, skip_special_tokens=True))
    return outputs


if __name__ == "__main__":
    load_model()
    print(translate_texts(["Hello, how are you?"], "en"))
    print(translate_texts(["お前は誰だ？"], "ja"))
    print(translate_texts(["너 누구야?"], "ko"))
    print(translate_texts(["你是谁？"], "zh_hans"))

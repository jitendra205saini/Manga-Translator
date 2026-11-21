import threading

# DirectML (GPU) par do onnxruntime model ek saath chale to crash (c0000005): detector, PaddleOCR,
# manga-ocr aur LaMa sab yahi ek lock lete hain, GPU par ek samay mein ek hi model
LOCK = threading.RLock()

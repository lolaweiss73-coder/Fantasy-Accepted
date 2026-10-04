import os
import numpy as np
import soundfile as sf
from kokoro import KPipeline

TEXT = """Hi, I’m Morin.
Fantasy Accepted is a place where you can share a wish that other people may be able to help you make real.
Your wish should be something another person can actually help with.
For example: I want a musician to write a song for my mother.
Or: I want someone to teach me piano.
A wish like, I want to win the lottery, doesn’t really fit, because nobody here can control the result.
You don’t need to know exactly how to make your wish happen.
Just tell me what you want, and I’ll do my AI magic to help make it happen.
You can speak or write to me in any language. I’ll understand you. My spoken voice is always in English.
So, what do you wish for?"""

os.makedirs("kokoro_samples", exist_ok=True)
pipeline = KPipeline(lang_code="a")
for voice in ("af_heart", "af_bella", "af_nicole"):
    chunks = []
    for _, _, audio in pipeline(TEXT, voice=voice, speed=0.95):
        chunks.append(np.asarray(audio, dtype=np.float32))
        chunks.append(np.zeros(int(24000 * 0.12), dtype=np.float32))
    waveform = np.concatenate(chunks)
    wav = f"kokoro_samples/{voice}.wav"
    mp3 = f"kokoro_samples/{voice}.mp3"
    sf.write(wav, waveform, 24000)
    rc = os.system(f'ffmpeg -hide_banner -loglevel error -y -i "{wav}" -codec:a libmp3lame -qscale:a 2 "{mp3}"')
    if rc != 0:
        raise SystemExit(rc)
    os.remove(wav)
    print("generated", mp3)

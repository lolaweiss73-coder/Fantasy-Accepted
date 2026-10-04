import os
import numpy as np
import soundfile as sf
from kokoro import KPipeline

GENERAL = [
"Hi, I’m Morin.",
"Fantasy Accepted is a place where you can share a wish that other people may be able to help you make real.",
"Your wish should be something another person can actually help with.",
"For example: I want a musician to write a song for my mother.",
"Or: I want someone to teach me piano.",
"A wish like, I want to win the lottery, doesn’t really fit, because nobody here can control the result.",
"You don’t need to know exactly how to make your wish happen.",
"Just tell me what you want, and I’ll do my AI magic to help make it happen.",
"You can speak or write to me in any language. I’ll understand you. My spoken voice is always in English.",
"So, what do you wish for?"
]

ADULT = [
"Hi, I’m Morin.",
"Fantasy Accepted eighteen-plus is a place where adults can share a fantasy that other adults may be able to help make real.",
"Your fantasy should involve something another person can actually choose to take part in or help with.",
"Tell me what you want in your own words. I can help clarify the people, roles and details that matter.",
"You can speak or write to me in any language. I’ll understand you. My spoken voice is always in English.",
"Nothing is published until you review it.",
"So, what do you wish for?"
]

os.makedirs("static/morin_voice", exist_ok=True)
pipeline = KPipeline(lang_code="a")

def make(text, out):
    chunks = []
    for _, _, audio in pipeline(text, voice="af_heart", speed=0.95):
        chunks.append(np.asarray(audio, dtype=np.float32))
    waveform = np.concatenate(chunks)
    wav = out + ".wav"
    sf.write(wav, waveform, 24000)
    rc = os.system(f'ffmpeg -hide_banner -loglevel error -y -i "{wav}" -codec:a libmp3lame -qscale:a 2 "{out}"')
    if rc != 0:
        raise SystemExit(rc)
    os.remove(wav)

for mode, lines in (("general", GENERAL), ("adult", ADULT)):
    for i, text in enumerate(lines):
        out = f"static/morin_voice/{mode}_{i}.mp3"
        make(text, out)
        print("generated", out)


EXTRAS = {
"how_general": "For example, you can say: I want someone to sing a song to my ex. I can understand that you are organizing the wish, identify the performer as the missing person, and ask only the questions that actually affect the match.",
"how_adult": "For example, tell me the fantasy in your own words. I can identify the people or roles that are missing, ask only the questions that affect the match, and prepare a draft for you to review before anything is published.",
"avi_prompt": "Avi may have left a personal message for you. What are the initials of your name?",
"annette_confirm": "Just to make sure, are you Annette Smirnoff?",
"no_personal_message": "I did not find a personal message for those initials, but the explanation of the site is open to everyone.",
"annette_message_1": "Annette, Avi asked me to tell you something personal. Behind the unusual choices you see here is a long-term entrepreneurial vision, not just another website.",
"annette_message_2": "He is working on several ideas that he believes could change entire fields, including scent technology for movies and virtual reality, and the E L project for products designed to last an extremely long time.",
"annette_message_3": "He also thinks a lot about the economic impact of artificial intelligence and ways to reduce the cost of living and give people more security and meaning. He asked me to tell you that his ambitions are much bigger than his current situation, and that is exactly the gap he intends to close.",
"annette_no": "Then the personal message probably was not meant for you. At least now I know not to identify people from two letters.",
}

for key, text in EXTRAS.items():
    out = f"static/morin_voice/extra_{key}.mp3"
    make(text, out)
    print("generated", out)

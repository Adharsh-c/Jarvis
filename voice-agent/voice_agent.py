"""JARVIS V6 desktop voice agent.

Modes:
- Hotkey/online fallback: existing SpeechRecognition Google STT.
- Offline STT: optional Vosk model via JARVIS_VOSK_MODEL. This keeps audio
  recognition local after the model has been downloaded to the PC.

The agent can only ask JARVIS for a response. It never executes remote shell
commands itself.
"""
import json, os, time
import httpx
import pyttsx3
from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
import speech_recognition as sr
try:
    import keyboard
except ImportError:
    keyboard = None

SERVER=os.getenv('JARVIS_SERVER','http://127.0.0.1:8000').rstrip('/')
TOKEN=os.getenv('JARVIS_VOICE_TOKEN','')
WAKE_PHRASE=os.getenv('JARVIS_WAKE_PHRASE','hey jarvis').lower().strip()
HOTKEY=os.getenv('JARVIS_HOTKEY','ctrl+alt+j')
LANGUAGE=os.getenv('JARVIS_STT_LANGUAGE','en-IN')
LISTEN_TIMEOUT=float(os.getenv('JARVIS_LISTEN_TIMEOUT','4'))
PHRASE_LIMIT=float(os.getenv('JARVIS_PHRASE_LIMIT','8'))
VOSK_MODEL=os.getenv('JARVIS_VOSK_MODEL','').strip()
OFFLINE_ONLY=os.getenv('JARVIS_OFFLINE_ONLY','false').lower()=='true'

def speak(text, engine):
    clean=(text or '').replace('```','').strip()
    if clean: engine.say(clean); engine.runAndWait()

def ask_jarvis(message):
    if not TOKEN: raise RuntimeError('JARVIS_VOICE_TOKEN is not configured')
    with httpx.Client(timeout=120) as client:
        r=client.post(f'{SERVER}/api/voice/chat',json={'token':TOKEN,'message':message})
        r.raise_for_status(); return r.json().get('reply','No reply returned.')

def google_recognize(recognizer,microphone):
    with microphone as source:
        try: audio=recognizer.listen(source,timeout=LISTEN_TIMEOUT,phrase_time_limit=PHRASE_LIMIT)
        except sr.WaitTimeoutError: return ''
    try:
        text=recognizer.recognize_google(audio,language=LANGUAGE); print('You:',text); return text.strip()
    except (sr.UnknownValueError,sr.RequestError) as exc:
        print('Speech recognition:',exc); return ''

def command_flow(recognizer,microphone,tts):
    text=google_recognize(recognizer,microphone)
    if not text:return
    try:
        reply=ask_jarvis(text); print('JARVIS:',reply); speak(reply,tts)
    except Exception as exc: print('JARVIS error:',exc); speak('I could not connect to JARVIS.',tts)

def offline_available():
    return bool(VOSK_MODEL and os.path.isdir(VOSK_MODEL))

def offline_loop(tts):
    try:
        import pyaudio
        from vosk import Model, KaldiRecognizer
    except ImportError as exc:
        raise RuntimeError('Offline mode needs vosk and pyaudio. Install voice-agent/requirements-offline.txt') from exc
    model=Model(VOSK_MODEL); rec=KaldiRecognizer(model,16000)
    pa=pyaudio.PyAudio(); stream=pa.open(format=pyaudio.paInt16,channels=1,rate=16000,input=True,frames_per_buffer=8000); stream.start_stream()
    print(f'JARVIS V6 OFFLINE voice ready. Wake phrase: "{WAKE_PHRASE}"')
    try:
        while True:
            data=stream.read(4000,exception_on_overflow=False)
            if rec.AcceptWaveform(data):
                text=json.loads(rec.Result()).get('text','').strip()
                if not text: continue
                print('You:',text)
                if WAKE_PHRASE in text:
                    command=text.split(WAKE_PHRASE,1)[1].strip()
                    if command:
                        try: reply=ask_jarvis(command); print('JARVIS:',reply); speak(reply,tts)
                        except Exception as exc: print('JARVIS error:',exc); speak('I could not connect to JARVIS.',tts)
                    else: speak('I am listening.',tts)
    finally:
        stream.stop_stream(); stream.close(); pa.terminate()

def online_loop(recognizer,microphone,tts):
    hotkey_event=False
    if keyboard:
        def trigger():
            nonlocal hotkey_event; hotkey_event=True
        keyboard.add_hotkey(HOTKEY,trigger); print('Global hotkey enabled.')
    try:
        with microphone as source: recognizer.adjust_for_ambient_noise(source,duration=0.8)
    except Exception as exc: print('Microphone calibration warning:',exc)
    print(f'JARVIS V6 online voice ready. Wake phrase: "{WAKE_PHRASE}" | Hotkey: {HOTKEY}')
    try:
        while True:
            if hotkey_event:
                hotkey_event=False; speak('Yes?',tts); command_flow(recognizer,microphone,tts); continue
            text=google_recognize(recognizer,microphone)
            if text and WAKE_PHRASE in text.lower():
                command=text.lower().split(WAKE_PHRASE,1)[1].strip(' ,.!?')
                if command:
                    try: reply=ask_jarvis(command); print('JARVIS:',reply); speak(reply,tts)
                    except Exception as exc: print('JARVIS error:',exc); speak('I could not connect to JARVIS.',tts)
                else: speak('I am listening.',tts); command_flow(recognizer,microphone,tts)
    finally:
        if keyboard:
            try: keyboard.unhook_all_hotkeys()
            except Exception: pass

def main():
    if not TOKEN: raise SystemExit('Set JARVIS_VOICE_TOKEN in voice-agent/.env first')
    tts=pyttsx3.init(); tts.setProperty('rate',int(os.getenv('JARVIS_TTS_RATE','175')))
    if OFFLINE_ONLY and not offline_available(): raise SystemExit('JARVIS_OFFLINE_ONLY=true but JARVIS_VOSK_MODEL is missing or invalid')
    if offline_available():
        try: offline_loop(tts); return
        except Exception as exc:
            print('Offline voice unavailable:',exc)
            if OFFLINE_ONLY: raise
    recognizer=sr.Recognizer(); recognizer.dynamic_energy_threshold=True; microphone=sr.Microphone()
    online_loop(recognizer,microphone,tts)

if __name__=='__main__': main()

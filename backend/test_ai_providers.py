from app.config import settings
from app.ai.providers import provider_status, generate_reply

print("JARVIS V9 Ollama connection test")
print("Configured provider:")
for item in provider_status():
    print(f"- {item['provider']}: {'enabled' if item['configured'] else 'disabled'} | {item['model']} | {item['local'] and 'local'}")
print(f"AI provider: {settings.ai_provider}")
print(f"Auto order: {settings.ai_auto_order}")
print(f"Ollama URL: {settings.ollama_base_url}")

try:
    result = generate_reply("Reply exactly: JARVIS V9 Ollama connection successful.", use_search=False, provider="ollama")
    print(f"SUCCESS: {result['provider']} / {result['model']}")
    print(result['reply'])
except Exception as exc:
    print(f"TEST FAILED: {type(exc).__name__}: {exc}")
    raise

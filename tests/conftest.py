import os

# los tests nunca escriben ni restauran la sesión del operador (data/sessions/current.json)
os.environ.setdefault("COPILOT_SESSIONS__PERSIST", "false")

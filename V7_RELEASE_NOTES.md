# JARVIS V7 — Desktop Control + VS Code

V7 adds a permission-based Windows desktop control gateway. The paired laptop agent can execute only allowlisted actions: launch VS Code/Explorer/Notepad/Calculator, open a workspace or file in VS Code, report system info, and open HTTPS URLs after explicit approval. It never accepts arbitrary shell commands.

## Start
1. Copy `.env.example` to `backend/.env` and use the V9 Ollama configuration.
2. Keep `AGENT_PAIRING_TOKEN` set to a long random value.
3. Install backend requirements and start FastAPI.
4. In another PowerShell window: `cd laptop-agent`, create/activate a Python 3.12 venv, `pip install -r requirements.txt`, set `JARVIS_AGENT_TOKEN` to the same pairing token, and run `python agent.py`.
5. Open the dashboard and use **Desktop Control**.

## Safety
The browser can request named desktop actions only. Sensitive external navigation is queued as an approval. The agent uses fixed executable names and workspace path checks; no arbitrary PowerShell/cmd execution is added.

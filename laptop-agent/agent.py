"""JARVIS V7 Windows desktop control agent.

The agent is intentionally allowlisted: it can launch a small set of apps,
open files/workspaces in VS Code, and open HTTPS URLs only when the server
has approved the action. It never accepts arbitrary shell commands.
"""
import os, platform, subprocess, time, webbrowser, uuid
from pathlib import Path
import httpx

SERVER=os.getenv("JARVIS_SERVER","http://127.0.0.1:8000").rstrip("/")
TOKEN=os.getenv("JARVIS_AGENT_TOKEN","")
AGENT_ID=os.getenv("JARVIS_AGENT_ID","local-laptop")
WORKSPACE=Path(os.getenv("JARVIS_WORKSPACE", str(Path.cwd().parent / "workspace"))).resolve()
POLL_SECONDS=float(os.getenv("JARVIS_AGENT_POLL_SECONDS","2"))

APP_COMMANDS={
    "vscode": ["code"],
    "explorer": ["explorer.exe"],
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
}

def safe_workspace_path(rel: str):
    p=(WORKSPACE/rel).resolve()
    if p != WORKSPACE and WORKSPACE not in p.parents:
        raise ValueError("Path escapes the JARVIS workspace")
    return p

def run_action(action,args):
    if action=="launch_app":
        app=str(args.get("app","")).lower()
        cmd=APP_COMMANDS.get(app)
        if not cmd: raise ValueError("App is not allowlisted")
        subprocess.Popen(cmd, cwd=str(WORKSPACE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Launched {app}."
    if action=="open_workspace":
        p=safe_workspace_path(str(args.get("path","")))
        p.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["code", str(p)], cwd=str(WORKSPACE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened workspace in VS Code: {p}"
    if action=="open_file":
        p=safe_workspace_path(str(args.get("path","")))
        if not p.is_file(): raise FileNotFoundError(f"File not found: {p}")
        subprocess.Popen(["code", "--reuse-window", str(p)], cwd=str(WORKSPACE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened file in VS Code: {p.relative_to(WORKSPACE)}"
    if action=="open_url":
        url=str(args.get("url",""))
        if not url.lower().startswith("https://"): raise ValueError("Only HTTPS URLs are allowed")
        webbrowser.open(url, new=2)
        return f"Opened HTTPS URL: {url}"
    if action=="system_info":
        return f"Host={platform.node()} | OS={platform.platform()} | Python={platform.python_version()}"
    if action=="capture_screen":
        # Explicitly approval-gated by the server. Screenshot is stored only inside
        # the configured JARVIS workspace and never uploaded by this agent.
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise RuntimeError("Pillow is required for capture_screen") from exc
        out_dir = WORKSPACE / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"screen-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.png"
        path = out_dir / filename
        ImageGrab.grab().save(path)
        return f"Screenshot captured: screenshots/{filename}"
    raise ValueError("Unsupported desktop action")

def main():
    if not TOKEN: raise SystemExit("Set JARVIS_AGENT_TOKEN first")
    headers={"X-Agent-Token":TOKEN}
    with httpx.Client(timeout=20, headers=headers) as client:
        r=client.post(f"{SERVER}/api/laptop/pair",json={"token":TOKEN}); r.raise_for_status()
        print("JARVIS V7 desktop agent paired:",r.json())
        while True:
            try:
                r=client.post(f"{SERVER}/api/laptop/heartbeat",json={"agent_id":AGENT_ID,"hostname":platform.node(),"platform":platform.platform()})
                if r.is_success:
                    for item in client.get(f"{SERVER}/api/laptop/actions/pending",params={"agent_id":AGENT_ID}).json():
                        try:
                            out=run_action(item["action"], item.get("args",{}))
                            body={"status":"ok","output":out}
                        except Exception as exc:
                            body={"status":"error","error":f"{type(exc).__name__}: {exc}"}
                        client.post(f"{SERVER}/api/laptop/actions/{item['id']}/result",json=body)
                        print(f"Action #{item['id']}: {body.get('status')}")
                time.sleep(POLL_SECONDS)
            except Exception as exc:
                print("Agent connection error:",type(exc).__name__,exc)
                time.sleep(max(POLL_SECONDS,3))

if __name__=="__main__": main()

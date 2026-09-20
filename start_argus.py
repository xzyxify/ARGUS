"""Double-click launcher: local server and the default browser."""
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
import os
import json
import uvicorn

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
URL = 'http://127.0.0.1:8000'

def open_when_ready():
    for _ in range(60):
        try:
            with urllib.request.urlopen(URL + '/api/health', timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(URL)
                    return
        except OSError:
            time.sleep(1)

if __name__ == '__main__':
    try:
        with urllib.request.urlopen(URL + '/api/health', timeout=2) as response:
            existing = json.load(response)
        if {m['id'] for m in existing.get('models', [])} == {'antacil','betadine','fahtalaijone','gaviscon','yoki'}:
            webbrowser.open(URL)
            raise SystemExit(0)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run('app:app', host='127.0.0.1', port=8000, log_level='info')

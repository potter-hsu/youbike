import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

URL = 'https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json'

BASE = Path(__file__).parent.parent
RAW_DIR = BASE / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

response = requests.get(URL, timeout=10)
response.raise_for_status()

now = datetime.now(ZoneInfo("Asia/Taipei"))
filename = f"youbike_{now.strftime('%Y%m%dT%H%M%z')}.json"
path = RAW_DIR / filename

with open(path, "w", encoding="utf-8") as f:
    f.write(response.text)

print(f"{now.isoformat()} saved {path.name} ({len(response.text)} bytes)")
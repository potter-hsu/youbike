import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

response = requests.get('https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json', timeout=10)
response.raise_for_status()

now = datetime.now(ZoneInfo("Asia/Taipei"))

with open(f"data/raw/youbike_{now.strftime('%Y%m%dT%H%M+0800')}.json", "w", encoding="utf-8") as f:
    f.write(response.text)
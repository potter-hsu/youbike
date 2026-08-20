import requests, time, os
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from dotenv import load_dotenv
from load_weather import main
load_dotenv()
API_KEY = os.getenv("CWA_API_KEY")


def fetch_with_retry(dataset_id):
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{dataset_id}?Authorization={API_KEY}"
    for i in range(3):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            response.json()
            return response
        
        except (requests.exceptions.Timeout, 
                requests.exceptions.ConnectionError, 
                requests.exceptions.JSONDecodeError):
            if i != 2:
                time.sleep(2**i)
            else:
                raise

BASE = Path(__file__).parent.parent
RAW_DIR = BASE / "data" / "weather"
RAW_DIR.mkdir(parents=True, exist_ok=True)
for dataset_id, prefix in [("O-A0002-001", "rain"), ("O-A0003-001", "obs")]:
    response = fetch_with_retry(dataset_id)
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    filename = f"{prefix}_{now.strftime('%Y%m%dT%H%M%z')}.json"
    path = RAW_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(response.text)
    print(f"{now.isoformat()} saved {path.name} ({len(response.text)} bytes)")
main()
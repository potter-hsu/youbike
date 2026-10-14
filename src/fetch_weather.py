import requests, time, os
import ssl, certifi
from requests.adapters import HTTPAdapter
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from dotenv import load_dotenv
from load_weather import main as load_main
load_dotenv()
API_KEY = os.getenv("CWA_API_KEY")
class CwaAdapter(HTTPAdapter):
    """氣象署憑證鏈缺 Subject Key Identifier，
    Python 3.13+ 的 VERIFY_X509_STRICT 會拒絕。
    僅放寬 RFC 合規檢查，憑證鏈仍完整驗證。"""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context(cafile=certifi.where())
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount("https://opendata.cwa.gov.tw", CwaAdapter())

def fetch_with_retry(dataset_id):
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{dataset_id}?Authorization={API_KEY}"
    for i in range(3):
        try:
            response = session.get(url, timeout=10)
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


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(ZoneInfo("Asia/Taipei"))

    # 兩個資料集都抓成功才寫檔：load_weather 以 rain/obs 成對處理，
    # 只存其中一個會留下孤兒檔（9/26 實測：一個孤兒 rain 檔讓之後 99 次執行都記一筆 skip）
    responses = {prefix: fetch_with_retry(dataset_id)
                 for dataset_id, prefix in [("O-A0002-001", "rain"), ("O-A0003-001", "obs")]}

    for prefix, response in responses.items():
        filename = f"{prefix}_{now.strftime('%Y%m%dT%H%M%z')}.json"
        path = RAW_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"{now.isoformat()} saved {path.name} ({len(response.text)} bytes)")
    load_main()


if __name__ == "__main__":
    main()

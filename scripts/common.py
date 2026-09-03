"""
フィットイージー西浦和店 備品在庫管理システム 共通処理

GitHub Actions から呼び出される check_counts.py / check_checkouts.py が
共通で使う関数をまとめたモジュールです。
"""
import json
import os
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS_PATH = os.path.join(REPO_ROOT, "data", "items.json")
STAFF_PATH = os.path.join(REPO_ROOT, "data", "staff.json")
COUNTS_DIR = os.path.join(REPO_ROOT, "data", "counts")
CHECKOUTS_DIR = os.path.join(REPO_ROOT, "data", "checkouts")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_items():
    """items.json を読み込み、id -> item dict のマップを返す"""
    data = load_json(ITEMS_PATH)
    return {item["id"]: item for item in data["items"]}


def list_data_files(directory):
    """directory 内の .json ファイル一覧を、ファイル名(=時系列順になる想定)でソートして返す"""
    if not os.path.isdir(directory):
        return []
    files = [f for f in os.listdir(directory) if f.endswith(".json")]
    files.sort()
    return [os.path.join(directory, f) for f in files]


def parse_iso(ts):
    """ISO8601文字列をdatetimeに変換(タイムゾーンが無ければJSTとみなす)"""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt


def load_all_counts():
    """counts/*.json を全て読み込み、(datetime, dict) のリストを時系列昇順で返す"""
    result = []
    for path in list_data_files(COUNTS_DIR):
        data = load_json(path)
        ts = parse_iso(f"{data['date']}T{data.get('time', '00:00')}:00")
        result.append((ts, data, path))
    result.sort(key=lambda x: x[0])
    return result


def load_all_checkouts():
    """checkouts/*.json を全て読み込み、(datetime, dict) のリストを時系列昇順で返す"""
    result = []
    for path in list_data_files(CHECKOUTS_DIR):
        data = load_json(path)
        ts = parse_iso(data["timestamp"])
        result.append((ts, data, path))
    result.sort(key=lambda x: x[0])
    return result


def sum_checkouts_between(checkouts, start_ts, end_ts, item_id):
    """start_ts(排他) 〜 end_ts(包含) の間の、指定item_idの持ち出し数量合計"""
    total = 0
    for ts, data, _path in checkouts:
        if data.get("item_id") != item_id:
            continue
        if start_ts is not None and ts <= start_ts:
            continue
        if ts > end_ts:
            continue
        total += data.get("qty", 0)
    return total


def send_chatwork_message(message):
    """Chatworkにメッセージを送信する。環境変数 CHATWORK_API_TOKEN / CHATWORK_ROOM_ID が
    無い場合は標準出力に出すだけにして、テスト・ローカル実行でもエラーにならないようにする。"""
    token = os.environ.get("CHATWORK_API_TOKEN")
    room_id = os.environ.get("CHATWORK_ROOM_ID")

    print("---- Chatwork送信メッセージ ----")
    print(message)
    print("--------------------------------")

    if not token or not room_id:
        print("::warning::CHATWORK_API_TOKEN または CHATWORK_ROOM_ID が未設定のため、"
              "Chatworkへの送信はスキップしました(ログ出力のみ)。")
        return False

    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    data = f"body={urllib.parse.quote(message)}".encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("X-ChatWorkToken", token)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("Chatworkへの通知を送信しました。")
        return True
    except urllib.error.HTTPError as e:
        print(f"::error::Chatwork送信に失敗しました(HTTP {e.code}): {e.read()}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"::error::Chatwork送信に失敗しました: {e}")
        return False

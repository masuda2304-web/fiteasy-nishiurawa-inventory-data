"""
持ち出し登録(data/checkouts/*.json)が追加されたときに実行するスクリプト。

直近の閉店時カウントを基準に「現在の推定在庫」を計算し、
今回の持ち出しによって最低在庫数を下回った(=閾値をまたいだ)瞬間だけ
Chatworkに即時通知する。既に閾値を下回っている状態での連続通知は行わない
(通知が毎回鳴ってうるさくならないようにするため)。

GitHub Actions からは、このpushで新規追加された checkouts ファイルのパスを
1つ以上引数で渡す想定。引数が無い場合は最新の1件のみを対象にする。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    load_items,
    load_all_counts,
    load_all_checkouts,
    send_chatwork_message,
)


def latest_count_before(all_counts, item_id, ts):
    """ts以前(かつ以下)で、item_idのカウント値を持つ最新のカウントを返す (ts, qty) or None"""
    best = None
    for c_ts, data, _path in all_counts:
        if c_ts > ts:
            continue
        qty = data.get("counts", {}).get(item_id)
        if qty is None:
            continue
        if best is None or c_ts > best[0]:
            best = (c_ts, qty)
    return best


def estimate_stock(all_counts, all_checkouts, item_id, as_of_ts, exclude_paths=()):
    """as_of_ts時点での推定在庫 = 直近カウント値 - (そのカウント以降・as_of_ts以前の持ち出し合計)"""
    base = latest_count_before(all_counts, item_id, as_of_ts)
    if base is None:
        return None
    base_ts, base_qty = base
    total = 0
    for ts, data, path in all_checkouts:
        if data.get("item_id") != item_id:
            continue
        if path in exclude_paths:
            continue
        if ts <= base_ts or ts > as_of_ts:
            continue
        total += data.get("qty", 0)
    return base_qty - total


def process_one(path, items, all_counts, all_checkouts):
    from common import load_json, parse_iso

    data = load_json(path)
    item_id = data.get("item_id")
    qty = data.get("qty", 0)
    ts = parse_iso(data["timestamp"])
    item = items.get(item_id)
    if item is None:
        print(f"::warning::items.json に存在しないitem_idです: {item_id} ({path})")
        return None

    min_stock = item.get("min_stock")
    if min_stock is None:
        return None

    after = estimate_stock(all_counts, all_checkouts, item_id, ts)
    before = estimate_stock(all_counts, all_checkouts, item_id, ts, exclude_paths={path})

    if after is None or before is None:
        print(f"{item['name']}: 基準となる閉店時カウントがまだ無いため、閾値判定をスキップしました。")
        return None

    crossed = before >= min_stock and after < min_stock
    print(
        f"{item['name']}: 持ち出し前推定 {before}{item['unit']} → "
        f"持ち出し後推定 {after}{item['unit']} (最低在庫 {min_stock}{item['unit']}) "
        f"crossed={crossed}"
    )

    if not crossed:
        return None

    lines = [
        "[info][title]備品 持ち出しによる在庫アラート[/title]",
        f"品目: {item['name']}",
        f"今回の持ち出し: {qty}{item['unit']}(登録者: {data.get('staff', '不明')})",
        f"持ち出し後の推定在庫: {after}{item['unit']}(最低在庫 {min_stock}{item['unit']})",
        "※この数値は直近の閉店時カウントからの推定です。閉店時の実カウントで最終確認されます。",
        "[/info]",
    ]
    return "\n".join(lines)


def main():
    target_paths = [p for p in sys.argv[1:] if p]
    items = load_items()
    all_counts = load_all_counts()
    all_checkouts = load_all_checkouts()

    if not target_paths:
        if not all_checkouts:
            print("checkouts データがありません。終了します。")
            return
        target_paths = [all_checkouts[-1][2]]

    for path in target_paths:
        message = process_one(os.path.abspath(path), items, all_counts, all_checkouts)
        if message:
            send_chatwork_message(message)


if __name__ == "__main__":
    main()

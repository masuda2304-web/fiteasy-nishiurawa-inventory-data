"""
閉店時の在庫個数入力(data/counts/*.json)が追加されたときに実行するスクリプト。

行うこと:
  1. 最低在庫数を下回っている品目を検出
  2. 前回カウント以降の持ち出しログ(data/checkouts/*.json)の合計と比較し、
     「前回カウント数 - 持ち出し合計」が「今回のカウント数」と一致しない品目(数量不一致)を検出
  3. 上記のいずれかがあればChatworkに通知

GitHub Actions からは、このpushで新規追加された counts ファイルのパスを引数で渡す想定。
引数が無い場合は、存在する中で最新の1件のみを対象にする(手動実行・テスト用)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    REPO_ROOT,
    load_items,
    load_all_counts,
    load_all_checkouts,
    sum_checkouts_between,
    send_chatwork_message,
)


def build_report(target_path=None):
    items = load_items()
    all_counts = load_all_counts()  # [(ts, data, path), ...] 昇順
    all_checkouts = load_all_checkouts()

    if not all_counts:
        print("counts データがありません。終了します。")
        return None

    if target_path:
        target_abs = os.path.abspath(target_path)
        matches = [c for c in all_counts if os.path.abspath(c[2]) == target_abs]
        if not matches:
            print(f"::warning::指定されたファイルが counts の中に見つかりません: {target_path}")
            current = all_counts[-1]
        else:
            current = matches[0]
    else:
        current = all_counts[-1]

    current_ts, current_data, current_path = current

    # 同じ current より前の(タイムスタンプが古い)最新カウントを「前回カウント」とする
    previous = None
    for ts, data, path in all_counts:
        if ts < current_ts:
            if previous is None or ts > previous[0]:
                previous = (ts, data, path)

    low_stock = []
    mismatches = []

    for item_id, qty in current_data.get("counts", {}).items():
        item = items.get(item_id)
        item_name = item["name"] if item else item_id
        unit = item["unit"] if item else ""
        min_stock = item.get("min_stock") if item else None

        if min_stock is not None and qty < min_stock:
            low_stock.append((item_name, qty, unit, min_stock))

        if item and item.get("requires_qr") and previous is not None:
            prev_qty = previous[1].get("counts", {}).get(item_id)
            if prev_qty is not None:
                checkout_sum = sum_checkouts_between(
                    all_checkouts, previous[0], current_ts, item_id
                )
                expected = prev_qty - checkout_sum
                if expected != qty:
                    mismatches.append(
                        (item_name, unit, prev_qty, checkout_sum, expected, qty)
                    )

    lines = []
    lines.append("[info][title]備品在庫チェック結果[/title]")
    lines.append(f"日付: {current_data.get('date')} {current_data.get('time', '')}")
    lines.append(f"入力担当: {current_data.get('staff', '(未入力)')}")
    lines.append("")

    if low_stock:
        lines.append("■ 最低在庫数を下回っている品目")
        for name, qty, unit, min_stock in low_stock:
            lines.append(f"・{name}: 現在 {qty}{unit} (最低在庫 {min_stock}{unit})")
        lines.append("")

    if mismatches:
        lines.append("■ 個数が合わない品目(前回カウント - 持ち出し合計 ≠ 今回カウント)")
        for name, unit, prev_qty, checkout_sum, expected, qty in mismatches:
            lines.append(
                f"・{name}: 前回{prev_qty}{unit} − 持ち出し{checkout_sum}{unit} "
                f"= 想定{expected}{unit} / 実際{qty}{unit}(差 {qty - expected:+d}{unit})"
            )
        lines.append("")

    lines.append("[/info]")

    should_notify = bool(low_stock or mismatches)
    message = "\n".join(lines)
    return should_notify, message, low_stock, mismatches


def main():
    target_path = sys.argv[1] if len(sys.argv) > 1 else None
    result = build_report(target_path)
    if result is None:
        return
    should_notify, message, low_stock, mismatches = result

    if should_notify:
        send_chatwork_message(message)
    else:
        print("在庫不足・個数不一致はありませんでした。Chatworkへの通知はしません。")
        print(message)


if __name__ == "__main__":
    main()

"""
備品個数チェックスクリプト(新仕様)

毎日2回(12:30〜13:00 / 18:30〜19:30)の在庫個数入力が登録されるたびに
GitHub Actionsから呼び出されます。やること:

  1. 今回登録された個数が、品目ごとの最低在庫数を下回っていないかチェック
     → 下回っていれば「発注連絡」としてリストアップ
  2. 今回登録された個数が、前回登録した個数から2個以上増減していないかチェック
     → 増減していれば「要確認」としてリストアップ
  3. 上記の有無にかかわらず、結果をまとめて必ず店長のChatworkに通知する

使い方:
  python check_counts.py path/to/data/counts/xxxxx.json
"""
import os
import sys

from common import load_all_counts, load_items, send_chatwork_message

BIG_CHANGE_THRESHOLD = 2  # これ以上の増減で「要確認」とする


def find_target_and_previous(target_path):
    """全カウント履歴から、対象ファイルのデータと、その直前のカウントのデータを取得する"""
    all_counts = load_all_counts()  # [(timestamp, data, path), ...] 時系列昇順
    target_name = os.path.basename(target_path)

    target = None
    target_index = None
    for i, (_ts, data, path) in enumerate(all_counts):
        if os.path.basename(path) == target_name:
            target = data
            target_index = i
            break

    if target is None:
        raise SystemExit(f"対象ファイルがカウント履歴の中に見つかりませんでした: {target_path}")

    previous = all_counts[target_index - 1][1] if target_index > 0 else None
    return target, previous


def build_message(target, previous, items):
    date = target.get("date", "-")
    time = target.get("time", "-")
    staff = target.get("staff", "-")
    counts = target.get("counts", {})
    prev_counts = (previous or {}).get("counts", {})

    low_stock_lines = []
    big_change_lines = []

    for item_id, qty in counts.items():
        item = items.get(item_id)
        name = item["name"] if item else item_id
        unit = item["unit"] if item else ""
        min_stock = item.get("min_stock") if item else None

        if min_stock is not None and qty < min_stock:
            low_stock_lines.append(f"・{name}: 現在 {qty}{unit}(最低在庫 {min_stock}{unit})")

        if item_id in prev_counts:
            diff = qty - prev_counts[item_id]
            if abs(diff) >= BIG_CHANGE_THRESHOLD:
                sign = "+" if diff > 0 else ""
                big_change_lines.append(
                    f"・{name}: 前回 {prev_counts[item_id]}{unit} → 今回 {qty}{unit}(差 {sign}{diff}{unit})"
                )

    lines = []
    lines.append("[info][title]備品個数チェック結果[/title]")
    lines.append(f"登録日時: {date} {time}")
    lines.append(f"担当: {staff}")
    lines.append("")

    if low_stock_lines:
        lines.append("■ 最低在庫数を下回りました(発注をお願いします)")
        lines.extend(low_stock_lines)
        lines.append("")

    if big_change_lines:
        lines.append("■ 前回から2個以上の増減がありました(ご確認ください)")
        lines.extend(big_change_lines)
        lines.append("")

    if not low_stock_lines and not big_change_lines:
        lines.append("特に異常はありませんでした。")
        lines.append("")

    lines.append("[/info]")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2 or not sys.argv[1]:
        raise SystemExit("対象ファイルのパスを引数で指定してください。")

    target_path = sys.argv[1]
    items = load_items()
    target, previous = find_target_and_previous(target_path)
    message = build_message(target, previous, items)
    send_chatwork_message(message)


if __name__ == "__main__":
    main()

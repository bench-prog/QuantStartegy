"""
批量回测脚本：通过 subprocess 依次运行所有 OHLCV-only 策略，汇总结果。
每个策略在独立进程中运行，避免 NautilusTrader Rust core 日志重复初始化冲突。
用法: python batch_backtest.py
"""

import argparse
import json
import subprocess
import sys


STRATEGY_KEYS = [
    ("ema_cross", "EMA Cross"),
    ("donchian_breakout", "Donchian Breakout"),
    ("roc_momentum", "ROC Momentum"),
    ("supertrend", "SuperTrend"),
    ("bollinger_reversion", "Bollinger Reversion"),
    ("grid_trading", "Grid Trading"),
    ("rsi_reversion", "RSI Reversion"),
    ("atr_trailing_stop", "ATR Trailing Stop"),
    ("keltner_breakout", "Keltner Breakout"),
    ("engulfing_pattern", "Engulfing Pattern"),
]

# 跨品种策略需要多个 instrument，暂不纳入
#   - pair_trading, multi_asset_momentum, volume_price_momentum


def main():
    parser = argparse.ArgumentParser(description="批量回测所有 OHLCV-only 策略")
    parser.add_argument("--metrics", action="store_true", help="启用 InfluxDB 监控导出")
    args = parser.parse_args()

    results = []
    total = len(STRATEGY_KEYS)

    for i, (key, name) in enumerate(STRATEGY_KEYS, 1):
        print(f"[{i}/{total}] Running {name} ...", end=" ", flush=True)
        cmd = [sys.executable, "backtest_one.py", key, name]
        if args.metrics:
            cmd.append("--metrics")
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            print(f"FAILED (exit {proc.returncode})")
            print(f"  stderr: {proc.stderr[:300]}")
            results.append({"name": name, "status": "crashed", "note": proc.stderr[:200]})
            continue

        # 取最后一行 JSON 输出（前面可能有 WARNING 日志）
        lines = proc.stdout.strip().splitlines()
        json_line = None
        for line in reversed(lines):
            try:
                json.loads(line)
                json_line = line
                break
            except json.JSONDecodeError:
                continue

        if json_line is None:
            print(f"FAILED (no JSON output)")
            results.append({"name": name, "status": "error", "note": proc.stdout[-300:]})
            continue

        r = json.loads(json_line)
        results.append(r)
        if r["status"] == "ok":
            pnl_str = f"PnL={r['pnl']:,.2f} USD" if r["pnl"] is not None else "PnL=N/A"
            print(f"done ({r['elapsed']}s) | orders={r['orders']}, positions={r['positions']}, {pnl_str}")
        else:
            print(f"FAILED: {r.get('note', 'unknown')[:120]}")

    # ── 汇总 ──
    print("\n" + "=" * 95)
    print(f"{'Strategy':<24} {'Bars':>8} {'Orders':>8} {'Positions':>10} {'PnL (USD)':>16} {'Time(s)':>8} {'Status':>10}")
    print("=" * 95)
    for r in results:
        status = r.get("status", "ok")
        if status == "ok":
            bars = r.get("bars", 0)
            orders = r.get("orders", 0)
            positions = r.get("positions", 0)
            pnl = r.get("pnl")
            pnl_str = f"{pnl:>16,.2f}" if pnl is not None else "             N/A"
            elapsed = r.get("elapsed", 0)
            print(f"{r['name']:<24} {bars:>8} {orders:>8} {positions:>10} {pnl_str} {elapsed:>8.1f}s {'OK':>10}")
        else:
            note = r.get("note", "")[:60]
            print(f"{r['name']:<24} {'-':>8} {'-':>8} {'-':>10} {'-':>16} {'-':>8}s {'FAILED':>10}  {note}")

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    print(f"\n{ok_count}/{total} strategies completed successfully.")


if __name__ == "__main__":
    main()

"""vol.1（ローカル版）のエントリーポイント。

使い方:
  python run.py                     # 1回実行
  python run.py --loop              # 定期実行（interval_minutes 間隔）
  python run.py --log-level DEBUG   # ログレベル指定
  python run.py --config ./config.yaml
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

# `python run.py` でも `python local/run.py` でも core/ を解決できるようにする
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(_PROJECT_ROOT))

from core.converter import convert_folder, convert_single, move_to_done  # noqa: E402

__all__ = ["main", "process_input_dir"]


def load_config(path: Path) -> dict:
  with path.open("r", encoding="utf-8") as f:
    return yaml.safe_load(f) or {}


def setup_logging(logs_dir: Path, level: str) -> None:
  logs_dir.mkdir(parents=True, exist_ok=True)
  today = datetime.now().strftime("%Y-%m-%d")
  log_file = logs_dir / f"{today}.log"

  logging.basicConfig(
    level=getattr(logging, level.upper(), logging.INFO),
    format="[%(asctime)s] %(levelname)-5s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
      logging.FileHandler(log_file, encoding="utf-8"),
      logging.StreamHandler(sys.stdout),
    ],
    force=True,
  )


def process_input_dir(
  input_dir: Path,
  output_dir: Path,
  done_dir: Path,
  *,
  hybrid: str | None,
  use_struct_tree: bool,
  add_timestamp: bool,
) -> int:
  """input_dir 配下のPDF/サブフォルダを変換し、done へ退避した件数を返す。"""
  processed = 0
  for item in sorted(input_dir.iterdir()):
    if item.name.startswith("."):
      continue
    try:
      if item.is_file() and item.suffix.lower() == ".pdf":
        convert_single(
          item, output_dir, hybrid=hybrid, use_struct_tree=use_struct_tree
        )
        move_to_done(item, done_dir, add_timestamp=add_timestamp)
        processed += 1
      elif item.is_dir():
        pdfs = sorted(item.glob("*.pdf"))
        if not pdfs:
          logging.info("スキップ（PDFなし）: %s", item)
          continue
        convert_folder(
          pdfs, item.name, output_dir,
          hybrid=hybrid, use_struct_tree=use_struct_tree,
        )
        move_to_done(item, done_dir, add_timestamp=add_timestamp)
        processed += 1
    except Exception:
      logging.exception("処理失敗: %s", item)
  return processed


def _run_once(paths: dict[str, Path], conv: dict, done_conf: dict) -> None:
  logging.info("処理開始")
  count = process_input_dir(
    paths["input"], paths["output"], paths["done"],
    hybrid=conv.get("hybrid") or None,
    use_struct_tree=bool(conv.get("use_struct_tree", True)),
    add_timestamp=bool(done_conf.get("add_timestamp", True)),
  )
  logging.info("処理完了 (%d件)", count)


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
    description="PDF → Markdown 変換パイプライン（ローカル版）"
  )
  parser.add_argument(
    "--config", type=Path,
    default=Path(__file__).parent / "config.yaml",
    help="config.yaml へのパス",
  )
  parser.add_argument("--log-level", default="INFO")
  parser.add_argument(
    "--loop", action="store_true",
    help="schedule.interval_minutes 間隔で繰り返し実行する",
  )
  args = parser.parse_args(argv)

  config = load_config(args.config)
  base = args.config.resolve().parent
  paths = {k: (base / v).resolve() for k, v in config.get("paths", {}).items()}
  for key in ("input", "output", "done", "logs"):
    paths.setdefault(key, base / key)
    paths[key].mkdir(parents=True, exist_ok=True)

  setup_logging(paths["logs"], args.log_level)

  conv = config.get("conversion", {}) or {}
  done_conf = config.get("done", {}) or {}
  schedule = config.get("schedule", {}) or {}
  interval = max(1, int(schedule.get("interval_minutes", 60))) * 60

  if args.loop:
    logging.info("loopモード開始（interval=%d分）", interval // 60)
    while True:
      _run_once(paths, conv, done_conf)
      time.sleep(interval)
  _run_once(paths, conv, done_conf)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

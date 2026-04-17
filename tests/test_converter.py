"""`core.converter` の外部依存なしテスト。

`opendataloader_pdf.convert` はモック化し、move_to_done とファイル連結の振る舞いを検証する。
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _stub_opendataloader(monkeypatch):
  """`opendataloader_pdf` を最小限のスタブで差し替える。"""
  calls: list[dict] = []

  def convert(**kwargs):
    calls.append(kwargs)
    out_dir = Path(kwargs["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in kwargs["input_path"]:
      stem = Path(p).stem
      (out_dir / f"{stem}.md").write_text(f"# {stem}\n", encoding="utf-8")

  module = types.ModuleType("opendataloader_pdf")
  module.convert = convert  # type: ignore[attr-defined]
  module._calls = calls  # type: ignore[attr-defined]
  monkeypatch.setitem(sys.modules, "opendataloader_pdf", module)
  return module


def test_convert_single_writes_markdown(tmp_path):
  from core.converter import convert_single

  pdf = tmp_path / "sample.pdf"
  pdf.write_bytes(b"%PDF-1.4\n")
  out = tmp_path / "output"

  result = convert_single(pdf, out)

  assert result == out / "sample.md"
  assert result.read_text(encoding="utf-8") == "# sample\n"


def test_convert_folder_concatenates_in_sorted_order(tmp_path):
  from core.converter import convert_folder

  src = tmp_path / "bundle"
  src.mkdir()
  (src / "02_body.pdf").write_bytes(b"%PDF-1.4\n")
  (src / "01_intro.pdf").write_bytes(b"%PDF-1.4\n")
  out = tmp_path / "output"

  pdfs = sorted(src.glob("*.pdf"))
  result = convert_folder(pdfs, src.name, out)

  assert result == out / "bundle.md"
  text = result.read_text(encoding="utf-8")
  assert text.index("01_intro") < text.index("02_body")


def test_move_to_done_appends_timestamp_for_file(tmp_path):
  from core.converter import move_to_done

  pdf = tmp_path / "doc.pdf"
  pdf.write_bytes(b"%PDF-1.4\n")
  done = tmp_path / "done"

  dst = move_to_done(pdf, done)

  assert not pdf.exists()
  assert dst.parent == done
  assert dst.name.startswith("doc_") and dst.suffix == ".pdf"


def test_move_to_done_handles_directory(tmp_path):
  from core.converter import move_to_done

  folder = tmp_path / "bundle"
  folder.mkdir()
  (folder / "a.pdf").write_bytes(b"")
  done = tmp_path / "done"

  dst = move_to_done(folder, done)

  assert not folder.exists()
  assert dst.is_dir()
  assert dst.name.startswith("bundle_")

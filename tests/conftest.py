# tests/conftest.py
"""pytest 用設定: バックエンド（Django プロジェクト）を import できるようにする。"""
import sys
from pathlib import Path

# stock-app/backend を sys.path に追加（stockapp パッケージを参照可能にする）
BACKEND_DIR = Path(__file__).resolve().parents[1] / "stock-app" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

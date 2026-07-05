# tests/test_api.py
"""
FastAPI の TestClient を使った簡易テスト例。
実際のエンドポイントやモデルに合わせて調整してください。
"""

import pytest
from fastapi.testclient import TestClient

# ← ここをあなたのアプリケーションモジュール名に書き換えてください
try:
    from app.main import app
except Exception as e:   # pragma: no cover
    raise ImportError("app.main をインポートできません。パスを確認してください。") from e

client = TestClient(app)

# ---------------------------------------------------------------------------
# ユーザー関連のサンプルテスト（実際のエンドポイントに合わせて調整）
# ---------------------------------------------------------------------------

def test_get_users():
    """GET /api/v1/users/ が 200 を返し、リストを返すことを確認する。"""
    response = client.get("/api/v1/users/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:  # 空でも OK
        user = data[0]
        assert "id" in user
        assert "email" in user


def test_create_user():
    """POST /api/v1/users/ が 201 を返し、作成したユーザー情報を返すことを確認する。"""
    payload = {"email": "test@example.com", "password": "secret"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == payload["email"]
    assert "id" in data


def test_get_user_not_found():
    """存在しないユーザー ID に対して 404 を返すことを確認する。"""
    response = client.get("/api/v1/users/9999")
    assert response.status_code == 404

# 必ず .clinerules を確認し、開発ルールを守るようにしてください

- [x] フロントエンドが期待する `/api/stocks/<symbol>` エンドポイントを実装
- [x] 移動平均取得の URL をフロントエンドと合わせる（`/api/moving_average/<symbol>/`）
+ [x] バックエンド側で CORS 設定が必要なら追加
- [x] API が正しく動作するか Postman 等で確認（直叩き / vite dev プロキシ / nginx 経由の 3 経路で検証済み）
- [ ] フロント側のチャート描画と移動平均表示を統合し、UI を微調整

## Issue #19 E2E 統合修正（対応済み）

- [x] テストを pytest-django + DRF で実行可能に書き換え（`tests/test_api.py`、`pytest.ini`、`requirements-dev.txt` 追加）
- [x] vite プロキシ修正（`/api` プレフィックス除去（rewrite）を削除、ターゲットを `http://localhost:8000` に変更）
- [x] `db` サービスを backend の SQLite ファイル（`./backend/db`）と共有し常駐化（named volume 廃止）
- [x] frontend の nginx に `/api/` → backend へプロキシする設定を追加（`frontend/nginx.conf`、Dockerfile 更新）
- [x] backend 起動時に `migrate` を実行するよう Dockerfile を更新
- [x] 初期マイグレーションを追加（`stockapp/app/migrations/0001_initial.py`）
- [x] `INSTALLED_APPS` に `django.contrib.auth` を追加（DRF の無名ユーザー生成に必要。未追加時は全 API が 500）
- [x] URL 解決順を修正（`/api/stocks/<symbol>/` が router の `{pk}` に先取りされ 500 になる問題）
- [x] README.md を実プロジェクト向けに書き換え（起動手順・API リファレンス・アーキテクチャ）

## PR #20 レビュー対応（Issue #19 への追加対応）

- [x] `moving_average` の `days` バリデーション（非整数・1 未満は 400）+ テスト追加
- [x] README の UTF-16 問題: 旧 README（base ブランチ）を UTF-8 に変換し、PR の diff をテキスト化
- [x] `.dockerignore` 追加（backend: `db/*.db` 等 / frontend: `node_modules/`・`dist/`）
- [x] `DEBUG` / `SECRET_KEY` / `ALLOWED_HOSTS` を環境変数から（既定は安全側）
- [x] 汎用 router 廃止 → 関数ビューでルートを明示（到達不能 detail ルート排除）
- [x] `unique_together`（非推奨）→ `UniqueConstraint` 制約
- [x] CI（GitHub Actions で pytest 実行）追加
- [x] `pytest.ini` の `pythonpath` と `tests/conftest.py` の重複を解消（ini の `pythonpath` に統一。conftest 読み込みは pytest-django 初期化より遅いため）


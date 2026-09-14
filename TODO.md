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

## Issue #40 タートル戦略数値エリア（ホバー時点の値）

- [x] タートル戦略 ON 時に、現在値エリアと区切りの入った独立した数値エリアを表示（固定情報パネル内の独立セクション）
- [x] タートル戦略 OFF 時にはエリアが非表示
- [x] 表示項目: 日付 / DC20 (エントリーライン) / DC10 (手仕舞いライン) / N (ATR) / トレーリングストップ / BUY・EXIT シグナル（ホバー中のインデックス時点の値）
- [x] 値がクロスヘア（axisPointer）のホバーに追従し、グリッド外出時は直近の値を保持（現在値パネルと同一の dataIndex マッピング）
- [x] データ取得（銘柄切替・再取得）時に古い値をリセット
- [x] 現在値パネルのドラッグ・リサイズクランプ等への影響がない（スクリプト側のドラッグ・クランプコードは不変更）
- [x] `npm run typecheck` / `npm run build` / ユニットテストが通る

## Issue #44 タートル戦略: ブレイク日選択 + 買い増し / EXIT 計画表示

- [x] `computeUnitShares` の数式変更: `floor(口座資金 × 0.01 / N)`（1 株あたりの価値 = 1 固定のため買値を掛けない）
- [x] `computeTurtlePlan` 実装: ブレイク日以降の買い増し (P2/P3/P4、毎日その日の N で再計算) と EXIT（買値 − 2N または DC10 下抜けの初回到達、ストップ優先）をシミュレート
- [x] `computeTurtlePlan` のユニットテスト追加（同日複数買い増し / ストップ EXIT / DC10 EXIT / ブレイク日欠落・買値不正 / ATR 不足）
- [x] タートルパネルにブレイク日セレクタ追加（BUY シグナル日のみ候補、既定は最新の BUY 日、手動選択後は上書きしない、銘柄変更でリセット）
- [x] ブレイク日選択時に買値をその日終値へ自動設定（買値の手動入力優先）
- [x] 情報パネルの表に買い増し計画 (P2/P3/P4) と EXIT 計画（到達日・目標価格 / 理由・終値）を追加
- [x] チャートに買い増し (◇ 紫) / 計画 EXIT (■ 緑) マーカーを追加（指標 BUY/EXIT マーカーとは区別）
- [x] `npm test`（29 件パス）/ `npm run typecheck` / `npm run build` を実行
- [x] `docs/turtle-strategy.md` と `README.md` を更新

## Issue #46 BUY/EXIT シグナルマーカーをローソク足と重ならない位置に表示

- [x] BUY マーカーをローソク足の高値より上側に配置（従来は終値でローソク足と重なっていた）
- [x] EXIT マーカーをローソク足の安値より下側に配置（従来は終値でローソク足と重なっていた）
- [x] ローソク足からの隙間を当日 ATR の半分に（ATR 未算出時はレンジ幅の 2% にフォールバック）
- [x] チャート表示エリア（y 軸自動レンジ）の上下限を超えそうな場合はレンジ内にクランプ（ローソク足との重なりを許容）
- [x] マーカーが既存の軸スケールを変えないこと（ローソク足 + Donchian バンド + markLine 値で構成されるレンジ内に収める）
- [x] `npm test`（29 件パス）/ `npm run typecheck` / `npm run build` を実行
- [x] `docs/turtle-strategy.md` と `README.md` を更新

## Issue #63 タートル BUY ブレイクの OBV 検証

- [x] `src/utils/obv.ts`: OBV 検証ヘルパー追加（純粋関数・ルックアヘッドなし）
  - `computeObv20DayHighs`: OBV 20 日間最高値更新日（厳密 `>`、履歴 20 日未満は対象外）
  - `evaluateBreakoutObv` / `computeBreakoutObvChecks`: BUY シグナル日の ①②③ 条件評価（単日 / 全日 Map）
- [x] `src/utils/obv.test.ts`: ユニットテスト追加（① 境界 / ② 20 日境界 / ③ 直前ウィンドウ / ブレイク日自身の OBV 更新を除外 / 全有効ケース / Map API）
- [x] タートルパネル: 選択ブレイク日の OBV 検証行（①②③ を ✓/✗、全有効時は ★）
- [x] 固定情報パネル: BUY シグナル日ホバー時に ①②③ カラーチップ（全有効で ★）
- [x] チャート: ①②③ 全条件を満たすブレイクの BUY マーカーを金色三角で識別（それ以外は赤）
- [x] OBV 検証の表示は OBV 表示トグル (obvEnabled) に非依存
- [x] `npm test`（111 件パス）/ `npm run typecheck` / `npm run build` を実行
- [x] `README.md` と `docs/turtle-strategy.md` を更新


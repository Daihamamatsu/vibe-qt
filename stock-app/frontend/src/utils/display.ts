// 表示ウィンドウ（表示期間 / ローソク足本数）の解決と初期表示範囲の計算 (Issue #36)
//
// チャートの初期表示範囲を「表示期間」または「ローソク足本数」で指定するための
// 純関数群。チャートには取得済みデータすべてが入り、表示期間より古いデータは
// パン（ホイール / ドラッグ / スライダー）で表示できる。
// Stock.vue 側で dispatchAction 経由で使用し、
// ここに単体テスト (display.test.ts) で挙動を固定する。

/** 表示期間プリセット。count = null は「全件」を意味する。 */
export interface DisplayPreset {
  value: string;
  label: string;
  count: number | null;
}

/** 表示期間プリセット（営業日換算の概算: 約 21〜22 営業日/月）。 */
export const DISPLAY_PRESETS: DisplayPreset[] = [
  { value: '1mo', label: '1mo', count: 22 },
  { value: '3mo', label: '3mo', count: 66 },
  { value: '6mo', label: '6mo', count: 132 },
  { value: '1y', label: '1y', count: 261 },
  { value: '2y', label: '2y', count: 522 },
  { value: 'all', label: '全', count: null },
];

/**
 * 表示するローソク足の本数を解決する。
 *
 * 優先順位: 有効なカスタム本数指定(>0 の数値) > 期間プリセット > null (全件表示)。
 * カスタム指定が無効な場合（空文字・0・負・NaN など）は期間プリセットにフォールバックする。
 */
export function resolveDisplayCount(
  preset: string,
  custom: number | string | null | undefined,
): number | null {
  if (custom !== null && custom !== '') {
    const n = Math.floor(Number(custom));
    if (Number.isFinite(n) && n > 0) return n;
  }
  const p = DISPLAY_PRESETS.find((x) => x.value === preset);
  return p ? p.count : null;
}

/**
 * 表示期間 / 本数に応じた初期表示範囲を ECharts dataZoom の percent で返す。
 *
 * チャートには全データが入り、こちらは「直近 N 本」の初期表示範囲だけを指定する。
 * より古いデータはパン（ホイール / ドラッグ / スライダー）で表示できる。
 *
 * - count = null（「全」）または count が総数以上 → 全表示 (0〜100%)
 * - total < 2 → 範囲調整が意味をなさないため全表示 (0〜100%)
 * - ECharts の category 軸では percent とインデックスは
 *   index = percent/100 × (total - 1) で対応する（dataExtent = [0, total-1]）ため、
 *   直近 n 本（インデックス total-n … total-1）の開始位置は
 *   start = (total - n) / (total - 1) × 100 [%]
 * - 結果の幅が dataZoom の minSpan (2%) より小さい場合（例: 本数 1）は、
 *   ECharts 側で自動的に minSpan まで拡大される（AxisProxy のクランプ）ため、
 *   ここでは特に処理しない
 */
export function getDisplayRange(
  total: number,
  preset: string,
  custom: number | string | null | undefined,
): { start: number; end: number } {
  if (total < 2) return { start: 0, end: 100 };
  const count = resolveDisplayCount(preset, custom);
  const n = Math.min(count ?? total, total);
  if (n >= total) return { start: 0, end: 100 };
  const start = Math.round(((total - n) / (total - 1)) * 10000) / 100;
  return { start, end: 100 };
}

// 表示ウィンドウ（表示期間 / ローソク足本数）の解決と末尾部分列取得 (Issue #36)
//
// チャートに表示するローソク足の範囲を「表示期間」または「ローソク足本数」で
// 指定するための純関数群。Stock.vue 側で computed 経由で使用し、
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
 * records の末尾（最新側）から表示本数分を切り出す。
 *
 * - count = null の場合（「全」）は全件を返す
 * - count が総数より大きい場合は全件を返す
 * - records が空の場合は空配列を返す
 */
export function getVisibleWindow<T>(
  records: readonly T[],
  preset: string,
  custom: number | string | null | undefined,
): T[] {
  const total = records.length;
  if (total === 0) return [];
  const count = resolveDisplayCount(preset, custom);
  if (count === null) return records.slice();
  const n = Math.min(count, total);
  return records.slice(total - n);
}

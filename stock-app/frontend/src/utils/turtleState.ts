// タートル戦略の銘柄ごとの状態保存ユーティリティ (Issue #53)
//
// ブラウザの localStorage にシンボル（大文字）をキーにしたタートル戦略の状態を
// 保存する（バックエンド / DB は変更しない）。
//
// 保存する状態:
//   - accountValue: 口座資金（null = 未指定）
//   - breakoutDate: ブレイク日（BUY シグナル日、null = 未指定）
//   - buyPrice:     買値（null = 未指定）
//   - atrPeriod:    ATR 期間 N（14 または 20）
//
// 本モジュールは Vue 非依存の関数のみで構成しており、Node でも実行・検証できる。
// Storage は引数で注入可能なため、テストでは in-memory 実装を渡せる。

/** 銘柄ごとのタートル戦略状態。 */
export interface TurtleState {
  /** 口座資金（円、null = 未指定）。 */
  accountValue: number | null;
  /** ブレイク日（YYYY-MM-DD、BUY シグナル日、null = 未指定）。 */
  breakoutDate: string | null;
  /** 買値（null = 未指定）。 */
  buyPrice: number | null;
  /** ATR 期間 N（14 または 20）。 */
  atrPeriod: number;
}

/** バリデーション結果（成功時は state、失敗時は error）。 */
export type TurtleStateResult =
  | { ok: true; state: TurtleState }
  | { ok: false; error: string };

/** 保存元の入力値（UI の v-model 由来のため number / string（空欄 ''）のいずれもあり得る）。 */
export interface TurtleStateInput {
  accountValue: number | string | null;
  breakoutDate: string | null;
  buyPrice: number | string | null;
  atrPeriod: number;
}

/** localStorage のキー（v1 = スキーマバージョン付き）。 */
export const TURTLE_STATE_STORAGE_KEY = 'turtle-state-v1';

/** 日付形式（YYYY-MM-DD）。 */
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** シンボルを正規化（trim + 大文字化）。空文字列の時は '' を返す。 */
export function normalizeTurtleSymbol(symbol: string): string {
  return symbol.trim().toUpperCase();
}

/** 数値入力を状態用数値に変換する（空欄 '' / null は null = 未指定）。 */
function normalizeNumber(
  value: number | string | null,
  label: string,
  requirePositive: boolean,
): { value: number | null; error?: string } {
  if (value === null || value === '') return { value: null };
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return { value: null, error: `${label}が有効な数値ではありません` };
  if (requirePositive) {
    if (num <= 0) return { value: null, error: `${label}は正の数で指定してください` };
  } else if (num < 0) {
    return { value: null, error: `${label}は 0 以上で指定してください` };
  }
  return { value: num };
}

/**
 * UI の入力値から保存する状態を構築する。
 * 未指定（空欄）は null として許容する（保存済み状態のない項目は復元時も空欄のまま）。
 */
export function buildTurtleState(input: TurtleStateInput): TurtleStateResult {
  const accountValue = normalizeNumber(input.accountValue, '口座資金', false);
  if (accountValue.error) return { ok: false, error: accountValue.error };
  const buyPrice = normalizeNumber(input.buyPrice, '買値', true);
  if (buyPrice.error) return { ok: false, error: buyPrice.error };
  const breakoutDate = input.breakoutDate?.trim() ?? '';
  if (breakoutDate !== '' && !DATE_RE.test(breakoutDate)) {
    return { ok: false, error: 'ブレイク日は YYYY-MM-DD 形式で指定してください' };
  }
  if (input.atrPeriod !== 14 && input.atrPeriod !== 20) {
    return { ok: false, error: 'ATR 期間は 14 または 20 で指定してください' };
  }
  return {
    ok: true,
    state: {
      accountValue: accountValue.value,
      breakoutDate: breakoutDate === '' ? null : breakoutDate,
      buyPrice: buyPrice.value,
      atrPeriod: input.atrPeriod,
    },
  };
}

/** 破損 / 不正な状態オブジェクトをサニタイズする（不正なら null を返す）。 */
export function sanitizeTurtleState(raw: unknown): TurtleState | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (r.atrPeriod !== 14 && r.atrPeriod !== 20) return null;
  const accountValue = r.accountValue;
  if (
    accountValue !== null &&
    (typeof accountValue !== 'number' || !Number.isFinite(accountValue) || accountValue < 0)
  ) {
    return null;
  }
  const buyPrice = r.buyPrice;
  if (buyPrice !== null && (typeof buyPrice !== 'number' || !Number.isFinite(buyPrice) || buyPrice <= 0)) {
    return null;
  }
  const breakoutDate = r.breakoutDate;
  if (breakoutDate !== null && (typeof breakoutDate !== 'string' || !DATE_RE.test(breakoutDate))) {
    return null;
  }
  return {
    accountValue,
    breakoutDate,
    buyPrice,
    atrPeriod: r.atrPeriod as 14 | 20,
  };
}

/** ブラウザ環境の localStorage を返す（Node 等非ブラウザ環境では null）。 */
function defaultStorage(): Storage | null {
  if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
    return window.localStorage;
  }
  return null;
}

/**
 * 全銘柄の保存済み状態を読み出す。
 * 読み取り失敗・不正な JSON・不正な項目は無視して（可能な範囲で）安全に返す。
 */
export function loadAllTurtleStates(storage: Storage | null = defaultStorage()): Record<string, TurtleState> {
  if (storage === null) return {};
  let raw: string | null = null;
  try {
    raw = storage.getItem(TURTLE_STATE_STORAGE_KEY);
  } catch (e) {
    console.warn('タートル戦略状態の読み取りに失敗しました:', e);
    return {};
  }
  if (raw === null) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    console.warn('タートル戦略状態の JSON が不正なため無視します:', e);
    return {};
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};
  const out: Record<string, TurtleState> = {};
  for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
    const sym = normalizeTurtleSymbol(key);
    const state = sanitizeTurtleState(value);
    if (sym === '' || state === null) continue;
    out[sym] = state;
  }
  return out;
}

/**
 * 指定銘柄の状態を上書き保存する。
 * シンボル不正 / ストレージ利用不可 / 書き込み失敗時は Error を投げる。
 */
export function saveTurtleState(
  symbol: string,
  state: TurtleState,
  storage: Storage | null = defaultStorage(),
): void {
  const sym = normalizeTurtleSymbol(symbol);
  if (sym === '') throw new Error('無効なシンボルです');
  if (storage === null) throw new Error('ブラウザのストレージが利用できません');
  const all = loadAllTurtleStates(storage);
  all[sym] = state;
  storage.setItem(TURTLE_STATE_STORAGE_KEY, JSON.stringify(all));
}

/**
 * 指定銘柄の保存済み状態を削除する（未保存の場合は何もしない）。
 * 削除失敗時は Error を投げる。
 */
export function clearTurtleState(
  symbol: string,
  storage: Storage | null = defaultStorage(),
): void {
  const sym = normalizeTurtleSymbol(symbol);
  if (storage === null) return;
  const all = loadAllTurtleStates(storage);
  if (!(sym in all)) return;
  delete all[sym];
  storage.setItem(TURTLE_STATE_STORAGE_KEY, JSON.stringify(all));
}

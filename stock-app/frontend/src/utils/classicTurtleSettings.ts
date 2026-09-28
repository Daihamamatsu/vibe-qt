// 古典タートルズの共通口座設定。
// 口座資金は円を正本とし、米国株を表示するときだけ為替換算する。

export const DEFAULT_ACCOUNT_EQUITY_YEN = 10_000_000;
export const DEFAULT_USD_JPY_RATE = 150;
export const CLASSIC_TURTLE_SETTINGS_STORAGE_KEY = 'classic-turtle-settings-v1';

export interface ClassicTurtleSettings {
  accountEquityYen: number;
  usdJpyRate: number;
}

export type ClassicTurtleCurrency = 'JPY' | 'USD';

/** Yahoo Finance の日本株シンボル（末尾 .T）を判定する。 */
export function isJapaneseStockSymbol(symbol: string): boolean {
  return symbol.trim().toUpperCase().endsWith('.T');
}

/** 銘柄シンボルから表示通貨を決める。 */
export function getClassicTurtleCurrency(symbol: string): ClassicTurtleCurrency {
  return isJapaneseStockSymbol(symbol) ? 'JPY' : 'USD';
}

/** 円建ての共通資金を表示通貨へ換算する。 */
export function convertAccountEquity(
  accountEquityYen: number,
  currency: ClassicTurtleCurrency,
  usdJpyRate: number,
): number {
  if (!Number.isFinite(accountEquityYen) || accountEquityYen < 0) return 0;
  if (currency === 'JPY') return accountEquityYen;
  if (!Number.isFinite(usdJpyRate) || usdJpyRate <= 0) return 0;
  return accountEquityYen / usdJpyRate;
}

/** 表示通貨の入力値を円建ての共通資金へ戻す。 */
export function convertToAccountEquityYen(
  value: number,
  currency: ClassicTurtleCurrency,
  usdJpyRate: number,
): number {
  if (!Number.isFinite(value) || value < 0) return 0;
  if (currency === 'JPY') return value;
  if (!Number.isFinite(usdJpyRate) || usdJpyRate <= 0) return 0;
  return value * usdJpyRate;
}

function isValidSettings(value: unknown): value is ClassicTurtleSettings {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.accountEquityYen === 'number' &&
    Number.isFinite(record.accountEquityYen) &&
    record.accountEquityYen >= 0 &&
    typeof record.usdJpyRate === 'number' &&
    Number.isFinite(record.usdJpyRate) &&
    record.usdJpyRate > 0
  );
}

/** 保存済み設定を読み込む。不正値や利用できない環境では既定値を返す。 */
export function loadClassicTurtleSettings(storage: Storage | null = defaultStorage()): ClassicTurtleSettings {
  const defaults: ClassicTurtleSettings = {
    accountEquityYen: DEFAULT_ACCOUNT_EQUITY_YEN,
    usdJpyRate: DEFAULT_USD_JPY_RATE,
  };
  if (storage === null) return defaults;
  try {
    const raw = storage.getItem(CLASSIC_TURTLE_SETTINGS_STORAGE_KEY);
    if (raw === null) return defaults;
    const parsed: unknown = JSON.parse(raw);
    return isValidSettings(parsed) ? parsed : defaults;
  } catch {
    return defaults;
  }
}

/** 設定を保存する。ブラウザストレージが使えない場合は何もしない。 */
export function saveClassicTurtleSettings(
  settings: ClassicTurtleSettings,
  storage: Storage | null = defaultStorage(),
): void {
  if (storage === null || !isValidSettings(settings)) return;
  try {
    storage.setItem(CLASSIC_TURTLE_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // ストレージ容量不足などでは、計算自体は継続する。
  }
}

function defaultStorage(): Storage | null {
  if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
    return window.localStorage;
  }
  return null;
}
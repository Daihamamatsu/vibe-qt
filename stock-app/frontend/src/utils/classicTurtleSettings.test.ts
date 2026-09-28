import { describe, expect, it } from 'vitest';
import {
  CLASSIC_TURTLE_SETTINGS_STORAGE_KEY,
  DEFAULT_ACCOUNT_EQUITY_YEN,
  DEFAULT_USD_JPY_RATE,
  convertAccountEquity,
  convertToAccountEquityYen,
  getClassicTurtleCurrency,
  loadClassicTurtleSettings,
  saveClassicTurtleSettings,
} from './classicTurtleSettings';

class MemoryStorage implements Storage {
  private map = new Map<string, string>();
  getItem(key: string): string | null { return this.map.get(key) ?? null; }
  setItem(key: string, value: string): void { this.map.set(key, value); }
  removeItem(key: string): void { this.map.delete(key); }
  clear(): void { this.map.clear(); }
  key(index: number): string | null { return Array.from(this.map.keys())[index] ?? null; }
  get length(): number { return this.map.size; }
}

describe('classicTurtleSettings', () => {
  it('既定値は1000万円と150円/USD', () => {
    expect(loadClassicTurtleSettings(null)).toEqual({
      accountEquityYen: DEFAULT_ACCOUNT_EQUITY_YEN,
      usdJpyRate: DEFAULT_USD_JPY_RATE,
    });
  });

  it('日本株はJPY、米国株はUSDとして判定する', () => {
    expect(getClassicTurtleCurrency('7203.T')).toBe('JPY');
    expect(getClassicTurtleCurrency(' aapl ')).toBe('USD');
  });

  it('円資金をドルへ換算し、ドル入力を円へ戻せる', () => {
    expect(convertAccountEquity(10_000_000, 'USD', 150)).toBeCloseTo(66_666.6667);
    expect(convertToAccountEquityYen(70_000, 'USD', 150)).toBe(10_500_000);
    expect(convertAccountEquity(10_000_000, 'JPY', 150)).toBe(10_000_000);
  });

  it('為替レート変更では円資金を維持する', () => {
    const yen = convertToAccountEquityYen(10_000_000 / 150, 'USD', 150);
    expect(convertAccountEquity(yen, 'USD', 140)).toBeCloseTo(71_428.5714);
  });

  it('設定を保存・復元できる', () => {
    const storage = new MemoryStorage();
    const settings = { accountEquityYen: 10_500_000, usdJpyRate: 145 };
    saveClassicTurtleSettings(settings, storage);
    expect(storage.getItem(CLASSIC_TURTLE_SETTINGS_STORAGE_KEY)).not.toBeNull();
    expect(loadClassicTurtleSettings(storage)).toEqual(settings);
  });

  it('不正な保存値は既定値へ戻す', () => {
    const storage = new MemoryStorage();
    storage.setItem(CLASSIC_TURTLE_SETTINGS_STORAGE_KEY, JSON.stringify({ accountEquityYen: 1, usdJpyRate: 0 }));
    expect(loadClassicTurtleSettings(storage)).toEqual({
      accountEquityYen: DEFAULT_ACCOUNT_EQUITY_YEN,
      usdJpyRate: DEFAULT_USD_JPY_RATE,
    });
  });
});
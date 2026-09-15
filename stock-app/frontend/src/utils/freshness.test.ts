// freshness.ts モジュールのユニットテスト（引け後自動リフレッシュ判定）
//
// 最新レコード日付から Yahoo Finance へ再取得するかどうかの判定ロジックを固定する。

import { describe, expect, it } from 'vitest';
import { shouldAutoRefreshYahoo, toLocalIsoDate } from './freshness';

// 2026-09-15 は火曜日
const NOW = new Date(2026, 8, 15);

describe('toLocalIsoDate', () => {
  it('ローカル時間 YYYY-MM-DD でフォーマットする', () => {
    expect(toLocalIsoDate(new Date(2026, 0, 5))).toBe('2026-01-05');
    expect(toLocalIsoDate(new Date(2026, 11, 31))).toBe('2026-12-31');
  });
});

describe('shouldAutoRefreshYahoo', () => {
  it('無データ（undefined / 空文字）では false', () => {
    expect(shouldAutoRefreshYahoo(undefined, 7, NOW)).toBe(false);
    expect(shouldAutoRefreshYahoo('', 7, NOW)).toBe(false);
  });

  it('当日 / 前日の最新レコードでは true', () => {
    expect(shouldAutoRefreshYahoo('2026-09-15', 7, NOW)).toBe(true);
    expect(shouldAutoRefreshYahoo('2026-09-14', 7, NOW)).toBe(true);
  });

  it('週末・祝日のギャップ（数日前）でも true', () => {
    expect(shouldAutoRefreshYahoo('2026-09-10', 7, NOW)).toBe(true); // 木曜日
  });

  it('直近 recentDays 日の境界（7 日前）では true', () => {
    expect(shouldAutoRefreshYahoo('2026-09-08', 7, NOW)).toBe(true); // 7 日前
  });

  it('recentDays 日を超える古いデータ（8 日前以降）では false', () => {
    expect(shouldAutoRefreshYahoo('2026-09-07', 7, NOW)).toBe(false); // 8 日前
    expect(shouldAutoRefreshYahoo('2026-01-01', 7, NOW)).toBe(false);
  });

  it('recentDays の指定を尊重する', () => {
    expect(shouldAutoRefreshYahoo('2026-09-12', 3, NOW)).toBe(true); // 3 日前（境界）
    expect(shouldAutoRefreshYahoo('2026-09-11', 3, NOW)).toBe(false); // 4 日前
  });
});

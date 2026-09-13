// display.ts モジュールのユニットテスト (Issue #36)
//
// 表示ウィンドウ（表示期間 / ローソク足本数）の解決ロジックを固定する:
// カスタム本数指定と期間プリセットの優先順位、末尾部分列の切り出し挙動。

import { describe, expect, it } from 'vitest';
import { getDisplayRange, resolveDisplayCount, chartTitle } from './display';

describe('resolveDisplayCount', () => {
  it('期間プリセットに応じた本数を返す', () => {
    expect(resolveDisplayCount('1mo', null)).toBe(22);
    expect(resolveDisplayCount('3mo', null)).toBe(66);
    expect(resolveDisplayCount('6mo', null)).toBe(132);
    expect(resolveDisplayCount('1y', null)).toBe(261);
    expect(resolveDisplayCount('2y', null)).toBe(522);
  });

  it('「全」プリセットでは null を返す', () => {
    expect(resolveDisplayCount('all', null)).toBeNull();
  });

  it('不明なプリセットでは null を返す', () => {
    expect(resolveDisplayCount('unknown', null)).toBeNull();
  });

  it('有効なカスタム本数指定はプリセットを優先する', () => {
    expect(resolveDisplayCount('1y', 30)).toBe(30);
    // 「全」でもカスタム本数指定があればそちらが優先される
    expect(resolveDisplayCount('all', '30')).toBe(30);
  });

  it('カスタム本数指定は小数点以下を切り捨てて扱う', () => {
    expect(resolveDisplayCount('1y', 30.9)).toBe(30);
  });

  it('無効なカスタム本数指定（空文字・0・負・NaN）はプリセットにフォールバックする', () => {
    expect(resolveDisplayCount('1mo', '')).toBe(22);
    expect(resolveDisplayCount('1mo', 0)).toBe(22);
    expect(resolveDisplayCount('1mo', -5)).toBe(22);
    expect(resolveDisplayCount('all', NaN)).toBeNull();
  });
});

describe('getDisplayRange', () => {
  it('空 / 単一ローソクのデータでは全表示 (0-100) を返す', () => {
    expect(getDisplayRange(0, '1y', null)).toEqual({ start: 0, end: 100 });
    expect(getDisplayRange(1, '1y', null)).toEqual({ start: 0, end: 100 });
  });

  it('「全」プリセットでは全表示 (0-100) を返す', () => {
    expect(getDisplayRange(100, 'all', null)).toEqual({ start: 0, end: 100 });
  });

  it('本数が総数以上では全表示 (0-100) を返す', () => {
    // 1y = 261 本 >= 総数 100
    expect(getDisplayRange(100, '1y', null)).toEqual({ start: 0, end: 100 });
    expect(getDisplayRange(50, 'all', 50)).toEqual({ start: 0, end: 100 });
  });

  it('期間プリセットに応じた直近 N 本の表示範囲を返す', () => {
    // 1mo = 22 本, 総数 100 → start = (100-22)/(100-1)*100 = 78.7878... ≈ 78.79
    expect(getDisplayRange(100, '1mo', null)).toEqual({ start: 78.79, end: 100 });
    // 2y = 522 本, 総数 5000 → start = (5000-522)/4999*100 = 89.5779... ≈ 89.58
    expect(getDisplayRange(5000, '2y', null)).toEqual({ start: 89.58, end: 100 });
  });

  it('カスタム本数指定は期間プリセットを優先する', () => {
    // 30 本, 総数 100 → start = 70/99*100 = 70.7070... ≈ 70.71
    expect(getDisplayRange(100, '1y', 30)).toEqual({ start: 70.71, end: 100 });
  });

  it('無効なカスタム本数指定（空文字）は期間プリセットにフォールバックする', () => {
    // 空文字 → 1mo = 22 本, 総数 100 → プリセット指定と同じ 78.79
    expect(getDisplayRange(100, '1mo', '')).toEqual({ start: 78.79, end: 100 });
  });
});

describe('chartTitle (Issue #49)', () => {
  it('銘柄名があれば "シンボル 銘柄名" を返す', () => {
    expect(chartTitle('AAPL', 'Apple Inc.')).toBe('AAPL Apple Inc.');
  });

  it('銘柄名がなければシンボルのみのタイトルを返す', () => {
    expect(chartTitle('AAPL', '')).toBe('AAPL');
  });
});

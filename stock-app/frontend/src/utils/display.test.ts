// display.ts モジュールのユニットテスト (Issue #36)
//
// 表示ウィンドウ（表示期間 / ローソク足本数）の解決ロジックを固定する:
// カスタム本数指定と期間プリセットの優先順位、末尾部分列の切り出し挙動。

import { describe, expect, it } from 'vitest';
import { getVisibleWindow, resolveDisplayCount } from './display';

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

describe('getVisibleWindow', () => {
  it('空配列には空配列を返す', () => {
    expect(getVisibleWindow([], '1y', null)).toEqual([]);
  });

  it('末尾から指定本数分の部分列を返す', () => {
    expect(getVisibleWindow([1, 2, 3, 4, 5], 'all', 3)).toEqual([3, 4, 5]);
  });

  it('本数が総数より大きい場合は全件を返す', () => {
    expect(getVisibleWindow([1, 2, 3], '2y', 10)).toEqual([1, 2, 3]);
  });

  it('「全」プリセットでは全件を返す', () => {
    expect(getVisibleWindow([1, 2, 3], 'all', null)).toEqual([1, 2, 3]);
  });

  it('カスタム本数指定がない場合は期間プリセットに従う', () => {
    // 1mo = 22 本
    const records = Array.from({ length: 30 }, (_, i) => i);
    expect(getVisibleWindow(records, '1mo', null)).toEqual(records.slice(-22));
  });
});

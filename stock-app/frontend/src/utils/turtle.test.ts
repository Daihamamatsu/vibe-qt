// turtle.ts モジュールのユニットテスト (Issue #31)
//
// 合成 OHLC データで Donchian バンド / ATR / BUY・EXIT シグナルの計算と、
// ポジションサイジング補助関数の挙動を固定する。
// 特に「ルックアヘッドなし」（バンドは前日までのデータのみ参照）を
// レグレッションテストとして担保する（上昇系列で DC20[20] が 21 ならバグ）。

import { describe, expect, it } from 'vitest';
import {
  type Bar,
  computePyramidTargets,
  computeTurtle,
  computeUnitShares,
} from './turtle';

/** 指定した OHLC の 1 本バーを生成（出来高は固定 1000）。 */
function makeBar(i: number, open: number, high: number, low: number, close: number): Bar {
  return {
    date: `2026-09-${String(i + 1).padStart(2, '0')}`,
    open,
    high,
    low,
    close,
    volume: 1000,
  };
}

/** 上昇系列: o=h=l=c = i+1（既定 25 本） */
function makeRisingBars(count = 25): Bar[] {
  return Array.from({ length: count }, (_, i) => makeBar(i, i + 1, i + 1, i + 1, i + 1));
}

/** 下落系列: o=h=l=c = 100-i（既定 25 本） */
function makeFallingBars(count = 25): Bar[] {
  return Array.from({ length: count }, (_, i) => makeBar(i, 100 - i, 100 - i, 100 - i, 100 - i));
}

/** 一定 TR 系列: o=10, h=12, l=10, c=11（TR が常に 2） */
function makeConstantTrBars(count = 30): Bar[] {
  return Array.from({ length: count }, (_, i) => makeBar(i, 10, 12, 10, 11));
}

/** トレーリングストップ系列: o=10+i, h=12+i, l=10+i, c=11+i（TR が常に 2） */
function makeRisingTrBars(count = 30): Bar[] {
  return Array.from({ length: count }, (_, i) => makeBar(i, 10 + i, 12 + i, 10 + i, 11 + i));
}

// 固定シードの擬似乱数生成器 (mulberry32)。
// プロパティテストを再現可能（シード固定）にするため標準ライブラリで実装する。
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 乱数（固定シード）で有効な OHLC（low <= open/close <= high）を count 本生成する。 */
function makeRandomBars(count: number, seed = 20260912): Bar[] {
  const rnd = mulberry32(seed);
  const bars: Bar[] = [];
  let price = 100;
  for (let i = 0; i < count; i++) {
    // 終値ベースのランダムウォーク（±10% 程度）
    price = Math.max(1, price * (1 + (rnd() - 0.5) * 0.2));
    const open = price * (1 + (rnd() - 0.5) * 0.04);
    const close = price * (1 + (rnd() - 0.5) * 0.04);
    const bodyLow = Math.min(open, close);
    const bodyHigh = Math.max(open, close);
    const low = bodyLow * (1 - rnd() * 0.02);
    const high = bodyHigh * (1 + rnd() * 0.02);
    bars.push(makeBar(i, open, high, low, close));
  }
  return bars;
}

describe('computeTurtle: Donchian バンド（ルックアヘッドなし）', () => {
  it('上昇系列: DC20[20] = 20（21 なら当日高値を混入しているルックアヘッドバグ）', () => {
    const rows = computeTurtle(makeRisingBars(25));
    expect(rows).toHaveLength(25);
    // 前日までの 20 日分が揃うまで null
    expect(rows[19].donchianUpper).toBeNull();
    // 前日までの最高値 = max(hi[0..19]) = 20（当日高値 21 は含めない）
    expect(rows[20].donchianUpper).toBe(20);
    // 前日までの最低値 = min(lo[0..9]) = 1
    expect(rows[10].donchianLower).toBe(1);
    // 上昇系列は i >= 20 で常に終値 > エントリーライン → BUY
    for (let i = 20; i < 25; i++) {
      expect(rows[i].buy, `i=${i} で buy === true となるべき`).toBe(true);
    }
  });

  it('下落系列: DC10[10] = 91 かつ i >= 10 で EXIT', () => {
    const rows = computeTurtle(makeFallingBars(25));
    // 前日までの 10 日最低値 = min(lo[0..9]) = 100 - 9 = 91
    expect(rows[10].donchianLower).toBe(91);
    // 下落系列は i >= 10 で常に終値 < 手仕舞いライン → EXIT
    for (let i = 10; i < 25; i++) {
      expect(rows[i].exit, `i=${i} で exit === true となるべき`).toBe(true);
    }
  });
});

describe('computeTurtle: ATR（True Range の単純移動平均）', () => {
  it('一定 TR=2 系列 (atrPeriod: 14) では ATR = 2、それ以前は null', () => {
    const rows = computeTurtle(makeConstantTrBars(30), { atrPeriod: 14 });
    // 14 日分が揃う前 (i < 13) は null
    expect(rows[12].atr).toBeNull();
    // 14 日目から ATR = 2 で安定
    expect(rows[13].atr).toBe(2);
    expect(rows[29].atr).toBe(2);
  });
});

describe('computeTurtle: トレーリングストップ（直近10日高値 - 2*N）', () => {
  it('stop[20] = 31 - 2*2 = 27、stop[12] は null（ATR が揃っていない）', () => {
    const rows = computeTurtle(makeRisingTrBars(30), { atrPeriod: 14 });
    // 直近 10 日高値 = max(hi[10..19]) = 12 + 19 = 31、ATR = 2 → 31 - 2*2 = 27
    expect(rows[20].trailingStop).toBe(27);
    // ATR 期間 (14) > exitDays (10) のため i >= 10 でも ATR が null なら stop は null
    expect(rows[12].trailingStop).toBeNull();
  });
});

describe('computeUnitShares', () => {
  it('floor((口座資金 * 0.01) / (N * 1株あたりの価値)) を計算する', () => {
    expect(computeUnitShares(1_000_000, 2, 50)).toBe(100);
    // 小数は切り捨て（10000 / 21 = 476.19... → 476）
    expect(computeUnitShares(1_000_000, 3, 7)).toBe(476);
  });

  it('不正な入力（ゼロ / 負 / NaN）は 0 を返す', () => {
    expect(computeUnitShares(0, 2, 50)).toBe(0);
    expect(computeUnitShares(1_000_000, 0, 50)).toBe(0);
    expect(computeUnitShares(1_000_000, 2, -1)).toBe(0);
    expect(computeUnitShares(Number.NaN, 2, 50)).toBe(0);
  });
});

describe('computePyramidTargets', () => {
  it('買値基準の +0.5N / +1.0N / +1.5N 目標と -2N ストップを返す', () => {
    expect(computePyramidTargets(100, 2)).toEqual({
      target1: 101,
      target2: 102,
      target3: 103,
      stop: 96,
    });
  });
});

describe('computeTurtle: エッジケース', () => {
  it('空の配列は空の配列を返す', () => {
    expect(computeTurtle([])).toEqual([]);
  });

  it('データが短すぎるとバンド / ATR / ストップが全て null かつシグナルなし', () => {
    // entryDays (既定 20) より短い 5 本だけ与える
    const rows = computeTurtle(makeRisingBars(5));
    expect(rows).toHaveLength(5);
    for (const row of rows) {
      expect(row.donchianUpper).toBeNull();
      expect(row.donchianLower).toBeNull();
      expect(row.atr).toBeNull();
      expect(row.trailingStop).toBeNull();
      expect(row.buy).toBe(false);
      expect(row.exit).toBe(false);
    }
  });

  it('high / low が null のレコードは close にフォールバックして計算する', () => {
    const bars: Bar[] = [
      { date: '2026-01-01', open: null, high: null, low: null, close: 10, volume: null },
      { date: '2026-01-02', open: null, high: null, low: null, close: 11, volume: null },
      { date: '2026-01-03', open: null, high: null, low: null, close: 12, volume: null },
      { date: '2026-01-04', open: null, high: null, low: null, close: 13, volume: null },
      { date: '2026-01-05', open: null, high: null, low: null, close: 14, volume: null },
    ];
    // high/low が null なので close にフォールバック:
    // entryDays=2 で i=2 の最高値 = max(close[0..1]) = 11、最低値 = min(close[0..1]) = 10
    const rows = computeTurtle(bars, { entryDays: 2, exitDays: 2, atrPeriod: 2 });
    expect(rows[2].donchianUpper).toBe(11);
    expect(rows[2].donchianLower).toBe(10);
    // TR は常に |close - 前日close| = 1 になり、atrPeriod=2 で ATR = 1
    expect(rows[2].atr).toBe(1);
  });
});

describe('computeTurtle: プロパティ（乱数 OHLC、固定シード）', () => {
  it('buy と exit が同時に真にならない', () => {
    const bars = makeRandomBars(60, 20260912);
    const rows = computeTurtle(bars);
    for (let i = 0; i < rows.length; i++) {
      expect(rows[i].buy && rows[i].exit, `i=${i} で buy と exit が同時真になった`).toBe(false);
    }
  });
});

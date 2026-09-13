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
  computeTurtlePlan,
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

describe('computeTurtle: ATR（True Range の Wilder 平滑化）', () => {
  it('一定 TR=2 系列 (atrPeriod: 14) では ATR = 2、それ以前は null（一定系列では SMA と一致）', () => {
    const rows = computeTurtle(makeConstantTrBars(30), { atrPeriod: 14 });
    // 14 日分が揃う前 (i < 13) は null
    expect(rows[12].atr).toBeNull();
    // 14 日目から ATR = 2 で安定
    expect(rows[13].atr).toBe(2);
    expect(rows[29].atr).toBe(2);
  });

  it('一定 TR=2 系列で既定の atrPeriod (20) では i=19 から ATR = 2、stop = 12 - 2*2 = 8', () => {
    const rows = computeTurtle(makeConstantTrBars(30));
    // 20 日分が揃う前 (i < 19) は ATR / stop は null
    expect(rows[18].atr).toBeNull();
    expect(rows[18].trailingStop).toBeNull();
    // 20 日目から ATR = 2、stop = 直近高値 12 - 2*2 = 8
    expect(rows[19].atr).toBe(2);
    expect(rows[19].trailingStop).toBe(8);
    expect(rows[29].atr).toBe(2);
    expect(rows[29].trailingStop).toBe(8);
  });

  it('初期値 = 最初の atrPeriod 日間の TR 単純平均、以降は Wilder 再帰で更新される', () => {
    // close = 10,12,15,19,24,30 (hi=lo=close にフォールバック) → TR = [0, 2, 3, 4, 5, 6]
    const bars: Bar[] = [10, 12, 15, 19, 24, 30].map((c, i) => makeBar(i, c, c, c, c));
    const rows = computeTurtle(bars, { atrPeriod: 4 });
    // 初期データ (3 日) までは null
    expect(rows[2].atr).toBeNull();
    // 初期値 = (0+2+3+4)/4 = 2.25
    expect(rows[3].atr).toBe(2.25);
    // Wilder 再帰: (2.25*3+5)/4 = 2.9375, (2.9375*3+6)/4 = 3.703125
    expect(rows[4].atr).toBe(2.9375);
    expect(rows[5].atr).toBe(3.703125);
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
  it('floor(口座資金 * 0.01 / N) を計算する (買値は掛けない)', () => {
    expect(computeUnitShares(1_000_000, 2)).toBe(5000);
    // 小数は切り捨て (10000 / 7 = 1428.57... → 1428)
    expect(computeUnitShares(1_000_000, 7)).toBe(1428);
  });

  it('不正な入力 (ゼロ / 負 / NaN) は 0 を返す', () => {
    expect(computeUnitShares(0, 2)).toBe(0);
    expect(computeUnitShares(1_000_000, 0)).toBe(0);
    expect(computeUnitShares(1_000_000, -2)).toBe(0);
    expect(computeUnitShares(Number.NaN, 2)).toBe(0);
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

describe('computeTurtlePlan: 買い増し / EXIT の機械的シミュレーション', () => {
  // ブレイク日は i=3 (BUY: DC2 = max(h1,h2) = 13 < 終値 14)。
  // entryDays=2, exitDays=2, atrPeriod=2 で ATR は i>=1 から有効 (i=3 で 2.5)。
  const RISING: Bar[] = [
    makeBar(0, 10, 12, 10, 11),
    makeBar(1, 10, 12, 10, 11),
    makeBar(2, 11, 13, 11, 12),
    makeBar(3, 12, 15, 12, 14),
    makeBar(4, 14, 16, 14, 15), // 終値 15 < P2 ライン 15.125 (N=2.25) → 到達しない
    makeBar(5, 15, 18, 15, 17), // 終値 17 ≥ 15.3125 (P2) かつ ≥ 16.625 (P3)
  ];
  // 緩やかな下落: i=6 で N = 1.1875, ストップ = 14 - 2*1.1875 = 11.625,
  // 終値 11 ≤ 11.625 (DC10 = min(l1..l5) = 10 を上回るため理由は 'stop')
  const FALLING: Bar[] = [
    makeBar(0, 10, 12, 10, 11),
    makeBar(1, 10, 12, 10, 11),
    makeBar(2, 11, 13, 11, 12),
    makeBar(3, 12, 15, 12, 14),
    makeBar(4, 13, 14, 13, 13),
    makeBar(5, 12, 13, 12, 12),
    makeBar(6, 11, 12, 11, 11),
  ];
  // 急落: i=5 で TR = 6 → Wilder N = (2.25+6)/2 = 4.125, ストップ = 14 - 2*4.125 = 5.75 (到達せず)。
  // DC10 = min(l3,l4) = 12, 終値 10.5 < 12 → DC10 下抜けで EXIT
  const DC10_DROP: Bar[] = [
    makeBar(0, 10, 12, 10, 11),
    makeBar(1, 10, 12, 10, 11),
    makeBar(2, 11, 13, 11, 12),
    makeBar(3, 12, 15, 12, 14),
    makeBar(4, 14, 16, 14, 15),
    makeBar(5, 10, 16, 10, 10.5),
  ];

  it('同日に複数の買い増し到達を許容する (P2/P3 到達、P4 未到達、EXIT なし)', () => {
    const rows = computeTurtle(RISING, { entryDays: 2, exitDays: 2, atrPeriod: 2 });
    expect(rows[3].buy).toBe(true);
    const plan = computeTurtlePlan(rows, rows[3].date, rows[3].close);
    expect(plan).not.toBeNull();
    const [p2, p3, p4] = plan!.levels;
    // Wilder: N(5) = 2.625 → P2 = 14+0.5N = 15.3125, P3 = 15.3125+0.5N = 16.625, P4 = 16.625+0.5N = 17.9375
    // 終値 17: P2/P3 到達、P4 未到達
    expect(p2).toMatchObject({ level: 2, date: rows[5].date, price: 15.3125, hitClose: 17 });
    expect(p3).toMatchObject({ level: 3, date: rows[5].date, price: 16.625, hitClose: 17 });
    expect(p4).toMatchObject({ level: 4, date: null, price: null, hitClose: null });
    expect(plan!.exit).toEqual({ date: null, close: null, reason: null });
    // 直近日 (i=5) の再計算値
    expect(plan!.latest).toEqual({
      date: rows[5].date,
      n: 2.625,
      target1: 15.3125,
      target2: 16.625,
      target3: 17.9375,
      stop: 8.75,
      dc10: 12,
    });
  });

  it('P2 到達後は P3 が固定された P2 ラインから +0.5×N(当日) で更新される (buyPrice 基準にならない)', () => {
    const CHAIN: Bar[] = [
      makeBar(0, 10, 12, 10, 11),
      makeBar(1, 10, 12, 10, 11),
      makeBar(2, 11, 13, 11, 12),
      makeBar(3, 12, 15, 12, 14),
      // i=4: N = (2.5*1+1)/2 = 1.75 → P2 ライン = 14.875 ≤ 終値 15 → P2 到達(ライン固定)
      makeBar(4, 14, 15, 14, 15),
      // i=5: N = (1.75*1+3)/2 = 2.375 → P3 ライン = 14.875 + 0.5*2.375 = 16.0625 (買値基準の 16.375 とは異なる)
      makeBar(5, 15, 18, 15, 16),
    ];
    const rows = computeTurtle(CHAIN, { entryDays: 2, exitDays: 2, atrPeriod: 2 });
    const plan = computeTurtlePlan(rows, rows[3].date, rows[3].close);
    const [p2, p3, p4] = plan!.levels;
    expect(p2).toMatchObject({ level: 2, date: rows[4].date, price: 14.875, hitClose: 15 });
    // P3/P4 は到達しない (16 < 16.0625)
    expect(p3).toMatchObject({ level: 3, date: null, price: null, hitClose: null });
    expect(p4).toMatchObject({ level: 4, date: null, price: null, hitClose: null });
    // target1 は到達時に固定された 14.875、target2 は固定 P2 ライン + 0.5×N(当日) = 16.0625
    expect(plan!.latest).toEqual({
      date: rows[5].date,
      n: 2.375,
      target1: 14.875,
      target2: 16.0625,
      target3: 17.25,
      stop: 9.25,
      dc10: 12,
    });
    expect(plan!.exit).toEqual({ date: null, close: null, reason: null });
  });

  it('終値 ≤ 買値 − 2N の初回到達日でストップロス EXIT', () => {
    const rows = computeTurtle(FALLING, { entryDays: 2, exitDays: 5, atrPeriod: 2 });
    expect(rows[3].buy).toBe(true);
    const plan = computeTurtlePlan(rows, rows[3].date, rows[3].close);
    // i=6: N = 1.1875 → ストップ = 14 - 2*1.1875 = 11.625, 終値 11 ≤ 11.625
    // (DC10 = min(l1..l5) = 10 を上回るため理由は 'stop')
    expect(plan!.exit).toEqual({ date: rows[6].date, close: 11, reason: 'stop' });
    // 目標到達前に EXIT したため買い増しは未到達
    expect(plan!.levels.every(l => l.date === null)).toBe(true);
  });

  it('終値 < DC10 の初回到達日で DC10 下抜け EXIT (ストップより上の場合)', () => {
    const rows = computeTurtle(DC10_DROP, { entryDays: 2, exitDays: 2, atrPeriod: 2 });
    const plan = computeTurtlePlan(rows, rows[3].date, rows[3].close);
    // i=5: N = 4 → ストップ = 6 (終値 10.5 は超過)、DC10 = 12 (終値 10.5 < 12 → 'dc10')
    expect(plan!.exit).toEqual({ date: rows[5].date, close: 10.5, reason: 'dc10' });
    expect(plan!.levels.every(l => l.date === null)).toBe(true);
  });

  it('ブレイク日が存在しない・買値が無効な場合は null を返す', () => {
    const rows = computeTurtle(RISING, { entryDays: 2, exitDays: 2, atrPeriod: 2 });
    expect(computeTurtlePlan(rows, '2099-01-01', 14)).toBeNull();
    expect(computeTurtlePlan(rows, rows[3].date, 0)).toBeNull();
    expect(computeTurtlePlan(rows, rows[3].date, Number.NaN)).toBeNull();
  });

  it('ATR が揃わないデータでも安全に空の計画を返す (latest = null)', () => {
    // entryDays=20 より短い 5 本 → 全日 ATR / バンド null
    const rows = computeTurtle(makeRisingBars(5));
    const plan = computeTurtlePlan(rows, rows[0].date, 1);
    expect(plan).not.toBeNull();
    expect(plan!.latest).toBeNull();
    expect(plan!.levels.every(l => l.date === null)).toBe(true);
    expect(plan!.exit.date).toBeNull();
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
    // TR は [0, 1, 1, 1, 1] (初日は high-low = 0)
    // Wilder: 初期値 (0+1)/2 = 0.5 → 以降 (0.5*1+1)/2 = 0.75
    expect(rows[2].atr).toBe(0.75);
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

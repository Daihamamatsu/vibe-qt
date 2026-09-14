// obv.ts モジュールのユニットテスト (Issue #61)
//
// 合成 OHLC データで OBV (On-Balance Volume) の計算式を固定する:
// - 初日の出来高を最初の OBV とする
// - ① 上昇日: OBV[i] = OBV[i-1] + 出来高[i]
// - ② 下降日: OBV[i] = OBV[i-1] − 出来高[i]
// - ③ 同値日: OBV[i] = OBV[i-1]（不変）
// - 出来高が null の日は出来高 0 扱い (OBV は横ばい)

import { describe, expect, it } from 'vitest';
import type { Bar } from './turtle';
import { computeObv } from './obv';

/** 指定した終値・出来高の 1 本バーを生成 (始値 = 高値 = 安値 = 終値)。 */
function makeBar(i: number, close: number, volume: number | null): Bar {
  return {
    date: `2026-09-${String(i + 1).padStart(2, '0')}`,
    open: close,
    high: close,
    low: close,
    close,
    volume,
  };
}

/** closes / volumes からバー列を生成（長さは closes を基準にする）。 */
function makeBars(closes: number[], volumes: (number | null)[]): Bar[] {
  return closes.map((c, i) => makeBar(i, c, volumes[i]));
}

/**
 * 参照実装: Issue の計算式 (①②③) をそのまま記述。
 * computeObv と独立に実装し、固定シードの擬似乱数系列での回帰比較に使う。
 */
function referenceObv(bars: Bar[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < bars.length; i++) {
    const volume = bars[i].volume ?? 0;
    if (i === 0) {
      out.push(volume); // 最初の出来高 = 最初の OBV
    } else if (bars[i].close > bars[i - 1].close) {
      out.push(out[i - 1] + volume); // ①
    } else if (bars[i].close < bars[i - 1].close) {
      out.push(out[i - 1] - volume); // ②
    } else {
      out.push(out[i - 1]); // ③
    }
  }
  return out;
}

// 固定シードの擬似乱数生成器 (mulberry32)。テストの再現性を担保する。
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe('computeObv', () => {
  it('空の入力は空配列を返す', () => {
    expect(computeObv([])).toEqual([]);
  });

  it('単一バー: OBV はその出来高に等しい', () => {
    expect(computeObv(makeBars([100], [1000])).map(r => r.obv)).toEqual([1000]);
  });

  it('単一バーで出来高 null: OBV は 0', () => {
    expect(computeObv(makeBars([100], [null])).map(r => r.obv)).toEqual([0]);
  });

  it('①②③ 基本式: 上昇は加算・下降は減算・同値は不変', () => {
    // 終値: 10, 11, 12, 12, 11, 12, 13 → 上昇, 上昇, 同値, 下降, 上昇, 上昇
    const bars = makeBars(
      [10, 11, 12, 12, 11, 12, 13],
      [1000, 1000, 1000, 1000, 1000, 1000, 1000],
    );
    expect(computeObv(bars).map(r => r.obv)).toEqual([1000, 2000, 3000, 3000, 2000, 3000, 4000]);
  });

  it('すべて同値: OBV は初日出来高のまま一定（出来高の大小は無関係）', () => {
    const bars = makeBars([100, 100, 100, 100], [1000, 2000, 3000, 4000]);
    expect(computeObv(bars).map(r => r.obv)).toEqual([1000, 1000, 1000, 1000]);
  });

  it('連続下落: OBV は減少し負にもなる', () => {
    const bars = makeBars([10, 9, 8, 7], [1000, 1000, 1000, 1000]);
    expect(computeObv(bars).map(r => r.obv)).toEqual([1000, 0, -1000, -2000]);
  });

  it('出来高 null の日は 0 扱い (OBV 横ばい)', () => {
    // 初日 null → OBV[0] = 0。上昇日だが出来高 null → 不変。翌日 +2000
    const bars = makeBars([10, 11, 12], [null, null, 2000]);
    expect(computeObv(bars).map(r => r.obv)).toEqual([0, 0, 2000]);
  });

  it('出来高が日ごとに変動しても計算式は成立', () => {
    // 終値: 10 → 12 → 11 → 13 (上昇, 下降, 上昇)
    const bars = makeBars([10, 12, 11, 13], [100, 500, 300, 700]);
    // [100, 100+500=600, 600-300=300, 300+700=1000]
    expect(computeObv(bars).map(r => r.obv)).toEqual([100, 600, 300, 1000]);
  });

  it('昇順日付をそのまま保持する', () => {
    const bars = makeBars([10, 11], [100, 100]);
    const rows = computeObv(bars);
    expect(rows.map(r => r.date)).toEqual(bars.map(b => b.date));
    expect(rows).toHaveLength(bars.length);
  });

  it('乱数系列: 参照実装 (Issue の計算式①②③) と一致する (回帰)', () => {
    const rand = mulberry32(20260914);
    let price = 100;
    const closes: number[] = [];
    const volumes: number[] = [];
    for (let i = 0; i < 200; i++) {
      price = Math.max(1, price + (rand() - 0.5) * 4); // ランダムウォーク
      closes.push(Number(price.toFixed(2)));
      volumes.push(Math.floor(rand() * 10000));
    }
    // 同値日（差分 0）も確実に含める
    closes[50] = closes[49];
    const bars = makeBars(closes, volumes);
    expect(computeObv(bars).map(r => r.obv)).toEqual(referenceObv(bars));
  });
});

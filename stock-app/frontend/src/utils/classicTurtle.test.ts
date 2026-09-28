import { describe, expect, it } from 'vitest';
import type { Bar } from './turtle';
import {
  backtestClassicTurtle,
  computeClassicTurtleIndicators,
  computeClassicUnitShares,
} from './classicTurtle';

function bar(i: number, close: number, high = close, low = close, open = close): Bar {
  return {
    date: `2026-01-${String(i + 1).padStart(2, '0')}`,
    open,
    high,
    low,
    close,
    volume: 1000,
  };
}

describe('computeClassicTurtleIndicators', () => {
  it('System 1 / System 2のラインは当日を含めずに計算する', () => {
    const bars = Array.from({ length: 6 }, (_, i) => bar(i, i + 1));
    const rows = computeClassicTurtleIndicators(bars, {
      nPeriod: 2,
      system1EntryDays: 2,
      system1ExitDays: 2,
      system2EntryDays: 4,
      system2ExitDays: 4,
    });
    expect(rows[1].system1LongEntry).toBeNull();
    expect(rows[2].system1LongEntry).toBe(2);
    expect(rows[4].system2LongEntry).toBe(4);
    expect(rows[0].system1LongEntry).toBeNull();
  });

  it('NはTrue RangeのWilder平滑化で計算する', () => {
    const bars = [
      bar(0, 10, 12, 10),
      bar(1, 12, 14, 11),
      bar(2, 13, 16, 12),
    ];
    const rows = computeClassicTurtleIndicators(bars, { nPeriod: 2 });
    // TR=[2,4,4] -> 初期N=3、次のN=(3+4)/2=3.5
    expect(rows[0].n).toBeNull();
    expect(rows[1].n).toBe(3);
    expect(rows[2].n).toBe(3.5);
  });
});

describe('computeClassicUnitShares', () => {
  it('資金の1%をN×ポイント価値で割り、ロット単位で切り捨てる', () => {
    expect(computeClassicUnitShares(1_000_000, 2)).toBe(5000);
    expect(computeClassicUnitShares(1_000_000, 2, 5, 10)).toBe(1000);
    expect(computeClassicUnitShares(0, 2)).toBe(0);
  });
});

describe('backtestClassicTurtle', () => {
  it('最終日まで保有したポジションを強制決済せず、評価損益と保有状態を維持する', () => {
    const bars = [
      bar(0, 10, 11, 9),
      bar(1, 10, 11, 9),
      bar(2, 12, 12, 12), // S1 long entry
      bar(3, 13, 13, 12), // 決済条件なし
    ];
    const result = backtestClassicTurtle(bars, {
      nPeriod: 2,
      accountEquity: 100_000,
      system1EntryDays: 2,
      system1ExitDays: 2,
      system2EntryDays: 5,
      system2ExitDays: 2,
    });

    expect(result.trades).toHaveLength(1);
    expect(result.trades[0].exit).toBeNull();
    expect(result.trades[0].pnl).toBeGreaterThan(0);
    const lastDay = result.days[result.days.length - 1];
    expect(lastDay.date).toBe('2026-01-04');
    expect(lastDay.exit).toBeNull();
    expect(lastDay.position).not.toBeNull();
  });

  it('日付降順の入力でも日付昇順の入力と同じ結果を返す', () => {
    const bars = [
      bar(0, 10, 11, 9),
      bar(1, 10, 11, 9),
      bar(2, 12, 12, 12),
      bar(3, 13, 13, 12),
    ];
    const params = {
      nPeriod: 2,
      accountEquity: 100_000,
      system1EntryDays: 2,
      system1ExitDays: 2,
      system2EntryDays: 5,
      system2ExitDays: 2,
    };
    const ascending = backtestClassicTurtle(bars, params);
    const descending = backtestClassicTurtle([...bars].reverse(), params);

    expect(descending.indicators.map(row => row.date)).toEqual(
      ascending.indicators.map(row => row.date),
    );
    expect(descending.days.map(day => day.date)).toEqual(
      ascending.days.map(day => day.date),
    );
    expect(descending.trades).toEqual(ascending.trades);
  });

  it('ロングSystem 1をエントリーし、0.5Nごとに最大4ユニット追加する', () => {
    const bars = [
      bar(0, 10, 11, 9),
      bar(1, 10, 11, 9),
      bar(2, 11, 12, 10),
      bar(3, 12, 13, 11), // 2日高値12を上抜け、P1=12 / N=2
      bar(4, 13, 14, 12), // P2=13 到達
      bar(5, 14, 15, 13), // P3=14 到達
      bar(6, 15, 16, 14), // P4=15 到達
      bar(7, 15, 15, 15),
    ];
    const result = backtestClassicTurtle(bars, {
      nPeriod: 2,
      accountEquity: 100_000,
      system1EntryDays: 2,
      system1ExitDays: 2,
      system2EntryDays: 5,
      system2ExitDays: 2,
    });
    expect(result.trades).toHaveLength(1);
    const trade = result.trades[0];
    expect(trade.side).toBe('long');
    expect(trade.system).toBe('system1');
    expect(trade.entries).toHaveLength(4);
    expect(trade.entries.map(entry => entry.kind)).toEqual([
      'initial', 'pyramid', 'pyramid', 'pyramid',
    ]);
    expect(trade.entries.every(entry => entry.shares === trade.entries[0].shares)).toBe(true);
    expect(trade.entries.map(entry => entry.n)).toEqual([2, 2, 2, 2]);
    expect(trade.entries.map(entry => entry.price - 2 * entry.n)).toEqual([7, 8, 9, 10]);
    expect(result.days[4].position?.nextAddPrice).toBe(14);
    expect(result.days[4].position?.stopPrice).toBe(9);
  });

  it('ショートSystem 1をエントリーし、上昇で2Nストップ決済する', () => {
    const bars = [
      bar(0, 10, 10, 10),
      bar(1, 10, 10, 10),
      bar(2, 8, 8, 8), // 2日安値10を下抜け、N=1
      bar(3, 10, 10, 10), // ショート初期ストップ=10に到達
    ];
    const result = backtestClassicTurtle(bars, {
      nPeriod: 2,
      accountEquity: 100_000,
      system1EntryDays: 2,
      system1ExitDays: 2,
      system2EntryDays: 5,
      system2ExitDays: 2,
    });
    expect(result.trades[0].side).toBe('short');
    expect(result.trades[0].exit?.reason).toBe('stop');
    expect(result.trades[0].exit?.price).toBe(10);
  });

  it('System 1の利益トレード後は次のSystem 1シグナルを見送り、System 2で解除する', () => {
    const bars = [
      bar(0, 10, 11, 9),
      bar(1, 10, 11, 9),
      bar(2, 12, 12, 12), // S1 long entry at 11
      bar(3, 13, 13, 11), // DC1=12を下抜けず保有
      bar(4, 13, 14, 10), // S1 long entryはブロック中だが、既存ポジションのDC1=11を下抜けて決済
      bar(5, 14, 15, 13), // 次のS1シグナル候補
    ];
    const result = backtestClassicTurtle(bars, {
      nPeriod: 2,
      accountEquity: 100_000,
      system1EntryDays: 2,
      system1ExitDays: 1,
      system2EntryDays: 5,
      system2ExitDays: 1,
    });
    expect(result.trades[0].pnl).toBeGreaterThan(0);
    expect(result.days[3].exit?.reason).toBe('channel');
    expect(result.days[4].system1EntrySkipped).toBe(true);
    expect(result.system1EntryBlocked).toBe(false);
  });

  it('System 1の利益トレード後は、次の1回だけスキップして、その次は再び有効になる', () => {
    const bars = [
      bar(0, 10, 11, 9),
      bar(1, 10, 11, 9),
      bar(2, 12, 12, 12), // S1 entry
      bar(3, 13, 13, 11), // 利益でS1 exit
      bar(4, 14, 14, 13), // 次のS1 signalは1回だけskip
      bar(5, 15, 15, 14), // その次のS1 signalはentry可能
    ];
    const result = backtestClassicTurtle(bars, {
      nPeriod: 2,
      accountEquity: 100_000,
      system1EntryDays: 2,
      system1ExitDays: 1,
      system2EntryDays: 10,
      system2ExitDays: 1,
    });
    expect(result.days[4].system1EntrySkipped).toBe(true);
    expect(result.days[5].entry?.kind).toBe('initial');
  });

  it('同じ日の日中にロング・ショート両方のシグナルが出た場合は見送る', () => {
    const bars = [
      bar(0, 10),
      bar(1, 10),
      bar(2, 10, 12, 8, 10),
    ];
    const result = backtestClassicTurtle(bars, {
      nPeriod: 2,
      accountEquity: 100_000,
      system1EntryDays: 2,
      system1ExitDays: 2,
      system2EntryDays: 5,
      system2ExitDays: 2,
    });
    expect(result.days[2].ambiguous).toBe(true);
    expect(result.days[2].entry).toBeNull();
  });
});

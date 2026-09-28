// 古典的タートルズ手法のOHLCバックテスト・エンジン。
//
// 対象仕様:
// - System 1: 20日ブレイクでエントリー、10日ブレイクで決済
// - System 2: 55日ブレイクでエントリー、20日ブレイクで決済
// - N: 20日True RangeのWilder平滑化
// - 1ユニットのリスク: 口座資金の1%
// - 追加エントリー: 0.5Nごと、最大4ユニット
// - 初期ストップ: 2N
//
// 日足OHLCだけでは同一バー内の高値・安値の順序を復元できないため、
// 既存ポジションのストップ / 決済を追加エントリーより先に評価する。
// 同一バーでロング・ショートの両方、または異なる方向の複数シグナルが
// 発生した場合は、曖昧な約定を避けるため新規エントリーを見送る。

import type { Bar } from './turtle';

export type TurtleSide = 'long' | 'short';
export type ClassicTradeSideFilter = TurtleSide | 'both';
export type TurtleSystem = 'system1' | 'system2';
export type TurtleExitReason =
  | 'stop'
  | 'channel'
  | 'end_of_data';

export interface ClassicTurtleParams {
  /** 古典仕様では20日固定。設定値として公開し、テストで短縮可能にする。 */
  nPeriod?: number;
  /** 口座資金。未指定の場合、unitSharesは0になる。 */
  accountEquity?: number;
  /** 1ポイントの金銭価値。株式は通常1。 */
  pointValue?: number;
  /** 最小取引単位。株式は通常1。 */
  lotSize?: number;
  /** 1ポジションの最大ユニット数。古典仕様は4。 */
  maxUnits?: number;
  /** System 1のエントリー期間。古典仕様は20。 */
  system1EntryDays?: number;
  /** System 1の決済期間。古典仕様は10。 */
  system1ExitDays?: number;
  /** System 2のエントリー期間。古典仕様は55。 */
  system2EntryDays?: number;
  /** System 2の決済期間。古典仕様は20。 */
  system2ExitDays?: number;
}

export interface ClassicTurtleIndicator {
  date: string;
  n: number | null;
  system1LongEntry: number | null;
  system1ShortEntry: number | null;
  system1LongExit: number | null;
  system1ShortExit: number | null;
  system2LongEntry: number | null;
  system2ShortEntry: number | null;
  system2LongExit: number | null;
  system2ShortExit: number | null;
}

export interface ClassicTurtleEntry {
  date: string;
  side: TurtleSide;
  price: number;
  shares: number;
  unit: number;
  n: number;
  /** 初回エントリーか、追加エントリーか。 */
  kind: 'initial' | 'pyramid';
}

export interface ClassicTurtleExit {
  date: string;
  price: number;
  reason: TurtleExitReason;
}

export interface ClassicTurtleTrade {
  system: TurtleSystem;
  side: TurtleSide;
  entries: ClassicTurtleEntry[];
  exit: ClassicTurtleExit | null;
  /** 決済済みなら実現損益、未決済なら直近終値による評価損益。 */
  pnl: number;
  /** 初回ユニットの1Rを基準にした損益。 */
  riskMultiple: number;
}

export interface ClassicTurtleDay {
  date: string;
  indicator: ClassicTurtleIndicator;
  position: ClassicTurtlePosition | null;
  entry: ClassicTurtleEntry | null;
  exit: ClassicTurtleExit | null;
  system1EntrySkipped: boolean;
  ambiguous: boolean;
}

export interface ClassicTurtlePosition {
  system: TurtleSystem;
  side: TurtleSide;
  entries: ClassicTurtleEntry[];
  initialN: number;
  stopPrice: number;
  nextAddPrice: number | null;
}

export interface ClassicTurtleBacktest {
  indicators: ClassicTurtleIndicator[];
  days: ClassicTurtleDay[];
  trades: ClassicTurtleTrade[];
  /** System 1の利益トレード後に、次のSystem 1シグナルをスキップする状態か。 */
  system1EntryBlocked: boolean;
}

export interface ClassicTurtleSqn {
  /** SQNの対象になった完了取引数。 */
  tradeCount: number;
  /** R倍率の平均。 */
  meanRiskMultiple: number;
  /** R倍率の標本標準偏差。 */
  standardDeviation: number;
  /** meanRiskMultiple × √tradeCount ÷ standardDeviation。 */
  value: number;
}

/** 取引方向フィルターを適用する。`both` は全方向を返す。 */
export function filterClassicTurtleTrades(
  trades: ClassicTurtleTrade[],
  side: ClassicTradeSideFilter,
): ClassicTurtleTrade[] {
  if (side === 'both') return trades;
  return trades.filter(trade => trade.side === side);
}

interface InternalPosition {
  system: TurtleSystem;
  side: TurtleSide;
  entries: ClassicTurtleEntry[];
  initialN: number;
  stopPrice: number;
  nextAddPrice: number | null;
  tradeIndex: number;
}

interface PreparedBar {
  high: number;
  low: number;
  close: number;
  open: number;
}

function positiveInt(value: number | undefined, fallback: number): number {
  return Number.isInteger(value) && (value as number) > 0 ? (value as number) : fallback;
}

function finitePositive(value: number | undefined, fallback: number): number {
  return Number.isFinite(value) && (value as number) > 0 ? (value as number) : fallback;
}

function prepareBars(bars: Bar[]): PreparedBar[] {
  return bars.map(bar => {
    const close = Number(bar.close);
    const open = Number(bar.open ?? close);
    const high = Number(bar.high ?? close);
    const low = Number(bar.low ?? close);
    return {
      open: Number.isFinite(open) ? open : close,
      high: Number.isFinite(high) ? high : close,
      low: Number.isFinite(low) ? low : close,
      close,
    };
  });
}

function priorHigh(values: PreparedBar[], endExclusive: number, days: number): number | null {
  if (endExclusive < days) return null;
  let result = -Infinity;
  for (let i = endExclusive - days; i < endExclusive; i++) result = Math.max(result, values[i].high);
  return result;
}

function priorLow(values: PreparedBar[], endExclusive: number, days: number): number | null {
  if (endExclusive < days) return null;
  let result = Infinity;
  for (let i = endExclusive - days; i < endExclusive; i++) result = Math.min(result, values[i].low);
  return result;
}

function computeN(bars: PreparedBar[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(bars.length).fill(null);
  const tr: number[] = new Array(bars.length);
  for (let i = 0; i < bars.length; i++) {
    tr[i] = i === 0
      ? bars[i].high - bars[i].low
      : Math.max(
          bars[i].high - bars[i].low,
          Math.abs(bars[i].high - bars[i - 1].close),
          Math.abs(bars[i].low - bars[i - 1].close),
        );
  }
  if (bars.length < period) return result;
  let sum = 0;
  for (let i = 0; i < period; i++) sum += tr[i];
  result[period - 1] = sum / period;
  for (let i = period; i < bars.length; i++) {
    result[i] = ((result[i - 1] as number) * (period - 1) + tr[i]) / period;
  }
  return result;
}

export function computeClassicTurtleIndicators(
  bars: Bar[],
  params: Pick<ClassicTurtleParams, 'nPeriod' | 'system1EntryDays' | 'system1ExitDays' | 'system2EntryDays' | 'system2ExitDays'> = {},
): ClassicTurtleIndicator[] {
  const nPeriod = positiveInt(params.nPeriod, 20);
  const s1Entry = positiveInt(params.system1EntryDays, 20);
  const s1Exit = positiveInt(params.system1ExitDays, 10);
  const s2Entry = positiveInt(params.system2EntryDays, 55);
  const s2Exit = positiveInt(params.system2ExitDays, 20);
  const values = prepareBars(bars);
  const ns = computeN(values, nPeriod);
  return bars.map((bar, i) => ({
    date: bar.date,
    n: ns[i],
    system1LongEntry: priorHigh(values, i, s1Entry),
    system1ShortEntry: priorLow(values, i, s1Entry),
    system1LongExit: priorLow(values, i, s1Exit),
    system1ShortExit: priorHigh(values, i, s1Exit),
    system2LongEntry: priorHigh(values, i, s2Entry),
    system2ShortEntry: priorLow(values, i, s2Entry),
    system2LongExit: priorLow(values, i, s2Exit),
    system2ShortExit: priorHigh(values, i, s2Exit),
  }));
}

/** 1ユニットの株数。資金の1%をN×ポイント価値に割り当てる。 */
export function computeClassicUnitShares(
  accountEquity: number,
  n: number,
  pointValue = 1,
  lotSize = 1,
): number {
  if (!Number.isFinite(accountEquity) || accountEquity <= 0) return 0;
  if (!Number.isFinite(n) || n <= 0 || !Number.isFinite(pointValue) || pointValue <= 0) return 0;
  const lot = finitePositive(lotSize, 1);
  return Math.floor((accountEquity * 0.01) / (n * pointValue) / lot) * lot;
}

function executionPrice(bar: PreparedBar, trigger: number, side: TurtleSide, isStop: boolean): number {
  // ギャップでトリガーを飛び越えた場合は始値で約定する。
  if (side === 'long') {
    if (isStop) return bar.open <= trigger ? bar.open : trigger;
    return bar.open >= trigger ? bar.open : trigger;
  }
  if (isStop) return bar.open >= trigger ? bar.open : trigger;
  return bar.open <= trigger ? bar.open : trigger;
}

function positionView(position: InternalPosition): ClassicTurtlePosition {
  return {
    system: position.system,
    side: position.side,
    entries: position.entries.map(entry => ({ ...entry })),
    initialN: position.initialN,
    stopPrice: position.stopPrice,
    nextAddPrice: position.nextAddPrice,
  };
}

function totalPnl(trade: ClassicTurtleTrade, exitPrice: number, pointValue: number): number {
  return trade.entries.reduce((sum, entry) => {
    const difference = trade.side === 'long' ? exitPrice - entry.price : entry.price - exitPrice;
    return sum + difference * entry.shares * pointValue;
  }, 0);
}

function tradeRisk(trade: ClassicTurtleTrade, pointValue: number): number {
  const first = trade.entries[0];
  return first ? first.n * first.shares * pointValue : 0;
}

/** 完了取引のR倍率からSystem Quality Number (SQN)を計算する。 */
export function computeClassicTurtleSqn(trades: ClassicTurtleTrade[]): ClassicTurtleSqn | null {
  const riskMultiples = trades
    .filter(trade => trade.exit !== null && Number.isFinite(trade.riskMultiple))
    .map(trade => trade.riskMultiple);
  const tradeCount = riskMultiples.length;
  if (tradeCount < 2) return null;

  const meanRiskMultiple = riskMultiples.reduce((sum, value) => sum + value, 0) / tradeCount;
  const variance = riskMultiples.reduce(
    (sum, value) => sum + (value - meanRiskMultiple) ** 2,
    0,
  ) / (tradeCount - 1);
  const standardDeviation = Math.sqrt(variance);
  if (standardDeviation === 0) return null;

  return {
    tradeCount,
    meanRiskMultiple,
    standardDeviation,
    value: meanRiskMultiple * Math.sqrt(tradeCount) / standardDeviation,
  };
}

function makeTrade(position: InternalPosition): ClassicTurtleTrade {
  return {
    system: position.system,
    side: position.side,
    // ポジションへの追加エントリーを取引履歴にも即時反映するため、
    // バックテスト中は同じ配列を共有する。返却時の利用者側での変更は
    // 想定しない純粋な計算結果として扱う。
    entries: position.entries,
    exit: null,
    pnl: 0,
    riskMultiple: 0,
  };
}

/** 古典タートルズを日足OHLCで再現する。 */
export function backtestClassicTurtle(
  bars: Bar[],
  params: ClassicTurtleParams = {},
): ClassicTurtleBacktest {
  const pointValue = finitePositive(params.pointValue, 1);
  const maxUnits = positiveInt(params.maxUnits, 4);
  const indicators = computeClassicTurtleIndicators(bars, params);
  const values = prepareBars(bars);
  const trades: ClassicTurtleTrade[] = [];
  const days: ClassicTurtleDay[] = [];
  let position: InternalPosition | null = null;
  let system1EntryBlocked = false;

  const closePosition = (
    index: number,
    price: number,
    reason: TurtleExitReason,
  ): ClassicTurtleExit => {
    const current = position as InternalPosition;
    const trade = trades[current.tradeIndex];
    const exit: ClassicTurtleExit = { date: bars[index].date, price, reason };
    trade.exit = exit;
    trade.pnl = totalPnl(trade, price, pointValue);
    const risk = tradeRisk(trade, pointValue);
    trade.riskMultiple = risk > 0 ? trade.pnl / risk : 0;
    if (trade.system === 'system1') system1EntryBlocked = trade.pnl > 0;
    position = null;
    return exit;
  };

  for (let i = 0; i < bars.length; i++) {
    const row = indicators[i];
    const bar = values[i];
    let entry: ClassicTurtleEntry | null = null;
    let exit: ClassicTurtleExit | null = null;
    let system1EntrySkipped = false;
    let ambiguous = false;

    if (position !== null) {
      const isLong = position.side === 'long';
      const stopHit = isLong ? bar.low <= position.stopPrice : bar.high >= position.stopPrice;
      const channel = isLong
        ? (position.system === 'system1' ? row.system1LongExit : row.system2LongExit)
        : (position.system === 'system1' ? row.system1ShortExit : row.system2ShortExit);
      const channelHit = channel !== null && (isLong ? bar.low <= channel : bar.high >= channel);

      if (stopHit || channelHit) {
        // 同一バーで両方に到達した場合はストップを優先する。
        const trigger = stopHit ? position.stopPrice : (channel as number);
        const isStop = stopHit;
        const price = executionPrice(bar, trigger, position.side, isStop);
        exit = closePosition(i, price, isStop ? 'stop' : 'channel');
      } else if (position !== null && position.nextAddPrice !== null && position.entries.length < maxUnits) {
        // 追加注文は既存のストップ / 決済を確認した後に評価する。
        const favorable = position.side === 'long'
          ? bar.high >= position.nextAddPrice
          : bar.low <= position.nextAddPrice;
        if (favorable) {
          const addPrice = executionPrice(bar, position.nextAddPrice, position.side, false);
          const add: ClassicTurtleEntry = {
            date: bars[i].date,
            side: position.side,
            price: addPrice,
            shares: position.entries[0].shares,
            unit: position.entries.length + 1,
            n: position.initialN,
            kind: 'pyramid',
          };
          position.entries.push(add);
          position.stopPrice = position.side === 'long'
            ? addPrice - 2 * position.initialN
            : addPrice + 2 * position.initialN;
          position.nextAddPrice = position.entries.length < maxUnits
            ? (position.side === 'long'
                ? addPrice + 0.5 * position.initialN
                : addPrice - 0.5 * position.initialN)
            : null;
          entry = add;
        }
      }
    }

    if (position === null && exit === null && row.n !== null && row.n > 0) {
      const candidates: { system: TurtleSystem; side: TurtleSide; price: number }[] = [];
      const s1Long = row.system1LongEntry !== null && bar.high >= row.system1LongEntry;
      const s1Short = row.system1ShortEntry !== null && bar.low <= row.system1ShortEntry;
      const s2Long = row.system2LongEntry !== null && bar.high >= row.system2LongEntry;
      const s2Short = row.system2ShortEntry !== null && bar.low <= row.system2ShortEntry;

      if (s1Long && !system1EntryBlocked) candidates.push({ system: 'system1', side: 'long', price: row.system1LongEntry as number });
      else if (s1Long && system1EntryBlocked) {
        system1EntrySkipped = true;
        system1EntryBlocked = false;
      }
      if (s1Short && !system1EntryBlocked) candidates.push({ system: 'system1', side: 'short', price: row.system1ShortEntry as number });
      else if (s1Short && system1EntryBlocked) {
        system1EntrySkipped = true;
        system1EntryBlocked = false;
      }
      if (s2Long) candidates.push({ system: 'system2', side: 'long', price: row.system2LongEntry as number });
      if (s2Short) candidates.push({ system: 'system2', side: 'short', price: row.system2ShortEntry as number });

      const sides = new Set(candidates.map(candidate => candidate.side));
      if (sides.size > 1) {
        ambiguous = true;
      } else if (candidates.length > 0) {
        // 同方向で複数Systemが同時成立した場合は短期のSystem 1を優先。
        const candidate = candidates.find(item => item.system === 'system1') ?? candidates[0];
        if (candidate.system === 'system2') system1EntryBlocked = false;
        const price = executionPrice(bar, candidate.price, candidate.side, false);
        const shares = computeClassicUnitShares(
          params.accountEquity ?? 0,
          row.n,
          pointValue,
          params.lotSize ?? 1,
        );
        const initial: ClassicTurtleEntry = {
          date: bars[i].date,
          side: candidate.side,
          price,
          shares,
          unit: 1,
          n: row.n,
          kind: 'initial',
        };
        const nextAddPrice = candidate.side === 'long'
          ? price + 0.5 * row.n
          : price - 0.5 * row.n;
        position = {
          system: candidate.system,
          side: candidate.side,
          entries: [initial],
          initialN: row.n,
          stopPrice: candidate.side === 'long' ? price - 2 * row.n : price + 2 * row.n,
          nextAddPrice,
          tradeIndex: trades.length,
        };
        trades.push(makeTrade(position));
        entry = initial;
      }
    }

    if (position !== null) {
      const trade = trades[position.tradeIndex];
      trade.pnl = trade.entries.reduce((sum, item) => {
        const difference = position?.side === 'long' ? bar.close - item.price : item.price - bar.close;
        return sum + difference * item.shares * pointValue;
      }, 0);
      const risk = tradeRisk(trade, pointValue);
      trade.riskMultiple = risk > 0 ? trade.pnl / risk : 0;
    }

    days.push({
      date: bars[i].date,
      indicator: row,
      position: position === null ? null : positionView(position),
      entry,
      exit,
      system1EntrySkipped,
      ambiguous,
    });
  }

  if (position !== null && bars.length > 0) {
    const lastIndex = bars.length - 1;
    const trade = trades[position.tradeIndex];
    const lastClose = values[lastIndex].close;
    const finalExit: ClassicTurtleExit = {
      date: bars[lastIndex].date,
      price: lastClose,
      reason: 'end_of_data',
    };
    trade.exit = finalExit;
    trade.pnl = totalPnl(trade, lastClose, pointValue);
    const risk = tradeRisk(trade, pointValue);
    trade.riskMultiple = risk > 0 ? trade.pnl / risk : 0;
    const day = days[lastIndex];
    day.exit = finalExit;
    day.position = null;
    position = null;
  }

  return { indicators, days, trades, system1EntryBlocked };
}

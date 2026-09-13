// turtleState.ts モジュールのユニットテスト (Issue #53)
//
// 銘柄ごとのタートル戦略状態（口座資金 / ブレイク日 / 買値 / ATR 期間）の
// 保存・読取・削除、バリデーション、破損データ時のサニタイズ挙動を固定する。
// Node 環境（jsdom なし）でも動作するよう Storage を in-memory 実装で注入する。

import { beforeEach, describe, expect, it } from 'vitest';
import {
  TURTLE_STATE_STORAGE_KEY,
  buildTurtleState,
  clearTurtleState,
  loadAllTurtleStates,
  normalizeTurtleSymbol,
  saveTurtleState,
  sanitizeTurtleState,
  type TurtleState,
} from './turtleState';

/** in-memory の Storage 実装（vitest は node 環境のため localStorage が存在しない）。 */
class MemoryStorage implements Storage {
  private map = new Map<string, string>();
  getItem(key: string): string | null {
    return this.map.has(key) ? this.map.get(key)! : null;
  }
  setItem(key: string, value: string): void {
    this.map.set(key, String(value));
  }
  removeItem(key: string): void {
    this.map.delete(key);
  }
  clear(): void {
    this.map.clear();
  }
  key(index: number): string | null {
    return Array.from(this.map.keys())[index] ?? null;
  }
  get length(): number {
    return this.map.size;
  }
}

const STORAGE = new MemoryStorage();

// 各テスト間でストレージを共有するため、テスト毎に初期化する
beforeEach(() => STORAGE.clear());

const validState: TurtleState = {
  accountValue: 1000000,
  breakoutDate: '2026-09-01',
  buyPrice: 150,
  atrPeriod: 20,
};

describe('normalizeTurtleSymbol', () => {
  it('trim + 大文字化する', () => {
    expect(normalizeTurtleSymbol(' aapl ')).toBe('AAPL');
    expect(normalizeTurtleSymbol('brk-b')).toBe('BRK-B');
    expect(normalizeTurtleSymbol('   ')).toBe('');
  });
});

describe('buildTurtleState: バリデーション', () => {
  it('完全指定の入力は state を返す', () => {
    const r = buildTurtleState({
      accountValue: 1000000,
      breakoutDate: '2026-09-01',
      buyPrice: 150,
      atrPeriod: 20,
    });
    expect(r).toEqual({ ok: true, state: validState });
  });

  it('全項目空欄は null 状態として許容する（未指定の保存）', () => {
    const r = buildTurtleState({
      accountValue: '',
      breakoutDate: null,
      buyPrice: null,
      atrPeriod: 14,
    });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.state).toEqual({
        accountValue: null,
        breakoutDate: null,
        buyPrice: null,
        atrPeriod: 14,
      });
    }
  });

  it('文字列数値（v-model.number で空欄が空文字になる入力）を数値化する', () => {
    const r = buildTurtleState({
      accountValue: '500000',
      breakoutDate: null,
      buyPrice: '100.5',
      atrPeriod: 20,
    });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.state.accountValue).toBe(500000);
      expect(r.state.buyPrice).toBe(100.5);
    }
  });

  it.each([
    ['口座資金', { accountValue: 'abc' as unknown as number, breakoutDate: null, buyPrice: null, atrPeriod: 20 }],
    ['買値', { accountValue: null, breakoutDate: null, buyPrice: 'abc', atrPeriod: 20 }],
  ] as const)('%sが数値でない場合はエラー', (_label, input) => {
    const r = buildTurtleState(input);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain('有効な数値');
  });

  it('口座資金が負の場合はエラー', () => {
    const r = buildTurtleState({ accountValue: -100, breakoutDate: null, buyPrice: null, atrPeriod: 20 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain('0 以上');
  });

  it('口座資金は 0 を許容する', () => {
    const r = buildTurtleState({ accountValue: 0, breakoutDate: null, buyPrice: null, atrPeriod: 20 });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.state.accountValue).toBe(0);
  });

  it('買値が 0 または負の場合はエラー（正の数値を要求）', () => {
    for (const bad of [0, -5]) {
      const r = buildTurtleState({ accountValue: null, breakoutDate: null, buyPrice: bad, atrPeriod: 20 });
      expect(r.ok).toBe(false);
      if (!r.ok) expect(r.error).toContain('正の数');
    }
  });

  it('ブレイク日が YYYY-MM-DD 形式でない場合はエラー', () => {
    const r = buildTurtleState({
      accountValue: null,
      breakoutDate: '09/01/2026',
      buyPrice: null,
      atrPeriod: 20,
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain('YYYY-MM-DD');
  });

  it('ブレイク日が前後空白のみは空欄（null）として扱う', () => {
    const r = buildTurtleState({
      accountValue: null,
      breakoutDate: '   ',
      buyPrice: null,
      atrPeriod: 20,
    });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.state.breakoutDate).toBeNull();
  });

  it.each([10, 30, 0, -1, 14.5])('ATR 期間が %s の場合はエラー（14/20 のみ）', (atrPeriod) => {
    const r = buildTurtleState({
      accountValue: null,
      breakoutDate: null,
      buyPrice: null,
      atrPeriod,
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain('14 または 20');
  });
});

describe('sanitizeTurtleState: 破損データ', () => {
  it('有効なオブジェクトはそのまま返す', () => {
    expect(sanitizeTurtleState(validState)).toEqual(validState);
  });

  it('null / 配列 / スカラーは null', () => {
    expect(sanitizeTurtleState(null)).toBeNull();
    expect(sanitizeTurtleState([])).toBeNull();
    expect(sanitizeTurtleState(42)).toBeNull();
    expect(sanitizeTurtleState('AAPL')).toBeNull();
  });

  it('atrPeriod が 14/20 でない場合は null', () => {
    expect(sanitizeTurtleState({ ...validState, atrPeriod: 10 })).toBeNull();
    expect(sanitizeTurtleState({ ...validState, atrPeriod: '20' })).toBeNull();
  });

  it('accountValue / buyPrice が数値でない場合は null', () => {
    expect(sanitizeTurtleState({ ...validState, accountValue: '1000' })).toBeNull();
    expect(sanitizeTurtleState({ ...validState, buyPrice: NaN })).toBeNull();
    expect(sanitizeTurtleState({ ...validState, buyPrice: 0 })).toBeNull();
  });

  it('breakoutDate が文字列でない / 形式不正の場合は null', () => {
    expect(sanitizeTurtleState({ ...validState, breakoutDate: 20260901 })).toBeNull();
    expect(sanitizeTurtleState({ ...validState, breakoutDate: '2026-9-1' })).toBeNull();
  });
});

describe('save / load / clear: localStorage への往復', () => {
  it('保存した状態は読み戻せる（シンボルは大文字に正規化される）', () => {
    saveTurtleState(' aapl ', validState, STORAGE);
    const all = loadAllTurtleStates(STORAGE);
    expect(Object.keys(all)).toEqual(['AAPL']);
    expect(all['AAPL']).toEqual(validState);
  });

  it('複数銘柄を個別に保存できる', () => {
    saveTurtleState('AAPL', validState, STORAGE);
    saveTurtleState('MSFT', { ...validState, buyPrice: 300, atrPeriod: 14 }, STORAGE);
    const all = loadAllTurtleStates(STORAGE);
    expect(all['AAPL']).toEqual(validState);
    expect(all['MSFT']).toEqual({ ...validState, buyPrice: 300, atrPeriod: 14 });
  });

  it('同じ銘柄への再保存は上書きする', () => {
    saveTurtleState('AAPL', validState, STORAGE);
    saveTurtleState('AAPL', { ...validState, buyPrice: 200 }, STORAGE);
    const all = loadAllTurtleStates(STORAGE);
    expect(all['AAPL']).toEqual({ ...validState, buyPrice: 200 });
    expect(Object.keys(all)).toEqual(['AAPL']);
  });

  it('clearTurtleState は対象銘柄のみ削除する', () => {
    saveTurtleState('AAPL', validState, STORAGE);
    saveTurtleState('MSFT', validState, STORAGE);
    clearTurtleState('aapl', STORAGE); // 小文字指定でも大文字キーから削除
    const all = loadAllTurtleStates(STORAGE);
    expect(all['AAPL']).toBeUndefined();
    expect(all['MSFT']).toEqual(validState);
  });

  it('未保存銘柄の clear は何もしない（エラーにもならない）', () => {
    expect(() => clearTurtleState('NONE', STORAGE)).not.toThrow();
  });

  it('無効なシンボル（空白のみ）の保存は Error を投げる', () => {
    expect(() => saveTurtleState('   ', validState, STORAGE)).toThrow('無効なシンボルです');
  });

  it('ストレージ指定なし（Node 環境）では読み取りは空 / 保存は Error', () => {
    expect(loadAllTurtleStates(null)).toEqual({});
    expect(() => saveTurtleState('AAPL', validState, null)).toThrow('ブラウザのストレージが利用できません');
  });
});

describe('loadAllTurtleStates: 破損ストレージデータ', () => {
  it('空のストレージは {} を返す', () => {
    expect(loadAllTurtleStates(new MemoryStorage())).toEqual({});
  });

  it('不正な JSON は無視して {} を返す', () => {
    STORAGE.setItem(TURTLE_STATE_STORAGE_KEY, '{oops');
    expect(loadAllTurtleStates(STORAGE)).toEqual({});
  });

  it('オブジェクトでない JSON（配列 / スカラー）は無視する', () => {
    STORAGE.setItem(TURTLE_STATE_STORAGE_KEY, '[1,2]');
    expect(loadAllTurtleStates(STORAGE)).toEqual({});
    STORAGE.setItem(TURTLE_STATE_STORAGE_KEY, '42');
    expect(loadAllTurtleStates(STORAGE)).toEqual({});
  });

  it('不正な項目は除外し、有効な項目のみ残す（キーは大文字正規化）', () => {
    STORAGE.setItem(
      TURTLE_STATE_STORAGE_KEY,
      JSON.stringify({
        AAPL: validState,
        bad1: { atrPeriod: 10, accountValue: null, breakoutDate: null, buyPrice: null },
        bad2: { atrPeriod: 20, accountValue: -5, breakoutDate: null, buyPrice: null },
        msft: { ...validState, atrPeriod: 14 },
        '': { atrPeriod: 20, accountValue: null, breakoutDate: null, buyPrice: null },
      }),
    );
    const all = loadAllTurtleStates(STORAGE);
    expect(Object.keys(all).sort()).toEqual(['AAPL', 'MSFT']);
    expect(all['AAPL']).toEqual(validState);
    expect(all['MSFT'].atrPeriod).toBe(14);
  });
});


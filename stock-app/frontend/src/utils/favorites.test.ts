// favorites.ts モジュールのユニットテスト (Issue #50)
//
// シンボル検証とお気に入りリスト操作（純関数）の挙動を固定する:
// バックエンドのバリデーション・ステータスコードと整合したメッセージ生成。

import { describe, expect, it } from 'vitest';
import {
  SYMBOL_PATTERN,
  addFavorite,
  favoriteErrorMessage,
  getFavorite,
  indexOfFavorite,
  isValidSymbol,
  removeFavorite,
} from './favorites';
import type { FavoriteEntry } from './favorites';

const FAVORITES: FavoriteEntry[] = [
  { symbol: 'AAPL', name: 'Apple Inc.' },
  { symbol: 'MSFT', name: 'Microsoft Corporation' },
];

describe('SYMBOL_PATTERN / isValidSymbol', () => {
  it('バックエンドと一致する有効なシンボルを受け入れる', () => {
    expect(SYMBOL_PATTERN.test('AAPL')).toBe(true);
    expect(isValidSymbol('AAPL')).toBe(true);
    // 小文字・前後空白は正規化して検証する
    expect(isValidSymbol(' aapl ')).toBe(true);
    // ドット・ハイフン・ハット・イコールを含むシンボル（ETF / インデックス等）
    expect(isValidSymbol('BRK.B')).toBe(true);
    expect(isValidSymbol('SPY-USD')).toBe(true);
    expect(isValidSymbol('^GSPC')).toBe(true);
    expect(isValidSymbol('=10Y')).toBe(true);
  });

  it('無効なシンボルを拒否する', () => {
    expect(isValidSymbol('')).toBe(false);
    expect(isValidSymbol('A'.repeat(11))).toBe(false);
    expect(isValidSymbol('BAD SYMBOL')).toBe(false);
    expect(isValidSymbol('AAPL!')).toBe(false);
    expect(isValidSymbol('aapl;drop')).toBe(false);
  });
});

describe('indexOfFavorite / getFavorite', () => {
  it('大文字・小文字を無視して位置・エントリを探す', () => {
    expect(indexOfFavorite(FAVORITES, 'aapl')).toBe(0);
    expect(indexOfFavorite(FAVORITES, ' msft ')).toBe(1);
    expect(indexOfFavorite(FAVORITES, 'NOSUCH')).toBe(-1);
    expect(getFavorite(FAVORITES, 'AAPL')).toEqual({ symbol: 'AAPL', name: 'Apple Inc.' });
    expect(getFavorite(FAVORITES, 'NOSUCH')).toBeNull();
  });
});

describe('addFavorite', () => {
  it('末尾に大文字正規化されたエントリを追加する', () => {
    const next = addFavorite(FAVORITES, 'goog', 'Alphabet Inc.');
    expect(next).toHaveLength(3);
    expect(next[2]).toEqual({ symbol: 'GOOG', name: 'Alphabet Inc.' });
    // 元のリストは不変（純関数）
    expect(FAVORITES).toHaveLength(2);
  });

  it('既登録シンボル（小文字指定含む）はリストを変更しない', () => {
    expect(addFavorite(FAVORITES, 'AAPL', 'Duplicate')).toBe(FAVORITES);
    expect(addFavorite(FAVORITES, 'msft', 'Duplicate')).toBe(FAVORITES);
  });
});

describe('removeFavorite', () => {
  it('指定シンボルを削除したコピーを返す（元リストは不変）', () => {
    const next = removeFavorite(FAVORITES, 'aapl');
    expect(next).toEqual([FAVORITES[1]]);
    expect(FAVORITES).toHaveLength(2);
  });

  it('未登録シンボルはリストを変更しない', () => {
    expect(removeFavorite(FAVORITES, 'NOSUCH')).toBe(FAVORITES);
  });
});

describe('favoriteErrorMessage', () => {
  it('ステータスコードに応じたメッセージを返す', () => {
    expect(favoriteErrorMessage(400, 'invalid symbol: X')).toBe(
      'お気に入りに追加できません: invalid symbol: X',
    );
    expect(favoriteErrorMessage(400)).toBe('お気に入りに追加できません');
    expect(favoriteErrorMessage(409)).toBe('この銘柄は既にお気に入りに登録されています');
    expect(favoriteErrorMessage(undefined)).toContain('通信エラー');
    expect(favoriteErrorMessage(502)).toContain('502');
  });
});
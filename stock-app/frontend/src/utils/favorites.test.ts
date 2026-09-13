// favorites.ts モジュールのユニットテスト (Issue #50)
//
// シンボル検証・リスト操作（純関数）・バックエンド API ヘルパーの挙動を固定する:
// バックエンドのバリデーション・ステータスコードと整合したメッセージ生成。

import axios from 'axios';
import { describe, expect, it, vi } from 'vitest';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import {
  LIST_NAME_MAX_LENGTH,
  SYMBOL_PATTERN,
  addFavoriteStock,
  addStockToList,
  createFavoriteList,
  deleteFavoriteList,
  favoriteErrorMessage,
  fetchFavoriteGroups,
  fetchFavoriteLists,
  indexOfStock,
  isStockInList,
  isValidListName,
  isValidSymbol,
  removeFavoriteStock,
  removeStockFromList,
  renameFavoriteList,
} from './favorites';
import type { FavoriteEntry, FavoriteGroup } from './favorites';

const STOCKS: FavoriteEntry[] = [
  { symbol: 'AAPL', name: 'Apple Inc.' },
  { symbol: 'MSFT', name: 'Microsoft Corporation' },
];

const GROUPS: FavoriteGroup[] = [
  { id: 1, name: 'リスト1', stocks: STOCKS },
  { id: 2, name: 'リスト2', stocks: [] },
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

describe('isValidListName', () => {
  it('trim 後に空でなく 50 字以内の名前を受け入れる', () => {
    expect(isValidListName('私のリスト')).toBe(true);
    expect(isValidListName(` ${'A'.repeat(LIST_NAME_MAX_LENGTH)} `)).toBe(true);
    expect(isValidListName('A'.repeat(LIST_NAME_MAX_LENGTH))).toBe(true);
  });

  it('空文字（空白のみ）・50 字超過の名前を拒否する', () => {
    expect(isValidListName('')).toBe(false);
    expect(isValidListName('   ')).toBe(false);
    expect(isValidListName('A'.repeat(LIST_NAME_MAX_LENGTH + 1))).toBe(false);
  });
});

describe('indexOfStock / isStockInList', () => {
  it('大文字・小文字を無視して位置・所属を探す', () => {
    expect(indexOfStock(STOCKS, 'aapl')).toBe(0);
    expect(indexOfStock(STOCKS, ' msft ')).toBe(1);
    expect(indexOfStock(STOCKS, 'NOSUCH')).toBe(-1);
    expect(isStockInList(STOCKS, 'AAPL')).toBe(true);
    expect(isStockInList(STOCKS, 'NOSUCH')).toBe(false);
    expect(isStockInList([], 'AAPL')).toBe(false);
  });
});

describe('addStockToList', () => {
  it('対象リストの末尾に大文字正規化されたエントリを追加する（元リストは不変）', () => {
    const next = addStockToList(GROUPS, 2, 'goog', 'Alphabet Inc.');
    expect(next).toHaveLength(2);
    expect(next[0]).toBe(GROUPS[0]); // 他リストは同一参照のまま
    expect(next[1]?.stocks).toEqual([{ symbol: 'GOOG', name: 'Alphabet Inc.' }]);
    expect(GROUPS[1].stocks).toHaveLength(0);
  });

  it('既登録シンボル・存在しないリスト ID ではリストを変更しない', () => {
    expect(addStockToList(GROUPS, 1, 'AAPL', 'Duplicate')).toBe(GROUPS);
    expect(addStockToList(GROUPS, 1, 'msft', 'Duplicate')).toBe(GROUPS);
    expect(addStockToList(GROUPS, 999, 'AAPL')).toBe(GROUPS);
  });
});

describe('removeStockFromList', () => {
  it('対象リストから指定シンボルを削除する（元リストは不変）', () => {
    const next = removeStockFromList(GROUPS, 1, 'aapl');
    expect(next[0]?.stocks).toEqual([STOCKS[1]]);
    expect(next[1]).toBe(GROUPS[1]);
    expect(GROUPS[0].stocks).toHaveLength(2);
  });

  it('未登録シンボル・存在しないリスト ID ではリストを変更しない', () => {
    expect(removeStockFromList(GROUPS, 1, 'NOSUCH')).toBe(GROUPS);
    expect(removeStockFromList(GROUPS, 999, 'AAPL')).toBe(GROUPS);
  });
});

describe('favoriteErrorMessage', () => {
  it('ステータスコードに応じたメッセージを返す', () => {
    expect(favoriteErrorMessage(400, 'invalid symbol: X')).toBe(
      'お気に入りに追加できません: invalid symbol: X',
    );
    expect(favoriteErrorMessage(400)).toBe('お気に入りに追加できません');
    expect(favoriteErrorMessage(404)).toContain('リストが存在しません');
    expect(favoriteErrorMessage(409)).toBe('この銘柄は既にこのリストに登録されています');
    expect(favoriteErrorMessage(undefined)).toContain('通信エラー');
    expect(favoriteErrorMessage(502)).toContain('502');
  });
});

// =====================================================================
// バックエンド API ヘルパー（axios をモックして URL・ペイロードを確認）
// =====================================================================
describe('API ヘルパー', () => {
  const getMock = axios.get as unknown as ReturnType<typeof vi.fn>;
  const postMock = axios.post as unknown as ReturnType<typeof vi.fn>;
  const patchMock = axios.patch as unknown as ReturnType<typeof vi.fn>;
  const deleteMock = axios.delete as unknown as ReturnType<typeof vi.fn>;

  it('fetchFavoriteLists は GET /api/favorite-lists/ を呼ぶ', async () => {
    const payload = [{ id: 1, name: 'リスト1', count: 2 }];
    getMock.mockResolvedValueOnce({ data: payload });
    const lists = await fetchFavoriteLists();
    expect(getMock).toHaveBeenCalledWith('/api/favorite-lists/');
    expect(lists).toEqual(payload);
  });

  it('fetchFavoriteGroups は GET /api/favorites/ を呼び、空リストも保持する', async () => {
    const payload = [
      { id: 1, name: 'リスト1', stocks: STOCKS },
      { id: 2, name: 'リスト2', stocks: [] },
    ];
    getMock.mockResolvedValueOnce({ data: payload });
    const groups = await fetchFavoriteGroups();
    expect(getMock).toHaveBeenCalledWith('/api/favorites/');
    expect(groups).toEqual(payload);
    expect(groups[1]?.stocks).toEqual([]); // 空リストも一覧に含まれる
  });

  it('createFavoriteList は trim 済み名前を POST /api/favorite-lists/ に送る', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 11, name: '新リスト' } });
    const created = await createFavoriteList('  新リスト  ');
    expect(postMock).toHaveBeenCalledWith('/api/favorite-lists/', { name: '新リスト' });
    expect(created).toEqual({ id: 11, name: '新リスト' });
  });

  it('renameFavoriteList は PATCH /api/favorite-lists/<id>/ を呼ぶ', async () => {
    patchMock.mockResolvedValueOnce({ data: { id: 3, name: '変更後' } });
    const renamed = await renameFavoriteList(3, '  変更後  ');
    expect(patchMock).toHaveBeenCalledWith('/api/favorite-lists/3/', { name: '変更後' });
    expect(renamed).toEqual({ id: 3, name: '変更後' });
  });

  it('deleteFavoriteList は DELETE /api/favorite-lists/<id>/ を呼ぶ', async () => {
    deleteMock.mockResolvedValueOnce({ data: null });
    await deleteFavoriteList(5);
    expect(deleteMock).toHaveBeenCalledWith('/api/favorite-lists/5/');
  });

  it('addFavoriteStock は正規化済みシンボルと list_id を POST /api/favorites/ に送る', async () => {
    const payload = { symbol: 'GOOG', name: 'Alphabet Inc.', list_id: 1 };
    postMock.mockResolvedValueOnce({ data: payload });
    const entry = await addFavoriteStock(1, ' goog ');
    expect(postMock).toHaveBeenCalledWith('/api/favorites/', { symbol: 'GOOG', list_id: 1 });
    expect(entry).toEqual(payload);
  });

  it('removeFavoriteStock は DELETE /api/favorites/<list_id>/<symbol>/ を呼ぶ', async () => {
    deleteMock.mockResolvedValueOnce({ data: null });
    await removeFavoriteStock(2, ' aapl ');
    expect(deleteMock).toHaveBeenCalledWith('/api/favorites/2/AAPL/');
  });
});
"""古典タートルズのエントリーシグナル計算と保存。"""

from decimal import Decimal

from .models import ClassicTurtleSignal, StockRecord

STRATEGY_VERSION = 'classic-v1'
N_PERIOD = 20
SYSTEM1_ENTRY = 20
SYSTEM1_EXIT = 10
SYSTEM2_ENTRY = 55
SYSTEM2_EXIT = 20


def _number(value, fallback=Decimal('0')):
    if value is None:
        return fallback
    return Decimal(str(value))


def _prior_high(values, end, days):
    if end < days:
        return None
    return max(values[end - days:end])


def _prior_low(values, end, days):
    if end < days:
        return None
    return min(values[end - days:end])


def _indicators(records):
    highs = [_number(record.high, _number(record.close)) for record in records]
    lows = [_number(record.low, _number(record.close)) for record in records]
    closes = [_number(record.close) for record in records]
    true_ranges = []
    for index, _ in enumerate(records):
        if index == 0:
            true_ranges.append(highs[index] - lows[index])
        else:
            true_ranges.append(max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            ))

    ns = [None] * len(records)
    if len(records) >= N_PERIOD:
        ns[N_PERIOD - 1] = sum(true_ranges[:N_PERIOD]) / N_PERIOD
        for index in range(N_PERIOD, len(records)):
            ns[index] = ((ns[index - 1] * (N_PERIOD - 1)) + true_ranges[index]) / N_PERIOD

    return highs, lows, closes, ns


def calculate_signals(records):
    """日付昇順のStockRecordから、実際に成立したエントリーを返す。"""
    if not records:
        return []
    highs, lows, closes, ns = _indicators(records)
    signals = []
    position = None
    system1_blocked = False

    for index, record in enumerate(records):
        high = highs[index]
        low = lows[index]
        close = closes[index]
        open_price = _number(record.open, close)

        if position is not None:
            stop_hit = low <= position['stop'] if position['side'] == 'long' else high >= position['stop']
            channel = (
                _prior_low(lows, index, SYSTEM1_EXIT if position['system'] == 'system1' else SYSTEM2_EXIT)
                if position['side'] == 'long'
                else _prior_high(highs, index, SYSTEM1_EXIT if position['system'] == 'system1' else SYSTEM2_EXIT)
            )
            channel_hit = channel is not None and (low <= channel if position['side'] == 'long' else high >= channel)
            if stop_hit or channel_hit:
                trigger = position['stop'] if stop_hit else channel
                exit_price = (
                    min(open_price, trigger) if position['side'] == 'long'
                    else max(open_price, trigger)
                )
                pnl = sum(
                    exit_price - entry if position['side'] == 'long' else entry - exit_price
                    for entry in position['entries']
                )
                if position['system'] == 'system1':
                    system1_blocked = pnl > 0
                position = None
                continue

            if position['next_add'] is not None and position['units'] < 4:
                favorable = high >= position['next_add'] if position['side'] == 'long' else low <= position['next_add']
                if favorable:
                    add_price = min(open_price, position['next_add']) if position['side'] == 'long' else max(open_price, position['next_add'])
                    position['units'] += 1
                    position['entries'].append(add_price)
                    position['stop'] = add_price - 2 * position['n'] if position['side'] == 'long' else add_price + 2 * position['n']
                    position['next_add'] = (
                        add_price + Decimal('0.5') * position['n']
                        if position['side'] == 'long'
                        else add_price - Decimal('0.5') * position['n']
                    ) if position['units'] < 4 else None

        if position is not None or ns[index] is None or ns[index] <= 0:
            continue

        candidates = []
        s1_long = _prior_high(highs, index, SYSTEM1_ENTRY)
        s1_short = _prior_low(lows, index, SYSTEM1_ENTRY)
        s2_long = _prior_high(highs, index, SYSTEM2_ENTRY)
        s2_short = _prior_low(lows, index, SYSTEM2_ENTRY)
        if s1_long is not None and high >= s1_long:
            if not system1_blocked:
                candidates.append(('system1', 'long', s1_long))
            else:
                system1_blocked = False
        if s1_short is not None and low <= s1_short:
            if not system1_blocked:
                candidates.append(('system1', 'short', s1_short))
            else:
                system1_blocked = False
        if s2_long is not None and high >= s2_long:
            candidates.append(('system2', 'long', s2_long))
        if s2_short is not None and low <= s2_short:
            candidates.append(('system2', 'short', s2_short))

        sides = {candidate[1] for candidate in candidates}
        if len(sides) != 1 or not candidates:
            continue
        candidate = next((item for item in candidates if item[0] == 'system1'), candidates[0])
        system, side, trigger = candidate
        price = min(open_price, trigger) if side == 'long' else max(open_price, trigger)
        signals.append({
            'date': record.date,
            'system': system,
            'side': side,
            'price': price,
            'n': ns[index],
            'volume': record.volume,
            'turnover': close * record.volume if record.volume is not None else None,
        })
        position = {
            'system': system,
            'side': side,
            'n': ns[index],
            'units': 1,
            'entries': [price],
            'stop': price - 2 * ns[index] if side == 'long' else price + 2 * ns[index],
            'next_add': price + Decimal('0.5') * ns[index] if side == 'long' else price - Decimal('0.5') * ns[index],
        }
        if system == 'system2':
            system1_blocked = False
    return signals


def rebuild_symbol_signals(symbol):
    """指定銘柄の保存済み日足からシグナルを再構築する。"""
    records = list(StockRecord.objects.filter(symbol=symbol).order_by('date'))
    signals = calculate_signals(records)
    ClassicTurtleSignal.objects.filter(symbol=symbol, strategy_version=STRATEGY_VERSION).delete()
    ClassicTurtleSignal.objects.bulk_create([
        ClassicTurtleSignal(symbol=symbol, strategy_version=STRATEGY_VERSION, **signal)
        for signal in signals
    ])
    return len(signals)
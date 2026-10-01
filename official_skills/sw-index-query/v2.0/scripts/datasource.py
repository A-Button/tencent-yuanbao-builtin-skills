"""WeStock CLI adapter. Canonical SW keys stay six digits; no HTTP fallback."""

from __future__ import annotations
import json
import math
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from functools import lru_cache

SOURCE_NOTE = '数据来源：腾讯自选股（申万行业板块口径），行情可能有延迟，以交易所披露为准。'

class DataSourceError(RuntimeError):
    pass

class RateLimitError(DataSourceError):
    pass

class TransientDataSourceError(DataSourceError):
    pass

class UnsupportedCapabilityError(DataSourceError):
    pass

class IncompleteDataError(DataSourceError):
    pass


def to_symbol(code):
    code = str(code)
    if not re.fullmatch(r'\d{6}', code):
        raise ValueError('请输入六位申万代码；数据源前缀由适配层转换')
    n = int(code)
    if 807000 <= n < 809000 or 801271 <= n <= 801276 or 802608 <= n <= 802612:
        raise UnsupportedCapabilityError(f'{code}: westock 未覆盖基金/大类风格/金创指数，请使用获授权的申万官方数据源')
    if not code.startswith('801'):
        raise UnsupportedCapabilityError(f'{code}: 未登记的申万板块映射')
    return 'pt01' + code


def from_symbol(symbol):
    if not re.fullmatch(r'pt01\d{6}', str(symbol)):
        raise ValueError(f'未知板块代码: {symbol}')
    return symbol[4:]


def _run_cli_once(args):
    try:
        proc = subprocess.run([os.environ.get('WESTOCK_BIN', 'westock'), *args, '--raw'],
                              capture_output=True, text=True,
                              timeout=float(os.environ.get('SW_CLI_TIMEOUT', '90')))
    except FileNotFoundError as exc:
        raise DataSourceError('未安装 westock；请配置 WESTOCK_BIN 为已授权 CLI 路径') from exc
    except subprocess.TimeoutExpired as exc:
        raise TransientDataSourceError('westock 请求超时') from exc
    # Do not expose stderr or raw server URLs: CLI errors may contain credentials.
    if proc.returncode:
        raise TransientDataSourceError(f'westock {args[0]} 失败（退出码 {proc.returncode}）')
    try:
        payload = json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise DataSourceError('westock 返回非 JSON；请核验 CLI 版本及 --raw 支持') from exc
    if isinstance(payload, dict) and (payload.get('Success') is False or payload.get('success') is False or payload.get('error')):
        err = payload.get('error') or {}
        code = str(err.get('code','UNKNOWN')) if isinstance(err,dict) else 'UNKNOWN'
        code = code if re.fullmatch(r'[A-Z0-9_]+', code) else 'UNKNOWN'
        if code == 'LOCAL_RATE_LIMITED':
            raise RateLimitError('westock 本地请求额度已达上限（LOCAL_RATE_LIMITED）；等待CLI额度窗口恢复，不继续自动请求')
        raise TransientDataSourceError(f'westock {args[0]} 上游错误 {code}；请检查网络与 CLI 授权')
    return payload


def run_cli(args):
    try:
        return _run_cli_once(args)
    except TransientDataSourceError:
        time.sleep(0.5)
        return _run_cli_once(args)


def records(payload, symbols, nodes=False):
    """Accept batch envelopes and current single-symbol flat lists; never infer batch order."""
    if isinstance(payload, list):
        if len(symbols) == 1:
            return {symbols[0]: payload}
        result = {s: [] for s in symbols}
        for row in payload:
            symbol = row.get('symbol') or row.get('code') or row.get('IndustryCode')
            if symbol in result:
                result[symbol].append(row)
        return result
    if not isinstance(payload, dict) or not isinstance(payload.get('Data'), list):
        raise DataSourceError('westock JSON 结构变化：期望列表或 Data 批量封装')
    result = {}
    for item in payload['Data']:
        symbol = item.get('Symbol')
        if symbol not in symbols:
            continue
        data = item.get('Data')
        if isinstance(data, dict) and 'nodes' in data:
            data = data['nodes']
        if isinstance(data, dict):
            data = [data]
        if isinstance(data, list):
            result[symbol] = data
    errors = (payload.get('Metadata') or {}).get('ErrorCount', 0)
    if errors and all(result.get(s) for s in symbols):
        raise IncompleteDataError('westock 批量元数据报告错误，与返回条目不一致')
    return result


def number(value, required=False):
    try:
        value = float(value)
        if not math.isfinite(value):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        if required:
            raise DataSourceError('行情字段缺失或非有限数值')
        return None


def normalize_bars(rows):
    bars = {}
    for r in rows:
        d = str(r.get('date', '')).replace('-', '')[:8]
        try:
            datetime.strptime(d, '%Y%m%d')
        except ValueError as exc:
            raise DataSourceError('K线日期格式变化') from exc
        close = number(r.get('last', r.get('close')), True)
        if close <= 0:
            raise DataSourceError('K线收盘价必须大于零')
        o, h, l = [number(r.get(k), True) for k in ('open', 'high', 'low')]
        if l > min(o, close) or h < max(o, close) or l <= 0:
            raise DataSourceError('K线 OHLC 校验失败')
        volume, amount = number(r.get('volume')), number(r.get('amount'))
        bars[d] = dict(bargaindate=f'{d[:4]}-{d[4:6]}-{d[6:]}', closeindex=close,
                       openindex=o, maxindex=h, minindex=l,
                       # CLI amount is yuan; sector volume is lots (100 shares).
                       bargainamount=volume / 1e6 if volume is not None else None,
                       bargainsum=amount / 1e8 if amount is not None else None,
                       markup=number(r.get('change_pct')), turnoverrate=number(r.get('exchange')))
    return [bars[d] for d in sorted(bars)]


def _batch(codes, args, normalize=lambda x: x):
    codes = list(dict.fromkeys(codes))
    symbols = [to_symbol(c) for c in codes]
    raw = records(run_cli([*args[:1], ','.join(symbols), *args[1:]]), symbols)
    result = {}
    for code, symbol in zip(codes, symbols):
        rows = raw.get(symbol)
        if not rows:
            # One bounded retry, only the missing symbol.
            rows = records(run_cli([args[0], symbol, *args[1:]]), [symbol]).get(symbol)
        if not rows:
            raise IncompleteDataError(f'{code}: 重试后仍无数据，停止生成完整性不实的报告')
        result[code] = normalize(rows)
    return result


_KLINE_CACHE = {}

def get_klines(codes, period='DAY', limit=250, start=None, end=None):
    if period.upper() not in ('DAY', 'WEEK', 'MONTH') or limit < 1:
        raise ValueError('period 必须是 DAY/WEEK/MONTH，limit 必须大于零')
    codes = list(codes)
    for c in codes:
        to_symbol(c)
    requested = max(250, limit) if period.upper() == 'DAY' else limit
    key = (period.upper(), requested, start, end)
    missing = [c for c in codes if (c, key) not in _KLINE_CACHE]
    args = ['kline', '--period', period.lower(), '--limit', str(requested)]
    if start:
        args += ['--start', start]
    if end:
        args += ['--end', end]
    chunks = [missing[i:i+6] for i in range(0, len(missing), 6)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for batch in pool.map(lambda cs: _batch(cs, args, normalize_bars), chunks):
            for c, bars in batch.items():
                _KLINE_CACHE[c, key] = bars
    result = {c: _KLINE_CACHE[c, key][-limit:] for c in codes}
    if any(not rows for rows in result.values()):
        raise IncompleteDataError('K线规范化后为空')
    if len({rows[-1]['bargaindate'] for rows in result.values()}) > 1:
        raise IncompleteDataError('批量K线最新日期不一致，不能混作同日分析')
    if len(codes)>1:
        common = set.intersection(*(set(r['bargaindate'] for r in rows) for rows in result.values()))
        if len(common)<2:
            raise IncompleteDataError('批量K线共同交易日期不足')
        result = {c:[r for r in rows if r['bargaindate'] in common] for c,rows in result.items()}
    return result


def get_kline(code, period='DAY', limit=250):
    return get_klines([code], period, limit)[code]


def normalize_quote(code, rows):
    r = rows[-1]
    price = number(r.get('price'), True)
    prev = number(r.get('prev_close'), True)
    if price <= 0 or prev <= 0:
        raise DataSourceError('行情价格无效')
    if r.get("code") and r["code"] != to_symbol(code):
        raise DataSourceError("行情返回代码与请求不一致")
    stamp = str(r.get('time', ''))
    return dict(code=code, name=r.get('name', code), latest=price, prev_close=prev,
                change=round(price-prev, 4), change_pct=round((price/prev-1)*100, 4),
                open=number(r.get('open'), True), high=number(r.get('high'), True),
                low=number(r.get('low'), True), amount=number(r.get('amount'), True)/1e8,
                volume=number(r.get('volume'), True)/1e6, date=stamp[:10], time=stamp[11:],
                source='westock', data_note=SOURCE_NOTE)


def get_quotes(codes):
    result = {}
    codes = list(codes)
    for i in range(0, len(codes), 6):
        batch = _batch(codes[i:i+6], ['quote'])
        result.update({c: normalize_quote(c, rs) for c, rs in batch.items()})
    if len({q["date"] for q in result.values()}) > 1:
        raise IncompleteDataError("批量行情最新日期不一致")
    return result


def get_quote(code):
    return get_quotes([code])[code]


@lru_cache(maxsize=512)
def get_valuation(code, start=None, end=None, as_of=None):
    symbol = to_symbol(code)
    args = ['sector', 'valuation', symbol]
    if start and end:
        args += ['--start', start, '--end', end]
    if as_of:
        args += ['--date', as_of]
    rows = records(run_cli(args), [symbol]).get(symbol)
    if not rows:
        raise IncompleteDataError(f'{code}: 估值数据为空')
    for r in rows:
        stamp = str(r.get('EndDate',''))
        try:
            datetime.strptime(stamp,'%Y%m%d')
        except ValueError as exc:
            raise DataSourceError('估值日期字段变化') from exc
        if r.get('IndustryCode') and r['IndustryCode'] != symbol:
            raise DataSourceError('估值返回行业代码不一致')
        for k in ('PeTTMPct','PbLFPct'):
            pct = number(r.get(k))
            if pct is not None and not 0 <= pct <= 100:
                raise DataSourceError('估值百分位超出0~100范围')
    rows = sorted(rows,key=lambda r:str(r['EndDate']))
    return [dict(code=code, name=r.get('IndustryName', r.get('name', code)),
                 date=str(r.get('EndDate', '') )[:4]+'-'+str(r.get('EndDate', ''))[4:6]+'-'+str(r.get('EndDate', ''))[6:8],
                 pe=number(r.get('PeTTM')), pb=number(r.get('PbLF')), dp=number(r.get('DivTTM')),
                 pe_percentile=number(r.get('PeTTMPct')), pb_percentile=number(r.get('PbLFPct')),
                 percentile_window='供应商历史窗口（未指定年数）', source='westock') for r in rows]


def get_component(code):
    symbol = to_symbol(code)
    rows = records(run_cli(['sector', 'constituent', symbol, '--limit', '0']), [symbol]).get(symbol)
    if not rows:
        raise IncompleteDataError(f'{code}: 成分数据为空')
    return [dict(stockCode=r.get('code'), stockName=r.get('name'),
                 newWeight=number(r.get('weight')), beginningDate=r.get('date', ''),
                 source='westock', weight_available=r.get('weight') is not None) for r in rows]


def get_fund_flow(code):
    # CLI documents this command for individual stocks, not SW sector indices.
    raise UnsupportedCapabilityError('当前 CLI 未证实支持申万行业资金流；禁止将个股接口当作行业数据')


def risk_metrics(bars, annual_days=250, rf=0.02):
    closes = [r['closeindex'] for r in bars]
    if len(closes) < 2:
        raise IncompleteDataError('至少需要两根K线计算收益风险')
    rets = [b/a-1 for a,b in zip(closes, closes[1:])]
    ann = (closes[-1]/closes[0]) ** (annual_days/len(rets))-1
    vol = math.sqrt(sum((r-sum(rets)/len(rets))**2 for r in rets)/(len(rets)-1))*math.sqrt(annual_days) if len(rets)>1 else None
    peak, mdd = closes[0], 0
    for c in closes:
        peak = max(peak,c)
        mdd = min(mdd,c/peak-1)
    return dict(annual_return=ann*100, volatility=vol*100 if vol is not None else None,
                sharpe=(sum(rets)/len(rets)*annual_days-rf)/vol if vol else None,
                max_drawdown=mdd*100, calmar=ann/abs(mdd) if mdd else None)


def ytd_return(bars):
    cutoff = str(int(bars[-1]['bargaindate'][:4])-1)+'-12-31'
    base = next((r for r in reversed(bars) if r['bargaindate'] <= cutoff), None)
    if base is None:
        raise IncompleteDataError('缺少上年最后交易日基准，不能计算 YTD；增加回溯或日期区间')
    return (bars[-1]['closeindex']/base['closeindex']-1)*100


def get_risk_return(code):
    bars = get_kline(code, limit=1251)
    out = dict(code=code, m1_return=None, m3_return=None, ytd_return=ytd_return(bars))
    for label,n in [('m1',20),('m3',60)]:
        if len(bars)>n:
            out[label+'_return']=(bars[-1]['closeindex']/bars[-n-1]['closeindex']-1)*100
    for years in (1,3,5):
        n=250*years
        metric = risk_metrics(bars[-n-1:]) if len(bars)>n else None
        out[f'y{years}_return'] = metric['annual_return'] if metric else None
        out[f'y{years}_vol'] = metric['volatility'] if metric else None
    out.update(risk_metrics(bars))
    out['bars'] = len(bars)
    return out


def get_minute(code):
    symbol = to_symbol(code)
    q = get_quote(code)
    rows = records(run_cli(['minute', symbol]), [symbol]).get(symbol)
    if not rows:
        raise IncompleteDataError('分钟行情为空')
    result = []
    for r in sorted(rows, key=lambda x: str(x.get('time', ''))):
        t = str(r.get('time', ''))
        if not re.fullmatch(r'\d{4}', t):
            raise DataSourceError('分钟行情时间字段变化')
        result.append(dict(l1=code, l2=q['name'], l3=q['prev_close'], l4=q['open'],
                           l6=q['high'], l7=q['low'], l8=number(r.get('price'), True),
                           # Missing intraday amount is explicitly absent, never synthesized.
                           l5=None, l11=number(r.get('volume'), True)/1e4,
                           trading_time=t[:2]+':'+t[2:], trading_date=q['date']))
    return result

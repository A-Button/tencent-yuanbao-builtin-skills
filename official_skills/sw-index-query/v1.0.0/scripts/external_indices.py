"""External index adapter through the authorized WeStock CLI only."""

from __future__ import annotations
from datasource import run_cli, records, normalize_bars, IncompleteDataError
_INDEX_MAP = {
    "000001": ("上证指数", "sh000001"),
    "000016": ("上证50", "sh000016"),
    "000010": ("上证180", "sh000010"),
    "000300": ("沪深300", "sh000300"),
    "000905": ("中证500", "sh000905"),
    "000852": ("中证1000", "sh000852"),
    "932000": ("中证2000", "sh932000"),
    "000510": ("中证A500", "sh000510"),
    "930050": ("中证A50", "sh930050"),
    "399001": ("深证成指", "sz399001"),
    "399106": ("深证综指", "sz399106"),
    "399006": ("创业板指", "sz399006"),
    "399102": ("创业板综", "sz399102"),
    "399005": ("中小100", "sz399005"),
    "399330": ("深证100", "sz399330"),
    "000688": ("科创50", "sh000688"),
    "000698": ("科创100", "sh000698"),
    "000699": ("科创200", "sh000699"),
    "899050": ("北证50", "bj899050"),
    "000985": ("中证全指", "sh000985"),
    "HSI": ("恒生指数", "hkHSI"),
}

def is_supported_index(code):
    return str(code) in _INDEX_MAP

def index_name(code):
    return _INDEX_MAP[str(code)][0]

def index_daily(code, start, end):
    name,symbol = _INDEX_MAP[str(code)]
    fmt = lambda x: f"{x[:4]}-{x[4:6]}-{x[6:8]}" if len(x)==8 else x
    data=records(run_cli(['kline',symbol,'--period','day','--start',fmt(start),'--end',fmt(end),'--limit','2000']),[symbol])[symbol]
    rows=normalize_bars(data)
    if not rows:
        raise IncompleteDataError('外部指数K线为空')
    return dict(name=name,code=code,source='westock',bars=[dict(date=r['bargaindate'].replace('-',''),open=r['openindex'],high=r['maxindex'],low=r['minindex'],close=r['closeindex'],volume=r['bargainamount'],amount=r['bargainsum']) for r in rows])

def index_components(code):
    name,symbol=_INDEX_MAP[str(code)]
    rows=records(run_cli(['index','constituent',symbol]),[symbol]).get(symbol)
    if not rows:
        raise IncompleteDataError('外部指数成分为空')
    return dict(source='westock',components=[dict(stockCode=r.get('code'),stockName=r.get('name'),newWeight=r.get('weight')) for r in rows])

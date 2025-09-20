<div align="center">
  <img alt="logo tradingview screener api library" src="https://raw.githubusercontent.com/houseofai/tvscreener/main/.github/img/logo-tradingview-screener-api.png"><br>
</div>

-----------------

# TradingView Screener API: simple Python library to retrieve data from TradingView Screener
Get the results as a Pandas Dataframe

![dataframe.png](https://github.com/houseofai/tvscreener/blob/main/.github/img/dataframe.png?raw=true)

# Main Features

- Query **Stock**, **Forex** and **Crypto** Screener
- All the **fields available**: ~300 fields - even hidden ones)
- **Any time interval** (`no need to be a registered user` - 1D, 5m, 1h, etc.)
- Filters by any fields, symbols, markets, countries, etc.
- Get the results as a Pandas Dataframe

## Installation

The source code is currently hosted on GitHub at:
Fork From: https://github.com/houseofai/tvscreener

From pip + GitHub:

```sh
$ pip install git+https://github.com/msxfXF/tradingview-screener@main
```

## Usage

For Stocks screener:

```python
import tvscreener as tvs

ss = tvs.StockScreener()
df = ss.get()

# ... returns a dataframe with 150 rows by default
``` 

For Forex screener:

```python
import tvscreener as tvs

fs = tvs.ForexScreener()
df = fs.get()
```

For Crypto screener:

```python
import tvscreener as tvs

cs = tvs.CryptoScreener()
df = cs.get()
```

## Parameters

For Options and Filters, please check the [notebooks](https://github.com/houseofai/tvscreener/tree/main/notebooks) for
examples.
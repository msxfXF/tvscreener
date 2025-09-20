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
## Monitoring Service & Dashboard

The repository ships with a production-ready monitoring service that periodically pulls data from the TradingView stock
screener, persists the snapshots to SQLite and exposes a real-time dashboard plus REST API. The service runs on top of
FastAPI and can be launched directly or via Docker.

### Running locally

1. Install the project in editable mode:

   ```bash
   pip install -e .
   ```

2. Start the FastAPI application:

   ```bash
   uvicorn monitor_app:app --host 0.0.0.0 --port 8000
   ```

3. Open `http://localhost:8000/` to view the dashboard. Recent analyst rating changes are highlighted and clicking on a
   row reveals an interactive price & analyst rating chart together with live company fundamentals, sector context and
   rolling statistics for the selected symbol.

Environment variables control the monitoring behaviour (defaults in parentheses):

| Variable            | Description                                              |
|---------------------|----------------------------------------------------------|
| `INTERVAL_SECONDS`  | Polling interval in seconds (600).                        |
| `RANGE_START`       | Starting index for the TradingView screener range (0).    |
| `RANGE_END`         | End index (exclusive) for the screener range (150).       |
| `DB_PATH`           | Path to the SQLite database (`/app/data/monitor.db`).     |
| `MAX_RETRIES`       | Maximum retry attempts for failed fetches (3).            |
| `RETRY_BACKOFF_SECONDS` | Backoff seconds added between retries (30).           |

Snapshots are stored in the `snapshots` table, while analyst rating deltas are written to the `rating_changes` table.
Whenever a change is detected the service logs it and the dashboard updates automatically.

### REST API

- `GET /api/rating_changes` – Paginated list of rating change events.
- `GET /api/symbol/{symbol}/history` – Snapshot history, computed metrics, and enriched profile information for a symbol.
- `GET /healthz` – Health probe and latest run metadata.

### Docker image

Build and run the container for an out-of-the-box deployment:

```bash
docker build -t tvscreener-monitor .
docker run -d \
  --name tvscreener-monitor \
  -p 8000:8000 \
  -e INTERVAL_SECONDS=600 \
  -e RANGE_END=500 \
  -v $(pwd)/data:/app/data \
  tvscreener-monitor
```

The container exposes port `8000` and stores SQLite data inside `/app/data`. Mounting the path as a volume keeps the data
between restarts. The built-in health check pings `/healthz`, making it suitable for orchestration probes.

   # CycleMind                                 
                                            
AI-powered market-regime trading agent  for BTC, ETH, and SOL — built on Bitget.  
  
CycleMind reads market conditions across four integrated modules and surfaces signals you can act on  directly,  rather than just showing raw data.
 
## Modules  
 
1. **Market Regime Detection** — the core engine. Classifies each asset into one of five regimes (strong/weak uptrend, range-bound, weak/strong downtrend) using a composite confidence score weighted across Volume Divergence (25%), BTC Dominance Momentum (20%), Indicator Agreement — RSI/MACD/EMA (30%), and Funding Rate Alignment (25%). Each asset has its own confidence threshold (BTC 60%, ETH 62%, SOL 68%) before a signal is considered actionable. 
2. **Signal-Based DCA** — scales DCA buy size based  on Fear & Greed Index instead of a fixed calendar.
3. **Liquidation Heatmap** — estimates liquidation price clusters across common leverage tiers using live open interest and price data. Proximity to a cluster feeds back into the regime engine to reduce suggested position sizing near cascade-risk zones.
4. **Funding Rate Capture** — flags when funding rate sits in a historically extreme percentile, suggesting a delta-neutral capture opportunity.
5. **Portfolio Rebalancer** — pulls live spot balances from a connected Bitget account, compares against a target allocation for the user's risk profile (conservative/balanced/aggressive), and applies a light regime-aware tilt — shifting allocation toward USDT when an asset is in a detected downtrend. Returns a suggested plan only; does not execute trades.

All modules read from the same regime-detection engine (`regime_engine.py`), so liquidation proximity and funding alignment feed directly into the confidence score rather than acting as separate, disconnected signals.

## Project Structure

```
cyclemind/
├── frontend/        # Vanilla JS dashboard
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── backend/         # Python FastAPI server
│   ├── main.py
│   ├── bitget_client.py
│   ├── regime_engine.py    # Composite confidence scoring + regime classification
│   ├── indicators.py       # RSI, MACD, EMA calculations
│   ├── config.py
│   └── requirements.txt
└── README.md
```

## Local Setup

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in values if needed
python main.py
```

Backend runs at `http://localhost:8000`.

### Frontend

```bash
cd frontend
# Any static server works, e.g.:
python3 -m http.server 5500
```

Open `http://localhost:5500` in your browser.

> Note: public market-data endpoints (funding rate, open interest, ticker, fear/greed) work without any API keys. Account balance and rebalancing features require a user to connect their own Bitget API key, secret, and passphrase through the Connect button — these should be created as **read-only** keys unless you intend to enable trade execution.

## Deployment

**Frontend → Vercel**
1. Push this repo to GitHub.
2. Import the repo in Vercel, set the root directory to `frontend`.
3. Deploy — Vercel auto-detects static sites, no build config needed.

**Backend → Railway (or Render)**
1. Import the repo in Railway, set the root directory to `backend`.
2. Add environment variables from `.env.example` in Railway's dashboard.
3. Railway auto-detects Python and runs `python main.py`, or set the start command to:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
4. Once deployed, copy the Railway URL and update `API_BASE` in `frontend/app.js`, and set `FRONTEND_ORIGIN` in Railway's env vars to your Vercel URL.

## Security Notes

- API keys submitted through the Connect modal should ideally be **read-only** trading keys from Bitget unless trade execution is explicitly needed.
- This MVP stores credentials in browser `localStorage` for simplicity — for any real deployment with actual users, credentials should be sent to the backend and encrypted at rest, never persisted client-side.
- Trade execution is not yet wired up in this version — all account modules are currently read-only.

## Disclaimer

CycleMind is a research and signal tool. Nothing here is financial advice. Trading perpetual futures carries significant risk of loss.

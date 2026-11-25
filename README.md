# Options and Mathematics (MVE095)

Automated options trading system for 1-day maturity European short straddles (`SPX`, `ESTX50`) on Interactive Brokers, using Bayesian inference.

---

## Quick Start: Running the Trading Bot

### 1. Configure Credentials

Create a `.env` file at the repository root:

```bash
cp .env.example .env
```

Edit `.env` and set your Interactive Brokers credentials:

```env
TWS_USERID=your_ibkr_username
TWS_PASSWORD=your_ibkr_password
TRADING_MODE=paper
```

### 2. Run with Docker (Recommended)

Start the full stack (IB Gateway + Multi-Asset Trading Bot):

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

### 3. Monitor Logs

View real-time ping updates and trading events:

```bash
docker compose -f docker/docker-compose.yml logs -f
```

### 4. Stop the Bot

```bash
docker compose -f docker/docker-compose.yml down
```

---

## Running Locally without Docker

1. **Start TWS or IB Gateway** on your local machine with API socket connections enabled (e.g. port `7497` for paper trading).
2. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Launch the bot**:
   ```bash
   python src/main.py SPX:CBOE:USD ESTX50:EUREX:EUR --host 127.0.0.1 --port 7497 --client-id 10 --fixed-capital-amount 100000.0 --credibility-percentage 0.95 --decay-factor 0.995 --check-interval-seconds 30.0
   ```

---

## Research & Data Scripts

1. **Verify TWS Connection**:
   ```bash
   python src/check_tws_connection.py
   ```
2. **Fetch 10-Year Historical Data**:
   ```bash
   python src/get_data.py
   ```
3. **Run Bayesian Inference**:
   ```bash
   python src/bayesian_inference.py
   ```
4. **Generate Figures**:
   ```bash
   python src/figures.py
   ```

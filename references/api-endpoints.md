# IBKR Client Portal API (Read-Only Reference)

> This file is intentionally limited to read-only endpoints.
>
> Trading endpoints (place/modify/cancel orders) are deliberately omitted to align with this repository's safety boundary.

## Scope

- Primary architecture in this repo is **IB Gateway + ib_insync** (socket API).
- This document is only a **legacy HTTP reference** for account/market data reading.
- Base URL: `https://localhost:5000`

## Authentication

### Check Status
```
GET /v1/api/iserver/auth/status
```

### Keepalive (Tickle)
```
POST /v1/api/tickle
```
Call every 5 minutes if you are still using Client Portal session mode.

### Logout
```
POST /v1/api/logout
```

## Portfolio

### List Accounts
```
GET /v1/api/portfolio/accounts
```

### Account Summary
```
GET /v1/api/portfolio/{accountId}/summary
```
Key fields:
- `totalcashvalue.amount` - Available cash
- `netliquidation.amount` - Total account value
- `unrealizedpnl.amount` - Unrealized P&L

### Account Ledger
```
GET /v1/api/portfolio/{accountId}/ledger
```

## Positions

### Get Positions
```
GET /v1/api/portfolio/{accountId}/positions/{pageId}
```
`pageId` starts at 0 and returns paginated position lists.

### Position by Conid
```
GET /v1/api/portfolio/{accountId}/position/{conid}
```

## Market Data

### Symbol Search
```
GET /v1/api/iserver/secdef/search?symbol={symbol}
```

### Contract Details
```
GET /v1/api/iserver/contract/{conid}/info
```

### Market Data Snapshot
```
GET /v1/api/iserver/marketdata/snapshot?conids={conid}&fields={fields}
```

Common fields:
- `31` last price
- `84` bid
- `86` ask
- `87` volume
- `88` previous close
- `7295` open
- `7296` high
- `7297` low
- `7762` change %

Example:
```bash
curl -sk "https://localhost:5000/v1/api/iserver/marketdata/snapshot?conids=265598&fields=31,84,86,87"
```

### Historical Data
```
GET /v1/api/iserver/marketdata/history?conid={conid}&period={period}&bar={bar}
```

Periods: `1d`, `1w`, `1m`, `3m`, `6m`, `1y`, `5y`  
Bars: `1min`, `5min`, `1h`, `1d`, `1w`, `1m`

## Scanner

### Get Scanner Parameters
```
GET /v1/api/iserver/scanner/params
```

### Run Scanner
```
POST /v1/api/iserver/scanner/run
Content-Type: application/json

{
  "instrument": "STK",
  "type": "TOP_PERC_GAIN",
  "location": "STK.US.MAJOR",
  "size": "25"
}
```

## Explicitly Out of Scope

- Place order
- Modify order
- Cancel order
- Any endpoint that can change account state

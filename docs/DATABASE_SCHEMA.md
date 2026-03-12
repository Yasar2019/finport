# FinPort — Database Schema Reference

All tables use UUID primary keys and carry `created_at` / `updated_at` timestamps unless noted.
Multi-tenancy is enabled from day one via `user_id` on all user-owned entities.
Alembic manages all migrations; never alter tables manually.

---

## Design Principles

1. **Provenance on every record** — every financial entity carries the import session and parser run that created it, plus a JSON pointer to its raw source location.
2. **Append-only audit log** — the `audit_logs` table receives `INSERT` only; the application DB role has no `UPDATE/DELETE` rights on it.
3. **Security master normalisation** — all security references use `securities.id`; institution-specific tickers are resolved via `security_aliases`.
4. **Encrypted sensitive columns** — account numbers stored via application-layer AES encryption.
5. **Soft deletes** — user-facing entities use `deleted_at` (nullable) rather than hard deletes, preserving audit history.

---

## Entity Relationship Overview

```text
institutions ──< accounts ──< statements ──< transactions
                         │                └──< holdings
                         │                └──< dividends
                         │                └──< fees
                         │
                         └──< import_sessions ──< parser_runs
                                              └──< reconciliation_records

securities ──< security_aliases
           ──< holdings (via account)
           ──< transactions (via account)
           ──< corporate_actions
           ──< tax_lots

accounts ──< tax_lots
         ──< valuations
         ──< transfers (from / to)

audit_logs (references entity_type + entity_id polymorphically)
```

---

## Table Definitions

### `institutions`

```sql
CREATE TABLE institutions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    short_code      VARCHAR(50) UNIQUE NOT NULL,   -- 'fidelity', 'schwab', 'coinbase'
    institution_type VARCHAR(50) NOT NULL,          -- bank | brokerage | retirement | crypto | credit_card | other
    country         CHAR(2) NOT NULL DEFAULT 'US', -- ISO 3166-1 alpha-2
    default_currency CHAR(3) NOT NULL DEFAULT 'USD',
    parser_key      VARCHAR(100),                   -- maps to parser registry key
    logo_url        TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_institutions_short_code ON institutions(short_code);
```

---

### `accounts`

```sql
CREATE TABLE accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,              -- future multi-tenancy; single-user: fixed constant
    institution_id      UUID NOT NULL REFERENCES institutions(id),
    account_number_enc  BYTEA,                      -- AES-encrypted account number
    account_name        VARCHAR(200) NOT NULL,
    account_type        VARCHAR(50) NOT NULL,       -- checking | savings | brokerage | ira_traditional |
                                                    -- ira_roth | k401 | k403b | crypto | credit_card |
                                                    -- hsa | savings_bond | annuity | other
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    opened_date         DATE,
    closed_date         DATE,
    notes               TEXT,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_institution ON accounts(institution_id);
```

---

### `import_sessions`

One row per uploaded file. File hash prevents duplicate ingestion.

```sql
CREATE TABLE import_sessions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL,
    account_id              UUID REFERENCES accounts(id),   -- resolved during processing
    original_filename       VARCHAR(500) NOT NULL,
    file_hash               CHAR(64) NOT NULL,              -- SHA-256 hex; UNIQUE per user
    storage_path            TEXT NOT NULL,                  -- relative path in encrypted store
    file_format             VARCHAR(20) NOT NULL,           -- pdf | csv | excel | ofx | qfx
    file_size_bytes         BIGINT NOT NULL,
    status                  VARCHAR(30) NOT NULL DEFAULT 'pending',
                            -- pending | queued | processing | completed | needs_review | failed
    detected_institution_id UUID REFERENCES institutions(id),
    detected_account_type   VARCHAR(50),
    statement_period_start  DATE,
    statement_period_end    DATE,
    statement_date          DATE,
    error_message           TEXT,
    completed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, file_hash)
);
CREATE INDEX idx_import_sessions_user ON import_sessions(user_id);
CREATE INDEX idx_import_sessions_status ON import_sessions(status);
CREATE INDEX idx_import_sessions_hash ON import_sessions(file_hash);
```

---

### `parser_runs`

Records every execution of a parser against an import session.

```sql
CREATE TABLE parser_runs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    import_session_id    UUID NOT NULL REFERENCES import_sessions(id) ON DELETE CASCADE,
    parser_name          VARCHAR(100) NOT NULL,   -- 'FidelityPDFParser', 'GenericCSVParser'
    parser_version       VARCHAR(20) NOT NULL,    -- semver, e.g. '1.3.0'
    started_at           TIMESTAMPTZ NOT NULL,
    completed_at         TIMESTAMPTZ,
    status               VARCHAR(20) NOT NULL,    -- running | completed | failed
    confidence_score     NUMERIC(5,4),            -- 0.0000 – 1.0000
    pages_processed      INTEGER,
    records_extracted    JSONB,                   -- {"transactions":42,"holdings":15,"fees":3}
    warnings             JSONB,                   -- array of warning messages
    errors               JSONB,                   -- array of error messages
    raw_text_storage_path TEXT,                   -- path to extracted raw text for debugging
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_parser_runs_session ON parser_runs(import_session_id);
```

---

### `statements`

A statement is the logical document associated with an account period.

```sql
CREATE TABLE statements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    import_session_id   UUID NOT NULL REFERENCES import_sessions(id),
    account_id          UUID NOT NULL REFERENCES accounts(id),
    institution_id      UUID NOT NULL REFERENCES institutions(id),
    statement_date      DATE,
    period_start        DATE,
    period_end          DATE,
    opening_balance     NUMERIC(18,4),
    closing_balance     NUMERIC(18,4),
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_statements_account ON statements(account_id);
CREATE INDEX idx_statements_period ON statements(period_start, period_end);
```

---

### `securities` (SecurityMaster)

Canonical reference for all financial instruments.

```sql
CREATE TABLE securities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          VARCHAR(20),                -- primary ticker (may be NULL for bonds by ISIN only)
    isin            CHAR(12) UNIQUE,            -- ISO 6166
    cusip           CHAR(9) UNIQUE,
    figi            VARCHAR(12),                -- Financial Instrument Global Identifier
    name            VARCHAR(300) NOT NULL,
    security_type   VARCHAR(50) NOT NULL,       -- stock | bond | etf | mutual_fund | money_market |
                                                -- option | future | crypto | cash_equivalent | reit | other
    primary_exchange VARCHAR(30),
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    sector          VARCHAR(100),
    industry        VARCHAR(100),
    asset_class     VARCHAR(50),               -- equity | fixed_income | alternative | cash | real_estate | commodity
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_securities_symbol ON securities(symbol);
CREATE INDEX idx_securities_isin ON securities(isin);
CREATE INDEX idx_securities_cusip ON securities(cusip);
```

---

### `security_aliases`

Maps institution-specific symbols/identifiers to the SecurityMaster.

```sql
CREATE TABLE security_aliases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id     UUID NOT NULL REFERENCES securities(id),
    alias_symbol    VARCHAR(50) NOT NULL,
    institution_id  UUID REFERENCES institutions(id),   -- NULL = universal alias
    alias_type      VARCHAR(20) NOT NULL DEFAULT 'ticker', -- ticker | cusip | isin | name_fragment
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (alias_symbol, institution_id)
);
CREATE INDEX idx_security_aliases_symbol ON security_aliases(alias_symbol);
```

---

### `transactions`

Core financial events. Every transaction must be traceable to its source.

```sql
CREATE TABLE transactions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL,
    account_id              UUID NOT NULL REFERENCES accounts(id),
    statement_id            UUID REFERENCES statements(id),
    import_session_id       UUID REFERENCES import_sessions(id),
    parser_run_id           UUID REFERENCES parser_runs(id),

    -- Date fields
    transaction_date        DATE NOT NULL,
    settlement_date         DATE,
    posted_date             DATE,

    -- Classification
    transaction_type        VARCHAR(50) NOT NULL,
    -- Enum: buy | sell | dividend_cash | dividend_reinvest | interest | fee_commission |
    --       fee_management | fee_other | transfer_in | transfer_out | deposit | withdrawal |
    --       return_of_capital | corporate_action | split_adjustment | option_exercise |
    --       margin_interest | journal | unknown

    -- Description
    description_raw         TEXT,                    -- verbatim from statement
    description_normalized  VARCHAR(500),            -- cleaned/standardised

    -- Amounts
    amount                  NUMERIC(18,4) NOT NULL,  -- positive = inflow, negative = outflow
    currency                CHAR(3) NOT NULL DEFAULT 'USD',
    fx_rate_to_usd          NUMERIC(18,8),           -- if original currency != USD

    -- Securities (nullable for cash transactions)
    security_id             UUID REFERENCES securities(id),
    quantity                NUMERIC(18,8),           -- shares / units
    price_per_unit          NUMERIC(18,6),           -- execution price
    lot_id                  UUID,                    -- references tax_lots.id (set post-normalisation)

    -- Running state
    running_balance         NUMERIC(18,4),           -- if available in statement

    -- Provenance
    raw_source_ref          JSONB,                   -- {"page":3,"table":0,"row":14}
    parser_confidence       NUMERIC(5,4),

    -- Reconciliation
    is_reconciled           BOOLEAN NOT NULL DEFAULT FALSE,
    reconciliation_note     TEXT,
    is_manually_reviewed    BOOLEAN NOT NULL DEFAULT FALSE,
    is_excluded             BOOLEAN NOT NULL DEFAULT FALSE, -- user manually excluded

    deleted_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transactions_account_date ON transactions(account_id, transaction_date DESC);
CREATE INDEX idx_transactions_security ON transactions(security_id);
CREATE INDEX idx_transactions_type ON transactions(transaction_type);
CREATE INDEX idx_transactions_session ON transactions(import_session_id);
CREATE INDEX idx_transactions_user ON transactions(user_id);
-- For duplicate detection:
CREATE INDEX idx_transactions_dedup ON transactions(account_id, transaction_date, amount, transaction_type)
    WHERE deleted_at IS NULL;
```

---

### `holdings`

Point-in-time position snapshots (as of a statement date).

```sql
CREATE TABLE holdings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    account_id          UUID NOT NULL REFERENCES accounts(id),
    security_id         UUID NOT NULL REFERENCES securities(id),
    statement_id        UUID REFERENCES statements(id),
    import_session_id   UUID REFERENCES import_sessions(id),
    parser_run_id       UUID REFERENCES parser_runs(id),

    as_of_date          DATE NOT NULL,
    quantity            NUMERIC(18,8) NOT NULL,
    cost_basis          NUMERIC(18,4),
    cost_basis_method   VARCHAR(20),             -- fifo | lifo | average_cost | specific_lot
    market_value        NUMERIC(18,4),           -- as reported on statement
    price               NUMERIC(18,6),           -- price per unit on statement date
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    unrealized_gain     NUMERIC(18,4),
    unrealized_gain_pct NUMERIC(8,4),

    raw_source_ref      JSONB,
    parser_confidence   NUMERIC(5,4),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_holdings_account_date ON holdings(account_id, as_of_date DESC);
CREATE INDEX idx_holdings_security ON holdings(security_id);
CREATE UNIQUE INDEX idx_holdings_unique ON holdings(account_id, security_id, as_of_date, import_session_id);
```

---

### `tax_lots`

Acquisition-level cost basis for realised gain/loss calculation.

```sql
CREATE TABLE tax_lots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    account_id          UUID NOT NULL REFERENCES accounts(id),
    security_id         UUID NOT NULL REFERENCES securities(id),
    opening_transaction_id UUID REFERENCES transactions(id),

    acquisition_date    DATE NOT NULL,
    quantity_original   NUMERIC(18,8) NOT NULL,
    quantity_remaining  NUMERIC(18,8) NOT NULL,
    cost_per_unit       NUMERIC(18,6) NOT NULL,
    total_cost          NUMERIC(18,4) NOT NULL,
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    lot_type            VARCHAR(10),             -- long | short (for tax treatment)
    is_open             BOOLEAN NOT NULL DEFAULT TRUE,
    wash_sale_disallowed NUMERIC(18,4),          -- disallowed loss from wash sale

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_lots_account_security ON tax_lots(account_id, security_id);
CREATE INDEX idx_tax_lots_open ON tax_lots(account_id) WHERE is_open = TRUE;
```

---

### `valuations`

Account-level net value snapshots over time.

```sql
CREATE TABLE valuations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    account_id          UUID NOT NULL REFERENCES accounts(id),
    import_session_id   UUID REFERENCES import_sessions(id),

    as_of_date          DATE NOT NULL,
    total_value         NUMERIC(18,4) NOT NULL,
    cash_balance        NUMERIC(18,4),
    securities_value    NUMERIC(18,4),
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    source              VARCHAR(20) NOT NULL DEFAULT 'statement', -- statement | manual | computed

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (account_id, as_of_date, source)
);
CREATE INDEX idx_valuations_account_date ON valuations(account_id, as_of_date DESC);
```

---

### `dividends`

Dividend events (cash and reinvested).

```sql
CREATE TABLE dividends (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    account_id          UUID NOT NULL REFERENCES accounts(id),
    security_id         UUID NOT NULL REFERENCES securities(id),
    statement_id        UUID REFERENCES statements(id),
    import_session_id   UUID REFERENCES import_sessions(id),
    parser_run_id       UUID REFERENCES parser_runs(id),
    linked_transaction_id UUID REFERENCES transactions(id),

    ex_date             DATE,
    record_date         DATE,
    pay_date            DATE,
    amount_per_share    NUMERIC(18,6),
    quantity            NUMERIC(18,8),
    total_amount        NUMERIC(18,4) NOT NULL,
    dividend_type       VARCHAR(30) NOT NULL,    -- cash | reinvested | return_of_capital | special | qualified
    tax_withheld        NUMERIC(18,4),
    currency            CHAR(3) NOT NULL DEFAULT 'USD',

    raw_source_ref      JSONB,
    parser_confidence   NUMERIC(5,4),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_dividends_account ON dividends(account_id);
CREATE INDEX idx_dividends_security ON dividends(security_id);
```

---

### `fees`

```sql
CREATE TABLE fees (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    account_id          UUID NOT NULL REFERENCES accounts(id),
    statement_id        UUID REFERENCES statements(id),
    import_session_id   UUID REFERENCES import_sessions(id),
    linked_transaction_id UUID REFERENCES transactions(id),

    fee_date            DATE NOT NULL,
    fee_type            VARCHAR(50) NOT NULL,    -- commission | management | advisory | forex |
                                                 -- early_withdrawal | transfer | margin | other
    amount              NUMERIC(18,4) NOT NULL,  -- always positive
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    description         TEXT,

    raw_source_ref      JSONB,
    parser_confidence   NUMERIC(5,4),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fees_account ON fees(account_id);
```

---

### `transfers`

Internal transfer pairing (same money, two accounts).

```sql
CREATE TABLE transfers (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL,
    from_account_id         UUID REFERENCES accounts(id),
    to_account_id           UUID REFERENCES accounts(id),
    from_transaction_id     UUID REFERENCES transactions(id),
    to_transaction_id       UUID REFERENCES transactions(id),

    transfer_date           DATE NOT NULL,
    amount                  NUMERIC(18,4) NOT NULL,
    currency                CHAR(3) NOT NULL DEFAULT 'USD',
    description             TEXT,
    match_confidence        NUMERIC(5,4),        -- confidence of auto-match
    match_method            VARCHAR(30),         -- auto_exact | auto_fuzzy | manual
    reconciliation_status   VARCHAR(20) NOT NULL DEFAULT 'matched',
    -- matched | partial | unmatched | dismissed

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_transfers_accounts ON transfers(from_account_id, to_account_id);
```

---

### `corporate_actions`

Retroactive adjustments to holdings and cost basis.

```sql
CREATE TABLE corporate_actions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id         UUID NOT NULL REFERENCES securities(id),
    new_security_id     UUID REFERENCES securities(id),  -- for mergers / spin-offs

    action_type         VARCHAR(30) NOT NULL,
    -- split | reverse_split | merger | spin_off | name_change | delisting | rights_issue | special_dividend

    effective_date      DATE NOT NULL,
    ratio_from          NUMERIC(10,4),           -- e.g. 1 (for 3-for-1 split: from=1)
    ratio_to            NUMERIC(10,4),           -- e.g. 3
    cash_in_lieu        NUMERIC(18,4),           -- for fractional shares
    notes               TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_corporate_actions_security ON corporate_actions(security_id, effective_date);
```

---

### `reconciliation_records`

Every anomaly detected during the reconciliation pass.

```sql
CREATE TABLE reconciliation_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    import_session_id   UUID REFERENCES import_sessions(id),

    -- Polymorphic reference to the flagged record
    entity_type         VARCHAR(50) NOT NULL,    -- transaction | holding | balance | transfer | fee | dividend
    entity_id           UUID NOT NULL,

    issue_type          VARCHAR(80) NOT NULL,
    -- duplicate_transaction | balance_mismatch | missing_holding | ticker_not_found |
    -- currency_inconsistency | transfer_unmatched | fee_mismatch | drip_misclassification |
    -- lot_quantity_exceed | negative_quantity | future_date | unknown

    severity            VARCHAR(10) NOT NULL,    -- info | warning | error
    description         TEXT NOT NULL,
    suggested_action    TEXT,
    suggested_entity_id UUID,                    -- the entity suggested as a match/resolution

    status              VARCHAR(20) NOT NULL DEFAULT 'open',  -- open | resolved | dismissed
    resolution_note     TEXT,
    auto_resolved       BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by         UUID,                    -- user_id
    resolved_at         TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_reconciliation_session ON reconciliation_records(import_session_id);
CREATE INDEX idx_reconciliation_entity ON reconciliation_records(entity_type, entity_id);
CREATE INDEX idx_reconciliation_status ON reconciliation_records(status) WHERE status = 'open';
```

---

### `audit_logs`

Append-only. The DB role used by the application has INSERT privilege only on this table.

```sql
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID,
    action          VARCHAR(50) NOT NULL,
    -- upload | parse | normalise | reconcile | edit | delete | view | login | logout | export

    entity_type     VARCHAR(50),
    entity_id       UUID,
    before_state    JSONB,           -- redacted for sensitive fields
    after_state     JSONB,
    ip_address      INET,
    user_agent      TEXT,
    session_id      UUID,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- NO updated_at — this table is never updated
);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id, occurred_at DESC);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
```

---

### `fx_rates`

Daily FX rates for multi-currency valuation.

```sql
CREATE TABLE fx_rates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_currency   CHAR(3) NOT NULL,
    to_currency     CHAR(3) NOT NULL DEFAULT 'USD',
    rate_date       DATE NOT NULL,
    rate            NUMERIC(18,8) NOT NULL,
    source          VARCHAR(50),            -- 'ecb' | 'manual' | 'statement'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (from_currency, to_currency, rate_date)
);
CREATE INDEX idx_fx_rates_lookup ON fx_rates(from_currency, to_currency, rate_date DESC);
```

---

## Index Strategy Summary

| Access Pattern | Index |
| --- | --- |
| All transactions for an account, recent first | `(account_id, transaction_date DESC)` |
| All open reconciliation issues | `(status) WHERE status='open'` |
| Duplicate detection | `(account_id, transaction_date, amount, transaction_type)` |
| Holdings as of latest date | `(account_id, as_of_date DESC)` |
| Security lookup by symbol | `(symbol)` on securities |
| Institution lookup | `(short_code)` UNIQUE |
| File deduplication | `(user_id, file_hash)` UNIQUE |

---

## Migration Strategy

- All schema changes go through Alembic migration scripts in `backend/alembic/versions/`.
- Naming convention: `YYYYMMDD_HHmm_short_description.py`.
- Never modify a migration once merged; always create a new one.
- Production deployments run `alembic upgrade head` before starting the API.

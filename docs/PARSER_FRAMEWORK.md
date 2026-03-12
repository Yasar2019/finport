# FinPort — Parser Framework Design

## Overview

The parser framework is a **plugin-based, institution-aware document processing system**.
Its sole responsibility is to convert raw uploaded files (PDF, CSV, Excel) into
`CandidateRecord` collections that the downstream normalisation pipeline can safely
validate and persist.

Parsers **do not** write to the database. They output structured Python objects.
This separation makes parsers independently testable and independently deployable.

---

## Architecture Principles

1. **Structured extraction first, OCR last.** PDF text extraction with pdfplumber is attempted first. If the table yield is below the `min_confidence_threshold`, camelot is tried. OCR via pytesseract is only used if both yield < 20% of expected records.

2. **Each parser registers itself** via `@ParserRegistry.register(institution_key, file_format)` decorator. No manual wiring needed.

3. **Parsers declare what they can detect.** `InstitutionDetector` uses lightweight header heuristics before selecting a parser. Parsers expose `can_parse(file_path, raw_text) -> DetectionResult`.

4. **Output is always `ParserResult`.** Every parser returns the same type. Upstream code never needs to know which parser ran.

5. **Parser versioning is semantic.** Version is a string (`"1.3.0"`). A parser run records the version so historical imports can be reprocessed when the parser is updated.

6. **Confidence scoring is mandatory.** Every `CandidateRecord` carries a `confidence: float` (0–1). The `ParserResult` carries an aggregate `overall_confidence`. Scores below 0.50 trigger a `NEEDS_REVIEW` status on the import session.

---

## Component Map

```
                    ┌────────────────────────────────┐
                    │        Parser Registry         │
                    │  {institution_key + format}    │
                    │      → Parser class            │
                    └──────────────┬─────────────────┘
                                   │ lookup
             ┌─────────────────────▼────────────────────┐
             │          InstitutionDetector              │
             │  (header heuristics + filename patterns)  │
             └──────────────┬───────────────────────────┘
                            │ DetectionResult
             ┌──────────────▼───────────────────────────┐
             │         Parser Selection Logic            │
             │  1. Try institution-specific parser       │
             │  2. Fall back to format-generic parser    │
             │  3. Final fallback: GenericFallbackParser │
             └──────────────┬───────────────────────────┘
                            │
    ┌───────────────────────▼──────────────────────────────────┐
    │                  BaseParser (ABC)                         │
    │  + extract_transactions() → List[CandidateTransaction]   │
    │  + extract_holdings()     → List[CandidateHolding]       │
    │  + extract_balances()     → List[CandidateBalance]       │
    │  + extract_dividends()    → List[CandidateDividend]      │
    │  + extract_fees()         → List[CandidateFee]           │
    │  + extract_metadata()     → StatementMetadata            │
    └──────────────────────────────────────────────────────────┘
             │
    ┌────────┴────────────────────────────────────────────────────┐
    │  Institution Parsers          │  Generic Parsers             │
    │  ─────────────────────        │  ──────────────────          │
    │  FidelityPDFParser            │  GenericCSVParser            │
    │  SchwabCSVParser              │  GenericExcelParser          │
    │  VanguardPDFParser            │  GenericPDFParser            │
    │  CoinbasePDFParser            │  OFXParser                   │
    │  ChaseBankPDFParser           │                              │
    │  AmeritradeCSVParser          │                              │
    │  WellsFargoCSVParser          │                              │
    │  ...                          │                              │
    └─────────────────────────────────────────────────────────────┘
```

---

## Data Contracts (CandidateRecord Models)

All parser outputs are typed Pydantic v2 models. Pydantic validation is the gate between
raw parser output and the normalisation layer.

```python
# parsers/base/candidate_models.py  (see scaffold for full source)

class RawSourceRef(BaseModel):
    """Pointer back to the raw location in the source file."""
    page: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    cell_ref: str | None = None          # e.g. "B14" for Excel
    text_snippet: str | None = None      # first 100 chars for debugging

class CandidateTransaction(BaseModel):
    transaction_date: date
    settlement_date: date | None = None
    description_raw: str
    amount: Decimal
    currency: str = "USD"
    transaction_type_hint: str | None = None   # parser's best guess; normaliser resolves
    quantity: Decimal | None = None
    price_per_unit: Decimal | None = None
    symbol_raw: str | None = None              # institution-specific; resolved by SecurityMaster
    running_balance: Decimal | None = None
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)

class CandidateHolding(BaseModel):
    symbol_raw: str
    name_raw: str | None = None
    quantity: Decimal
    price: Decimal | None = None
    market_value: Decimal | None = None
    cost_basis: Decimal | None = None
    currency: str = "USD"
    as_of_date: date
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)

class CandidateBalance(BaseModel):
    balance_type: str          # opening | closing | cash | total
    amount: Decimal
    currency: str = "USD"
    as_of_date: date
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)

class CandidateDividend(BaseModel):
    symbol_raw: str
    pay_date: date
    ex_date: date | None = None
    total_amount: Decimal
    amount_per_share: Decimal | None = None
    quantity: Decimal | None = None
    dividend_type_hint: str = "cash"   # cash | reinvested | return_of_capital
    tax_withheld: Decimal | None = None
    currency: str = "USD"
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)

class CandidateFee(BaseModel):
    fee_date: date
    description_raw: str
    amount: Decimal            # always positive
    currency: str = "USD"
    fee_type_hint: str | None = None
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)

class StatementMetadata(BaseModel):
    institution_name: str | None = None
    account_number_raw: str | None = None   # raw (will be encrypted at normalisation)
    account_type_hint: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    statement_date: date | None = None
    currency: str = "USD"
    confidence: float = Field(ge=0.0, le=1.0)

class ParserResult(BaseModel):
    parser_name: str
    parser_version: str
    metadata: StatementMetadata
    transactions: list[CandidateTransaction] = []
    holdings: list[CandidateHolding] = []
    balances: list[CandidateBalance] = []
    dividends: list[CandidateDividend] = []
    fees: list[CandidateFee] = []
    overall_confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = []
    errors: list[str] = []
    raw_text: str | None = None            # preserved for debugging
```

---

## BaseParser Abstract Interface

```python
# parsers/base/parser_interface.py  (see scaffold for full source)

class BaseParser(ABC):
    """
    All parsers inherit from this class.
    Parser authors implement the extract_* methods.
    The parse() orchestration method is final (not overridable).
    """

    name: str                   # must be set on subclass
    version: str                # semver, e.g. "1.0.0"
    institution_key: str | None # None for generic parsers
    supported_formats: list[str]  # ["pdf"], ["csv"], ["excel"], etc.

    @classmethod
    @abstractmethod
    def can_parse(cls, file_path: Path, raw_text: str | None) -> DetectionResult:
        """
        Quickly assess whether this parser can handle the given file.
        Should take < 500 ms. Used by InstitutionDetector.
        Returns a DetectionResult with confidence score.
        """
        ...

    @abstractmethod
    def extract_metadata(self) -> StatementMetadata:
        """Extract statement-level metadata (dates, account info)."""
        ...

    @abstractmethod
    def extract_transactions(self) -> list[CandidateTransaction]:
        """Extract all transaction rows."""
        ...

    @abstractmethod
    def extract_holdings(self) -> list[CandidateHolding]:
        """Extract portfolio holdings / positions."""
        ...

    def extract_balances(self) -> list[CandidateBalance]:
        """Default: returns empty. Override in institution parsers."""
        return []

    def extract_dividends(self) -> list[CandidateDividend]:
        """Default: returns empty. Override if institution has dividend section."""
        return []

    def extract_fees(self) -> list[CandidateFee]:
        """Default: returns empty. Override if institution has fee section."""
        return []

    def parse(self, file_path: Path) -> ParserResult:
        """
        Orchestration method (final). Calls all extract_* methods,
        catches per-section errors without failing the whole parse,
        computes overall_confidence, returns ParserResult.
        """
        ...   # see implementation in scaffold
```

---

## Parser Registry

```python
# parsers/registry.py

class ParserRegistry:
    _parsers: dict[str, type[BaseParser]] = {}

    @classmethod
    def register(cls, institution_key: str | None, file_format: str):
        """Decorator to register a parser class."""
        def decorator(parser_cls: type[BaseParser]) -> type[BaseParser]:
            key = f"{institution_key or 'generic'}:{file_format}"
            cls._parsers[key] = parser_cls
            return parser_cls
        return decorator

    @classmethod
    def get_parser(
        cls,
        institution_key: str | None,
        file_format: str,
    ) -> type[BaseParser]:
        specific_key = f"{institution_key}:{file_format}"
        generic_key  = f"generic:{file_format}"
        fallback_key = "generic:pdf"   # last resort
        return (
            cls._parsers.get(specific_key)
            or cls._parsers.get(generic_key)
            or cls._parsers.get(fallback_key)
            or GenericFallbackParser
        )
```

---

## Institution Detection

```python
# parsers/detector.py

class InstitutionDetector:
    """
    Lightweight heuristic detector. Analyses filename, PDF text header,
    and CSV column signatures to identify the institution and format.
    Does NOT instantiate parsers — just returns a DetectionResult.
    """

    FILENAME_PATTERNS: dict[str, str] = {
        r"fidelity":        "fidelity",
        r"schwab":          "schwab",
        r"vanguard":        "vanguard",
        r"tdameritrade|tda": "tdameritrade",
        r"coinbase":        "coinbase",
        r"chase":           "chase_bank",
        r"wellsfargo|wf":   "wells_fargo",
        r"merrill":         "merrill_lynch",
        r"robinhood":       "robinhood",
    }

    PDF_HEADER_PATTERNS: dict[str, str] = {
        r"Fidelity Investments":      "fidelity",
        r"Charles Schwab":            "schwab",
        r"The Vanguard Group":        "vanguard",
        r"TD Ameritrade":             "tdameritrade",
        r"Coinbase":                  "coinbase",
        r"JPMorgan Chase":            "chase_bank",
        r"Wells Fargo":               "wells_fargo",
    }

    CSV_COLUMN_FINGERPRINTS: dict[frozenset, str] = {
        frozenset({"Run Date", "Action", "Symbol", "Security Description", "Quantity"}): "fidelity",
        frozenset({"Date", "Action", "Symbol", "Quantity", "Price", "Fees & Comm", "Amount"}): "schwab",
        frozenset({"Trade Date", "Transaction Type", "Symbol", "Shares", "Price", "Amount"}): "tdameritrade",
    }
```

---

## OCR Fallback Strategy

```
PDF file
    │
    ├── pdfplumber structured extraction
    │       └── yield ≥ 60% expected records → use this result (confidence: high)
    │
    ├── camelot lattice extraction (if pdfplumber < 60%)
    │       └── yield ≥ 40% expected records → use this result (confidence: medium)
    │
    └── pytesseract OCR (if both < 40%)
            └── DPI=300, language=eng
            └── Post-process with regex patterns for financial data
            └── confidence: low → always triggers NEEDS_REVIEW status
```

OCR is an optional dependency. If `pytesseract` is not installed, the parser logs a warning
and returns what it could extract with a low confidence score.

---

## Confidence Scoring Guide

| Score Range | Meaning | Import Status |
|---|---|---|
| 0.85 – 1.00 | High confidence; all expected fields found | `COMPLETED` |
| 0.65 – 0.84 | Moderate confidence; some fields missing | `COMPLETED` with info notices |
| 0.45 – 0.64 | Low confidence; significant gaps | `NEEDS_REVIEW` |
| 0.00 – 0.44 | Very low confidence or OCR-only | `NEEDS_REVIEW` with errors |

---

## Adding a New Institution Parser

1. Create `parsers/institutions/{institution_key}/parser.py`.
2. Subclass `BaseParser`.
3. Decorate with `@ParserRegistry.register("institution_key", "pdf")` (or csv/excel).
4. Implement `can_parse()`, `extract_metadata()`, `extract_transactions()`, `extract_holdings()`.
5. Optionally override `extract_dividends()`, `extract_fees()`, `extract_balances()`.
6. Write unit tests in `tests/parsers/test_{institution_key}_parser.py` using fixture files in `tests/fixtures/statements/`.
7. Bump `version` on the parser class when logic changes.

---

## Parser Debugging

Every `ParserResult` carries:

- `raw_text`: the full extracted text (stored to file, path in `parser_runs.raw_text_storage_path`)
- `warnings`: list of per-record issues
- `errors`: fatal extraction failures per section
- `overall_confidence`: aggregate score

The UI's "Import Detail" page shows parser warnings and confidence scores to help users
identify statements that need manual correction.

# QuantileFlow

Tracking option-implied distributions and managing daily positions.
**Research version (26 September 2026).**

For now this repository holds the system's technical proposal, a reference
mathematical core that generates its figures, the measurement-pilot pipeline
(ingestion, controls, labels, report and manifest) and an adapter that turns
Robinhood option chains into the normalized data contract. There is no market
history, no trained model and no empirical result: every figure and the report
template use **synthetic** data with fixed seeds.

The interface is in English — command-line flags, configuration keys, report
and table headers, figure text, manifest keys. The internals and the technical
proposal are in Spanish; output values are translated at the boundary by
[`quantileflow/vocabulario.py`](quantileflow/vocabulario.py).

## Documents

- [`docs/plan_de_trabajo.md`](docs/plan_de_trabajo.md): current research plan
  (26 September 2026). Opening question, phases with exit criteria and earlier
  corrections to the core.
- [`docs/avance_y_pendientes.md`](docs/avance_y_pendientes.md): what was done,
  findings and what is missing.
- [`docs/como_proseguir.md`](docs/como_proseguir.md): continuation of the plan;
  the next milestone is a reproducible report over real opening sessions
  (SPXW PM, 09:45, constant 30-day maturity).
- [`docs/estado_continuacion.md`](docs/estado_continuacion.md): what was built
  of that plan without data, the data-access problem and what is left.
- `docs/QuantileFlow_propuesta_tecnica.pdf`: technical guide to the process,
  stage by stage, with 64 charts and 19 diagrams. The PDF and the PNG figures
  are generated artifacts: `make figures && make pdf` rebuilds them.
- LaTeX source in [`docs/propuesta/`](docs/propuesta/): `main.tex`,
  `preambulo.tex`, one section per file under `secciones/` and the TikZ
  diagrams in `diagramas/`.

Contents: product and hypotheses; data and reconstruction of Q (raw chain with
controls, parity and call/put skew; SSVI, de-Americanization,
Breeden–Litzenberger, bands); transport, dynamics and innovation (W1/W2,
functional PCA, Kalman); from Q to P (quantile regression, combination);
regimes and confidence (BOCPD, calibration, adaptive conformal, abstention);
decision (joint scenarios, CVaR, no-trade zone, robustness, MPC); evidence
protocol; architecture and daily operation; build sequence and priorities.

## Layout

```
quantileflow/          reference core (numpy, scipy, pandas)
  calendario.py        real exchange calendar (XNYS), UTC instants, AM/PM settlement, ACT/365
  contrato.py          normalized quote and underlying schema, validator, OCC symbols,
                       table-to-capture adapter
  sources/robinhood.py Robinhood chains, instruments and quotes -> the data contract
  vocabulario.py       internal codes (Spanish) -> English labels for every output
  cadenas.py           immutable raw capture, controls with exclusion reasons, same-strike
                       parity with out-of-sample forward, de-Americanization, call - put
                       skew (log distance, RR25, slope), quality metrics
  etiquetas.py         1- and 5-session returns with decision_at, label_end_at, label_available_at
  piloto.py            constant 30-day maturity, daily table, changes, stability and verdict
  informe.py           exportable table, charts and Markdown report of the pilot
  corrida.py           reproducible run with a manifest of hashes
  almacen.py           immutable raw, Parquet, manifests and environment fingerprint
  opciones.py          Black, greeks, binomial tree with dividends
  superficies.py       constrained SSVI, function g, anchored CDF, convex fit in prices
  distribuciones.py    Breeden–Litzenberger, controls, quantiles with identification state
  transporte.py        1-D Wasserstein, signed changes, functional PCA, rearrangement
  filtrado.py          Kalman with time-varying observation noise, EWMA, persistence
  regimenes.py         BOCPD and threshold detector
  calibracion.py       pinball, CRPS, Brier, reliability, adaptive conformal with verified bound
  pronostico.py        regularized quantile regression (linear program)
  decision.py          linear program with CVaR, costs and risk budget
  evidencia.py         deflated Sharpe, block bootstrap, purged walk-forward
  sintetico.py         generators of the synthetic world behind the figures
tests/                 property tests of the core, quantiles, conformal, chains, contract,
                       calendar, labels, storage, pilot and the Robinhood adapter
configs/pilot.toml     versioned pilot configuration (provisional thresholds)
scripts/               pilot over normalized data, synthetic template, Robinhood ingest,
                       environment record
reports/               generated reports (never edited by hand) and verification records
docs/propuesta/        LaTeX source, diagrams, figure scripts and PNG figures
```

## Reproduce

```bash
pip install -r requirements.txt   # or requirements-bloqueo.txt for the exact verified versions
make test               # tests
make figures            # rebuilds the PNG figures (matplotlib, default style)
make pdf                # compiles the document and copies it to docs/QuantileFlow_propuesta_tecnica.pdf
make verify             # records commit, environment and test outcome in reports/verification/
make synthetic-pilot    # pilot report template on synthetic data in reports/synthetic_pilot/
```

With real normalized data (schemas in `quantileflow/contrato.py`):

```bash
python scripts/pilot.py --quotes data/normalized/quotes.parquet \
    --underlying data/normalized/underlying.parquet --from YYYY-MM-DD --to YYYY-MM-DD
```

`data/` stays out of Git: `data/raw/` keeps the original files, immutable and
addressed by their SHA-256; `data/normalized/` holds the Parquet tables. Every
run writes a `manifest.json` with the hashes of inputs and outputs, the
configuration, the commit and the exclusions.

`make pdf` needs a TeX distribution with `latexmk`, `tikz`, `tcolorbox`,
`mathpazo` and `babel-spanish` (for example TeX Live with the `latex-extra`,
`fonts-recommended`, `lang-spanish`, `science` and `pictures` packages).

## Robinhood

The committed path stops at files. `quantileflow/sources/robinhood.py` maps the
payloads Robinhood returns for options onto the data contract, and
`scripts/robinhood_ingest.py` reads capture files and writes normalized tables:

```bash
python scripts/robinhood_ingest.py captures/*.json --output data/normalized/robinhood
```

Neither opens a socket, holds a credential or can place an order. Fetching with
your own account lives in `local/`, which is outside Git — see
[`local/README.md`](local/README.md) once you have it, and the notes below.

**Capture both expirations, not one.** The pilot measures at constant maturity
by interpolating in total variance between the two expirations that bracket 30
days, so a capture holding a single expiration leaves the session unmeasured.
Which pair brackets 30 days changes every session, so
`sources.robinhood.bracketing_expirations` works it out with the pilot's own
rule before any contract is requested.

**What maps cleanly.** `settle_on_open` gives the AM/PM settlement the pilot
refuses to mix (SPX is AM, SPXW is PM), `underlying_type` gives the exercise
style, `trade_value_multiplier` the multiplier, and the quote carries bid, ask
and both sizes. `tests/fixtures/robinhood/spxw_2026-10-21.json` is a real
read-only capture of twenty SPXW contracts over both expirations that session
needed (29.3 and 30.3 days); the tests drive it end to end and it measures
RR25 at 30 days to a band of about 0.15 volatility points.

**What Robinhood cannot give, and is therefore left null.** There is no
exchange timestamp on an option quote, so `sello_evento_utc` stays empty and
the age of a quote is unknown rather than fabricated; the staleness control
then does not apply, and the report says so. There is no documented historical
availability either, so `disponible_utc` stays empty.

**There is no history to pull.** The endpoint answers "now", plus the previous
session's official close. A 09:45 series exists only if you poll at 09:45 each
session and accumulate it forward; it cannot be reconstructed backwards. A
capture taken after the close falls outside every in-session cut-off, which the
pipeline rejects instead of quietly accepting
(`tests/test_robinhood.py::test_captura_posterior_al_cierre_no_sirve_en_sesion`).

**Before you point this at your account.** Robinhood publishes no options API:
the only programmatic route is the private endpoints, reached with the same
credentials that can trade, under a customer agreement that prohibits automated
access. Captured quotes are OPRA-licensed, so they belong in `data/` or
`captures/` — both ignored — and not in a public repository. Every chain
request is an authenticated call that tells your broker which strikes and
expiries you are studying before you trade them.

## Scope of the tests

The tests use synthetic data, plus one real Robinhood capture for the adapter.
They check mathematical properties and that processing bid/ask chains separates
data effects (lagged quotes, dividends, early exercise, missing strikes,
opening windows) from a possible signal. They do not demonstrate predictive
validity or the quality of real data: that needs the historical sample from
phase 0 of the work plan.

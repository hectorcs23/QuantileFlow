# QuantileFlow

Tracking option-implied distributions and managing positions day to day.
**Research version; simulator and distribution analysis, progress as of 6 November 2026.**

This repository holds the technical proposal for the system, a reference mathematical core that
generates its figures, the measurement pilot's pipeline (ingestion, quality controls, labels, report
and manifest) and the daily capture of option chains from Alpaca. Market data is not in Git. There
are operational reviews and descriptive experiments on real captures, but there is still no
validated predictor. The proposal's figures, the report template and the PDE benchmarks all use
**synthetic** data.

> **A note on language.** This README and the demo are in English; the research documents linked
> below are written in Spanish, which is the working language of the project.

## Conditional simulator: budget, maturity and contracts

**[Live demo](https://hectorcs23.github.io/demo/quantileflow/)** — the budget comparator ported to
the browser, on synthetic data, with no install and no broker connection. It cross-checks itself
against this engine's reference cases while you watch.

[Historical capture on US$300](docs/CONTRATOS_OBSERVADOS_2026-11-06.md): 57 SPXW calls computable
in the 22 October snapshot, with filters, whole quantities, A/B comparison and maps by move, time
and IV. The indicative feed and the parity-implied reference block any purchase recommendation.
It opens at `/observadas` once a private capture is configured; the synthetic example stays
separate.

[A/B comparison of two purchases](docs/DOS_COMPRAS_2026-11-04.md): pick the two series and their
quantities, check the free cash each leaves, and compare the net gains if the move, the maturity or
the IV changes. It includes the example of three short-dated calls against one long-dated call on
the same US$300 budget.

Run `python scripts/simulador_opciones.py` and open <http://127.0.0.1:8791>. It compares complete
positions with whole contracts, costs, cash and sensitivity to move, time and IV, with charts and
scenario downloads. **This version uses synthetic European calls; it does not estimate probabilities
of winning.**

[Usage guide](apps/simulador/README.md) ·
[Results and next step](docs/SIMULADOR_CONDICIONAL_2026-10-21.md) ·
[Feasibility diagnosis of the surfaces](docs/FACTIBILIDAD_Y_DECISION_2026-10-20.md)

## Documents

- [Direct test of put verticals](docs/VERTICAL_PUTS_2026-11-04.md): 18 of 60 central changes clear
  the bid/ask; none clears every parity and timing control. The budget simulator takes priority.

- [Intraday change of the CDF at fixed SPX levels](docs/CAMBIO_CDF_2026-11-03.md): across eleven
  sessions, each of the 44 capture-and-expiry pairs admits simultaneous equality at the five levels
  studied.

- [Concentrated error and contrast with other sessions, 26 October](docs/RUIDO_CONCENTRADO_2026-10-26.md):
  bounds on total and per-quote error, five extra sessions and an independent check; the tails
  improve, but the distributional ambiguity persists.

- [Distributions under noisy quotes, 22 October](docs/DISTRIBUCIONES_RUIDOSAS_2026-10-22.md):
  route B, sets of admissible measures, filters and CDF bands; the repair's uncertainty checked
  against extreme distributions.

- [`docs/SKEW_BANDAS_2026-10-10.md`](docs/SKEW_BANDAS_2026-10-10.md): a fair contrast between flat
  IV and SSVI, ranking sensitivity and an independent forward control; six sessions of the free
  feed, US$0 of data.

- [`docs/VALIDACION_CADENAS_GRATIS_2026-10-10.md`](docs/VALIDACION_CADENAS_GRATIS_2026-10-10.md):
  the comparator tested on twelve private cut-offs; flat IV, holdout by strike, bands and
  synchronisation limits. Only aggregate results are public; US$0 of data.

- [`docs/COMPARADOR_PDF_2026-10-10.md`](docs/COMPARADOR_PDF_2026-10-10.md): PDE comparator, costs
  and loss limit; gain, return and robustness rankings, spot/IV/maturity sweeps and a check on a
  finer grid. Synthetic data, US$0.

- [`docs/VALORACION_CONSISTENTE_2026-10-10.md`](docs/VALORACION_CONSISTENTE_2026-10-10.md): pricing
  calls and puts from the same PDF, per-strike identities, sensitivities and convergence.

- [`docs/SENSIBILIDAD_DISTRIBUCION_2026-10-09.md`](docs/SENSIBILIDAD_DISTRIBUCION_2026-10-09.md):
  PDF, CDF, quantiles and tails; tangents and adjoints, verification and charts on a US$0 data
  budget.
- [`docs/AVANCE_PDE_GRATIS_2026-10-09.md`](docs/AVANCE_PDE_GRATIS_2026-10-09.md): the first European
  benchmark of prices and sensitivities, raw-data integrity and an isolated test of the extended
  capture.

- [`docs/plan_de_trabajo.md`](docs/plan_de_trabajo.md): the research plan in force (26 September
  2026). The opening question, the phases with their exit criteria, and earlier corrections to the
  core.
- [`docs/avance_y_pendientes.md`](docs/avance_y_pendientes.md): what was done, what was found and
  what is missing.
- [`docs/como_proseguir.md`](docs/como_proseguir.md): the plan's continuation; the next milestone is
  a reproducible report over real opening sessions (SPXW PM, 09:45, constant 30-day maturity).
- [`docs/estado_continuacion.md`](docs/estado_continuacion.md): what was built of that plan without
  data, the data-access problem and what is still missing.
- [`docs/resumen_sesion_alpaca.md`](docs/resumen_sesion_alpaca.md): a summary of the Alpaca session
  and a map of where each file lives.
- [`docs/respuesta_revision_e2b92f0.md`](docs/respuesta_revision_e2b92f0.md): the eight findings from
  the review of commit `e2b92f0`, their corrections and regression tests, and the methodological
  decisions still open.
- [`docs/aceptacion_operacion.md`](docs/aceptacion_operacion.md): acceptance of the operation,
  session by session. On Monday the 28th GitHub did not fire the scheduled workflows and the session
  was lost.
- [`docs/respuesta_verificacion_instalacion.md`](docs/respuesta_verificacion_instalacion.md): the
  independent verification of the installation and the upkeep of the templates before 19 October
  (`ubuntu-24.04`).
- [`docs/instalacion_repo_datos.md`](docs/instalacion_repo_datos.md): the data repository's
  installation and its manual test, both verified, and what acceptance still needs.
- [`docs/respuesta_verificacion_4ffde8a.md`](docs/respuesta_verificacion_4ffde8a.md): the
  verification of `4ffde8a` (now pinned in the workflows) and the sequence for accrediting the daily
  capture.
- [`docs/respuesta_cambios_operativos.md`](docs/respuesta_cambios_operativos.md): logging the capture
  even when it fails on start, an explicit `--resoluciones`, and tests portable to Windows.
- [`docs/respuesta_cierre_b240dc2.md`](docs/respuesta_cierre_b240dc2.md): after the revalidation
  closed: a failure-proof log of every run, the operational review of the first sessions, and how to
  continue with the capture test.
- [`docs/respuesta_revalidacion_5c15028.md`](docs/respuesta_revalidacion_5c15028.md): the
  revalidation of `5c15028`: a dividend received without an ex-date or without an amount leaves the
  labels it could affect pending, until the provider completes it or a resolution supplies the data.
- [`docs/respuesta_revalidacion_a5e2748.md`](docs/respuesta_revalidacion_a5e2748.md): the
  revalidation of `a5e2748`: dividend discrepancies that only dated evidence resolves, coverage
  under each query's filters, label spans carrying the state at each instant (provisional, accepted
  under the 60-day policy, pending) and the backup as a favourable scenario.
- [`docs/respuesta_revision_8c97b2b.md`](docs/respuesta_revision_8c97b2b.md): the review of
  `8c97b2b`: dividend coverage kept separate, events and labels versioned, a preparation window for
  the backup, and corrections to the previous delivery.
- [`docs/respuesta_revalidacion_d815bdd.md`](docs/respuesta_revalidacion_d815bdd.md): the delivery
  the revalidation of `d815bdd` asked for: signal, reference and target kept separate; SPY from the
  historical SIP with dividends; recovery of interrupted captures and hourly workflows.
- [`docs/fuente_alpaca.md`](docs/fuente_alpaca.md): what Alpaca offers (verified 26 September 2026),
  the daily forward capture, the first verification against real data, and the decisions still open
  (where the capture runs and which feed to use).
- `docs/QuantileFlow_propuesta_tecnica.pdf`: a technical guide to the process, stage by stage, with
  64 charts and 21 diagrams. Its section 11 summarises the state of the project as of 28 September
  2026: what was built, the daily capture now installed, the reviews, and what is missing. The PDF
  and the PNG figures are generated artefacts: `make figuras && make pdf` regenerates them.
- LaTeX source in [`docs/propuesta/`](docs/propuesta/): `main.tex`, `preambulo.tex`, one section per
  file in `secciones/`, and the TikZ diagrams in `diagramas/`.

Contents: product and hypothesis; data and reconstruction of Q (raw chain with quality controls,
parity and call/put asymmetry; SSVI, de-Americanisation, Breeden–Litzenberger, bands); transport,
dynamics and innovation (W1/W2, functional PCA, Kalman); from Q to P (quantile regression,
combination); regimes and confidence (BOCPD, calibration, adaptive conformal, abstention); decision
(joint scenarios, CVaR, no-trade zone, robustness, MPC); evidence protocol; architecture and daily
operation; build sequence and priorities.

## Layout

```
quantileflow/          reference core (numpy, scipy, pandas)
  calendario.py        real exchange calendar (XNYS), UTC instants, AM/PM settlement, ACT/365 maturity
  contrato.py          normalised schema for quotes and underlying, validator, OCC symbols,
                       adapter from tables to captures
  cadenas.py           immutable raw capture, controls with exclusion reasons, same-strike parity
                       with an out-of-sample forward, de-Americanisation, call − put asymmetry
                       (log distance, RR25, slope), quality metrics
  etiquetas.py         1- and 5-session returns with decision_at, label_end_at, label_available_at;
                       total return (dividends on their ex-date) and price return
  piloto.py            constant 30-day maturity, daily table, changes, stability and verdict;
                       signal (SPXW), option reference (pointwise rule) and target (historical rule)
  informe.py           exportable table, charts and Markdown report for the pilot
  corrida.py           reproducible run with a manifest of hashes
  almacen.py           immutable raw data, Parquet, manifests and environment fingerprint
  alpaca.py            Alpaca adapter: client, immutable raw data per response, log and manifest per
                       capture, recovery, absolute maturity, historical SIP, dividends, expiry
                       selection and normalisation to the contract
  implicito.py         implied level of the underlying by parity (Alpaca does not give the SPX level)
  diagnostico.py       capture diagnosis: strict eligibility at the cut-off and feed quality
  operacion.py         operational review: state of each cut-off, punctuality, backup, SIP and dividends
  opciones.py          Black, greeks, binomial tree with dividends
  pde.py               reference European diffusion and discrete adjoint of prices
  distribucion_pde.py  reconstructed PDF/CDF, quantiles, tails and sensitivities of Q distributions
  superficies.py       SSVI with constraints, g function, anchored CDF, convex fit in prices
  distribuciones.py    Breeden–Litzenberger, controls, quantiles with identification state
  transporte.py        1-D Wasserstein, signed changes, functional PCA, rearrangement
  filtrado.py          Kalman with varying observation noise, EWMA, persistence
  regimenes.py         BOCPD and threshold detector
  calibracion.py       pinball, CRPS, Brier, reliability, adaptive conformal with a verified bound
  pronostico.py        regularised quantile regression (linear program)
  decision.py          linear program with CVaR, costs and risk budget
  evidencia.py         deflated Sharpe, block bootstrap, walk-forward with purging
  sintetico.py         generators for the synthetic world behind the figures
tests/                 property tests for the core, quantiles, conformal, chains, contract,
                       calendar, labels, storage, pilot and the Alpaca adapter (no network)
configs/piloto.toml    versioned pilot configuration (provisional thresholds)
configs/captura_alpaca.toml  what is captured from Alpaca, when, and with which feed
ops/repo_datos/        template for the private data repository: hourly capture workflows, historical
                       SIP and README
scripts/               pilot on normalised data, synthetic template, environment log, capture,
                       history, normalisation, verification and operational review of Alpaca
reports/               generated reports (never hand-edited) and verification logs
docs/propuesta/        LaTeX source, diagrams, figure scripts and PNG figures
```

## Reproducing

```bash
pip install -r requirements.txt   # or requirements-bloqueo.txt for the exact verified versions
make test               # tests
make figuras            # regenerates the PNG figures (matplotlib, default style)
make pdf                # builds the document and copies it to docs/QuantileFlow_propuesta_tecnica.pdf
make verificar          # logs commit, environment and test result in reports/verificacion/
make piloto-sintetico   # pilot report template on synthetic data in reports/piloto_sintetico/
```

Capturing from Alpaca (needs `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` in the environment; see
[`docs/fuente_alpaca.md`](docs/fuente_alpaca.md)):

```bash
make captura-prueba                                   # immediate test capture
make captura                                          # trading day: waits and captures at 09:45 and 10:00 ET
make historico-alpaca                                 # SPY SIP at each cut-off (after 15 min) and dividends
make verificar-alpaca FECHA=2026-09-28                # eligibility and quality in reports/verificacion_alpaca/
make normalizar-alpaca DESDE=2026-09-28 HASTA=2026-11-13   # pilot tables from the raw data
```

With real normalised data (schemas in `quantileflow/contrato.py`). The target is SPY from the
historical SIP, with dividends:

```bash
N=data/normalized/alpaca
python scripts/piloto.py --cotizaciones $N/cotizaciones.parquet --subyacente $N/subyacente.parquet \
    --dividendos $N/dividendos.parquet --cobertura-dividendos $N/cobertura_dividendos.parquet \
    --fuente-objetivo alpaca/sip --desde YYYY-MM-DD --hasta YYYY-MM-DD
```

`data/` stays out of Git (licensing and size; this repository is public): `data/raw/` keeps the
original files, immutable and addressed by their SHA-256; `data/normalized/` keeps the Parquet
tables. Every run writes a `manifiesto.json` with the hashes of its inputs and outputs, the
configuration, the commit and the exclusions.

`make pdf` needs a TeX distribution with `latexmk`, `tikz`, `tcolorbox`, `mathpazo` and
`babel-spanish` (for example TeX Live with the `latex-extra`, `fonts-recommended`, `lang-spanish`,
`science` and `pictures` packages).

## What the tests cover

The 404 tests run on synthetic data. They check mathematical properties, and that the bid/ask chain
processing separates data effects (stale quotes, dividends, early exercise, missing strikes, opening
windows) from a possible signal. They do not demonstrate predictive validity, nor the quality of
real data: that requires the historical sample from phase 0 of the research plan.

## Data provenance and what gets published

This repository is public. Access to a source does not imply permission to redistribute its data, so
the rule is: code, aggregate results and synthetic data are published; raw third-party quotes and
anything coming from an account are not.

| Source | How the data arrives | What is published here |
|---|---|---|
| Alpaca | HTTP API. The key and secret are read from `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` in the environment and are never written to a file; in GitHub Actions they travel as encrypted secrets. See [`docs/fuente_alpaca.md`](docs/fuente_alpaca.md). | Aggregates and derived measures only: counts, percentages, medians, bands and RR25 per expiry, as in [`reports/verificacion_alpaca/`](reports/verificacion_alpaca/). Raw chains stay in `data/`, outside Git. |
| Robinhood | A read-only market-data connector, on a separate branch of this repository. It is never used to send orders or to query the account: the adapter is a pure mapping, with no sockets, credentials or tokens. | Aggregates only. Raw captures are not published and the adapter's fixture is **synthetic**, generated with Black–Scholes on an invented smile and a fixed seed. |
| Synthetic | Generators from this repository, with fixed, reproducible seeds. | Everything: the proposal's figures, the pilot report template, the PDE benchmarks and the test fixtures. |

Outside the repository, without exception: keys, secrets, access and refresh tokens, cookies and
saved sessions, TOTP seeds and recovery codes, account numbers and personal data, and any personal
financial activity (positions, real quantities, orders, fills, balances, PnL). The exclusions live
in [`.gitignore`](.gitignore); the variables the code expects, with empty values, in
[`.env.example`](.env.example).

Removing a name does not anonymise: dates, symbols, quantities and prices can still identify
personal trades, and turning an identifier into a hash does not prevent that either.

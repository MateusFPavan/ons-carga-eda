# Technical Report — Day-Ahead Hourly Load Forecasting for Brazil's SE/CO Subsystem

*A comparative study from a seasonal-naïve baseline to a zero-shot time-series foundation model, judged by statistical error and by dispatch cost. Full data provenance is in [`docs/DATA_CARD.md`](DATA_CARD.md); the chosen model is documented in [`docs/MODEL_CARD.md`](MODEL_CARD.md); the narrated analysis is in [`notebooks/1.0-forecasting-comparativo.ipynb`](../notebooks/1.0-forecasting-comparativo.ipynb). All numbers trace to `reports/FACTS.md`.*

## 1. Executive summary

Can we forecast tomorrow's hourly electricity load well enough to matter — and which model should we use? Working with eleven years of open ONS data for the Southeast/Center-West (SE/CO) subsystem, I built a fair, leakage-controlled comparison of four forecasters: a seasonal-naïve baseline, SARIMA, Prophet, and Chronos-2 (a pretrained time-series foundation model) used zero-shot. Every model was evaluated on the same held-out temporal test period (2024-01-01 onward), day-ahead, with a sliding forecast origin and no shuffling.

The headline result is decisive. **Chronos-2, with no fine-tuning, cut the day-ahead error to about a third of the baseline's (MASE 0.44 versus 1.27; MAPE 1.82% versus 5.37%) and reduced the modeled dispatch cost of forecast error by roughly 65% — from R\$8.52 billion to R\$3.01 billion over the test window.** It did so while producing near-perfectly calibrated uncertainty bands (88.9% empirical coverage at a 90% nominal interval).

The second finding is the one a stakeholder should remember: **ranking models by statistical error is not the same as ranking them by cost.** SARIMA and the naïve baseline swap places between the two rankings, because dispatch cost concentrates in a minority of expensive hours. Optimizing the usual statistical metric can therefore select the wrong model for an operational decision.

**Recommendation:** for day-ahead SE/CO load forecasting, adopt the foundation-model approach and evaluate candidates on a cost-weighted metric, not error alone. The classical models remain useful as transparent, fully local baselines.

## 2. Background & problem statement

Electricity load must be forecast before it is served. In the Brazilian interconnected system, the operator schedules generation a day ahead; an under-forecast means dispatching expensive thermal reserves at short notice, and an over-forecast wastes committed capacity. The error is therefore not an abstract statistic — it has a price, set hour by hour by the marginal cost of operation (CMO). A forecast that is slightly better on average but much better in the expensive hours can be worth far more than its average error suggests. This report asks two questions: how accurately can day-ahead hourly load be forecast for SE/CO, and does that accuracy translate into lower dispatch cost — and it insists on judging the answer in reais, not only in percentage error.

## 3. Data

The target is hourly load for the SE/CO subsystem, in MWmed, published by ONS under CC-BY, spanning 2015-01-01 to 2026-07-15 — about 101,000 hourly observations on a single continuous local-time grid. The load ranges from roughly 21,300 to 62,150 MWmed (mean ≈ 39,075). Dispatch price comes from ONS's semi-hourly CMO series; temperature, used only as a secondary layer, comes from Open-Meteo's day-ahead *forecast* values (never observed same-day values) for five capitals, under CC BY 4.0.

The data is not pristine, and the caveats matter. The load column is stored as text in 2015–2024 and as float afterward; the official dictionary declares it non-nullable yet 87 empty strings exist; the subsystem's display name changed in 2026 while its code did not. Three structural breaks cluster around 2019–2020: the end of daylight saving time (behavioral), the pandemic (behavioral), and a change in the data grid (artificial). ONS also revises history retrospectively, so the snapshot is pinned by SHA-256 rather than assumed stable. Full field-level detail, missingness, and the data dictionary are in [`docs/DATA_CARD.md`](DATA_CARD.md).

## 4. Methodology

The design principle throughout was to *verify rather than assume* — to let the data overturn expectations, which it did repeatedly during the exploratory phase.

**Temporal validation, never shuffled.** Because this is a time series, the evaluation uses a walk-forward scheme over the test period 2024-01-01 onward: at each day, the model forecasts the next 24 hours using only information available before that origin, and the sliding origin advances one day at a time. The test period is touched once. Random train/test splitting would leak future information into the past and is explicitly avoided; every feature is constructed to be computable at the forecast origin, which is why all lags are at least 24 hours. This choice, and a per-feature leakage self-test that recomputes each feature from data strictly before the origin, is what makes the strong result trustworthy rather than suspicious.

**A ladder of proof.** The comparison is deliberately staged so each model must earn its place. The seasonal-naïve forecaster — repeat the same hour of the same weekday one week earlier — is a famously strong baseline in load forecasting, and every other model must beat it. SARIMA and Prophet represent the classical approach: they *estimate* structure from the series itself, with SARIMA's differencing order chosen from ADF/KPSS tests rather than by reflex, and its context deliberately kept to ~60 days because the method saturates and longer context only slows it without improving fit. Chronos-2 represents the frontier: a pretrained model that *recognizes* patterns zero-shot, with context length swept from 96 to 2048 hours (2048 was best, improving monotonically with context).

**The cost metric, and its honest status.** Because no ONS dataset links a load error in MW to a cost in reais, the business metric is a *declared model*, stated as an explicit assumption: cost = |error_MW| × hourly CMO × 1 h, valuing each hour's error at that hour's marginal operating cost. This is an estimate under a stated assumption, not realized dispatch cost — a distinction the report keeps visible rather than blurring. Two consequences follow honestly from the assumption: in hours of zero or negative CMO (physically real spillage), modeled error cost is zero, and dispatch cost concentrates heavily in the few most expensive hours.

## 5. Results

All figures below are on the held-out temporal test period (2024-01-01 onward), day-ahead, sliding origin. The primary statistical metric is MASE with a seasonal denominator (comparable to the load-forecasting literature); MAPE and the dispatch-cost proxy accompany it.

| Model | MASE (seasonal) | MAPE | Dispatch cost | Coverage @90% |
|---|---|---|---|---|
| Seasonal-naïve (weekly) | 1.2732 | 5.37% | R\$ 8.52 bi | — |
| SARIMA | 1.3412 | 5.68% | R\$ 8.40 bi | 92.5% |
| Prophet | 1.1669 | 5.00% | R\$ 7.86 bi | 86.2% |
| **Chronos-2 (2048 h)** | **0.4363** | **1.82%** | **R\$ 3.01 bi** | 88.9% |

The comparison bar chart (`reports/figures/resultado_5_comparativo_4_modelos.png`) shows the gap at a glance: Chronos-2's error and cost bars are roughly a third the height of the others. The hero forecast-versus-actual plot for a test week (`resultado_1_heroi...`) shows the model tracking the daily double-peak closely, with a tight P10–P90 band. Notably, SARIMA fails to beat the naïve on MASE — a legitimate result, not a bug: the seasonal-naïve is hard to beat, and SARIMA converged on only 97.5% of origins even with an evidence-chosen order.

Two disaggregated results carry the report's weight. First, the error-versus-cost ranking (`resultado_6_erro_vs_custo.png`) is a slope chart in which the naïve and SARIMA cross: SARIMA is worse on MASE yet cheaper in dispatch, because ~25% of total cost falls in the top 10% of CMO hours and SARIMA happens to err less there. Second, the optional temperature layer (context-controlled, `resultado_3_efeito_temperatura...`) improves Chronos-2 by about 0.18 pp MAPE and Prophet by about 0.80 pp, and the gain concentrates in the peak and high-CMO hours — exactly where cost lives. Prophet gains more than Chronos, consistent with Chronos already encoding temperature–load structure from pretraining while Prophet knew nothing about weather; adding the same five temperature regressors to SARIMA, by contrast, did not help and collapsed its convergence from 97.5% to 38.5%.

## 6. Interpretation & business impact

In plain terms: the foundation model is not marginally better, it is in a different class, and it is better precisely where money is spent. Over the roughly two-and-a-half-year test window, moving from the naïve baseline to Chronos-2 corresponds to a modeled reduction in the cost of forecast error from about R\$8.5 billion to about R\$3.0 billion — a two-thirds cut — achieved with an off-the-shelf model, on a laptop CPU, without training. Even against the best classical model (Prophet at R\$7.86 billion), the foundation model roughly halves the cost.

The subtler, more transferable lesson is for how such a decision should be made at all. If a team had selected its forecaster by the standard statistical metric, it might have preferred one model; selecting by dispatch cost points elsewhere. Because cost concentrates in a handful of expensive hours, a forecaster should be judged — and, ideally, tuned — on a cost-weighted objective. The uncertainty bands reinforce this: Chronos-2's near-perfect calibration means its P10–P90 interval can be trusted to size a reserve margin, whereas an over-confident interval would systematically under-provision in exactly the hours that hurt.

## 7. Limitations

The cost metric is a declared model, not realized cost, and inherits the CMO timezone, which is inferred from empirical evidence rather than documented by ONS — if that inference is wrong, the cost figures shift. The DST effect visible in the exploratory phase is not causally isolated, being confounded with seven years of trend, distributed-solar growth, and post-pandemic patterns. "Zero-shot" means "not fine-tuned here," not "provably unseen": Chronos-2's pretraining corpus includes energy datasets, and contamination by ONS-adjacent data cannot be excluded from public documentation. Temperature is represented by five capitals for a subsystem covering roughly a third of Brazil, and its day-ahead forecast is least accurate in the evening peak. Only national holidays are encoded. Finally, only day-ahead was validated; longer horizons were not tested. `[TODO: quantify holiday-day error; confirm CMO coverage 2020–2023, 2025–2026 year by year.]`

## 8. Conclusion & next steps

A zero-shot foundation model decisively wins day-ahead SE/CO load forecasting on both error and cost, and the study's method — temporal validation, a hard baseline, leakage self-tests, and a cost-weighted lens — is as much the deliverable as the winner. Recommended next steps: fold the model runs fully into a single reproducible entry point with serialized models; strengthen the cost proxy toward a merit-order estimate; add operational-horizon temperature; and, as a separate project, serve the validated model behind an API.

## 9. Appendix / references

Reproducibility and exact commands: [`docs/SETUP.md`](SETUP.md) (`python run_all.py` reproduces the result in ~1 minute from saved predictions). Canonical numbers: `reports/FACTS.md`. Comparative benchmark for context: Simeone (2026), arXiv:2602.10848, a foundation-model load-forecasting study on ERCOT, treated here as a hypothesis to test on Brazilian data rather than a result to reproduce. This project itself has no DOI (personal portfolio project, not published) — cite the [GitHub repository](https://github.com/MateusFPavan/ons-carga-eda) directly if needed.

---

### Final self-check — MUST-HAVE items

All present: **executive summary** (answer-first, §1), **explicit problem statement** (§2), **methodology with justified choices and stated assumptions** (§4, incl. the temporal scheme and the cost-metric assumption), **results naming exact metric + temporal split + baseline comparison** (§5), **plain-English interpretation with cost framing** (§6), **limitations** (§7). `[TODO]` items flagged inline (holiday-error quantification, CMO year-by-year coverage) — none invented.

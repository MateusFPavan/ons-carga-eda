# Cutting the Cost of Electricity Forecast Error by 65% for Brazil's Largest Grid Region

**Summary:** Grid operators must predict tomorrow's electricity demand hour by hour — and every error costs real money in emergency generation. I built and validated a forecasting approach that cuts the modeled cost of that error by roughly two-thirds.

---

## 📊 Headline impact

> **R\$8.5bi → R\$3.0bi** in modeled dispatch cost of forecast error over a 2.5-year test period — a **65% reduction**, with forecast error cut from 5.4% to **1.8%**.
>
> *Achieved with an off-the-shelf model, on a laptop CPU, with no model training.*

---

## Context

Brazil's grid operator schedules generation a day in advance. Under-predict demand and expensive backup plants fire up at short notice; over-predict and committed capacity is wasted. The error carries an hourly price. This project asked whether modern forecasting could meaningfully reduce that bill for the Southeast/Center-West region, which serves roughly a third of the country.

## What I did

- **Built a fair comparison of four forecasters** — from a hard industry baseline (seasonal-naïve) through classical models (SARIMA, Prophet) to a pretrained AI foundation model — judged on identical terms.
- **Used 11 years of official open data** (grid operator + weather), version-locked by checksum so results are exactly reproducible.
- **Enforced realistic validation**: forecasts only ever saw the past — the discipline separating a real forecast from an accidentally cheating one.
- **Measured error in reais**, pricing each hour's mistake at that hour's marginal cost of generation.
- **Tested whether weather forecasts add value**, using only information genuinely available the day before.

## Results

- **The AI model won decisively** — one-third the error of the baseline, 65% lower cost, with no training or tuning.
- **Ranking models by accuracy gives the wrong answer** — two models swap places when judged by cost, because cost concentrates in a few expensive hours. A team optimizing the standard metric would pick the costlier model.
- **Weather data helps exactly where it pays** — gains concentrate in peak, high-price hours.
- **Uncertainty estimates proved trustworthy** (88.9% coverage on a 90% band), so they can safely size a reserve margin.

## Skills & stack

`Time-Series Forecasting` · `Python` · `pandas` · `Foundation Models (Chronos-2)` · `SARIMA` · `Prophet` · `statsmodels` · `PyTorch` · `Backtesting / Walk-Forward Validation` · `Data Leakage Prevention` · `Reproducible Pipelines` · `Cost-Benefit Analysis` · `Open Data (ONS, Open-Meteo)` · `matplotlib` · `Git`

## Links

**Repository:** [https://github.com/MateusFPavan/ons-carga-eda](https://github.com/MateusFPavan/ons-carga-eda) · **Full technical report:** [`docs/technical_report.md`](../docs/technical_report.md) · **Contact:** [mateusfardinpavan@gmail.com](mailto:mateusfardinpavan@gmail.com) · [LinkedIn](https://www.linkedin.com/in/mateus-fardin-pavan)

*The cost figure is a transparent estimate — each hour's error priced at that hour's official marginal generation cost — not audited operator accounting. Full methodology and limitations in the report.*

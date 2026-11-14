# Together 9B: full 100-prompt evaluation

Model: `jared-309b/Qwen-9B-finetune`. System prompt: `v1`. Temperature: 0. Maximum output tokens: 4096.

All 100 held-out prompts across 10 strategy templates. The 870 training prompts are excluded. Three previously evaluated 9B outputs are reused. Original generations are preserved, with no repairs or mock outputs.

All original generations were saved before QC and judge processing. Together inference is no longer required for this run.

Candidate execution and 1-5 prompt adherence are separate results. Missing behavior metrics remain blank. Template similarity is diagnostic and does not penalize unspecified prompt choices.

Gold evidence is reused only when its exact source hash matches. Some Gold runs are historical and use an older QC engine. Candidate run engine versions and exact evidence remain in the JSON files.

Original provider outputs can contain language-instruction violations. They are retained unchanged as evaluation evidence. The report and derived summaries are in English.

English code views translate one non-English comment fragment from the reused third smoke-test output. These display copies are separate from the exact original code used by QC and Claude. No trading logic is changed.

| Metric | Value |
|---|---:|
| Requested prompts | 100 |
| Completed candidate backtests | 15 |
| Valid Claude judgments | 100 |
| Mean fidelity | 1.9 |

[Full terminal log](evaluation.txt) | [Machine-readable summary](results_summary.json)

## equity-rsi-overbought-oversold_v01

Prompt: Can you make me a bot for QQQ that buys when the RSI says it's oversold and shorts when it says overbought? I usually look at the hourly chart. Test it on the last few months of 2024.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate trades QQQ with a 14-period hourly RSI over Sep–Dec 2024, and it buys when RSI is oversold. However, it never opens a short position: line 46 is the only order that opens a position, and it is long-only (+1.0). The explicit 'shorts when overbought' half of the request is therefore missing, and the short-cover branch on line 42 can never run. Signals are also checked only once a day, one minute after the open (lines 25-29), instead of on the user's hourly chart. Finally, the exit logic liquidates a long as soon as RSI is back above 30 (line 48). With one key element missing and a second mismatch in signal timing, the code is in the same strategy family but with several elements wrong.

[English code view](candidates_english/equity-rsi-overbought-oversold_v01.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v01.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v01.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 18
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-rsi-overbought-oversold_v02

Prompt: I want a QQQ bot on 1 hour candles. Use the 14 period RSI. Buy with everything when RSI goes under 30 and sell once it's back over 50. Short with everything when RSI goes over 70 and buy back once it's under 50. Run it Sept 1 to Dec 31 2024 with 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The asset, date range, cash, sizing and threshold logic match the request. Two key elements tied to '1 hour candles' are wrong. First, line 18 calls self.rsi(self._qqq, 14, Resolution.HOUR), which passes Resolution.HOUR positionally into the moving_average_type slot instead of the resolution slot. So the indicator is not reliably a 14-period Wilder RSI on hourly bars: depending on binding it either fails or runs on the security's minute data with a different smoothing type. Second, lines 25-29 evaluate signals only once per day, one minute after the open, instead of on each hourly bar. Thresholds also use inclusive comparisons (<=30, >=50, <=50, >=70) instead of strict 'under' and 'over', a minor boundary difference.

[English code view](candidates_english/equity-rsi-overbought-oversold_v02.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v02.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v02.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 18
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-rsi-overbought-oversold_v03

Prompt: I want a QQQ bot on 1 hour candles. Use the 14 period RSI (the Wilder kind). Buy with everything when RSI goes under 30 and sell once it's back over 50. Short with everything when RSI goes over 70 and buy back once it's under 50. Run it Sept 1 to Dec 31 2024 with 100k. Also plot the RSI on a chart so I can see it, name the class RsiBot, don't trade until the RSI has enough data, and put comments explaining each rule.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate keeps the right asset, period, dates, cash, RSI plot and readiness guard, but the core trading logic is wrong. There is no short entry when RSI goes over 70. The long exit fires at RSI > 70 instead of > 50. The short cover fires at RSI < 30 instead of < 50. Signals are checked only once a day instead of on each hourly candle. Wilder smoothing is never passed: Resolution.HOUR sits in the moving-average-type slot. The class is not named RsiBot, and the comments describe the wrong rules. This is the same strategy family with several key elements wrong.

[English code view](candidates_english/equity-rsi-overbought-oversold_v03.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v03.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v03.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._rsi = self.rsi(self._qqq.symbol, 14, Resolution.HOUR)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 16
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-rsi-overbought-oversold_v04

Prompt: QQQ RSI mean-rev, hourly, long oversold / short overbought, exit at midline. Q4 2024. Need it today.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is an RSI strategy on QQQ, but several key requested elements are wrong or missing. (1) There is no long-on-oversold entry; _rsi_threshold_buy=30 is defined but never used. (2) The short exits when RSI falls back to 70 or below, not at the 50 midline. (3) Signals are checked once per day, 1 minute after the open, not hourly. (4) The backtest starts 2024-09-01, which adds September to the requested Q4 2024 window. Only the asset, the hourly 14-period RSI and the short-overbought entry match the request.

[English code view](candidates_english/equity-rsi-overbought-oversold_v04.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v04.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v04.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._qqq.rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 15
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-rsi-overbought-oversold_v05

Prompt: QQQ hourly, RSI(14). Long 100% <30, flat >50. Short 100% >70, flat <50. 2024-09-01 to 2024-12-31, 100k. Gate on indicator ready.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

Asset, dates, cash, RSI period and the ready-gate are correct, and the long/short entries match the request. However, both requested exits (flatten a long when RSI>50, flatten a short when RSI<50) are missing, so positions only ever flip between long and short. The QQQ subscription uses default minute resolution rather than hourly, so trade decisions run every minute. The RSI helper call passes Resolution.HOUR in the moving-average-type position, which leaves the indicator's smoothing and resolution uncertain. That is several key elements wrong within the same strategy family.

[English code view](candidates_english/equity-rsi-overbought-oversold_v05.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v05.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v05.json)

QC error:

```text
Algorithm.Initialize() Error: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'QCAAlgorithm' is not defined
  at 
    class EquityRSIMeanReversionAlgorithm(QCAAlgorithm):
                                          ^^^^^^^^^^^^
 in main.py: line 5
 name 'QCAAlgorithm' is not defined Stack Trace: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'QCAAlgorithm' is not defined
  at 
    class EquityRSIMeanReversionAlgorithm(QCAAlgorithm):
                                          ^^^^^^^^^^^^
 in main.py: line 5
 name 'QCAAlgorithm' is not defined
```

## equity-rsi-overbought-oversold_v06

Prompt: QQQ hourly, RSI(14) Wilder. Long 100% <30, flat >50. Short 100% >70, flat <50. 2024-09-01 to 2024-12-31, 100k. Gate on indicator ready. Also: auto warm-up on, plot RSI, snake_case API only, one class, no helper files, keep it under 40 lines so we can diff it fast.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

This is the RSI mean-reversion family on QQQ with the right dates, cash, warm-up, plotting and ready gate. Several key rules are wrong or missing. The entire short side (short at RSI>70, cover at RSI<50) is absent. The long exit fires at RSI>70 instead of RSI>50. The equity is added at default (minute) resolution rather than hourly. Resolution.HOUR is passed positionally into the RSI's moving-average-type slot, so Wilder smoothing is not set explicitly and hourly resolution is not reliably applied.

[English code view](candidates_english/equity-rsi-overbought-oversold_v06.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v06.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v06.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 15
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-rsi-overbought-oversold_v07

Prompt: Our research desk needs a baseline two-sided RSI mean-reversion algorithm on QQQ at hourly resolution for the September to December 2024 window, consistent with our internal implementation. Standard paper account. Use conventional thresholds.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate keeps the general family: RSI(14) mean reversion on QQQ with conventional 30/70 thresholds over Sep 1 to Dec 31, 2024, using $100k cash. Two key elements are wrong, however. (1) The request explicitly asks for a two-sided strategy, but the candidate is long-only: it buys when RSI < 30 and liquidates when RSI > 70, with no short entry. (2) The request asks for hourly resolution, but the candidate subscribes to QQQ at the default (minute) resolution and evaluates signals only once per day, 1 minute after the open. It does not act hourly. The RSI call on line 13 is also questionable: Resolution.HOUR is passed in the third positional slot, which in the rsi() signature is moving_average_type. That may misconfigure the indicator or fail. 'Consistent with our internal implementation' refers to something not provided, so the request is partly unverifiable.

[English code view](candidates_english/equity-rsi-overbought-oversold_v07.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v07.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v07.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._qqq.rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 13
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-rsi-overbought-oversold_v08

Prompt: Implement the desk's two-sided RSI mean-reversion reference on QQQ. Resolution: hourly. Window: 2024-09-01 to 2024-12-31. Capital: 100,000. Indicator: RSI, 14 periods, Wilder smoothing. Rules: flat or short and RSI below 30, allocate 100% long; long and RSI above 50, liquidate; flat or long and RSI above 70, allocate 100% short; short and RSI below 50, liquidate. No signals before the indicator is ready.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested two-sided RSI mean-reversion strategy. It enters on RSI crossing 50 in the momentum direction: it goes long when RSI is above 50 and short when RSI is below 50. The requested 30/70 entry thresholds are absent. Both exit rules are inverted. Resolution is daily or minute, not hourly. Sizing passes 1000 to set_holdings, which means 100000% of the portfolio instead of 100%. Only the asset, the date window, the capital and the RSI period match.

[English code view](candidates_english/equity-rsi-overbought-oversold_v08.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v08.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v08.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._rsi = self.rsi(self._qqq, 14, Resolution.DAILY)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 18
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-rsi-overbought-oversold_v09

Prompt: Implement the desk's two-sided RSI mean-reversion reference on QQQ. Resolution: hourly. Window: 2024-09-01 to 2024-12-31. Capital: 100,000. Indicator: RSI, 14 periods, Wilder smoothing. Rules: flat or short and RSI below 30, allocate 100% long; long and RSI above 50, liquidate; flat or long and RSI above 70, allocate 100% short; short and RSI below 50, liquidate. No signals before the indicator is ready. Compliance: plot the RSI for audit, use the current snake_case QuantConnect API per our style guide, type-annotate initialize and on_data, enable automatic indicator warm-up, and keep position sizing at exactly 100% notional, no leverage beyond that.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested strategy. The unconditional `return` at line 37 makes every entry statement (lines 42-46) unreachable, so the algorithm can never open a position. The reachable branches (lines 33-36) only liquidate, and they fire where the request wants a 100% short (RSI>70) or a 100% long (RSI<30). The RSI>50 and RSI<50 exits are absent. The unreachable entry code is also inverted: RSI<30 goes short and RSI>70 goes long. RSI uses daily rather than hourly resolution, and the equity subscription keeps the default resolution instead of hourly. Asset, dates, capital, RSI period, plotting, annotations and warm-up are correct, but the trading logic is non-functional.

[English code view](candidates_english/equity-rsi-overbought-oversold_v09.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v09.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v09.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._rsi = self.rsi(self._qqq, 14, Resolution.DAILY)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 18
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-rsi-overbought-oversold_v10

Prompt: QuantConnect Python, current snake_case API. In initialize: set_start_date(2024, 9, 1), set_end_date(2024, 12, 31), set_cash(100000), settings.automatic_indicator_warm_up = True, equity = add_equity('QQQ', Resolution.HOUR), rsi = self.rsi(equity, 14, MovingAverageType.WILDERS, Resolution.HOUR), plot_indicator('RSI', rsi). In on_data: return unless rsi.is_ready; read equity.holdings.quantity; quantity <= 0 and rsi < 30 -> set_holdings(equity, 1); quantity > 0 and rsi > 50 -> liquidate(); quantity >= 0 and rsi > 70 -> set_holdings(equity, -1); quantity < 0 and rsi < 50 -> liquidate().

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

Assets, dates, cash, warm-up setting, hourly resolution and plotting all match the request. The trading rules, however, are materially wrong. The short-entry condition requires an existing short position (line 31), so the strategy can never open a short from flat. Longs are liquidated whenever RSI < 50 (line 33), which closes them almost immediately after entry instead of waiting for RSI > 50. Shorts never get the requested RSI < 50 exit. Positions are sized at 0.75/-0.75 instead of 1/-1. The RSI call drops the explicit MovingAverageType.WILDERS argument and passes Resolution.HOUR in the moving-average-type slot. The result is the same strategy family with several key elements wrong.

[English code view](candidates_english/equity-rsi-overbought-oversold_v10.py) | [Original evaluated source](candidates/equity-rsi-overbought-oversold_v10.py) | [Judgment](scoring/together_9b_tuned/equity-rsi-overbought-oversold_v10.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the rsi method. Please checkout the API documentation. The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 15
 No method matches given arguments for rsi: (, , ). The expected signature is:
  rsi(symbol: Symbol, period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v01

Prompt: Make me something for SPY that buys when it drops below the bottom Bollinger band and sells when it comes back to the middle. Just check once a day. Late 2024.

QC: runtime_error. Claude fidelity: 3. Judge: judged. Behavior: unavailable.

The candidate gets the core strategy right: SPY, Bollinger Bands (20, 2) on daily data, buy below the lower band, sell when price returns to the middle band, late 2024. However, the user explicitly asked to 'just check once a day', and the code does not do that. SPY is added at the default minute resolution (line 13). The trading logic sits in on_data (lines 20-30) with no scheduling or daily gating, so the rules are evaluated on every minute bar. Live intraday prices are compared against daily band values, which can trigger entries and exits intraday that a once-a-day check would not. This is an explicitly requested element that is wrong and changes trading behavior, so it counts as a key mismatch rather than a minor detail. Human review is suggested because the request is vague and the severity of this mismatch is a judgment call (3 vs 4).

[English code view](candidates_english/equity-bollinger-mean-reversion_v01.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v01.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v01.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._equity, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v02

Prompt: SPY strategy. Bollinger Bands with 20 days and 2 standard deviations on daily bars. Once a day before the open: if I'm not in and the price is below the lower band, buy with everything. If I'm in and the price is at or above the middle band, sell everything. Sept 1 to Dec 31 2024, 100k.

QC: runtime_error. Claude fidelity: 3. Judge: judged. Behavior: unavailable.

The core Bollinger mean-reversion logic is right. SPY, the 20/2 parameters, the pre-open daily schedule, the all-in entry below the lower band, the full liquidation, the dates and the cash all match. The indicator is built incorrectly, though. Line 14 passes Resolution.DAILY as the fourth positional argument of self.bb(symbol, period, k, moving_average_type, resolution). That argument is the moving-average-type slot, not the resolution. So the bands are not explicitly computed on daily bars: resolution falls back to the security's default (minute), and the MA type is set to an unintended value. This misses the explicitly requested 'daily bars' and is a key element. Separately, the exit uses `price > middle` instead of the requested 'at or above' (>=), which is a minor mismatch.

[English code view](candidates_english/equity-bollinger-mean-reversion_v02.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v02.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v02.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._spy, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v03

Prompt: SPY strategy. Bollinger Bands with 20 days and 2 standard deviations on daily bars. Once a day before the open: if I'm not in and the price is below the lower band, buy with everything. If I'm in and the price is at or above the middle band, sell everything. Sept 1 to Dec 31 2024, 100k. Also plot the upper, middle and lower bands, call the class BollingerDipBuyer, seed the starting prices so day one works, and add a comment above each rule.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is a Bollinger Band strategy on SPY with the correct 20/2 daily bands, dates, cash and all-in sizing. Several key requested elements are wrong. The exit does not sell when price is at or above the middle band; it sells when price is more than 1% above the upper band or more than 1% below the middle band, which is inverted logic. The entry adds an unrequested 1% tolerance below the lower band. Logic runs in on_data at the default minute resolution instead of once a day before the open. The class is not named BollingerDipBuyer, initial price seeding is missing, the three bands are not explicitly plotted, and there are no comments above each rule.

[English code view](candidates_english/equity-bollinger-mean-reversion_v03.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v03.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v03.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._spy, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 15
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v04

Prompt: SPY BB(20,2) dip buy, exit at midline, daily check. Q4 2024. Quick.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate uses SPY and a daily BB(20,2) check, so it is in the right strategy family. But both trading rules are wrong. Entry is `price < upper*0.95` instead of a dip below the lower band. Exit is `price > lower*1.05` instead of a return to the middle band, and the computed middle band is never used. The start date of 2024-09-01 adds September to the requested Q4 2024 window. The Resolution argument to `self.bb` is passed positionally, which may land in the moving-average-type slot. Several key elements are wrong, so the score is 2.

[English code view](candidates_english/equity-bollinger-mean-reversion_v04.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v04.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v04.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._equity, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v05

Prompt: SPY, BB(20, 2) on daily bars. Daily check pre-open: flat and price < lower band -> 100% long; invested and price >= middle band -> liquidate. 2024-09-01 to 2024-12-31, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate has the right assets, dates, cash, sizing and general Bollinger mean-reversion logic, but several key elements are wrong. (1) There is no daily pre-open scheduled check: trading logic runs in on_data on every bar of a default minute-resolution SPY subscription. (2) Resolution.DAILY is passed positionally as the 4th argument of self.bb, which in the QC Python API is moving_average_type, not resolution. The indicator therefore likely runs on minute data with a non-simple moving average type instead of BB(20,2) SMA on daily bars. (3) The exit uses > instead of the requested >=. Together these place it in the same strategy family with several key elements wrong.

[English code view](candidates_english/equity-bollinger-mean-reversion_v05.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v05.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v05.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._equity, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v06

Prompt: SPY, BB(20, 2) on daily bars. Daily check pre-open at 08:00: flat and price < lower band -> 100% long; invested and price >= middle band -> liquidate. 2024-09-01 to 2024-12-31, 100k. Auto warm-up, seed initial prices, plot all three bands, snake_case API, single class, no magic numbers (name the 20 and 2).

QC: runtime_error. Claude fidelity: 3. Judge: judged. Behavior: unavailable.

The core SPY Bollinger(20,2) mean-reversion strategy is present: an 08:00 daily check, a 100% long entry below the lower band, an exit at the middle band, the requested dates and 100k cash, auto warm-up, a single class and snake_case. However, several explicit requirements are missed. seed_initial_prices is never enabled. The 20 and 2 are not named constants. The exit uses price > middle instead of >= middle. The indicator call passes Resolution.DAILY positionally (line 14), which may land in the moving-average-type slot instead of resolution. Several explicit misses together exceed the 'one minor detail off' threshold for a 4.

[English code view](candidates_english/equity-bollinger-mean-reversion_v06.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v06.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v06.json)

QC error:

```text
[ERROR] FATAL UNHANDLED EXCEPTION:Engine.Run(): During the algorithm initialization, the following exception has occurred: 'EquityBBandsMeanReversionAlgorithm' object has no attribute 'bbands',  at initialize,    self._bbands = self.bbands(self._spy, 20, 2, Resolution.DAILY),                   ^^^^^^^^^^^, in main.py: line 14, 'EquityBBandsMeanReversionAlgorithm' object has no attribute 'bbands',Extensions.SetRuntimeError(): Extensions.SetRuntimeError(): RuntimeError at 09/01/2024 04:00:00 UTC. Context: RuntimeError System.Exception: 2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'EquityBBandsMeanReversionAlgorithm' object has no attribute 'bbands',  at initialize,    self._bbands = self.bbands(self._spy, 20, 2, Resolution.DAILY),                   ^^^^^^^^^^^, in main.py: line 14, 'EquityBBandsMeanReversionAlgorithm' object has no attribute 'bbands',ApiConnection.TryRequest(https://www.quantconnect.com/api/v2/cloud/backtest/status/update): Error: request timed out, no re
```

## equity-bollinger-mean-reversion_v07

Prompt: We need a Bollinger Band mean-reversion reference on SPY for the September to December 2024 window, daily signal evaluation, consistent with our internal implementation. Standard paper account and standard band parameters.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate trades SPY with BB(20,2) mean reversion over Sep-Dec 2024 on $100k, but it misses the explicit 'daily signal evaluation' requirement in two ways. First, SPY is added at default minute resolution and signals run in on_data on every bar, with no daily schedule. Second, Resolution.DAILY is passed as the 4th positional argument to self.bb, which is the moving_average_type slot. The bands are therefore not daily 20-period bands and may use a non-simple moving average. Entry and exit also add arbitrary 0.5% buffers and exit at the upper band, unlike the referenced internal implementation (exit at the middle band). Same strategy family, but several key elements are wrong.

[English code view](candidates_english/equity-bollinger-mean-reversion_v07.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v07.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v07.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._equity, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v08

Prompt: Implement the desk's Bollinger mean-reversion reference on SPY. Window: 2024-09-01 to 2024-12-31. Capital: 100,000. Indicator: Bollinger Bands, 20-period, 2 standard deviations, daily resolution. Evaluation: once per trading day at 08:00. Rules: not invested and price below the lower band, allocate 100% long; invested and price at or above the middle band, liquidate.

QC: runtime_error. Claude fidelity: 3. Judge: judged. Behavior: unavailable.

Asset, Bollinger parameters (20, 2, daily), date window, capital and 100% sizing all match the request. One key element is wrong: the request says to evaluate once per trading day at 08:00, but the candidate evaluates in on_data with default minute data, so it runs on every bar. The exit rule also has a minor boundary error: it liquidates on price > middle band instead of the requested price >= middle band.

[English code view](candidates_english/equity-bollinger-mean-reversion_v08.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v08.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v08.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._spy, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v09

Prompt: Implement the desk's Bollinger mean-reversion reference on SPY. Window: 2024-09-01 to 2024-12-31. Capital: 100,000. Indicator: Bollinger Bands, 20-period, 2 standard deviations, daily resolution. Evaluation: once per trading day at 08:00 via a scheduled event. Rules: not invested and price below the lower band, allocate 100% long; invested and price at or above the middle band, liquidate. Compliance: plot upper, middle and lower bands for audit, enable automatic indicator warm-up and seed initial prices, use the current snake_case API per our style guide, type-annotate methods, long-only with no leverage.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate implements a SPY Bollinger mean-reversion strategy with the correct dates, cash and 100% long sizing, but several key elements are wrong. There is no 08:00 scheduled event; logic runs in on_data on every minute bar. Resolution.DAILY is passed positionally into the moving_average_type slot of self.bb, so the indicator is likely not a daily SMA-based band. The exit uses > instead of >=. seed_initial_prices is never enabled. The upper, middle and lower bands are not plotted individually.

[English code view](candidates_english/equity-bollinger-mean-reversion_v09.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v09.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v09.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._equity, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-bollinger-mean-reversion_v10

Prompt: QuantConnect Python, snake_case. initialize: set_start_date(2024, 9, 1), set_end_date(2024, 12, 31), set_cash(100000), settings.seed_initial_prices = True, settings.automatic_indicator_warm_up = True, equity = add_equity('SPY'), bb = self.bb(equity, 20, 2, resolution=Resolution.DAILY), plot_indicator('SPY', bb.upper_band, bb.middle_band, bb.lower_band), schedule.on(date_rules.every_day(equity), time_rules.at(8, 0), self._rebalance). _rebalance: not portfolio.invested and equity.price < bb.lower_band.current.value -> set_holdings(equity, 1); portfolio.invested and equity.price >= bb.middle_band.current.value -> liquidate().

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is a Bollinger Band mean-reversion strategy on SPY, but several key requested elements are wrong or missing. (1) The requested scheduled `_rebalance` at 8:00 every trading day is replaced by `on_data`, which fires on every minute bar of the default-resolution subscription. (2) `Resolution.DAILY` is passed as the 4th positional argument to `self.bb`, which is the `moving_average_type` slot, not `resolution=`. The indicator therefore may not be daily-resolution SMA bands as requested. (3) `settings.seed_initial_prices = True` is missing. (4) `plot_indicator` receives the whole BB object rather than the three bands. (5) The exit uses `>` instead of `>=`. Assets, dates, cash and sizing match. Several key elements are wrong, so the score is 2.

[English code view](candidates_english/equity-bollinger-mean-reversion_v10.py) | [Original evaluated source](candidates/equity-bollinger-mean-reversion_v10.py) | [Judgment](scoring/together_9b_tuned/equity-bollinger-mean-reversion_v10.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the bb method. Please checkout the API documentation. The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
  at initialize
    self._bb = self.bb(self._equity, 20, 2, Resolution.DAILY)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for bb: (, , , ). The expected signature is:
  bb(symbol: Symbol, period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], float] = None)
Argument mismatch: argument 4 ('moving_average_type') expected MovingAverageType, got Resolution.
```

## equity-atr-volatility-stop_v01

Prompt: I want to basically always hold SPY but have it sell automatically if it drops too far from its recent high, then buy back in right away. Something ATR based. 2022 to 2024.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate trades SPY over 2022-2024 and builds a 14-period ATR, but the core trailing-stop logic is missing. It never tracks a recent high. The stop test compares the SPY close with ATR*1.01, which mixes a price level with a volatility amount; SPY's close will essentially always exceed its ATR, so the stop never fires. If the condition did fail, the code would go -100% short rather than sell and immediately buy back. This is the same strategy family (SPY plus ATR), but several key elements are wrong.

[English code view](candidates_english/equity-atr-volatility-stop_v01.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v01.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v01.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'Equity' object has no attribute 'set_holdings_target'
  at initialize
    self._equity.set_holdings_target(1.0)
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 13
 'Equity' object has no attribute 'set_holdings_target'
```

## equity-atr-volatility-stop_v02

Prompt: Hold SPY with all my money. Keep track of the highest close since I bought. Use a 14 period ATR. If the close drops below the highest close minus 3 times the ATR, sell everything, then buy again on the next bar and start tracking the high over. Minute data, Jan 1 2022 to Dec 31 2024, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

Asset, dates, cash and the 14-period ATR are present, so it belongs to the same strategy family. The core logic does not match the request. Highest-close tracking and the 3*ATR stop are delegated to a 'StopLossTrailingTemplate(-3.0)' (line 19) whose behaviour is not defined in the code. The entry/exit conditions on lines 35-38 are inverted: it buys only when the stop has triggered and liquidates whenever the stop has not triggered. As written, it never makes the initial full SPY buy. The 'sell then re-buy on the next bar and reset the high' cycle is not implemented. The ATR is also built on daily rather than minute bars.

[English code view](candidates_english/equity-atr-volatility-stop_v02.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v02.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v02.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the atr method. Please checkout the API documentation. The expected signature is:
  atr(symbol: Symbol, period: int, type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], IBaseDataBar] = None)
Argument mismatch: argument 3 ('type') expected MovingAverageType, got Resolution.
  at initialize
    self._equity.atr = self.atr(self._equity, 14, Resolution.DAILY)
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for atr: (, , ). The expected signature is:
  atr(symbol: Symbol, period: int, type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], IBaseDataBar] = None)
Argument mismatch: argument 3 ('type') expected MovingAverageType, got Resolution.
```

## equity-atr-volatility-stop_v03

Prompt: Hold SPY with all my money. Keep track of the highest close since I bought. Use a 14 period ATR. If the close drops below the highest close minus 3 times the ATR, sell everything, then buy again on the next bar and start tracking the high over. Minute data, Jan 1 2022 to Dec 31 2024, 100k. Also plot the stop level and the trailing high on a chart called Stop, name the class AtrTrailingStop, and don't do anything until the ATR has enough data.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate keeps SPY, ATR(14), the 3x multiplier, the dates, the cash and full allocation. Several key elements are wrong. The trailing high is a fixed 2000-day daily Maximum rather than the highest close since purchase, and it is never reset after a sale. Logic runs once a day at 09:00 through a schedule instead of on each minute bar, so re-entry happens the next day rather than on the next bar. The ATR is computed on daily bars. There is no plotting to a 'Stop' chart, and the class name is wrong. It also adds an unrequested 3% risk stop and a nonexistent update_stop_loss call. This is the same strategy family with multiple key mismatches.

[English code view](candidates_english/equity-atr-volatility-stop_v03.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v03.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v03.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'AtrTrailingStopAlgorithm' object has no attribute 'maximum' Did you mean: 'set_maximum_orders'?
  at initialize
    self._spy.high = self.maximum(self._spy, 2000, Resolution.DAILY)
                     ^^^^^^^^^^^^
 in main.py: line 22
 'AtrTrailingStopAlgorithm' object has no attribute 'maximum' Did you mean: 'set_maximum_orders'?
```

## equity-atr-volatility-stop_v04

Prompt: SPY long-only w/ chandelier stop, ATR(14) x3, immediate re-entry. 2022-2024. Fast.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate uses a Chandelier Exit and the correct 2022-2024 dates. It trades the SPY option chain instead of the SPY equity. The ATR(14)x3 stop is built incorrectly: the multiplier is taken from an unready ATR at initialization, so it is effectively 0, and the Chandelier period is 22 rather than an ATR(14)-based stop. Entry is gated on a price-vs-indicator condition rather than immediate re-entry. An extra end_time gate likely blocks trading altogether. The strategy family is the same, but several key elements are wrong.

[English code view](candidates_english/equity-atr-volatility-stop_v04.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v04.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v04.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'EquityOptionChandelierExitAlgorithm' object has no attribute 'chandelier_exit'
  at initialize
    self._option.chandelier_exit = self.chandelier_exit(self._option, 22, 3*self._option.atr(14).current.value)
                                   ^^^^^^^^^^^^^^^^^^^^
 in main.py: line 15
 'EquityOptionChandelierExitAlgorithm' object has no attribute 'chandelier_exit'
```

## equity-atr-volatility-stop_v05

Prompt: SPY minute, long 100%. Trailing high = max close since entry. Stop = high - 3*ATR(14). Close < stop -> liquidate, re-enter 100% next bar, reset high. 2022-01-01 to 2024-12-31, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate trades SPY long at 100% on minute data over the correct dates and cash, but the core chandelier stop is not implemented. There is no ATR(14) and no 3*ATR multiplier. Instead it uses a trailing_stop helper with argument 3 on daily resolution. It never tracks the maximum close since entry. The exit compares price to average_purchase_price minus stop_offset, not trailing high minus 3*ATR. Re-entry on the next bar happens implicitly, but there is no trailing-high reset because no trailing high exists. This is the same strategy family (trailing stop, always-long SPY) with several key elements wrong.

[English code view](candidates_english/equity-atr-volatility-stop_v05.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v05.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v05.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'EquityTrailingStopTemplateAlgorithm' object has no attribute 'trailing_stop' Did you mean: 'trailing_stop_order', 'train'?
  at initialize
    self._equity.trailing_stop = self.trailing_stop(self._equity, 3, Resolution.DAILY)
                                 ^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 'EquityTrailingStopTemplateAlgorithm' object has no attribute 'trailing_stop' Did you mean: 'trailing_stop_order', 'train'?
```

## equity-atr-volatility-stop_v06

Prompt: SPY minute, long 100%. Trailing high = max close since entry. Stop = high - 3*ATR(14). Close < stop -> liquidate, re-enter 100% next bar, reset high. 2022-01-01 to 2024-12-31, 100k. Auto warm-up, gate on atr.is_ready, plot stop + trailing high, snake_case, one class, keep state in two attributes max.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested strategy. Its only order is a liquidate call, and it never enters a position, so no trade can ever happen. The exit is unreachable: it requires holdings.quantity > 0 and not portfolio.invested at the same time. It uses a TrailingStop helper with period 3 on daily resolution instead of an explicit ATR(14) with a 3x multiplier. There is no trailing-high tracking, no re-entry, no high reset and no plot of the trailing high. Only the shell matches: SPY minute, dates, cash, warm-up flag and one class.

[English code view](candidates_english/equity-atr-volatility-stop_v06.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v06.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v06.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'EquityTrailingStopTemplateAlgorithm' object has no attribute 'trailing_stop' Did you mean: 'trailing_stop_order', 'train'?
  at initialize
    self._equity.trailing_stop = self.trailing_stop(self._equity, 3, Resolution.DAILY)
                                 ^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 'EquityTrailingStopTemplateAlgorithm' object has no attribute 'trailing_stop' Did you mean: 'trailing_stop_order', 'train'?
```

## equity-atr-volatility-stop_v07

Prompt: We need a long-only SPY position with an ATR-based chandelier exit and automatic re-entry for 2022 through 2024, consistent with our internal implementation. Standard paper account. Use the desk's usual ATR multiple.

QC: runtime_error. Claude fidelity: 4. Judge: judged. Behavior: unavailable.

The request is vague. It refers to an unknown 'internal implementation' and an unknown 'desk's usual ATR multiple'. The candidate is a sensible version of what can be specified: long-only SPY, a 22-period daily ATR with a 3x multiple, an exit when the trailing ATR stop is broken, automatic re-entry when price closes back above the stop, and dates from 2022-01-01 to 2024-12-31. One detail departs from a classic chandelier exit. The stop is a ratchet of max(close - 3*ATR) using the current ATR each time. A textbook chandelier uses the highest high over the lookback minus k*ATR. The stop is also evaluated on minute bars from the default equity resolution against a daily ATR. Neither point changes the core idea. Human review is needed because the internal implementation and the desk's ATR multiple cannot be verified.

[English code view](candidates_english/equity-atr-volatility-stop_v07.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v07.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v07.json)

QC error:

```text
2022-01-01 00:00:00 Runtime Error: name 'Bars' is not defined
  at on_warmup_finished
    bar = self.history[Bars](self._equity, 1, Resolution.DAILY).bars[-1]
                       ^^^^
 in main.py: line 45

```

## equity-atr-volatility-stop_v08

Prompt: Implement the desk's ATR chandelier stop reference on SPY. Resolution: minute. Window: 2022-01-01 to 2024-12-31. Capital: 100,000. Indicator: ATR, 14 periods. Rules: when flat, allocate 100% long and set the trailing high to the entry close; update the trailing high with each higher close; stop level is trailing high minus 3 times ATR; if a close falls below the stop, liquidate, then re-enter 100% on the next bar and reset the trailing high.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is in the right family: SPY, a chandelier-style 3x ATR stop, minute data, and the correct dates and capital. However, several key elements are wrong. It uses the built-in ChandelierExit indicator with period 20 on daily resolution instead of ATR(14). It never tracks a trailing high from the entry close. Its entry and exit conditions are inverted relative to the request: it buys only when the stop is above price and sells when the stop is below price. It does not implement unconditional entry when flat, or re-entry on the next bar with a trailing-high reset.

[English code view](candidates_english/equity-atr-volatility-stop_v08.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v08.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v08.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'EquityChandelierExitAlgorithm' object has no attribute 'chandelier_exit'
  at initialize
    self._equity.chandelier_exit = self.chandelier_exit(self._equity, 20, 3, Resolution.DAILY)
                                   ^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 'EquityChandelierExitAlgorithm' object has no attribute 'chandelier_exit'
```

## equity-atr-volatility-stop_v09

Prompt: Implement the desk's ATR chandelier stop reference on SPY. Resolution: minute. Window: 2022-01-01 to 2024-12-31. Capital: 100,000. Indicator: ATR, 14 periods, automatic warm-up. Rules: when flat, allocate 100% long and set the trailing high to the entry close; update the trailing high with each higher close; stop level is trailing high minus 3 times ATR; if a close falls below the stop, liquidate, then re-enter 100% on the next bar and reset the trailing high. Compliance: plot the stop level and trailing high for audit, no signals before the ATR is ready, snake_case API per our style guide, type annotations, no leverage, no short positions.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested strategy. It never opens a position, because there is no set_holdings call anywhere. The exit check runs only once, from on_warmup_finished. There is no re-entry on the next bar and no trailing-high tracking based on closes since entry. It replaces the requested stop (trailing high minus 3×ATR) with a misconstructed ChandelierExit: period 22, ATR object passed as the second argument, and the indicator updated manually with ATR values. The trailing high is not plotted. Only the asset, date range, cash and ATR(14) period match.

[English code view](candidates_english/equity-atr-volatility-stop_v09.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v09.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v09.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the atr method. Please checkout the API documentation. The expected signature is:
  atr(symbol: Symbol, period: int, type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], IBaseDataBar] = None)
Argument mismatch: argument 3 ('type') expected MovingAverageType, got Resolution.
  at initialize
    self._equity.atr = self.atr(self._equity, 14, Resolution.DAILY)
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 No method matches given arguments for atr: (, , ). The expected signature is:
  atr(symbol: Symbol, period: int, type: MovingAverageType = MovingAverageType.SIMPLE, resolution: Optional[Resolution] = None, selector: Callable[[IBaseData], IBaseDataBar] = None)
Argument mismatch: argument 3 ('type') expected MovingAverageType, got Resolution.
```

## equity-atr-volatility-stop_v10

Prompt: QuantConnect Python, snake_case. initialize: set_start_date(2022, 1, 1), set_end_date(2024, 12, 31), set_cash(100000), settings.automatic_indicator_warm_up = True, spy = add_equity('SPY', Resolution.MINUTE), atr = self.atr(spy.symbol, 14), self._trailing_high = 0.0, self._waiting_to_reenter = False. on_data: return unless atr.is_ready and a bar exists; if _waiting_to_reenter: set_holdings(spy, 1.0), _trailing_high = close, clear flag, return; if not portfolio.invested: set_holdings(spy, 1.0), _trailing_high = close, return; _trailing_high = max(_trailing_high, close); stop = _trailing_high - 3.0 * atr.current.value; plot both; if close < stop: liquidate(spy), _waiting_to_reenter = True, _trailing_high = 0.0.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: partial.

The candidate is in the same ATR trailing-stop family, but several key elements are wrong. The ATR uses SIMPLE smoothing at DAILY resolution instead of the default self.atr(spy.symbol, 14). The exit tests stop_price < previous_close instead of close < stop. There is no _waiting_to_reenter flag or immediate re-entry. Stop and trailing high are not plotted. Because of the exit logic, the liquidate branch fires on essentially every bar, so the strategy would almost never enter a position.

[English code view](candidates_english/equity-atr-volatility-stop_v10.py) | [Original evaluated source](candidates/equity-atr-volatility-stop_v10.py) | [Judgment](scoring/together_9b_tuned/equity-atr-volatility-stop_v10.json)

## equity-monthly-roc-rotation_v01

Prompt: Make a bot that once a month moves my money into whichever of SPY, EFA, EEM, AGG and GLD have been doing best lately. Hold a few of them. If everything is down just sit in cash. 2022 to 2024.

QC: syntax_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement momentum rotation. The rebalance exits immediately when the portfolio is not invested (line 28), and the portfolio starts in cash, so it never trades. If it did run past that guard, it would set static 20% weights in all five ETFs (lines 8, 20, 44) and ignore the computed ranking. The ranking itself uses a non-standard 'self.return(symbol, self.time_rules.month)' call (line 36), and its results (lines 38-42) only feed a meaningless drift check. There is no logic to move to cash when everything is down. It is effectively an equal-weight 'permanent portfolio', not the requested strategy. Only the assets and dates match.

[English code view](candidates_english/equity-monthly-roc-rotation_v01.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v01.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v01.json)

QC error:

```text
invalid syntax (main.py, line 36)
```

## equity-monthly-roc-rotation_v02

Prompt: Trade SPY, EFA, EEM, AGG and GLD. For each one use the 60 day rate of change on daily bars. On the first trading day of each month, put a third of my money into each of the top 3 by rate of change and sell the others. If all five are negative, sell everything and hold cash. Jan 1 2022 to Dec 31 2024, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The scaffolding matches the request: the five ETFs, 60-day daily ROC, monthly first-trading-day schedule, 2022-2024 dates and $100k cash. The core rotation logic does not implement it. Lines 42-44 compute a third-ranked symbol and assign it to `security.weight`. No positive target weight is ever set for a top-3 set. The 'all five negative' rule is replaced by a per-asset negativity filter and an any-target-weight check. Sizing uses 1/5 rather than 1/3, divided by a sum of zero/unset target weights, and passes the whole securities collection to `set_holdings`. The result is the same strategy family with several key elements wrong.

[English code view](candidates_english/equity-monthly-roc-rotation_v02.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v02.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v02.json)

QC error:

```text
2022-01-03 09:31:00 Runtime Error: name 'RowColumnLabel' is not defined
  at _rebalance
    self.plot(RowColumnLabel(security.symbol.value, "ROC"), roi)
              ^^^^^^^^^^^^^^
 in main.py: line 45

```

## equity-monthly-roc-rotation_v03

Prompt: Trade SPY, EFA, EEM, AGG and GLD. For each one use the 60 day rate of change on daily bars. On the first trading day of each month, a minute after the open, put a third of my money into each of the top 3 by rate of change and sell the others. If all five are negative, sell everything and hold cash. Jan 1 2022 to Dec 31 2024, 100k. Also call the class MonthlyRotation, add a comment explaining the cash rule, and make the 60 and the 3 named variables so I can tweak them.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: partial.

The candidate keeps the right assets, the 60-day daily ROC, the monthly schedule one minute after the open, the dates and the 100k cash. It also buys the top 3 at 1/3 each. However, it shorts the bottom 2 at -50% each (lines 42, 45) when the request said to sell them to zero. It has no all-negative-go-to-cash rule and no comment explaining one. It hardcodes 60 and 3 instead of making them named variables (lines 18, 41). The class is named MonthlyRotationAlgorithm, not the requested MonthlyRotation (line 6). These are several key mismatches, and the shorting turns the strategy into a long/short variant of the same family.

[English code view](candidates_english/equity-monthly-roc-rotation_v03.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v03.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v03.json)

## equity-monthly-roc-rotation_v04

Prompt: Monthly top-3 ROC rotation: SPY/EFA/EEM/AGG/GLD. Cash if all neg. 2022-2024. Quick.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement a top-3 ROC rotation. It builds fixed 20% targets for all five ETFs (lines 8, 25) and sets them on drift (lines 33-37). ROC values are never used to rank or select assets. 'security.roc.rank' (line 35) is not a valid way to choose among assets. There is no top-3 selection and no move to cash when all ROC values are negative. What remains is a static equal-weight portfolio with drift rebalancing. The tickers, a ROC indicator, the monthly schedule and the 2022-2024 dates are present, but the requested strategy logic is missing.

[English code view](candidates_english/equity-monthly-roc-rotation_v04.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v04.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v04.json)

QC error:

```text
2022-01-03 15:59:00 Runtime Error: float division by zero
  at _rebalance
    current_weight = security.holdings.quantity / self.portfolio.total_holdings_value
                     ~~~~~~~~~~~~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 in main.py: line 34

```

## equity-monthly-roc-rotation_v05

Prompt: SPY EFA EEM AGG GLD, ROC(60) daily. Month start +1m: top 3 by ROC at 1/3 each, liquidate rest; all ROC < 0 -> cash. 2022-01-01 to 2024-12-31, 100k.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: partial.

The candidate uses the requested assets, ROC(60) daily indicator, dates and cash, but it does not implement the core rotation. It never ranks assets or selects the top 3. Instead it holds every asset with non-negative ROC at 1/5 weight each, which is an absolute-momentum filter rather than top-3 relative momentum at 1/3 each. The rebalance also runs on the 3rd trading day of the month instead of month start. These are several key mismatches within the same strategy family.

[English code view](candidates_english/equity-monthly-roc-rotation_v05.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v05.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v05.json)

## equity-monthly-roc-rotation_v06

Prompt: SPY EFA EEM AGG GLD at minute res, ROC(60) on daily bars. Month start +1m after open: top 3 by ROC at 1/3 each via PortfolioTarget, liquidate rest; all ROC < 0 -> liquidate all. 2022-01-01 to 2024-12-31, 100k. Auto warm-up, snake_case, attach roc to each security object, no history() calls.

QC: completed. Claude fidelity: 3. Judge: judged. Behavior: partial.

The core rotation is implemented correctly: ROC(60) on daily bars is attached to each security, the top 3 are held at 1/3 each via PortfolioTarget, and set_holdings is called with liquidate_existing_holdings=True. Two problems remain. The explicit rule 'all ROC < 0 -> liquidate all' is missing, so the algorithm stays 100% invested in the top 3 even when all momentum is negative. This is a key element. Also, month_start("SPY", 1) adds a one-trading-day offset, so rebalancing happens on the second trading day of the month instead of at month start.

[English code view](candidates_english/equity-monthly-roc-rotation_v06.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v06.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v06.json)

## equity-monthly-roc-rotation_v07

Prompt: We need a monthly cross-asset momentum rotation across US equity, developed ex-US, emerging markets, aggregate bonds and gold (SPY, EFA, EEM, AGG, GLD) for 2022 through 2024, consistent with our internal implementation, with a cash fallback in broad drawdowns. Standard paper account.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate trades the five requested ETFs over the requested 2022–2024 window, but it does not implement a momentum rotation. It ranks the ETFs by the absolute level of a 63-day EMA of price (line 32). That compares share prices across ETFs, so it effectively always picks the highest-priced ETF (SPY), not the strongest performer. There is no monthly rebalance; the logic runs on every on_data call (lines 27-36). There is no cash fallback in broad drawdowns. The entry condition (line 34) needs an existing long in the previous top, so it can never open a first position. The previous holding is never explicitly exited. Only the assets and date range match.

[English code view](candidates_english/equity-monthly-roc-rotation_v07.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v07.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v07.json)

QC error:

```text
2022-01-03 09:31:00 Runtime Error: 'EFAEMAQLongOnlyAlgorithm' object has no attribute '_equities'
  at on_data
    if not all([equity.indicator.is_ready for equity in self._equities.values()]):
                                                        ^^^^^^^^^^^^^^
 in main.py: line 29

```

## equity-monthly-roc-rotation_v08

Prompt: Implement the desk's monthly ROC rotation reference. Assets: SPY, EFA, EEM, AGG, GLD. Window: 2022-01-01 to 2024-12-31. Capital: 100,000. Signal: 60-period rate of change on daily bars per asset. Schedule: first trading day of each month, one minute after the open. Rules: rank by ROC, hold the top 3 at one third each, liquidate the rest; if all five ROC values are negative, liquidate everything and hold cash.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: partial.

The core monthly top-3 ROC rotation is present: correct assets, 60-period daily ROC, correct schedule, correct dates, and non-top holdings are liquidated. Two key requested rules are wrong or missing. First, positions are sized at 1/len(tickers) = 0.20 instead of one third each, so 40% sits in cash (line 15 used in line 44). Second, the rule to liquidate everything and hold cash when all five ROC values are negative is absent (lines 32-45 have no negativity check). With several key elements wrong, the rubric gives a 2.

[English code view](candidates_english/equity-monthly-roc-rotation_v08.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v08.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v08.json)

## equity-monthly-roc-rotation_v09

Prompt: Implement the desk's monthly ROC rotation reference. Assets: SPY, EFA, EEM, AGG, GLD at minute resolution. Window: 2022-01-01 to 2024-12-31. Capital: 100,000. Signal: 60-period rate of change on daily bars per asset, automatic warm-up. Schedule: first trading day of each month, one minute after the open, via a scheduled event. Rules: rank by ROC, hold the top 3 at one third each using portfolio targets with liquidate_existing_holdings, liquidate the rest; if all five ROC values are negative, liquidate everything and hold cash. Compliance: equal weights only, no leverage, long-only, snake_case API per style guide, type annotations.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: partial.

The asset universe, daily 60-period ROC with automatic warm-up, date range, capital and monthly schedule are correct. However, two key elements are wrong. First, each position gets 1/len(tickers) = 0.2 instead of one third, so only 60% of capital is invested. Second, the rule to liquidate everything and hold cash when all five ROC values are negative is missing entirely. Several key elements are wrong, so this is the same strategy family only.

[English code view](candidates_english/equity-monthly-roc-rotation_v09.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v09.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v09.json)

## equity-monthly-roc-rotation_v10

Prompt: QuantConnect Python, snake_case. initialize: set_start_date(2022, 1, 1), set_end_date(2024, 12, 31), set_cash(100000), settings.automatic_indicator_warm_up = True; for ticker in SPY, EFA, EEM, AGG, GLD: equity = add_equity(ticker, Resolution.MINUTE), equity.roc = self.roc(equity, 60, Resolution.DAILY); schedule.on(date_rules.month_start('SPY'), time_rules.after_market_open('SPY', 1), self._rebalance). _rebalance: securities = the five; if all(s.roc.current.value < 0): liquidate(); return; top = sorted(securities, key=lambda s: s.roc.current.value, reverse=True)[:3]; set_holdings([PortfolioTarget(s.symbol, 1/3) for s in top], liquidate_existing_holdings=True).

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The initialize setup matches the request: dates, cash, automatic warm-up, the five tickers at minute resolution, ROC(60) on daily bars, and the month-start schedule. However, _rebalance never reads the ROC indicators. It has no all-negative liquidation, no top-3 momentum selection, and no rotation. Instead it targets all five assets at 1/3 each (about 167% gross exposure) and rebalances only on weight drift. That is a static equal-weight/permanent-portfolio rebalancer, not the requested momentum rotation strategy.

[English code view](candidates_english/equity-monthly-roc-rotation_v10.py) | [Original evaluated source](candidates/equity-monthly-roc-rotation_v10.py) | [Judgment](scoring/together_9b_tuned/equity-monthly-roc-rotation_v10.json)

QC error:

```text
2022-01-03 09:31:00 Runtime Error: float division by zero
  at _rebalance
    current_weight = self.portfolio[target.symbol].holdings_value / self.portfolio.total_holdings_value
                     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 in main.py: line 33

```

## equity-sixty-forty-portfolio_v01

Prompt: Set me up a classic 60/40 with SPY and TLT that rebalances every few months, but only if it's drifted a decent amount. 2022 to 2024.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: available.

The assets (SPY, TLT) and the 2022-2024 date range are correct, and the code has the general shape of a drift-gated scheduled rebalance. However, it does not build a 60/40 portfolio. Both assets get a 0.6 target (120% gross), which is wrong on the core feature of the request. It also rebalances monthly rather than 'every few months'. The drift check compares each asset's share of holdings against 0.6, so it fires almost every month and the 'only if drifted' gate is largely ineffective. With several key elements wrong, this is the same strategy family but not the requested strategy.

[English code view](candidates_english/equity-sixty-forty-portfolio_v01.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v01.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v01.json)

## equity-sixty-forty-portfolio_v02

Prompt: 60% SPY, 40% TLT. Buy on the first bar. At the start of every quarter check the weights and if either is more than 5 percentage points off, rebalance back to 60/40, otherwise leave it. Minute data, Jan 1 2022 to Dec 31 2024, 100k.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: available.

The candidate trades the right assets and uses the right dates, cash, resolution, initial-buy mechanism and 5-point threshold. Several key elements are wrong, though. Both SPY and TLT are targeted at 60%, giving 120% gross exposure instead of 60/40. The check runs once a year, not every quarter. The drift check compares both assets against 0.6 using total holdings value as the denominator, so each weight sits near 0.5 and the check effectively always fires. It is the same strategy family, but the allocation, schedule and drift logic are all incorrect.

[English code view](candidates_english/equity-sixty-forty-portfolio_v02.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v02.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v02.json)

## equity-sixty-forty-portfolio_v03

Prompt: 60% SPY, 40% TLT. Buy on the first bar. At the start of every quarter, a minute after the open, check the weights and if either is more than 5 percentage points off, rebalance back to 60/40, otherwise leave it. Minute data, Jan 1 2022 to Dec 31 2024, 100k. Call the class SixtyForty, make the 5% a named constant, and log a line whenever a rebalance is skipped.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: available.

The candidate keeps the general idea of a static SPY/TLT allocation with a 5% drift band, minute data, and the correct dates and cash. Several key requested elements are wrong: (1) both assets get a 0.6 weight (lines 7, 18), giving 60/60 and 120% gross exposure instead of 60/40; (2) the rebalance check runs yearly with a 2-day offset (line 21) instead of at each quarter start; (3) no log line is written when a rebalance is skipped (lines 29-34); (4) the class is named PermanentPortfolioAlgorithm, not SixtyForty (line 5). Drift is also measured against total_holdings_value, which excludes cash, rather than total portfolio value.

[English code view](candidates_english/equity-sixty-forty-portfolio_v03.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v03.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v03.json)

## equity-sixty-forty-portfolio_v04

Prompt: 60/40 SPY/TLT, quarterly rebal, 5% drift band. 2022-2024.

QC: runtime_error. Claude fidelity: 3. Judge: judged. Behavior: unavailable.

The candidate gets the 60/40 SPY/TLT weights, the 5% absolute drift check and the 2022-2024 dates right. The rebalance cadence is wrong: line 23 uses date_rules.year_start('SPY', 2), which schedules an annual check, not the requested quarterly one. That makes one key element wrong while the core idea is intact. Smaller issues: SPY and TLT are never subscribed with add_equity, and drift is measured against total_holdings_value instead of total portfolio value.

[English code view](candidates_english/equity-sixty-forty-portfolio_v04.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v04.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v04.json)

QC error:

```text
2022-01-01 00:00:00 Runtime Error: The ticker SPY was not found in the SymbolCache. Use the Symbol object as key instead. Accessing the securities collection/slice object by string ticker is only available for securities added with the add_security-family methods. For more details, please check out the documentation.
  at on_warmup_finished
    self.set_holdings(self._targets, liquidate_existing_holdings=True)
 in main.py: line 29

```

## equity-sixty-forty-portfolio_v05

Prompt: SPY 0.6 / TLT 0.4, minute. Allocate bar 1. Quarter start +1m: rebalance only if any |weight - target| > 0.05. 2022-01-01 to 2024-12-31, 100k.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: available.

The strategy family is right: a static SPY/TLT minute-resolution portfolio with an initial allocation and a drift-gated scheduled rebalance. Several key elements are wrong, though. TLT is targeted at 0.6 instead of 0.4, so the targets total 120%. The schedule is year-start plus 2 days instead of quarter start. The drift check compares both assets to 0.6 and divides by total_holdings_value instead of total portfolio value. As a result the 5% drift gate does not implement the requested condition and would effectively always trigger.

[English code view](candidates_english/equity-sixty-forty-portfolio_v05.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v05.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v05.json)

## equity-sixty-forty-portfolio_v06

Prompt: SPY 0.6 / TLT 0.4, minute. Allocate bar 1. Quarter start +1m after open via schedule: compute weights from holdings_value / total_portfolio_value, rebalance with PortfolioTargets only if any |weight - target| > 0.05. 2022-01-01 to 2024-12-31, 100k. _drift_threshold as class attr, snake_case, no magic numbers.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The scaffold matches the request: SPY/TLT at minute resolution, 2022-01-01 to 2024-12-31, $100k, quarter-start +1 minute schedule, holdings_value / total_portfolio_value drift check, and a _drift_threshold = 0.05 class attribute. The core strategy is wrong, though. Instead of fixed 0.6/0.4 targets, it derives targets from an invented covariance/correlation/duration model with a 0.5 fallback. Rebalancing calls set_holdings with a bare symbol list rather than PortfolioTargets carrying the 0.6/0.4 weights. Several key elements are wrong, so this is the same strategy family only.

[English code view](candidates_english/equity-sixty-forty-portfolio_v06.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v06.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v06.json)

QC error:

```text
2022-01-03 09:31:00 Runtime Error: 'SecurityPortfolioManager' object has no attribute 'holdings_value' Did you mean: 'total_holdings_value'?
  at _rebalance
    holdings_value = self.portfolio.holdings_value(security)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 30

```

## equity-sixty-forty-portfolio_v07

Prompt: We need a 60/40 SPY/TLT benchmark portfolio for 2022 through 2024 with quarterly rebalancing and a drift tolerance so small deviations do not generate trades, consistent with our internal implementation. Standard paper account.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate trades the right assets (SPY and TLT) over the right dates (2022-2024) as a static-allocation rebalancer. However, several key elements are wrong. Weights are 1/len(dict), meant to be equal weight but actually dividing by zero on an empty dict, instead of 60/40. Rebalancing is scheduled yearly (year_start) rather than quarterly. There is no drift tolerance at all, so every rebalance trades. These are multiple key mismatches in the same strategy family. The request ties the drift tolerance to an unspecified 'internal implementation', so the exact threshold cannot be verified.

[English code view](candidates_english/equity-sixty-forty-portfolio_v07.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v07.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v07.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: division by zero
  at initialize
    equity.weight = 1 / len(self._weight_by_symbol)
                    ~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 in main.py: line 16
 division by zero
```

## equity-sixty-forty-portfolio_v08

Prompt: Implement the desk's 60/40 reference. Assets: SPY at 60%, TLT at 40%. Resolution: minute. Window: 2022-01-01 to 2024-12-31. Capital: 100,000. Initial allocation on the first bar. Rebalance: first trading day of each quarter, one minute after the open; skip if every weight is within 5 percentage points of target, otherwise reset to target weights.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: available.

Assets, minute resolution, dates, capital, initial allocation and quarterly schedule are correct. The defining parameter is wrong: a single `_weight = 0.6` is applied to both SPY and TLT (lines 7, 17), so the code builds a 60/60 levered portfolio at 120% gross instead of 60/40. The drift check is also broken. It compares TLT against 0.6 instead of 0.4, and it divides by `total_holdings_value` rather than total portfolio value (line 29). With equal 60/60 targets, each holding is about 50% of holdings value, roughly 10 points from 0.6, so the 5-point skip condition will in practice never apply and the strategy rebalances every quarter. With two key elements wrong (target weights and the threshold rebalance rule), this is the same strategy family but not the requested 60/40 reference.

[English code view](candidates_english/equity-sixty-forty-portfolio_v08.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v08.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v08.json)

## equity-sixty-forty-portfolio_v09

Prompt: Implement the desk's 60/40 reference. Assets: SPY at 60%, TLT at 40%. Resolution: minute. Window: 2022-01-01 to 2024-12-31. Capital: 100,000. Initial allocation on the first bar. Rebalance: first trading day of each quarter, one minute after the open, via a scheduled event; compute each weight as holdings value over total portfolio value; skip if every weight is within 5 percentage points of target, otherwise reset to target weights with portfolio targets. Compliance: drift threshold as a named class attribute for audit, no leverage, long-only, snake_case API per style guide, type annotations.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: available.

The candidate is a static SPY/TLT rebalancing strategy, so it belongs to the right family, but several key elements are wrong. TLT gets 0.6 instead of 0.4, so the targets sum to 120% and use leverage. Rebalancing runs yearly with a 2-day offset instead of on the first trading day of each quarter. Current weights are divided by total holdings value instead of total portfolio value. Drift is checked against 0.6 for both assets.

[English code view](candidates_english/equity-sixty-forty-portfolio_v09.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v09.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v09.json)

## equity-sixty-forty-portfolio_v10

Prompt: QuantConnect Python, snake_case. Class attribute _drift_threshold = 0.05. initialize: set_start_date(2022, 1, 1), set_end_date(2024, 12, 31), set_cash(100000), spy = add_equity('SPY', Resolution.MINUTE).symbol, tlt = add_equity('TLT', Resolution.MINUTE).symbol, targets {spy: 0.6, tlt: 0.4}, schedule.on(date_rules.quarter_start('SPY'), time_rules.after_market_open('SPY', 1), self._rebalance). on_data: if not portfolio.invested, set_holdings to targets once. _rebalance: weights = portfolio[s].holdings_value / portfolio.total_portfolio_value; if all abs(weight - target) <= 0.05 return; set_holdings([PortfolioTarget(spy, 0.6), PortfolioTarget(tlt, 0.4)]).

QC: completed. Claude fidelity: 4. Judge: judged. Behavior: available.

Assets, dates, cash, resolution, schedule, targets and drift logic all match the request. The one deviation is the initial allocation. The request asked for an on_data handler that calls set_holdings once when not portfolio.invested. The candidate instead allocates in on_warmup_finished (line 27-28) and defines no on_data. That mirrors the template, not the prompt. The effect is similar (a single initial allocation), but the trigger and the invested guard differ. liquidate_existing_holdings=True is an extra flag that does nothing here, since only SPY and TLT are held.

[English code view](candidates_english/equity-sixty-forty-portfolio_v10.py) | [Original evaluated source](candidates/equity-sixty-forty-portfolio_v10.py) | [Judgment](scoring/together_9b_tuned/equity-sixty-forty-portfolio_v10.json)

## equity-momentum-cross-sectional-decile_v01

Prompt: I want a bot that buys the S&P 500 stocks with the best momentum over the past year and swaps them out every month. Maybe the top 10 or so, equal amounts. 2022 to 2024.

QC: syntax_error. Claude fidelity: 3. Judge: judged. Behavior: unavailable.

The candidate gets most of the request right: SPY constituents, monthly rotation, top 10, equal weight and 2022-2024. The key element, ranking by momentum over the past year, is not implemented correctly. On line 26, pct_change(12) is applied to daily bars, so it measures a 12-trading-day return rather than roughly 252 days. The line also ranks rows of the whole return DataFrame instead of each symbol's latest one-year return. The 365-day history request covers the lookback window, but the momentum calculation does not use it. Because the core idea is right but the defining momentum signal is wrong, the score is 3.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v01.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v01.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v01.json)

QC error:

```text
invalid syntax (main.py, line 26)
```

## equity-momentum-cross-sectional-decile_v02

Prompt: Use the stocks in the SPY ETF as my universe. Keep the 100 with the highest dollar volume. For each one measure the percent price change over the last 252 trading days using daily adjusted prices. At the start of each month hold the top 10% by that number in equal weights and sell anything no longer selected. Jan 1 2022 to Dec 31 2024, 250k.

QC: runtime_error. Claude fidelity: 3. Judge: judged. Behavior: unavailable.

The candidate gets the SPY-constituent universe, the 2022–2024 dates, $250k cash, monthly scheduling, equal weighting and liquidation of dropped names right. One key element is wrong: instead of keeping the 100 names with the highest dollar volume, it keeps every name above a fixed $100M dollar-volume threshold (line 22). Because of that, the hard-coded top 10 (line 30) is not 10% of a 100-name pool. The momentum measure depends on an unverified `self.total_return(s, 252)` call, so whether it matches 252-day percent price change on adjusted prices is uncertain.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v02.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v02.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v02.json)

QC error:

```text
2022-01-01 00:00:00 Runtime Error: 'ETFConstituentUniverse' object has no attribute 'dollar_volume'
  at 
    filtered = [c.symbol for c in constituents if c.dollar_volume > 100000000]
                                                  ^^^^^^^^^^^^^^^
 in main.py: line 22
  at _select_assets
    filtered = [c.symbol for c in constituents if c.dollar_volume > 100000000]
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 22

```

## equity-momentum-cross-sectional-decile_v03

Prompt: Use the stocks in the SPY ETF as my universe. Keep the 100 with the highest dollar volume. For each one measure the percent price change over the last 252 trading days using daily adjusted prices. At the start of each month at 9:31 hold the top 10% by that number in equal weights and sell anything no longer selected. Jan 1 2022 to Dec 31 2024, 250k. Call the class Sp500Momentum, make the 252, 100 and 10% named variables, and add a comment explaining why we warm up for 253 days.

QC: completed. Claude fidelity: 2. Judge: judged. Behavior: available.

The candidate keeps the general shape of the strategy: a SPY-constituent universe, a monthly 9:31 rebalance, equal weights, liquidating stale holdings, the correct dates and $250k. Several key elements are wrong or missing. (1) There is no top-100 dollar-volume selection; the filter replicates each symbol 100 times. (2) Momentum uses a non-existent `self.portfolio.momentum` call rather than a 252-day percent-change indicator on daily adjusted prices. (3) It applies an absolute >0.10 threshold instead of ranking and taking the top 10%. (4) There is no 253-day warm-up and no explanatory comment. (5) 252 and 100 are not named variables. (6) The class name is wrong.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v03.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v03.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v03.json)

## equity-momentum-cross-sectional-decile_v04

Prompt: SPY constituents, top 100 by $vol, 12m momentum, top decile EW, monthly. 2022-2024, 250k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate gets the scaffolding right: SPY constituents, monthly cadence, 2022-2024 dates, $250k cash and equal-weight full rebalancing. The core strategy logic is wrong or missing. No 12-month momentum is computed: history covers only 12 days (line 22), and the second sort key is bar duration (end_time - start_time, line 29), not a return. There is no top-decile step, so all 100 names are held instead of about 10. The ranking direction is not descending, so 'top 100 by dollar volume' is not reliably enforced. The result is equal-weight monthly holding of SPY constituents, not a momentum strategy.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v04.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v04.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v04.json)

QC error:

```text
2022-01-01 00:00:00 Runtime Error: 'DataFrame' object has no attribute 'sort'
  at __getattr__
    return object.__getattribute__(self, name)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in generic.py: line 6321
  at _select_assets
    return list(history.sort(
                ^^^^^^^^^^^^
 in main.py: line 26

```

## equity-momentum-cross-sectional-decile_v05

Prompt: Universe = SPY ETF constituents capped to top 100 by dollar_volume. MomentumPercent(252) per name from adjusted price. Monthly at 09:31: top decile equal weight, liquidate rest. 2022-01-01 to 2024-12-31, 250k. Warm up 253 daily.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

Several key elements are wrong, though the code stays in the same strategy family: a monthly, equal-weight momentum strategy on SPY constituents. Dates, cash, the 09:31 monthly schedule and liquidation of unselected names are correct. However: (1) no MomentumPercent(252) indicator is used; (2) the 252-calendar-day history window cannot support pct_change(252), so momentum is effectively all NaN; (3) the universe is not capped to the top 100 by dollar volume before ranking; a blended score of momentum rank times dollar volume is used instead; (4) it holds 100 names rather than the top decile, about 10 of a 100-name cap; (5) the requested 253-day daily warm-up is missing.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v05.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v05.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v05.json)

QC error:

```text
2022-01-01 00:00:00 Runtime Error: 'DataFrame' object has no attribute 'dollar_volume'
  at __getattr__
    return object.__getattribute__(self, name)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in generic.py: line 6321
  at _select_assets
    .multiply(history.dollar_volume, axis=0).rank(pct=True)
              ^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 27

```

## equity-momentum-cross-sectional-decile_v06

Prompt: Universe = SPY ETF constituents capped to top 100 by dollar_volume, minute universe res. MomentumPercent(252) per name updated from fundamental adjusted_price. Return unchanged universe while warming up. Monthly at 09:31: top decile (min 1) equal weight via PortfolioTargets, liquidate_existing_holdings. 2022-01-01 to 2024-12-31, 250k. set_warm_up(253, daily), seed initial prices, min order margin pct = 0, snake_case.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested momentum strategy. It has no MomentumPercent indicator and no fundamental adjusted_price updates. The top-100 dollar-volume cap is broken: it sorts by a string expression and returns DataFrame integer indices, not symbols. The top-decile selection and equal-weight PortfolioTargets are delegated to an undefined _get_targets. Warm-up, the unchanged universe during warm-up, and the minimum order margin setting are all missing. Only the shell is correct: dates, cash, seeded prices, minute resolution, the monthly 09:31 schedule and liquidate_existing_holdings.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v06.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v06.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v06.json)

QC error:

```text
2022-01-01 00:00:00 Runtime Error: bad operand type for unary -: 'str'
  at _select_assets
    return list(history.reset_index().sort_values(-("open" * 2)).iloc[:100].index)
                                                  ^^^^^^^^^^^^^
 in main.py: line 25

```

## equity-momentum-cross-sectional-decile_v07

Prompt: We need a long-only cross-sectional momentum factor reference on large-cap US equities for 2022 through 2024, consistent with our internal implementation: liquid S&P 500 names, top decile by trailing-year momentum, monthly rebalance. Standard paper account.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate gets the shell right: SPY constituents, the 2022-2024 window, a monthly schedule, long-only equal weighting and $250k cash. The defining factor logic is wrong, though. Line 25 never computes a per-symbol trailing-year return and never ranks names into a top decile. `quantile(0.91)` on a multi-indexed history Series returns one scalar, not a per-symbol cutoff. `return_` is not a standard history column. The code also intersects a top-~9% dollar-volume filter with a top-~9% return filter instead of taking the top decile by momentum within a liquid universe. Because the momentum signal, the decile rule and the liquidity filter all deviate, this is the same strategy family with several key elements wrong.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v07.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v07.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v07.json)

QC error:

```text
2022-01-01 00:00:00 Runtime Error: 'DataFrame' object has no attribute 'dollar_volume'
  at __getattr__
    return object.__getattribute__(self, name)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in generic.py: line 6321
  at _select_assets
    return list(history.dollar_volume.quantile(0.91).index & history.return_.quantile(0.91).index)
                ^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 25

```

## equity-momentum-cross-sectional-decile_v08

Prompt: Implement the desk's cross-sectional momentum reference. Universe: constituents of the SPY ETF, capped at the 100 highest by dollar volume. Window: 2022-01-01 to 2024-12-31. Capital: 250,000. Signal: 252-period momentum percent per symbol computed from daily adjusted prices. Rebalance: first trading day of each month at 09:31; hold the top 10% of the capped universe equal-weight and liquidate the rest. Warm up 253 daily bars before selecting.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate has the right shell: SPY ETF universe capped at 100, the correct dates and capital, a month-start 09:31 rebalance, a top-10 equal-weight portfolio, and liquidation of other holdings. Several key elements are wrong or missing. The requested per-symbol 252-period MomentumPercent on daily adjusted prices is replaced by a single undefined `PortfolioMomentum(252)` object fed minute-resolution slices from `on_data`. No 253-daily-bar warm-up is configured. The dollar-volume cap reads `dollar_volume` from ETF constituent records rather than from fundamental data, so the liquidity filter is questionable. These are several key mismatches within the same strategy family.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v08.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v08.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v08.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: name 'PortfolioMomentum' is not defined
  at initialize
    self._momentum = PortfolioMomentum(252)
                     ^^^^^^^^^^^^^^^^^
 in main.py: line 21
 name 'PortfolioMomentum' is not defined
```

## equity-momentum-cross-sectional-decile_v09

Prompt: Implement the desk's cross-sectional momentum reference. Universe: constituents of the SPY ETF, capped at the 100 highest by dollar volume, universe resolution minute. Window: 2022-01-01 to 2024-12-31. Capital: 250,000. Signal: 252-period momentum percent per symbol computed from daily adjusted prices. Rebalance: first trading day of each month at 09:31 via a scheduled event; hold the top 10% of the capped universe equal-weight with portfolio targets and liquidate the rest. Warm up 253 daily bars and return the universe unchanged while warming up. Compliance: seed initial prices, set minimum order margin portfolio percentage to zero, equal weights only, long-only, no leverage, snake_case API per style guide, type annotations.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate has the right strategy family: SPY ETF constituents, a monthly 09:31 scheduled rebalance, equal-weight PortfolioTargets with liquidation, the correct dates, capital, minute resolution and seeded prices. Several key elements are wrong or missing. It uses plain Momentum instead of MomentumPercent. The selection function returns sorted dollar-volume floats instead of the top 100 symbols, and adds unrequested filters (constituent weight, existing-security, 30-bar history). The top-10% selection is not implemented correctly. The 253-bar daily warm-up and the Universe.UNCHANGED return during warm-up are missing. minimum_order_margin_portfolio_percentage = 0 is missing.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v09.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v09.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v09.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'SP500LowPctUpcomingEarningsUniverseAlgorithm' object has no attribute 'momentum'
  at initialize
    self._momentum = self.momentum(self._universe, 252, Resolution.DAILY)
                     ^^^^^^^^^^^^^
 in main.py: line 18
 'SP500LowPctUpcomingEarningsUniverseAlgorithm' object has no attribute 'momentum'
```

## equity-momentum-cross-sectional-decile_v10

Prompt: QuantConnect Python, snake_case. initialize: dates 2022-01-01 to 2024-12-31, set_cash(250_000), settings.seed_initial_prices = True, settings.minimum_order_margin_portfolio_percentage = 0, _lookback = 252, _universe_cap = 100, _top_decile_pct = 0.1, dict of MomentumPercent per symbol, universe_settings.resolution = Resolution.MINUTE, _universe = add_universe(self.universe.etf('SPY'), self._select_assets), set_warm_up(253, Resolution.DAILY), schedule.on(date_rules.month_start('SPY'), time_rules.at(9, 31), self._rebalance). _select_assets: update each symbol's MomentumPercent with (f.end_time, f.adjusted_price); return Universe.UNCHANGED while warming up; sort ready by dollar_volume desc, cap 100; rank by momentum desc; return top max(1, int(n * 0.1)) symbols. _rebalance: selected = list(_universe.selected); set_holdings([PortfolioTarget(s, 1/len) ...], liquidate_existing_holdings=True).

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

Dates, cash, settings, minute resolution and the monthly 9:31 schedule match the request. Most of the core logic does not. There is no set_warm_up. The selector does not sort by dollar_volume, does not compute momentum and never returns Universe.UNCHANGED; it just takes the first 100 entries. The indicator is Momentum rather than MomentumPercent, is created only when the dict is empty, and is fed the live price in _rebalance instead of (f.end_time, f.adjusted_price) in selection. The rebalance is long top-10/short bottom-10 at ±0.1 instead of equal-weight long 1/len over the universe selection. The strategy family is the same, but several key elements are wrong.

[English code view](candidates_english/equity-momentum-cross-sectional-decile_v10.py) | [Original evaluated source](candidates/equity-momentum-cross-sectional-decile_v10.py) | [Judgment](scoring/together_9b_tuned/equity-momentum-cross-sectional-decile_v10.json)

QC error:

```text
Algorithm.Initialize() Error: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'ETF' is not defined
  at ETFUniverseAlgorithm
    def _select_assets(self, data: List[ETF]) -> List[Symbol]:
                                        ^^^
 in main.py: line 26
  at 
    class ETFUniverseAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'ETF' is not defined Stack Trace: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'ETF' is not defined
  at ETFUniverseAlgorithm
    def _select_assets(self, data: List[ETF]) -> List[Symbol]:
                                        ^^^
 in main.py: line 26
  at 
    class ETFUniverseAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'ETF' is not defined
```

## equity-opening-range-breakout_v01

Prompt: Make me a day trading bot for SPY that trades the morning breakout. Watch the first bit of the day, then go long if it breaks above or short if it breaks below, and close out before the end of the day. Last few months of 2024.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The asset (SPY), date range (Sep–Dec 2024), and long/short direction fit the request. The core strategy does not. No opening range is ever recorded: there is no high or low from the first part of the session, and the breakout test is replaced by a price-vs-previous_price(30) trend comparison gated on an otherwise unused 30-day daily ROC. Line 29 calls liquidate in the same function that just called set_holdings, so every position is opened and closed in the same callback. This is not a meaningful hold-until-end-of-day exit. The result is a degenerate intraday momentum check, not an opening-range breakout. It stays loosely in the intraday long/short family, but several key elements are wrong.

[English code view](candidates_english/equity-opening-range-breakout_v01.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v01.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v01.json)

QC error:

```text
2024-09-03 10:00:00 Runtime Error: 'Equity' object has no attribute 'previous_price'
  at _rebalance
    in_uptrend = self._spy.price > self._spy.previous_price(30)
                                   ^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 24

```

## equity-opening-range-breakout_v02

Prompt: SPY on minute bars. Track the high and low from 9:30 to 10:00. After 10:00, if a bar closes above that high buy with everything, if it closes below that low short with everything. Only one trade per day. Close everything at 3:55 and reset. Sept 1 to Dec 31 2024, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The asset, minute resolution, date range and 100k capital match the request. The trading logic does not. The code never builds a fixed 9:30-10:00 opening range. Instead it uses a rolling 30-bar range object from an undocumented call, IndicatorExtensions.create_range, which is fed every bar and never anchored to the session open. Breakout checks are not gated to after 10:00. There is no one-trade-per-day limit, and the long/short flags make it a repeated stop-and-reverse system. A short is only possible after a long already exists. There is no 3:55 liquidation and no daily reset. It is in the broad breakout family, but several key elements are wrong or missing.

[English code view](candidates_english/equity-opening-range-breakout_v02.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v02.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v02.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: type object 'IndicatorExtensions' has no attribute 'create_range'
  at initialize
    self._range = IndicatorExtensions.create_range(self, self._spy, 30, Resolution.MINUTE)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 type object 'IndicatorExtensions' has no attribute 'create_range'
```

## equity-opening-range-breakout_v03

Prompt: SPY on minute bars. Track the high and low from 9:30 to 10:00. After 10:00, if a bar closes above that high buy with everything, if it closes below that low short with everything. Only one trade per day. Close everything at 3:55 and reset. Sept 1 to Dec 31 2024, 100k. Plot the range high and low on a chart called ORB and the trade direction on a chart called Trades, call the class OpeningRangeBreakout, and seed the starting prices.

QC: syntax_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate belongs to the opening-range breakout family: SPY, the correct dates and cash, ±100% set_holdings, and a 15:55 liquidate check. Most key elements are wrong, though. The range is not anchored to 9:30–10:00. The entry compares a consolidated bar's close to that same bar's high and low, so it can never trigger. on_data calls set_holdings(SPY, 0) on every bar, which flattens any position. There is no one-trade-per-day tracking and no daily reset. The Trades chart does not plot direction. The class name is wrong, and the starting prices are not seeded.

[English code view](candidates_english/equity-opening-range-breakout_v03.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v03.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v03.json)

QC error:

```text
invalid syntax (main.py, line 22)
```

## equity-opening-range-breakout_v04

Prompt: SPY 30-min ORB, long/short break, 1 trade/day, flat 15:55. Q4 2024.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement a 30-minute opening range breakout. It builds no opening range. Instead it tries a Bollinger Band signal that is created on option contracts, while the trading code reads an indicator on SPY that is never assigned. It only checks for a signal once per day at a scheduled time. Every entry is long, so there is no short side. Exits happen on the next scheduled call, so positions are held overnight rather than closed at 15:55. It also adds an unrequested option universe and starts on Sep 1 instead of Q4 (Oct 1).

[English code view](candidates_english/equity-opening-range-breakout_v04.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v04.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v04.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: name 'UniverseType' is not defined
  at initialize
    self.universe_settings.universe_type = UniverseType.OPTIONS
                                           ^^^^^^^^^^^^
 in main.py: line 21
 name 'UniverseType' is not defined
```

## equity-opening-range-breakout_v05

Prompt: SPY minute. Range = high/low of 09:30-10:00 bars. After 10:00: close > range high -> 100% long; close < range low -> 100% short; clear range after a trade (1/day). Liquidate 15:55, reset. 2024-09-01 to 2024-12-31, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate keeps the right asset, dates and cash, and it is a range-breakout strategy. Most key elements are wrong. The range is not the 09:30-10:00 opening range; it is a nonstandard 2*24*60-period construct (line 14). Breakouts are checked only once a day at 09:31, not after 10:00. There is no 15:55 liquidation. There is no real one-trade-per-day range clearing; lines 29-30 overwrite the indicator's current and previous values, which does not clear the range high and low. These multiple key mismatches put it in the 'same family, several key elements wrong' band.

[English code view](candidates_english/equity-opening-range-breakout_v05.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v05.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v05.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: type object 'IndicatorExtensions' has no attribute 'create_range'
  at initialize
    self._range = IndicatorExtensions.create_range(self, self._spy, 2*24*60)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 type object 'IndicatorExtensions' has no attribute 'create_range'
```

## equity-opening-range-breakout_v06

Prompt: SPY minute. Range = high/low of bars with 09:30 <= t < 10:00. After 10:00: close > range high -> 100% long; close < range low -> 100% short; clear range after a trade (1/day). Scheduled liquidate at 15:55 every day, reset range there too. 2024-09-01 to 2024-12-31, 100k. Seed initial prices, plot range + direction, snake_case, keep range in two attrs, no consolidators.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate trades SPY breakouts with the correct dates, cash and price seeding, but most key rules are wrong. The range is not limited to 09:30-10:00: it accumulates closes from every bar since the start and never resets. Entry is checked only once per day at about 10:09 instead of on every bar after 10:00. There is no scheduled 15:55 liquidation; the minute==55 check inside a ~10:09 callback never fires, so the first position is held indefinitely. The range is never cleared after a trade or at day end. Range and direction plotting are missing.

[English code view](candidates_english/equity-opening-range-breakout_v06.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v06.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v06.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: property is read-only
  at initialize
    self._spy.low = None
    ^^^^^^^^^^^^^
 in main.py: line 14
 property is read-only
```

## equity-opening-range-breakout_v07

Prompt: We need an intraday opening-range breakout reference on SPY for the September to December 2024 window, consistent with our internal implementation: single trade per session, both directions, flat before the close. Standard paper account.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is an opening-range breakout on SPY for the requested window, but it misses explicit requirements. There is no end-of-day liquidation, so positions carry overnight, which breaks both 'flat before the close' and the intraday nature of the strategy. Breakouts are checked only once per day, at open+30 minutes, so later breakouts in the session are never traded. Exits also run on later days and close a position whenever price is outside the range in either direction, including continuation moves. The family and core idea are right, but several key elements are wrong.

[English code view](candidates_english/equity-opening-range-breakout_v07.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v07.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v07.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'Equity' object has no attribute 'opening_range'
  at initialize
    self._range = self._spy.opening_range(30, Resolution.MINUTE)
                  ^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 14
 'Equity' object has no attribute 'opening_range'
```

## equity-opening-range-breakout_v08

Prompt: Implement the desk's opening-range breakout reference on SPY. Resolution: minute. Window: 2024-09-01 to 2024-12-31. Capital: 100,000. Range: high and low of bars from 09:30 to 10:00. Entry after 10:00: a close above the range high allocates 100% long; a close below the range low allocates 100% short; at most one entry per day. Exit: liquidate at 15:55 and reset the range daily.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is a breakout-style strategy on SPY with the correct dates and capital, but several key elements are wrong. Line 14 builds a RangeBar(30, ...) object instead of the high and low of the 09:30–10:00 bars. Line 19 checks for a breakout only once, at 10:00, rather than on each bar after 10:00. Line 29 can go short only when already long, so it never shorts from flat. There is no 15:55 liquidation and no daily range reset, so positions are held overnight.

[English code view](candidates_english/equity-opening-range-breakout_v08.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v08.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v08.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'EquityOpeningRangeBreakoutAlgorithm' object has no attribute 'indicator' Did you mean: 'indicator_history', 'plot_indicator', 'warm_up_indicator', 'register_indicator', 'deregister_indicator'?
  at initialize
    self._spy.range = self.indicator(self._spy, RangeBar(30, Resolution.MINUTE))
                      ^^^^^^^^^^^^^^
 in main.py: line 14
 'EquityOpeningRangeBreakoutAlgorithm' object has no attribute 'indicator' Did you mean: 'indicator_history', 'plot_indicator', 'warm_up_indicator', 'register_indicator', 'deregister_indicator'?
```

## equity-opening-range-breakout_v09

Prompt: Implement the desk's opening-range breakout reference on SPY. Resolution: minute. Window: 2024-09-01 to 2024-12-31. Capital: 100,000. Range: high and low of bars from 09:30 to 10:00. Entry after 10:00: a close above the range high allocates 100% long; a close below the range low allocates 100% short; clear the range after an entry so there is at most one per day. Exit: scheduled liquidation at 15:55 every trading day, then reset the range. Compliance: seed initial prices, plot the range bounds and trade direction for audit, no overnight positions, no leverage beyond 100% notional, snake_case API per style guide, type annotations.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate sets the dates, cash, initial-price seeding and SPY subscription, and builds an ORB indicator. However, on_data is empty (line 21) and no other logic places orders. No breakout entries, long/short allocation, one-entry-per-day reset, 15:55 scheduled liquidation, range reset or audit plots exist. The code does not implement the requested trading strategy. It only adds a helper object that never drives any trades.

[English code view](candidates_english/equity-opening-range-breakout_v09.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v09.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v09.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'EquityOpeningRangeBreakoutAlgorithm' object has no attribute 'orb'
  at initialize
    self._orb = self.orb(self._spy, 30, 30, Resolution.MINUTE)
                ^^^^^^^^
 in main.py: line 16
 'EquityOpeningRangeBreakoutAlgorithm' object has no attribute 'orb'
```

## equity-opening-range-breakout_v10

Prompt: QuantConnect Python, snake_case. initialize: set_start_date(2024, 9, 1), set_end_date(2024, 12, 31), set_cash(100000), settings.seed_initial_prices = True, spy = add_equity('SPY', resolution=Resolution.MINUTE).symbol, _orb_high = _orb_low = None, schedule.on(date_rules.every_day(spy), time_rules.at(15, 55), self._liquidate_eod). _liquidate_eod: liquidate(spy); reset range. on_data: bar = data.bars.get(spy); t = self.time.time(); if time(9,30) <= t < time(10,0): extend range with bar.high/bar.low; elif t >= time(10,0): if _orb_high and bar.close > _orb_high: set_holdings(spy, 1.0), clear range; if _orb_low and bar.close < _orb_low: set_holdings(spy, -1.0), clear range.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate keeps the requested scaffolding: SPY at minute resolution, the date range, $100k cash, seed_initial_prices, a 15:55 daily liquidation, and set_holdings at ±1.0. It does not implement the requested opening range breakout. There is no _orb_high/_orb_low state and no 9:30–10:00 range construction with bar.high/bar.low. There is no breakout check of bar.close against the range after 10:00, and the range is never cleared after entry or at end of day. Instead it relies on an invented 'OneBarOption' indicator and an option_chain call that takes an indicator. Entries are triggered by comparing option strikes to bar.close. This is a different strategy, not the requested ORB.

[English code view](candidates_english/equity-opening-range-breakout_v10.py) | [Original evaluated source](candidates/equity-opening-range-breakout_v10.py) | [Judgment](scoring/together_9b_tuned/equity-opening-range-breakout_v10.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: name 'OneBarOption' is not defined
  at initialize
    self._orb = OneBarOption(self._spy)
                ^^^^^^^^^^^^
 in main.py: line 13
 name 'OneBarOption' is not defined
```

## equity-pairs-trading-cointegration_v01

Prompt: Can you build a pairs trading bot for Coke and Pepsi? When they drift apart bet on them coming back together, and close out when they're back to normal. 2022 to 2024.

QC: completed. Claude fidelity: 1. Judge: judged. Behavior: available.

The candidate does not implement a pairs trade. Its only indicator is an unregistered SimpleMovingAverage(20) that never receives data. Even ignoring that, it measures no KO/PEP spread or ratio. It opens a long KO position only when the 'ratio' is close to its target, which is the opposite of entering on divergence. It never takes the offsetting PEP position. Its exit conditions require a large negative KO or PEP weight, which this long-KO-only position cannot produce. Only the assets declared and the date range match the request.

[English code view](candidates_english/equity-pairs-trading-cointegration_v01.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v01.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v01.json)

## equity-pairs-trading-cointegration_v02

Prompt: Pairs trade KO and PEP. Once a week fit a linear regression of KO's price on PEP's price over the last 60 daily closes to get the slope and intercept, and save the mean and standard deviation of the spread. Every day at 10:00 compute the z-score of today's spread. If z is below -2 buy KO and short PEP with half the money each. If z is above 2 do the opposite. If z is between -0.5 and 0.5 close everything. Minute data, Jan 1 2022 to Dec 31 2024, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

Assets, dates, cash, minute resolution, the daily 10:00 schedule, the ±2 entry and ±0.5 exit thresholds, and the 50/50 sizing all match the request. The core statistical model, however, departs from it in several key ways. There is no weekly regression fit. A daily-updated regression indicator is used instead (line 21). Only its current value is treated as the slope, and no intercept is used (line 40). The spread mean and standard deviation are not taken from the 60-day fit window. They come from a separate rolling window of 60 residuals sampled at 10:00, each computed with a different slope (lines 26, 40-47). Several key elements are wrong within the same strategy family.

[English code view](candidates_english/equity-pairs-trading-cointegration_v02.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v02.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v02.json)

QC error:

```text
Algorithm.Initialize() Error: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'LinearRegression' is not defined
  at CocaCokePepsiPairTradingAlgorithm
    _pep_ratio = LinearRegression(60)
                 ^^^^^^^^^^^^^^^^
 in main.py: line 6
  at 
    class CocaCokePepsiPairTradingAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'LinearRegression' is not defined Stack Trace: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'LinearRegression' is not defined
  at CocaCokePepsiPairTradingAlgorithm
    _pep_ratio = LinearRegression(60)
                 ^^^^^^^^^^^^^^^^
 in main.py: line 6
  at 
    class CocaCokePepsiPairTradingAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'LinearRegression' is not defined
```

## equity-pairs-trading-cointegration_v03

Prompt: Pairs trade KO and PEP. Once a week at 9:31 fit a linear regression of KO's price on PEP's price over the last 60 daily closes to get the slope and intercept, and save the mean and standard deviation of the spread. Every day at 10:00 compute the z-score of today's spread. If z is below -2 buy KO and short PEP with half the money each. If z is above 2 do the opposite. If z is between -0.5 and 0.5 close everything. Minute data, Jan 1 2022 to Dec 31 2024, 100k. Use numpy for the regression, call the class KoPepPairs, keep a state variable for flat/long/short so it doesn't re-enter the same side, and add comments on each rule.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is a z-score pairs trade on KO/PEP with ±2 entry and ±0.5 exit thresholds, so it belongs to the requested strategy family. However, several key elements are wrong or missing. There is no numpy regression of KO on PEP over 60 daily closes; it uses an undefined 'MovingAveragePair(20, 20)' and misuses scipy.stats.zscore. There is no daily 10:00 evaluation; trading happens only in the weekly routine. Trade directions are inverted: z<-2 buys PEP and shorts KO instead of buying KO and shorting PEP. The class name is not KoPepPairs. The state variable does not distinguish long from short. Per-rule comments are missing.

[English code view](candidates_english/equity-pairs-trading-cointegration_v03.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v03.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v03.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: name 'MovingAveragePair' is not defined
  at _create_average
    average = MovingAveragePair(20, 20)
              ^^^^^^^^^^^^^^^^^
 in main.py: line 31
  at initialize
    self._averages[pep] = self._create_average(pep, ko)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 21
 name 'MovingAveragePair' is not defined
```

## equity-pairs-trading-cointegration_v04

Prompt: KO/PEP stat arb. 60d OLS hedge weekly, z-score daily, ±2 in, 0.5 out, $-neutral. 2022-2024.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is a KO/PEP z-score pairs strategy, so it belongs to the same family, but several key requested elements are wrong. There is no 60-day OLS hedge ratio, and nothing is re-fit weekly. The z-score comes from a minute-level on_data feed rather than a daily one, and appears to use non-standard pair APIs. The exit adds a 1% drift condition, and because _rebalance returns early when not invested, exits never trade. Positions are only placed on the weekly schedule, not acted on daily. Only the tickers, the ±2/0.5 threshold constants and the date range match.

[English code view](candidates_english/equity-pairs-trading-cointegration_v04.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v04.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v04.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'CocaCokePepsiPairTradingAlgorithm' object has no attribute 'get_pair' Did you mean: 'get_parameter', 'get_parameters'?
  at initialize
    self._pair = self.get_pair(self._pep, self._ko)
                 ^^^^^^^^^^^^^
 in main.py: line 24
 'CocaCokePepsiPairTradingAlgorithm' object has no attribute 'get_pair' Did you mean: 'get_parameter', 'get_parameters'?
```

## equity-pairs-trading-cointegration_v05

Prompt: KO, PEP minute. Weekly 09:31: OLS KO ~ PEP on last 60 daily closes -> beta, alpha, spread mean/std. Daily 10:00: z = (spread - mean)/std. z < -2: KO +50% PEP -50%. z > 2: reverse. |z| < 0.5: flat. Warm up 60 daily. 2022-01-01 to 2024-12-31, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

Same strategy family: a KO/PEP z-score pairs trade with ±2 thresholds, 60-day warm-up, correct dates and cash. Most key elements are wrong or missing. (1) The OLS fit is wrong: it regresses KO on KO, uses a log-ratio target, discards alpha, and runs only once at warm-up end instead of weekly at 09:31. (2) Spread mean and std come from a rolling window of minute-level residuals, not from the 60-day OLS fit. (3) The z formula adds the mean instead of subtracting it. (4) Trade directions are inverted. (5) The |z| < 0.5 flat exit is absent. (6) There is no daily 10:00 schedule. (7) The second set_holdings call with liquidate=True closes the first leg, so only one leg is held.

[English code view](candidates_english/equity-pairs-trading-cointegration_v05.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v05.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v05.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'CocaCokePepsiPairTradingAlgorithm' object has no attribute 'signal_registry'
  at initialize
    self._signal = self.signal_registry.add(self._rebalance)
                   ^^^^^^^^^^^^^^^^^^^^
 in main.py: line 25
 'CocaCokePepsiPairTradingAlgorithm' object has no attribute 'signal_registry'
```

## equity-pairs-trading-cointegration_v06

Prompt: KO, PEP minute. Weekly 09:31 (and on warm-up finished): OLS KO ~ PEP on last 60 daily session closes via np.linalg.lstsq -> beta, alpha, spread mean/std (floor std 1e-6). Daily 10:00: z = (spread - mean)/std. z < -2 and not long: KO +50% PEP -50%. z > 2 and not short: reverse. |z| < 0.5 and in position: liquidate. Track state 0/1/-1. set_warm_up(60, daily). 2022-01-01 to 2024-12-31, 100k. Use security.session for closes, snake_case, no history() calls.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested strategy. It never computes an OLS via np.linalg.lstsq. It makes history() calls, which the request forbids, instead of using security.session. It has no spread mean/std and no 1e-6 std floor, no daily 10:00 schedule, no set_warm_up, and no 0/1/-1 state tracking. Its z-score is built from PEP's own running price statistics, not the KO~PEP spread. The entry logic is a threshold-crossover that only runs when PEP is already invested (lines 143-144), so it can never open a position. It calls undefined _buy/_sell helpers. There is no |z|<0.5 liquidation. Only the tickers, dates, cash and the weekly 09:31 schedule match.

[English code view](candidates_english/equity-pairs-trading-cointegration_v06.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v06.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v06.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the .ctor method. Please checkout the API documentation. The following overloads are available:
  .ctor()
  .ctor(symbol: Symbol, quantity: float, time: datetime, tag: str = "", properties: IOrderProperties = None)
  .ctor(symbol: Symbol, quantity: float, time: datetime, price: float, tag: str = "", properties: IOrderProperties = None)
  at initialize
    self._rank_market_order = MarketOrder(self._rank_equity, self._rank_order_quantity)
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 63
 No method matches given arguments for .ctor: (, ). The following overloads are available:
  .ctor()
  .ctor(symbol: Symbol, quantity: float, time: datetime, tag: str = "", properties: IOrderProperties = None)
  .ctor(symbol: Symbol, quantity: float, time: datetime, price: float, tag: str = "", properties: IOrderProperties = None)
```

## equity-pairs-trading-cointegration_v07

Prompt: We need a market-neutral pairs trading reference on KO and PEP for 2022 through 2024, consistent with our internal implementation: rolling OLS hedge ratio, z-score entries and exits, dollar-neutral legs. Standard paper account.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate gets the tickers and the 2022-2024 dates right, and it builds a KO-vs-PEP log-price signal, so it is loosely in the pairs-trading family. Every core mechanic the request names is wrong or missing. (1) There is no rolling OLS hedge ratio between KO and PEP: line 16 uses an unexplained LinearRegressionOptimizer that line 28 feeds only KO prices, and its output is never used. (2) There is no real z-score: line 17 is a 10-period SMA of the log ratio, divided at line 34 by a 'correlation' SMA that is never updated. (3) There are no z-score exits. (4) Only KO is traded (line 51), so the legs are not dollar-neutral or market-neutral. Several key elements are wrong within the same strategy family, so the score is 2.

[English code view](candidates_english/equity-pairs-trading-cointegration_v07.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v07.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v07.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: name 'LinearRegressionOptimizer' is not defined
  at initialize
    self._optimizer = LinearRegressionOptimizer(180)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 16
 name 'LinearRegressionOptimizer' is not defined
```

## equity-pairs-trading-cointegration_v08

Prompt: Implement the desk's pairs trading reference on KO and PEP. Resolution: minute. Window: 2022-01-01 to 2024-12-31. Capital: 100,000. Model: weekly at 09:31, fit OLS of KO on PEP over the last 60 daily closes to obtain beta and alpha, and record the spread's mean and standard deviation. Signal: daily at 10:00, z-score of the current spread. Rules: z below -2, long KO 50% and short PEP 50%; z above 2, the reverse; absolute z below 0.5, liquidate. Warm up 60 daily bars.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is a KO/PEP pairs strategy with a regression and z-score, but most key elements are wrong. The regression uses 10-minute-sampled intraday bars, and its sums are cumulative and never reset. It records no spread mean or standard deviation. It has no ±2 entry thresholds and no daily 10:00 signal schedule. Its weights are long-only and continuous instead of a 50% long / 50% short split. There is no 60-daily-bar warm-up. Only the assets, resolution, dates, capital and the |z|<0.5 liquidation match the request.

[English code view](candidates_english/equity-pairs-trading-cointegration_v08.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v08.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v08.json)

QC error:

```text
2022-01-03 09:31:00 Runtime Error: 'ConsumerBraggingRightsAlgorithm' object has no attribute 'training_mode' Did you mean: 'train'?
  at on_data
    if not self.training_mode and self.time % timedelta(minutes=10) == 0:
           ^^^^^^^^^^^^^^^^^^
 in main.py: line 38

```

## equity-pairs-trading-cointegration_v09

Prompt: Implement the desk's pairs trading reference on KO and PEP. Resolution: minute. Window: 2022-01-01 to 2024-12-31. Capital: 100,000. Model: weekly at 09:31 via a scheduled event, and once when warm-up finishes, fit OLS of KO on PEP over the last 60 daily closes to obtain beta and alpha, and record the spread's mean and standard deviation, flooring the standard deviation at 1e-6. Signal: daily at 10:00 via a scheduled event, z-score of the current spread. Rules: z below -2 and not already long the spread, long KO 50% and short PEP 50%; z above 2 and not already short the spread, the reverse; absolute z below 0.5 while in a position, liquidate. Track the position state. Warm up 60 daily bars. Compliance: dollar-neutral legs at exactly 50% each, no net leverage beyond that, snake_case API per style guide, type annotations.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is a KO/PEP pairs strategy with the correct assets, minute resolution, dates, capital, 2.0/0.5 thresholds and 50% leg sizes. Several key elements are wrong or missing. (1) There is no OLS fit of KO on PEP over 60 daily closes; it relies on an unregistered 'LinearRegressionOptimizer' whose update returns alpha/beta from a single PEP price. (2) It records no spread mean, normalizes by residual standard error, and has no 1e-6 floor. (3) There is no 60-daily-bar warm-up. (4) There is no daily 10:00 signal schedule; signals are evaluated only in the weekly rebalance. (5) Entry uses abs(z)>2 and always goes long KO/short PEP, so the z>2 reverse leg is missing. (6) No long/short spread state is tracked. (7) It adds an unrequested 10-signal-evaluation cap.

[English code view](candidates_english/equity-pairs-trading-cointegration_v09.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v09.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v09.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: name 'LinearRegressionOptimizer' is not defined
  at initialize
    self._optimizer = LinearRegressionOptimizer(1)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 25
 name 'LinearRegressionOptimizer' is not defined
```

## equity-pairs-trading-cointegration_v10

Prompt: QuantConnect Python, snake_case. initialize: dates 2022-01-01 to 2024-12-31, set_cash(100_000), ko/pep = add_equity(..., Resolution.MINUTE), set each security.session.size = 60, _alpha/_beta/_spread_mean/_spread_std/_state, set_warm_up(60, Resolution.DAILY), schedule.on(date_rules.week_start(), time_rules.at(9, 31), self._update_model), schedule.on(date_rules.every_day(), time_rules.at(10, 0), self._trade_logic); on_warmup_finished calls _update_model. _update_model: pull 60 session closes, np.linalg.lstsq for beta/alpha, spread = ko - (beta*pep + alpha), store mean/std. _trade_logic: z from securities[].close; z < -2 and state != 1 -> set_holdings([PortfolioTarget(ko, 0.5), PortfolioTarget(pep, -0.5)]), state = 1; z > 2 and state != -1 -> reverse, state = -1; abs(z) < 0.5 and state != 0 -> liquidate(), state = 0.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate keeps the right assets, dates, cash, resolution, warm-up and the ±2 / 0.5 z-score thresholds. Most of the specified mechanics are missing or wrong: no _state, no scheduled _update_model or _trade_logic, no on_warmup_finished, no np.linalg.lstsq OLS on 60 session closes, a KO/PEP price-ratio spread instead of the regression residual, statistics computed once in initialize with an invalid formula, trading every minute in on_data, z-scaled position sizes instead of fixed ±0.5, and no reversal path. It is the same strategy family with several key elements wrong.

[English code view](candidates_english/equity-pairs-trading-cointegration_v10.py) | [Original evaluated source](candidates/equity-pairs-trading-cointegration_v10.py) | [Judgment](scoring/together_9b_tuned/equity-pairs-trading-cointegration_v10.json)

QC error:

```text
2022-01-01 00:00:00 During the algorithm initialization, the following exception has occurred: int() argument must be a string, a bytes-like object or a real number, not 'datetime.timedelta'
  at initialize
    self._ko.session.size = timedelta(minutes=60)
    ^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 24
 int() argument must be a string, a bytes-like object or a real number, not 'datetime.timedelta'
```

## option-iron-condor-spy_v01

Prompt: I want to sell iron condors on SPY every week to collect premium. Open them Monday, close them Friday before the market closes. Last few months of 2024.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate uses the right asset (SPY), the right date range (late 2024) and names an iron condor. Three key elements are wrong or missing. (1) The four legs are chosen once in initialize and never re-selected weekly. (2) Leg selection is inverted: the long call is the lowest strike and the short call the highest, which does not form a short iron condor. (3) There is no Friday close at all. The only scheduled event is Monday, 1 minute before close, calling a rebalance method. on_data keeps regenerating a strategy object, but no explicit sell or buy orders are placed. Same strategy family, with several key elements wrong.

[English code view](candidates_english/option-iron-condor-spy_v01.py) | [Original evaluated source](candidates/option-iron-condor-spy_v01.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v01.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'Equity' object has no attribute 'expiry'
  at 
    self._calls = sorted([x for x in self._chain if x.right == OptionRight.CALL and x.expiry == self._spy.expiry + timedelta(0)], key=lambda x: x.strike)
                                                                                                ^^^^^^^^^^^^^^^^
 in main.py: line 17
  at initialize
    self._calls = sorted([x for x in self._chain if x.right == OptionRight.CALL and x.expiry == self._spy.expiry + timedelta(0)], key=lambda x: x.strike)
                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 17
 'Equity' object has no attribute 'expiry'
```

## option-iron-condor-spy_v02

Prompt: Every Monday a minute after the open, open an iron condor on SPY expiring that Friday: sell the call closest to 0.10 delta and the put closest to -0.10 delta, and buy a call and a put 3 strikes further out, one contract. Skip the week if any leg has no bid or ask. Close everything Friday 5 minutes before the close. Sept 1 to Dec 31 2024, 100k.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not build an iron condor. It never sells any legs. It picks ATM strikes instead of ±0.10 delta and then calls remove_option on them (lines 47-48). It only buys two wings at ATM±$3 (lines 33-34, 50-51), which makes a net-long strangle, the opposite of the requested short-premium structure. There is no delta selection, no bid/ask skip check, and no option chain subscription. The Friday close is scheduled inside the Monday handler. Only the shell (SPY, dates, cash, Monday timing) matches.

[English code view](candidates_english/option-iron-condor-spy_v02.py) | [Original evaluated source](candidates/option-iron-condor-spy_v02.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v02.json)

QC error:

```text
2024-09-09 09:31:00 Runtime Error: 'Equity' object has no attribute 'options'
  at _rebalance
    if not self._spy.options.active_strikes:
           ^^^^^^^^^^^^^^^^^
 in main.py: line 18

```

## option-iron-condor-spy_v03

Prompt: Every Monday a minute after the open, open an iron condor on SPY expiring that Friday: sell the call closest to 0.10 delta and the put closest to -0.10 delta, and buy a call and a put 3 strikes further out, one contract. Skip the week if any leg has no bid or ask. Close everything Friday 5 minutes before the close. Sept 1 to Dec 31 2024, 100k. Filter the chain to strikes -10 to +10 and expiries 0 to 7 days so it loads fast, use the built-in iron condor strategy helper, call the class WeeklyCondor, and comment each leg.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is in the same family as the request: a weekly SPY short iron-condor-style trade opened at the start of the week and closed at the end. Nearly every key specified element is wrong or missing. The class name is wrong. The filter is a misspelled 'staddle(0,0)' instead of strikes(-10,10)/expiration(0,7). Short strikes are ATM rather than closest to ±0.10 delta. Wings are the extreme chain strikes rather than 3 strikes out. Expiry is not targeted to that Friday. There is no bid/ask skip check. The close is 3 minutes before the close instead of 5. There is no explicit one-contract order, the iron condor helper is called with the wrong strike arguments, and the legs are not commented. Only the asset, the date range, the cash and the Monday-open timing match.

[English code view](candidates_english/option-iron-condor-spy_v03.py) | [Original evaluated source](candidates/option-iron-condor-spy_v03.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v03.json)

QC error:

```text
2024-09-01 00:00:00 Runtime Error: 'OptionFilterUniverse' object has no attribute 'staddle' Did you mean: 'straddle'?
  at 
    self._option.set_filter(lambda u: u.staddle(0, 0))
                                      ^^^^^^^^^
 in main.py: line 15

```

## option-iron-condor-spy_v04

Prompt: SPY weekly IC. Mon open sell 10d strangle, wings +3 strikes, Fri expiry, close Fri before bell. Q4 2024.

QC: syntax_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The request is a weekly SPY iron condor: sell a 10-delta strangle on Monday open, buy wings 3 strikes further out, use Friday expiry, and close on Friday before the bell. The candidate instead tries to buy an ATM straddle on 0DTE options every bar. It has no short legs, no delta selection, no wings, no Monday/Friday scheduling and no exit logic. It does not implement the requested strategy.

[English code view](candidates_english/option-iron-condor-spy_v04.py) | [Original evaluated source](candidates/option-iron-condor-spy_v04.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v04.json)

QC error:

```text
invalid syntax (main.py, line 29)
```

## option-iron-condor-spy_v05

Prompt: SPY options, filter strikes(-10,10) expiration(0,7). Mon +1m after open: expiry = this Fri; short call nearest +0.10 delta, short put nearest -0.10 delta, wings 3 strikes out; skip if any leg missing bid/ask; buy OptionStrategies.iron_condor x1. Fri -5m before close: liquidate. 2024-09-01 to 2024-12-31, 100k.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate has the right setup: SPY options, the strikes(-10,10)/expiry(0,7) filter, the 2024-09-01 to 2024-12-31 range, $100k cash, and an iron condor bought x1. It is the same strategy family, but several key elements are wrong or missing. There is no Monday +1 minute entry schedule. The expiry is the first chain expiry, not this Friday. Strikes come from list slicing, not ±0.10 delta, and there are no 3-strike wings. There is no bid/ask check. The iron_condor call does not match the requested four-strike construction. The Friday exit fires at 15:45, not 5 minutes before close, and is re-registered inside on_data.

[English code view](candidates_english/option-iron-condor-spy_v05.py) | [Original evaluated source](candidates/option-iron-condor-spy_v05.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v05.json)

QC error:

```text
2024-09-01 00:00:00 Runtime Error: 'OptionFilterUniverse' object has no attribute 'expiry'
  at 
    self._option.set_filter(lambda u: u.expiry(0, 7).strikes(-10, 10))
                                      ^^^^^^^^
 in main.py: line 13

```

## option-iron-condor-spy_v06

Prompt: SPY options, filter strikes(-10,10) expiration(0,7). Mon +1m after open via schedule: expiry = this Fri; need >= 4 calls and >= 4 puts; short call nearest +0.10 delta, short put nearest -0.10 delta, wings 3 strikes out in sorted strike list with bounds check; skip if any leg missing bid/ask; buy OptionStrategies.iron_condor x1. Fri -5m before close via schedule: liquidate. 2024-09-01 to 2024-12-31, 100k. Seed initial prices, use self.option_chain not slice, snake_case.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate keeps the right asset, strike filter, dates and cash, and loosely attempts an iron condor-style structure. Almost every specific rule is wrong or missing. Entry runs every day instead of Monday. Expiry is not this Friday. The short legs are not chosen by the ±0.10 contract delta. There are no 3-strike wings with a bounds check and no bid/ask check. It does not buy OptionStrategies.iron_condor x1. There is no Friday liquidation. Initial prices are not seeded. It reads self._option.chain instead of self.option_chain. Because _min_strike starts at -1 (lines 7-8), the strike filter on lines 44-47 also excludes every SPY contract, so no order is ever attempted. This is the same strategy family with several key elements wrong.

[English code view](candidates_english/option-iron-condor-spy_v06.py) | [Original evaluated source](candidates/option-iron-condor-spy_v06.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v06.json)

QC error:

```text
2024-09-01 00:00:00 Runtime Error: 'OptionFilterUniverse' object has no attribute 'expiries' Did you mean: 'expiring_after', 'expiration'?
  at 
    self._option.set_filter(lambda u: u.strikes(-10, 10).expiries(0, 7))
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 17

```

## option-iron-condor-spy_v07

Prompt: We need a weekly SPY iron condor income reference for the September to December 2024 window, consistent with our internal implementation: short strikes near 10 delta, defined-risk wings, opened Monday and closed before Friday's close. Standard paper account.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate builds a SPY iron condor over the correct Sep–Dec 2024 window, so it is in the right strategy family. Several key requested elements are wrong or missing. Short strikes are set at ATM ±1 rather than near 10 delta. Expiry targets about 30 days rather than weekly. There is no Monday-only entry. There is no exit before Friday's close; positions are simply held. Defined-risk wings do exist (±2 strikes).

[English code view](candidates_english/option-iron-condor-spy_v07.py) | [Original evaluated source](candidates/option-iron-condor-spy_v07.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v07.json)

QC error:

```text
2024-09-01 00:00:00 Runtime Error: 'OptionFilterUniverse' object has no attribute 'staddle' Did you mean: 'straddle'?
  at 
    self._option.set_filter(lambda u: u.staddle(30, 0))
                                      ^^^^^^^^^
 in main.py: line 15

```

## option-iron-condor-spy_v08

Prompt: Implement the desk's weekly SPY iron condor reference. Window: 2024-09-01 to 2024-12-31. Capital: 100,000. Chain filter: strikes -10 to +10 around the money, expiries 0 to 7 days. Open: every Monday one minute after the open, using contracts expiring that Friday; short call nearest +0.10 delta, short put nearest -0.10 delta, long call and long put 3 strikes further out; one iron condor; skip if any leg lacks a bid or ask. Close: every Friday five minutes before the close, liquidate all positions.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The schedule, window, capital, underlying and Friday liquidation match the request. The core iron condor is not implemented correctly. There is no delta-based strike selection. The chain filter ignores the requested strike and expiry bounds. Contracts expire 7 or more days out instead of that Friday. Call and put legs are not filtered by right. There are no wings 3 strikes further out. All four legs end up net short. There is no bid/ask check. This is borderline 1/2, since the resulting position is not an iron condor; the score of 2 reflects only the shared weekly short-premium SPY options framework.

[English code view](candidates_english/option-iron-condor-spy_v08.py) | [Original evaluated source](candidates/option-iron-condor-spy_v08.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v08.json)

QC error:

```text
2024-09-01 00:00:00 Runtime Error: 'OptionUniverse' object has no attribute 'expiry'
  at 
    expiry = min([x.expiry for x in chain])
                  ^^^^^^^^
 in main.py: line 21
  at _filter
    expiry = min([x.expiry for x in chain])
                 ^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 21
  at 
    self._option.set_filter(lambda u: self._filter(u))
                                      ^^^^^^^^^^^^^^^
 in main.py: line 16

```

## option-iron-condor-spy_v09

Prompt: Implement the desk's weekly SPY iron condor reference. Window: 2024-09-01 to 2024-12-31. Capital: 100,000. Chain filter: strikes -10 to +10 around the money, expiries 0 to 7 days. Open: every Monday one minute after the open via a scheduled event, using contracts expiring that Friday; require at least 4 calls and 4 puts; short call nearest +0.10 delta, short put nearest -0.10 delta, long call and long put 3 strikes further out with bounds checks; one iron condor via the OptionStrategies helper; skip if any leg lacks a bid or ask. Close: every Friday five minutes before the close via a scheduled event, liquidate all positions. Compliance: defined risk only, one condor at a time, seed initial prices, snake_case API per style guide, type annotations, no naked short options.

QC: syntax_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is a weekly SPY four-leg short-premium structure with Monday entry and Friday liquidation, so it is in the same strategy family. Several key requested elements are wrong or missing. The chain filter is not strikes -10..+10 with 0-7 day expiries; it is replaced by an ATM straddle 30-day filter. The short legs are ATM rather than nearest ±0.10 delta, and they are gated by an ATM |delta|<0.1 condition that rarely or never holds. Long wings are the farthest-from-ATM contracts, not 3 strikes further out, and there are no bounds checks. Other requirements are absent: Friday expiry targeting, the 4-call/4-put minimum, the bid/ask check, the OptionStrategies.iron_condor helper (combo_market_order is used instead) and seed_initial_prices. The close runs 1 minute before the close instead of 5.

[English code view](candidates_english/option-iron-condor-spy_v09.py) | [Original evaluated source](candidates/option-iron-condor-spy_v09.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v09.json)

QC error:

```text
invalid syntax (main.py, line 47)
```

## option-iron-condor-spy_v10

Prompt: QuantConnect Python, snake_case. initialize: set_start_date(2024, 9, 1), set_end_date(2024, 12, 31), set_cash(100000), settings.seed_initial_prices = True, _option = add_option('SPY'), _option.set_filter(lambda u: u.strikes(-10, 10).expiration(0, 7)), schedule.on(date_rules.every(DayOfWeek.MONDAY), time_rules.after_market_open(_option, 1), self._open_iron_condor), schedule.on(date_rules.every(DayOfWeek.FRIDAY), time_rules.before_market_close(_option, 5), self._close). _open_iron_condor: next_friday = (self.time + timedelta(4)).date(); chain = [x for x in self.option_chain(_option) if x.expiry.date() == next_friday]; split calls/puts sorted by strike; shorts by abs(greeks.delta -/+ 0.10); wings at sorted-strike index +/-3 with bounds check; require bid_price and ask_price on all four; self.buy(OptionStrategies.iron_condor(_option.symbol, long_put.strike, short_put.strike, short_call.strike, long_call.strike, next_friday), 1). _close: liquidate().

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate matches the setup: dates, cash, seeding, SPY option, an equivalent filter and the Monday open schedule. It is a SPY iron-condor-style strategy, but the core rules are wrong or missing. There is no Friday close schedule and no _close/liquidate(). It does not select a next-Friday expiry, uses no 10-delta shorts, has no ±3 strike-index wings and no bid/ask check. It also does not use OptionStrategies.iron_condor with self.buy. Its leg assignment differs entirely, using adjacent strikes in an ATM range, and it adds an unrequested conditional liquidation. These are several key mismatches in the same strategy family, so the score is 2.

[English code view](candidates_english/option-iron-condor-spy_v10.py) | [Original evaluated source](candidates/option-iron-condor-spy_v10.py) | [Judgment](scoring/together_9b_tuned/option-iron-condor-spy_v10.json)

QC error:

```text
2024-09-09 09:31:00 Runtime Error: 'Option' object has no attribute 'chain' Did you mean: 'is_option_chain'?
  at _rebalance
    if not self._option.chain:
           ^^^^^^^^^^^^^^^^^^
 in main.py: line 21

```

## futures_v01

Prompt: I just want to hold one S&P 500 e-mini futures contract and have the bot handle switching to the next contract when it expires. Last few months of 2024.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate has the right goal: an S&P 500 futures roll over Sep–Dec 2024. The implementation does not do what the user asked. No position is opened until 3 days before front-month expiry (L21). The 'next' contract is the earliest expiry, i.e. the same expiring contract (L25). The old position is never liquidated. The buy fires on every callback while the condition holds, so quantity is not capped at one contract (L28). The asset is also requested as "SP500", not the E-mini (ES) contract (L11).

[English code view](candidates_english/futures_v01.py) | [Original evaluated source](candidates/futures_v01.py) | [Judgment](scoring/together_9b_tuned/futures_v01.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the add_future method. Please checkout the API documentation. The expected signature is:
  add_future(ticker: str, resolution: Optional[Resolution] = None, market: str = None, fill_forward: Optional[bool] = None, leverage: float = 0, extended_market_hours: Optional[bool] = None, data_mapping_mode: Optional[DataMappingMode] = None, data_normalization_mode: Optional[DataNormalizationMode] = None, contract_depth_offset: int = 0)
Argument mismatch: argument 2 ('resolution') expected Optional[Resolution], got method.
  at initialize
    self._future = self.add_future("SP500", self._rebalance)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 11
 No method matches given arguments for add_future: (, ). The expected signature is:
  add_future(ticker: str, resolution: Optional[Resolution] = None, market: str = None, fill_forward: Optional[bool] = None, leverage: float = 0, extended_market_hours: Optional[bool] = None, data_mapping_mode: Optional[DataMappingMode] = None, data_normalization_mode: Optional[DataNormalizationMode] = None, contract_depth_offset: int = 0)
Argument mismatch: argument 2 ('resolution') expected Optional[Resolution], got method.
```

## futures_v02

Prompt: Add the E-mini S&P 500 continuous future. Whenever I have no position, buy one contract of the currently mapped month. When the continuous contract rolls to a new month, sell the old contract and buy the same number of the new one. Sept 1 to Dec 31 2024.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate has the correct asset (ES continuous future, lines 11-12) and date range (lines 8-9), but it does not implement the requested strategy. The request is to buy one contract of the mapped month when flat and roll that position on symbol changes. The candidate instead picks a contract by open interest from a nonexistent 'slice.future_mapping' result (lines 24-29). It sizes by set_holdings at 100% equity instead of one contract (line 32). Its long/short branch flips the position every bar: if not long it goes long, otherwise it goes short (lines 31-35). There is no on_symbol_changed_events or any rollover logic. The requested rules are buy-when-flat, one contract, and roll on mapping change, so the core behavior is a different strategy.

[English code view](candidates_english/futures_v02.py) | [Original evaluated source](candidates/futures_v02.py) | [Judgment](scoring/together_9b_tuned/futures_v02.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: 'FutureAlgorithm' object has no attribute '_rebalance'
  at initialize
    self._rebalance
 in main.py: line 13
 'FutureAlgorithm' object has no attribute '_rebalance'
```

## futures_v03

Prompt: Add the E-mini S&P 500 continuous future with last-trading-day mapping and backwards-ratio normalization, extended hours on. Whenever I have no position, buy one contract of the currently mapped month. When the continuous contract rolls to a new month, sell the old contract and buy the same number of the new one, and tag those orders 'Rollover' so I can find them in the log. Sept 1 to Dec 31 2024. Call the class EsRoll and comment the rollover handler.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate is in the right strategy family: an ES continuous future, buy when flat, and some form of roll handling. It sets the date range correctly and normalization is intended to be BACKWARDS_RATIO. Several explicit requirements are wrong or missing. The class is named EsRollAlgorithm instead of EsRoll. Last-trading-day mapping and extended market hours are never set. Sizing uses set_holdings(…, 1), which targets 100% of the portfolio rather than one contract. Entry orders the continuous symbol, not the currently mapped contract. Rollover is not driven by the continuous contract's symbol-change events; it is a daily check via a fabricated next-contract lookup. Only the liquidation carries the 'Rollover' tag, not the re-buy. The re-buy is not the same quantity as the old position. The rollover logic has no comment.

[English code view](candidates_english/futures_v03.py) | [Original evaluated source](candidates/futures_v03.py) | [Judgment](scoring/together_9b_tuned/futures_v03.json)

QC error:

```text
Algorithm.Initialize() Error: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): type object 'FuturesContract' has no attribute 'Indices'
  at EsRollAlgorithm
    _symbol: Symbol = Symbol.create("ES", Market.USA, FuturesContract.Indices.SP_500_E_MINI)
                                                      ^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 7
  at 
    class EsRollAlgorithm(QCAlgorithm):
 in main.py: line 5
 type object 'FuturesContract' has no attribute 'Indices' Stack Trace: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): type object 'FuturesContract' has no attribute 'Indices'
  at EsRollAlgorithm
    _symbol: Symbol = Symbol.create("ES", Market.USA, FuturesContract.Indices.SP_500_E_MINI)
                                                      ^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 7
  at 
    class EsRollAlgorithm(QCAlgorithm):
 in main.py: line 5
 type object 'FuturesContract' has no attribute 'Indices'
```

## futures_v04

Prompt: Long 1 ES continuous front month, roll on symbol change. Q4 2024.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested strategy. It never places an order, so there is no long 1-contract position. It subscribes to an SPX index and a CFE 'SPX' future rather than the CME E-mini S&P 500 (ES) continuous contract. Its roll logic uses nonexistent constructs (open_interest(...).next, remove_future of a continuous future) instead of reacting to symbol-changed events. The date range also starts in September rather than at the beginning of Q4.

[English code view](candidates_english/futures_v04.py) | [Original evaluated source](candidates/futures_v04.py) | [Judgment](scoring/together_9b_tuned/futures_v04.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the create method. Please checkout the API documentation. The expected signature is:
  create(ticker: str, security_type: SecurityType, market: str, alias: str = None, base_data_type: type = None)
Argument mismatch: argument 2 ('security_type') expected SecurityType, got str.
  at initialize
    self._future = self.add_future(self._index, Symbol.create("CFE", "SPX", Market.CFE))
                                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 12
 No method matches given arguments for create: (, , ). The expected signature is:
  create(ticker: str, security_type: SecurityType, market: str, alias: str = None, base_data_type: type = None)
Argument mismatch: argument 2 ('security_type') expected SecurityType, got str.
```

## futures_v05

Prompt: ES (SP_500_E_MINI) continuous: LAST_TRADING_DAY mapping, BACKWARDS_RATIO, depth 0, ext hours, filter 0-92d. Flat -> market order 1 of .mapped. on_symbol_changed_events: liquidate old, re-enter same qty on new. 2024-09-01 to 2024-12-31.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested strategy. It adds the SPX index and passes a nonexistent mapping-callback signature to add_future instead of adding the SP_500_E_MINI continuous future. None of the requested settings are present: LAST_TRADING_DAY mapping, BACKWARDS_RATIO normalization, depth 0, extended hours and the 0-92d filter are all missing. Entry is not 'when flat, market order 1 contract of .mapped'. Instead it runs a scheduled rebalance that sizes by portfolio weight, orders the continuous object rather than .mapped, and keeps adding orders even when invested. There is no on_symbol_changed_events rollover logic at all. Only the date range matches.

[English code view](candidates_english/futures_v05.py) | [Original evaluated source](candidates/futures_v05.py) | [Judgment](scoring/together_9b_tuned/futures_v05.json)

QC error:

```text
Algorithm.Initialize() Error: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'BaseIndex' is not defined
  at FutureOnETFMappingAlgorithm
    def _get_mapping_target(self, index: BaseIndex) -> Future:
                                         ^^^^^^^^^
 in main.py: line 19
  at 
    class FutureOnETFMappingAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'BaseIndex' is not defined Stack Trace: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'BaseIndex' is not defined
  at FutureOnETFMappingAlgorithm
    def _get_mapping_target(self, index: BaseIndex) -> Future:
                                         ^^^^^^^^^
 in main.py: line 19
  at 
    class FutureOnETFMappingAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'BaseIndex' is not defined
```

## futures_v06

Prompt: ES (SP_500_E_MINI) continuous: LAST_TRADING_DAY mapping, BACKWARDS_RATIO, contract_depth_offset 0, extended_market_hours, set_filter(0, 92), universe_settings.asynchronous True. on_data: if invested return; market_order(future.mapped, 1). on_symbol_changed_events: for each event, qty = portfolio[old].quantity, liquidate(old, tag=rollover tag), market_order(new, qty, same tag). 2024-09-01 to 2024-12-31. snake_case, no set_cash call, no indicators.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested strategy. It never subscribes to ES through Futures.Indices.SP_500_E_MINI and sets none of the requested continuous-contract settings (mapping mode, normalization mode, depth offset, extended hours, filter, asynchronous). It defines neither on_data nor on_symbol_changed_events. It places no orders at all, and its scheduled handler returns early when the portfolio is not invested, so no position is ever opened. It instead attempts an unrelated custom open-interest re-subscription scheme. Only the date range matches.

[English code view](candidates_english/futures_v06.py) | [Original evaluated source](candidates/futures_v06.py) | [Judgment](scoring/together_9b_tuned/futures_v06.json)

QC error:

```text
Algorithm.Initialize() Error: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'FuturesMapping' is not defined
  at FutureRollExampleAlgorithm
    def _roll(self, mapping: List[FuturesMapping]) -> Optional[Future]:
                                  ^^^^^^^^^^^^^^
 in main.py: line 16
  at 
    class FutureRollExampleAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'FuturesMapping' is not defined Stack Trace: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'FuturesMapping' is not defined
  at FutureRollExampleAlgorithm
    def _roll(self, mapping: List[FuturesMapping]) -> Optional[Future]:
                                  ^^^^^^^^^^^^^^
 in main.py: line 16
  at 
    class FutureRollExampleAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'FuturesMapping' is not defined
```

## futures_v07

Prompt: We need a baseline long exposure to the E-mini S&P 500 future for the September to December 2024 window, consistent with our internal implementation, with contract rolls handled automatically. Standard paper account.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate does try to hold a long position in a futures product over Sep 1 to Dec 31, 2024 (lines 8-9, 23-24). However, it misses two key elements. First, it requests "SPX"/"SP" (line 13) instead of the E-mini S&P 500 future (ES / Futures.Indices.SP_500_E_MINI). Second, it has no rollover handling: no on_symbol_changed_events logic, no data mapping mode configuration, and it orders the canonical continuous symbol (line 24) rather than the mapped contract. The filtering logic (lines 15-18) uses attributes that do not exist in the QuantConnect futures API and does not set up a meaningful contract chain. The wrong asset plus missing automatic rolls puts this in the right strategy family with several key elements wrong.

[English code view](candidates_english/futures_v07.py) | [Original evaluated source](candidates/futures_v07.py) | [Judgment](scoring/together_9b_tuned/futures_v07.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: Trying to dynamically access a method that does not exist throws a TypeError exception. To prevent the exception, ensure each parameter type matches those required by the add_future method. Please checkout the API documentation. The expected signature is:
  add_future(ticker: str, resolution: Optional[Resolution] = None, market: str = None, fill_forward: Optional[bool] = None, leverage: float = 0, extended_market_hours: Optional[bool] = None, data_mapping_mode: Optional[DataMappingMode] = None, data_normalization_mode: Optional[DataNormalizationMode] = None, contract_depth_offset: int = 0)
Argument mismatch: argument 2 ('resolution') expected Optional[Resolution], got str.
  at initialize
    self._spx = self.add_future("SPX", "SP")
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 13
 No method matches given arguments for add_future: (, ). The expected signature is:
  add_future(ticker: str, resolution: Optional[Resolution] = None, market: str = None, fill_forward: Optional[bool] = None, leverage: float = 0, extended_market_hours: Optional[bool] = None, data_mapping_mode: Optional[DataMappingMode] = None, data_normalization_mode: Optional[DataNormalizationMode] = None, contract_depth_offset: int = 0)
Argument mismatch: argument 2 ('resolution') expected Optional[Resolution], got str.
```

## futures_v08

Prompt: Implement the desk's continuous futures reference. Contract: E-mini S&P 500 (Futures.Indices.SP_500_E_MINI), continuous series with last-trading-day mapping and backwards-ratio normalization, depth offset 0, extended market hours, contract filter 0 to 92 days. Window: 2024-09-01 to 2024-12-31. Rules: when flat, market order one contract of the mapped contract. Rollover: on each symbol-changed event, liquidate the old contract and re-establish the same quantity in the new one.

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The request is a hold-one-contract continuous futures reference with explicit symbol-changed rollover. The candidate instead implements an EMA-crossover trend strategy. The asset, normalization mode, depth offset and date window are correct. However, mapping mode, extended market hours, the 0-92 day filter, the always-on one-contract entry and the rollover handler are all wrong or missing. It adds unrequested EMA exits and sizes by portfolio weight rather than one contract. This does not implement the requested strategy.

[English code view](candidates_english/futures_v08.py) | [Original evaluated source](candidates/futures_v08.py) | [Judgment](scoring/together_9b_tuned/futures_v08.json)

QC error:

```text
Algorithm.Initialize() Error: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'EmaCrossAlgorithm' is not defined
  at 
    class FutureAlgorithmQcbs(EmaCrossAlgorithm):
                              ^^^^^^^^^^^^^^^^^
 in main.py: line 5
 name 'EmaCrossAlgorithm' is not defined Stack Trace: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'EmaCrossAlgorithm' is not defined
  at 
    class FutureAlgorithmQcbs(EmaCrossAlgorithm):
                              ^^^^^^^^^^^^^^^^^
 in main.py: line 5
 name 'EmaCrossAlgorithm' is not defined
```

## futures_v09

Prompt: Implement the desk's continuous futures reference. Contract: E-mini S&P 500 (Futures.Indices.SP_500_E_MINI), continuous series with last-trading-day mapping and backwards-ratio normalization, depth offset 0, extended market hours, contract filter 0 to 92 days, asynchronous universe settings. Window: 2024-09-01 to 2024-12-31. Rules: when flat, market order one contract of the mapped contract. Rollover: in on_symbol_changed_events, for each event read the old contract's quantity, liquidate it with a rollover tag that names both symbols and the time, and market order the same quantity on the new contract with the same tag. Compliance: one contract maximum, all rollover orders tagged for audit, snake_case API per style guide, type annotations, docstring on the rollover handler.

QC: runtime_error. Claude fidelity: 2. Judge: judged. Behavior: unavailable.

The candidate stays in the right family: continuous E-mini S&P 500 futures, with a one-contract market order when flat. Several key elements are wrong or missing. The contract configuration ignores every requested setting: last-trading-day mapping, backwards-ratio normalization, depth offset 0, extended market hours, the 0-92 day filter and asynchronous universe settings. The rollover handler is the wrong method (on_symbol_changed rather than on_symbol_changed_events) and contains no rollover logic. It reads no old-contract quantity, never liquidates the old contract, never re-enters the new contract and builds no audit tag. Instead it re-adds a future on each change. The _trade helper also liquidates the position on every bar once invested, which creates exit behavior that was never requested. A set_holdings call in initialize adds an unrequested allocation. The docstring and tagging compliance requirements are not met.

[English code view](candidates_english/futures_v09.py) | [Original evaluated source](candidates/futures_v09.py) | [Judgment](scoring/together_9b_tuned/futures_v09.json)

QC error:

```text
Algorithm.Initialize() Error: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'SymbolChangedEventList' is not defined
  at FutureRollingAlgorithm
    def on_symbol_changed(self, changes: SymbolChangedEventList) -> None:
                                         ^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 24
  at 
    class FutureRollingAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'SymbolChangedEventList' is not defined Stack Trace: During the algorithm initialization, the following exception has occurred: Loader.TryCreatePythonAlgorithm(): Unable to import python module ./cache/algorithm/project/main.pyc. AlgorithmPythonWrapper(): name 'SymbolChangedEventList' is not defined
  at FutureRollingAlgorithm
    def on_symbol_changed(self, changes: SymbolChangedEventList) -> None:
                                         ^^^^^^^^^^^^^^^^^^^^^^
 in main.py: line 24
  at 
    class FutureRollingAlgorithm(QCAlgorithm):
 in main.py: line 5
 name 'SymbolChangedEventList' is not defined
```

## futures_v10

Prompt: QuantConnect Python, snake_case. initialize: set_start_date(2024, 9, 1), set_end_date(2024, 12, 31), universe_settings.asynchronous = True, _future = add_future(Futures.Indices.SP_500_E_MINI, extended_market_hours=True, data_mapping_mode=DataMappingMode.LAST_TRADING_DAY, data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO, contract_depth_offset=0), _future.set_filter(0, 92). on_data: if portfolio.invested return; market_order(_future.mapped, 1). on_symbol_changed_events(events): for symbol, ev in events.items(): old = self.symbol(ev.old_symbol); new = self.symbol(ev.new_symbol); qty = portfolio[old].quantity; tag = f'Rollover - {old.value} -> {new.value}'; liquidate(old, tag=tag); if qty: market_order(new, qty, tag=tag).

QC: runtime_error. Claude fidelity: 1. Judge: judged. Behavior: unavailable.

The candidate does not implement the requested strategy. Only the date range matches. Key gaps: the add_future call is missing every requested configuration; there is no set_filter(0, 92) and no asynchronous universe setting. No on_data entry ever places market_order(mapped, 1), so the algorithm never opens a position. There is no on_symbol_changed_events rollover handler. Instead, a scheduled routine (lines 15, 23-33) only liquidates and never re-enters with the same quantity on the new contract. The request is explicit and the template matches it, so there are no conflicts.

[English code view](candidates_english/futures_v10.py) | [Original evaluated source](candidates/futures_v10.py) | [Judgment](scoring/together_9b_tuned/futures_v10.json)

QC error:

```text
2024-09-01 00:00:00 During the algorithm initialization, the following exception has occurred: name 'Indices' is not defined
  at initialize
    self._future = self.add_future(Indices.SP_500_E_MINI, self._select_assets)
                                   ^^^^^^^
 in main.py: line 13
 name 'Indices' is not defined
```


## Reproduce from saved evidence

From the repository root, run these commands with the project's Python environment:

```sh
python src/eval_results/2026-11-14/together_9b_100/build_report.py
python src/eval_results/2026-11-14/together_9b_100/validate_report.py
```

These commands read saved evidence without cloud model or backtest calls. The
workbook is included. Its optional JavaScript builder uses the Codex bundled
`@oai/artifact-tool` runtime, with `ARTIFACT_NODE_MODULES` available as an override.

The runner is pinned to the evaluated Together alias and system prompt. It reuses
saved generations and exact-source QC/judge caches. Its shared QC submission gate
spaces backtest creation requests by at least 65 seconds and backs off on explicit
rate-limit responses. Each QC worker reuses its own evaluation project, so a fresh
full run creates at most three projects. Cloud reruns require private credentials
in the root `.env`.

Original rate-limit errors are kept in `qc_initial_evidence`. A few terminal cloud
responses contained null performance statistics. Their original client-error
records are kept in `qc_parser_originals`; terminal outcomes were recovered from
the raw cloud responses. The client now accepts missing statistics without
converting a completed execution into an infrastructure error.

One Claude response wrapped valid JSON in Markdown and appended commentary. The
JSON object was schema-validated without changing its score or evidence. Both the
original response and normalization record are preserved. No algorithm source was
repaired or regenerated during QC recovery.

The human-review fields in the workbook are blank. Judge flags are recorded
separately and do not represent completed human reviews.

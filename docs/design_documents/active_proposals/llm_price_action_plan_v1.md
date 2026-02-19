# LLM Price Action Analysis Tools: Design & Evolution Plan

**Version:** 1.0
**Date:** May 13, 2025
**Authors:** User & Gemini Assistant

## 1. Overview & Goals

This document outlines a plan for developing and evolving Python-based analysis tools (`scanner` project and new components) designed to be called by a Large Language Model (LLM). The primary goal is to enable an LLM to understand, interpret, and explain cryptocurrency price action to retail users in an accessible and insightful manner.

The system aims to support two main operational workflows:

1.  **Interactive "Click-and-Chat":** Users interact with a live chart and can request explanations of current price action. The LLM uses the tools to gather specific, contextual data for its response.
2.  **Background "Sentinel" Monitoring:** The tools run automated scans on a schedule, identify significant market events or conditions, and can trigger alerts or summaries.

A core principle is balancing analytical depth with token efficiency for LLM interactions and ensuring clarity for end-users. Deterministic pre-computation and smart data summarization are preferred over letting an LLM improvise all data gathering.

## 2. Core Architectural Components (Recap)

These tools will function within a broader architecture, envisioned as:

*   **UI Button / Scheduler:** Initiates the request.
*   **Chat Orchestrator (Python, FastAPI):** Manages the overall workflow.
*   **Context Builder:** Assembles the initial prompt for the LLM, including data from various sources (chart snapshots, user preferences, cached stats).
*   **LLM Tool Router (e.g., OpenAI Assistants API):** Allows the LLM to call specific Python tools to get more data or perform analysis.

The tools detailed in this plan will be exposed to the `LLM Tool Router`.

## 3. Proposed LLM Tools

### 3.1. `tool_analyze_chart_window`

*   **Purpose:** Provide a detailed, multi-faceted analysis of a *single symbol's price action within a specific chart window*. This is key for interactive explanations.
*   **Inputs (Example):**
    *   `symbol` (e.g., "BTC/USD")
    *   `timeframe` (e.g., "15m", "1h")
    *   `window_start_utc` (ISO timestamp)
    *   `window_end_utc` (ISO timestamp)
*   **Key Internal Modules/Logic:**
    *   `DataHandler`: Fetches OHLCV data for the specified window.
    *   `IndicatorCalculator`: Computes a standard suite of technical indicators (RSI, MAs, BBands, VWAP, Volume, ADX, ATR, Z-score, etc.) on the fetched data. Also calculates intra-dataset deltas (see 4.1).
    *   `PriceActionAnalyzer` (New Module): Identifies and describes key price action events within the window (see 4.3).
    *   `WindowSummarizer` (Logic): Calculates summary statistics for the entire window (Overall Open, High, Low, Close, Total Volume, Percentage Change, Max Drawdown within the window).
    *   `CurrentStateExtractor` (Logic): Extracts detailed information for the *most recent candle(s)* in the window (OHLCV, all indicator values, intra-dataset deltas).
*   **Output (Conceptual JSON Structure):**
    ```json
    {
      "request_params": {
        "symbol": "BTC/USD",
        "timeframe": "15m",
        "window_start_utc": "2025-05-12T00:00:00Z",
        "window_end_utc": "2025-05-13T08:00:00Z"
      },
      "visible_window_summary": {
        "open": 102500.00,
        "high": 105800.00,
        "low": 101500.00,
        "close": 104080.38,
        "volume_sum": 1234567.89,
        "price_change_percent": 1.54,
        "max_drawdown_percent": -2.5 // Max drop from a peak within window
      },
      "current_candle_state": { // Latest complete candle in the window
        "timestamp_utc": "2025-05-13T07:45:00Z",
        "open": 104000.00,
        "high": 104100.00,
        "low": 103950.00,
        "close": 104080.38,
        "volume": 56.78,
        "RSI_14": 58.5,
        "RSI_14_1p_chg": 2.1,  // Change from previous candle
        "RSI_14_5p_chg": 7.3,  // Change from 5 candles ago
        "BB_percent_B_20_2": 0.65,
        "VWAP_gap_percent": 0.05, // % diff from anchored VWAP
        "ADX_14": 22.1,
        // ... other relevant indicators and their recent changes
      },
      "key_events_in_window": [
        {
          "event_type": "swing_low",
          "timestamp_utc": "2025-05-12T03:00:00Z",
          "price": 101500.00,
          "description": "Significant low formed, followed by a rally."
        },
        {
          "event_type": "rsi_oversold_exit",
          "timestamp_utc": "2025-05-12T03:15:00Z",
          "indicator_value": {"RSI_14": 32.5},
          "description": "RSI crossed above 30."
        },
        {
          "event_type": "volume_spike",
          "timestamp_utc": "2025-05-12T09:00:00Z",
          "volume_value": 150.2, "volume_avg_20p": 45.1,
          "description": "Volume significantly above recent average."
        },
        {
          "event_type": "rejection_at_daily_resistance",
          "timestamp_utc": "2025-05-13T02:00:00Z",
          "price": 105600.00,
          "level_tested": {"price": 105800.00, "type": "daily_resistance"},
          "description": "Price approached daily resistance and stalled."
        }
        // ... more events
      ]
    }
    ```
*   **Primary Use Case:** Interactive chart explanation.

### 3.2. `tool_scanner_run`

*   **Purpose:** Scan multiple symbols (or a specific one) against pre-defined criteria to identify those meeting specific conditions *based on their latest data*.
*   **Inputs (Example):**
    *   `config_id` (Name of a scan configuration from `scan_config.yaml`, e.g., "Overbought_Extreme_V1")
    *   `target_symbol` (Optional, e.g., "ETH/USD")
    *   `target_timeframe` (Optional, e.g., "1h")
*   **Key Internal Modules/Logic:**
    *   Adapts the existing `main_workflow.py` from the `scanner` project.
    *   Uses `FileScanner` and `IndicatorCalculator` (including intra-dataset deltas).
    *   Evaluates scan conditions.
    *   Optionally calculates inter-scan deltas (see 4.2) if configured.
*   **Output (Conceptual JSON Structure):** A list of symbols that met scan criteria.
    ```json
    [
      {
        "scan_name": "Overbought_Extreme_V1",
        "symbol": "XYZ/USD",
        "timeframe": "1h",
        "current_candle_state": { // Similar to above, latest candle
          "timestamp_utc": "2025-05-13T08:00:00Z",
          "close": 150.75,
          "RSI_14": 79.2,
          "RSI_14_1p_chg": 1.5,
          // ...
        },
        "inter_scan_deltas": { // Optional, if enabled
          "delta_RSI_14": 10.5, // Change in RSI since last 1h scan run
          "delta_zscore": 0.8
        },
        "flags_met": 3
      }
      // ... other symbols passing the scan
    ]
    ```
*   **Primary Use Cases:** Sentinel alerts, generating broad market overviews, finding specific setups.

## 4. Key Data Concepts

### 4.1. Intra-Dataset Deltas

*   **Definition:** Changes in indicator values over a short number of preceding periods (candles) within the *same dataset/analysis window*.
    *   Example: `RSI_1p_chg` (RSI.diff(1)), `Volume_5p_chg_pct` (Volume.pct_change(5)).
*   **Purpose:** Quantify immediate momentum and rate of change for the current candle. Essential for live price action interpretation.
*   **Calculation:** Performed by `IndicatorCalculator` or as a post-processing step on its output DataFrame. Periods (e.g., 1, 3, 5 candles) should be configurable.

### 4.2. Inter-Scan Deltas

*   **Definition:** Change in the *latest* indicator value for a symbol/timeframe compared to the *latest* value from the *previous execution of a scan for that same timeframe*.
    *   Example: `delta_RSI` (latest RSI now vs. latest RSI from `results_last_1h.parquet`).
*   **Purpose:** Track significant changes between scheduled analysis runs (Sentinel context).
*   **Storage:** Results from each scan run (for a specific timeframe) are saved to a timeframe-specific file (e.g., `scan_snapshots/results_last_1h.parquet`).
*   **Optionality:** Their inclusion in LLM tool output should be configurable (e.g., default `false` for interactive to save tokens, `true` for Sentinel).

### 4.3. `key_events_in_window` (from `PriceActionAnalyzer`)

*   **Purpose:** Provide a concise, human-readable summary of significant occurrences within the analyzed window, acting as "story beats" for the LLM. This is a crucial compression technique.
*   **Examples:**
    *   Swing high/low formation.
    *   Oscillator (RSI, Stoch) crossing into/out of Overbought/Oversold.
    *   Significant volume spikes (e.g., > X * N-period average).
    *   Price rejection or breakout at key S/R levels (including higher-TF levels if context is provided).
    *   (Advanced) Divergences, MA crossovers, specific candlestick patterns at key locations.
*   **Importance:** Balances the need for detail with token efficiency. Requires careful design of event detection logic and descriptive output.

## 5. `ContextBuilder` Role (External Orchestration)

The `ContextBuilder` (part of the main application, not these tools) is responsible for:
1.  Receiving the initial user query or chart context.
2.  Deciding which tool to call (e.g., `tool_analyze_chart_window` for a specific chart view).
3.  Fetching/retrieving **cached higher-timeframe context** (e.g., Daily/Weekly Support/Resistance levels, major trend direction, pivot points for the current symbol).
4.  Fetching/retrieving **user preferences** or historical Q&A for the symbol (if any).
5.  Assembling the **final complete prompt for the LLM**, combining:
    *   The rich JSON output from `tool_analyze_chart_window` or `tool_scanner_run`.
    *   The higher-TF context.
    *   User-specific context.
    *   The actual user query.

## 6. Data Storage & Management

*   **Raw OHLCV Data:** Stored in `data/cache/` as CSV files (e.g., `exchange_symbol_timeframe.csv`). Managed by `DataHandler`.
*   **Inter-Scan Snapshots:** `scan_snapshots/results_last_{timeframe}.parquet`. Stores the latest indicator values (including intra-dataset deltas) for each symbol from a `tool_scanner_run` execution, per timeframe. Used for calculating inter-scan deltas.
*   **Higher-TF Context Cache:** Managed by the `ContextBuilder` or a dedicated caching service. Contains pre-calculated S/R levels, trend states from Daily/Weekly charts. Refreshed periodically.

## 7. Development Phases & Considerations

### Phase 1: Core Tool Implementation & Intra-Dataset Deltas
1.  **`IndicatorCalculator` Enhancement:** Add logic to calculate configurable intra-dataset deltas (e.g., `_1p_chg`, `_3p_chg`, `_5p_chg`) for key indicators.
2.  **`PriceActionAnalyzer` (New Module - V1):**
    *   Implement basic swing point detection (local highs/lows).
    *   Implement OB/OS threshold crossing detection for RSI/Stoch.
    *   Implement volume spike detection (e.g., volume > N * SMA(volume, M)).
3.  **`tool_analyze_chart_window` (New Tool):**
    *   Develop the main function orchestrating data fetching, indicator calculation, window summarization, current state extraction, and `PriceActionAnalyzer` event generation.
    *   Define and implement the target rich JSON output structure.
4.  **`tool_scanner_run` Adaptation:**
    *   Refactor existing `scanner/main_workflow.py` to function as this tool.
    *   Ensure it incorporates intra-dataset deltas in its analysis and output.
    *   Implement logic for optional inter-scan delta calculation and output.
    *   Define its JSON output structure.
5.  **Configuration:** Update `scan_config.yaml` for new options (intra-dataset delta params, inter-scan delta inclusion).
6.  **Snapshot Storage:** Implement saving/loading for `scan_snapshots/results_last_{timeframe}.parquet`.

### Phase 2: Integration & Basic LLM Testing
1.  **Tool Schemas:** Define OpenAPI-compatible JSON schemas for `tool_analyze_chart_window` and `tool_scanner_run` for use with LLM assistant APIs.
2.  **`ContextBuilder` Prototype:** Develop a basic version that can:
    *   Take mock chart context.
    *   Call the new tools.
    *   Fetch mock higher-TF data.
    *   Assemble a prompt.
3.  **Initial LLM Integration:** Test tool calling with an OpenAI Assistant or similar. Focus on simple "explain this chart window" queries.
4.  **Latency & Token Usage:** Begin preliminary measurements.

### Phase 3: Sentinel Workflow & Advanced Analysis
1.  **Sentinel Implementation:**
    *   Develop scheduler logic.
    *   Use `tool_scanner_run` to monitor watchlists against various `config_id`s.
    *   Implement basic alerting mechanism if anomalies + significant inter-scan deltas are found.
2.  **`PriceActionAnalyzer` (V2):**
    *   Add divergence detection (e.g., price vs. RSI).
    *   Add key Moving Average crossover detection.
    *   Explore basic candlestick pattern recognition (e.g., pin bars, engulfing) at identified swing points or S/R levels.

### Testing & Validation Strategy
*   **Effectiveness of Summaries:** A critical aspect is validating whether the summarized context (especially `key_events_in_window`) allows the LLM to generate accurate, insightful, and human-like explanations of price action.
    *   **Method:** Prepare a set of diverse chart scenarios (screenshots or defined data windows).
    *   Generate the JSON context using `tool_analyze_chart_window`.
    *   Feed this context + a query ("Explain this price action") to the LLM.
    *   Compare the LLM's explanation against:
        1.  A human expert's explanation of the same chart.
        2.  (If feasible for small tests) An LLM explanation given more raw/verbose data.
    *   Iteratively refine the `PriceActionAnalyzer` and JSON structure based on these tests.
*   **Tool Accuracy:** Ensure indicators, deltas, and events are calculated correctly.
*   **Performance:** Continuously monitor latency of tool execution and token cost of generated JSON.

## 8. Future Considerations
*   Integration of news sentiment.
*   Code-assist features for users to define new scans/indicators via natural language (potentially involving a secondary "Coder" assistant).
*   More sophisticated machine learning models for pattern recognition or anomaly detection, if summaries prove insufficient for certain complex scenarios.

This plan provides a structured approach to developing a powerful suite of tools for LLM-driven financial analysis. The emphasis on iterative development, testing the efficacy of data summarization, and maintaining a balance between depth and efficiency will be key to success. 
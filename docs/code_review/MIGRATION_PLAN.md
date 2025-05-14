# Trade Suite v2: Frontend Migration Plan (Python Backend + JS Frontend)

## 1. Goal

Migrate the Trade Suite v2 application from its current Python/DearPyGui monolithic structure to a modern architecture featuring:

*   **Python Backend:** Reusing the existing, well-structured backend logic for data fetching, processing, task management, and exchange interaction. Exposing functionality via versioned APIs.
*   **JavaScript Frontend:** Building a new, modern web-based user interface using a standard JS framework to achieve a sophisticated, performant, and maintainable UI, targeting a visual appearance similar to the provided dashboard reference image.

This addresses limitations of the current UI framework while leveraging the robust backend components.

## 2. Architecture Overview

*   **Backend (Python):**
    *   Core Logic: Utilize existing modules (`DataSource`, `CCXTInterface`, `TaskManager`, `SECDataFetcher`, etc.).
    *   API Layer: Implement using **FastAPI**.
        *   **WebSockets:** For real-time data push (trades, order book updates, candle updates, custom signals). Consider **binary encoding (e.g., MsgPack, Protobuf) + compression** for high-frequency channels (L2).
        *   **REST APIs:** For request/response interactions (historical data, settings, user actions, initial state loading).
    *   API Contract: Define explicit, **versioned** request/response schemas using **Pydantic V2**.
*   **Frontend (JavaScript):**
    *   Framework Choice: **Evaluate React+Vite vs. Vue 3+Vite vs. SvelteKit**. Next.js is an option if SSR is explicitly needed for parts of the application (e.g., landing pages), but the core trading dashboard should likely be client-side rendered (CSR).
    *   Styling: **Tailwind CSS** (primary), potentially integrating others like Stitches based on component needs.
    *   Charting: **TradingView Lightweight Charts** (evaluate custom indicator needs) or alternatives.
    *   State Management: Framework-specific solutions (Context, Pinia, Svelte Stores) potentially combined with TanStack Query or similar for server state.
    *   Layout: Implement a flexible **docking/tiling layout system** (e.g., Dockview, Golden Layout).
*   **Communication:** WebSocket for real-time data (potentially binary encoded), REST for commands/initial loads.

## 3. Target Frontend Tech Stack Considerations

While the reference image uses React/Next.js, evaluate based on project needs:

*   **React (+Vite or Next.js):** Largest ecosystem/talent pool. Vite for lean CSR, Next.js if SSR is needed elsewhere.
*   **Vue 3 (+Vite):** Potentially gentler learning curve, excellent reactivity, good performance.
*   **SvelteKit:** Simplest model, best performance/bundle size, good Tauri integration for potential desktop app.
*   **Common Elements:** Tailwind CSS, Charting Library (TradingView), Docking Layout Library, State Management Library, Testing tools.

## 4. Key Backend Components for Reuse (Confirmation)

*   `trade_suite.data.ccxt_interface.CCXTInterface`
*   `trade_suite.data.data_source.DataSource` (API adaptation needed)
*   `trade_suite.data.candle_factory.CandleFactory`
*   `trade_suite.gui.task_manager.TaskManager` (API adaptation needed)
*   `trade_suite.gui.signals.SignalEmitter` (Adapt for WS push)
*   `trade_suite.data.sec_api.SECDataFetcher` & sub-modules
*   `trade_suite.analysis.orderbook_processor.OrderBookProcessor`
*   `trade_suite.config.ConfigManager` (Adapt for backend context)

## 5. Critical Considerations & Areas for Meticulous Focus

*   **API Contract Definition:**
    *   **Paramount:** Define *all* WebSocket message schemas (including **subscription/unsubscription formats**) and REST endpoint schemas using Pydantic V2 **before** significant frontend work.
    *   **Versioning:** Use explicit API versioning (`/api/v1/`, `/ws/v1/`).
    *   **Naming & Types:** Ensure clarity on data types, optionality, and naming conventions (camelCase for JSON).
    *   **Type Generation:** Use tools (`datamodel-code-generator`, `openapi-typescript`) to generate TS types from Python schemas (single source of truth).
*   **WebSocket Performance & Reliability:**
    *   **Encoding:** Strongly consider **binary formats (MsgPack/Protobuf) + compression (gzip)** for high-frequency data (e.g., L2 book updates > 5-10Hz, >~1-2kB/s). Define a **messaging SLA/budget** per channel type.
    *   **State Synchronization:** Design and **document** robust reconnection logic: sequence numbers, heartbeats, snapshot requests (`resume_token` if possible).
    *   **Subscription Management:** Backend needs clear logic to manage client subscriptions per WebSocket connection.
*   **Real-time Data Flow:** Adapt `SignalEmitter`/`TaskManager` to efficiently route/batch/throttle data to subscribed WebSocket clients.
*   **Initial State Loading:** Define REST endpoints for widgets to fetch initial data before WS subscription.
*   **Widget Linking & Shared State:** Use frontend state management (Context, Zustand, Pinia, etc.) for cross-widget communication (e.g., symbol selection).
*   **UI Component Selection:** Evaluate and prototype early:
    *   **Docking/Layout:** Crucial for UX (Golden Layout, Dockview, etc.).
    *   **Charting:** Verify TradingView Lightweight Charts limitations (esp. custom indicators) or evaluate alternatives (Full TV library, Plotly, ECharts).
    *   **Data Grids:** AG Grid, TanStack Table, etc.
*   **Testing Strategy:**
    *   **Backend:** Include load/replay testing for WebSocket endpoints.
    *   **Frontend:** Include performance testing (Lighthouse/Web Vitals) in CI for key metrics (e.g., "Time to First Candle").
    *   Unit/Integration/Component tests for both backend and frontend.
*   **Authentication/Authorization:** Define strategy (e.g., JWT) if needed.
*   **Desktop Viability:** Consider **Tauri/Electron** compatibility early if a native desktop app is a potential future goal.

## 6. Proposed Migration Roadmap (Incremental)

1.  **Iteration 0 - Setup & Scaffolding:**
    *   Set up monorepo (`pnpm workspace` or `nx`).
    *   Scaffold **chosen** JS framework project (Vite recommended) with TypeScript, Tailwind CSS, ESLint/Prettier.
    *   Set up basic FastAPI backend with Pydantic V2.
    *   Implement backend `/ws/v1/echo` endpoint and connect from frontend.
    *   Configure dev server proxy for backend communication.
2.  **Iteration 1 - Chart MVP:**
    *   **Define API (Pydantic/OpenAPI):** Schemas for `CandleUpdate` (WS), initial candle history (REST), basic WS subscription messages. Generate TS types.
    *   **Implement Backend:** Adapt backend (`DataSource`, etc.) to serve historical candles via REST and push live `CandleUpdate` messages via WS (JSON initially acceptable).
    *   **Implement Frontend:** Create **mock provider** for candle data. Implement basic TradingView Lightweight Chart component displaying mock data, then switch to live WS data.
3.  **Iteration 2 - Modular Widgets & Layout:**
    *   Implement/Integrate chosen **docking/tiling layout manager**.
    *   Refactor chart into a reusable component.
    *   Define API for `OrderBookUpdate` / `Trade` (consider binary encoding early here).
    *   Create basic Order Book and Trade Tape components (using mock providers first).
    *   Implement basic symbol selection UI -> state management -> component updates.
4.  **Iteration 3 - Settings & Persistence:**
    *   Implement frontend state management for user preferences/layout.
    *   Persist to `localStorage` or backend REST endpoint.
    *   Ensure state restoration on reload.
5.  **Iteration 4 - Authentication (If Needed):**
    *   Implement backend JWT auth. Secure endpoints/WS. Implement frontend login UI.
6.  **Iteration 5+ - Feature Parity & Refinement:**
    *   Systematically port remaining essential MVP widgets. Define/implement APIs for each.
    *   Refactor WS communication to use binary encoding + compression for high-frequency channels identified in the budget/SLA.
    *   Implement robust error handling and state synchronization logic.
    *   Use Storybook/Component Tests.

## 7. MVP Widget Scope Definition (To Be Finalized)

Essential widgets for initial migration (Confirm/Prioritize):

*   **Quote Monitor / Watchlist**
*   **Chart** (Candles, Volume, Basic Indicators, Symbol/TF selection)
*   **Options Chain**
*   **News Feed**
*   **Trade Tape (Time & Sales)**
*   **Order Book (Depth)**

## 8. Next Immediate Steps (Decision Points)

1.  **Finalize Frontend Framework Choice:** (React+Vite / Vue 3+Vite / SvelteKit) - Consider SSR needs, team familiarity, ecosystem.
2.  **Define & Prioritize MVP Widgets:** Confirm the list in Section 7.
3.  **Define Performance Target:** (e.g., "X symbols, Y widgets each, on hardware Z"). This informs encoding choices.
4.  **Define API Schemas (Iteration 1):** Detail Pydantic/OpenAPI schemas for `CandleUpdate` (WS), initial history (REST), and subscription messages.
5.  **Execute Iteration 0:** Set up projects based on framework choice. 
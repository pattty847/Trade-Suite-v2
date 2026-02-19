## Prompt for Codex: Documentation Reorganization and README Slimming for TradeSuite Project

**Objective:**

Reorganize the documentation within the `/docs` directory of the TradeSuite project and slim down the root `README.md` file. The goal is to create a more intuitive, maintainable, and user-friendly documentation structure. All changes should be made in a way that can be easily reviewed as a diff for a pull request.

**Current Situation:**

*   The `/docs` directory currently contains a mix of planning documents, code reviews, notes, changelogs, and feature documentation, some of which are outdated or haphazardly placed.
*   The root `README.md` is comprehensive but overly detailed in some sections, making it lengthy. Some of its content would be better suited for dedicated pages within the new `docs` structure.

**Files to Analyze for Content Relocation, Summarization, and Reorganization:**

Please analyze the content of the following files to understand what they contain and how they should be moved, restructured, or used to create new documentation pages:

*   `README.md` (root of the project)
*   `docs/partial_code_review.md`
*   `docs/ALERTBOTMANAGER.md`
*   `docs/TODO.md` (Consider if parts are still relevant, could be archived or integrated into planning docs if active)
*   `docs/REFACTOR.md` (Likely a design document or notes for an implemented design)
*   `docs/ARCHITECTURE.md`
*   `docs/DOCKABLE_WIDGETS.md`
*   `docs/SEC_API_METHOD_DOCS.md`
*   `docs/data_source_refactor/partial_review_notes.md`
*   `docs/data_source_refactor/data_source.md`
*   `docs/plans/trade_suite_core_improvement.md`
*   `docs/plans/alert_bot_ts_merge.md`
*   `docs/plans/llm_price_action_plan_v1.md`
*   `docs/plans/price_alert_feature.md`
*   `docs/code_review/CODE_REVIEW_CHART_CANDLEFACTORY.md`
*   `docs/code_review/MIGRATION_PLAN.md`
*   `docs/code_review/CODE_REVIEW.md`
*   `docs/code_review/CODE_OPTIMIZATION_FULL.md`
*   `docs/changelog/data-source-fetch-candles-improvement_5-11-2025.md`
*   `docs/changelog/dynamic-widget-layout-persistence_4-21-2025.md`
*   `docs/changelog/ccxt-initialization-refactoring_5-11-2025.md`

**Proposed New `/docs` Directory Structure:**

Please create and populate the following directory structure within `/docs`. Move existing content from the files listed above into this new structure, creating new markdown files as needed. Rename files where appropriate (e.g., `ALERTBOTMANAGER.md` to `sentinel_alert_bot.md`).

```
docs/
├── README.md  (A new, concise overview of the documentation, linking to sub-sections)
├── user_guide/
│   ├── getting_started.md (Expand from current README sections: "Getting Started", "Installation", "Environment Setup", "Running the Application")
│   ├── features/
│   │   ├── candlestick_charts.md
│   │   ├── order_book.md
│   │   ├── price_level_dom.md
│   │   └── sentinel_alert_bot.md (Incorporate content from `docs/ALERTBOTMANAGER.md` and the Sentinel Alert Bot section in the main `README.md`. Link to `sentinel/alert_bot/README.md` for deeper details if appropriate.)
│   └── faq.md (Create as a new, empty file or populate if obvious FAQs emerge from existing docs)
├── developer_guide/
│   ├── architecture.md (Use existing `docs/ARCHITECTURE.md`)
│   ├── sec_api_method_docs.md (Use existing `docs/SEC_API_METHOD_DOCS.md`)
│   ├── data_flow.md (Create new, or integrate into architecture.md if content exists in `docs/REFACTOR.md` or `docs/data_source_refactor/data_source.md`)
│   ├── contributing.md (Create new, or if a `CONTRIBUTING.md` exists at root, move it here)
│   ├── style_guide.md (Create as new, empty file)
│   └── testing.md (Create as new, empty file)
├── design_documents/
│   ├── active_proposals/
│   │   └── (Move relevant files from `docs/plans/`, e.g., `llm_price_action_plan_v1.md`, `price_alert_feature.md`)
│   ├── implemented_designs/
│   │   ├── data_source_refactor.md (Consolidate content from `docs/data_source_refactor/data_source.md` and potentially `docs/REFACTOR.md`)
│   │   ├── dockable_widgets.md (Use existing `docs/DOCKABLE_WIDGETS.md`)
│   │   └── (Move other relevant completed plan files from `docs/plans/` here e.g. `trade_suite_core_improvement.md`, `alert_bot_ts_merge.md`)
├── code_reviews/
│   └── (Move existing files from `docs/code_review/` here)
├── changelogs/
│   ├── main_changelog.md (Create a new, consolidated, user-facing changelog. Summarize content from files in `docs/changelog/`. Follow "Keep a Changelog" format if possible.)
│   └── feature_specific_changelogs/ (Optional: if files in `docs/changelog/` are very detailed and feature-specific, they can be moved here and linked from `main_changelog.md`)
├── archive/
│   └── (Move outdated or very specific notes like `docs/partial_code_review.md`, `docs/data_source_refactor/partial_review_notes.md`, and potentially parts of `docs/TODO.md` here.)
└── adr/ (Architectural Decision Records)
    └── (Create this directory. No files to create initially unless obvious decisions are documented elsewhere.)
```

**Tasks for `README.md` (Root Project File):**

1.  **Summarize and Relocate Detailed Sections:**
    *   **"Features":** Keep a high-level bullet list. Move detailed descriptions to `docs/user_guide/features/`.
    *   **"Implemented Features":** Summarize key achievements. Detailed explanations of specific implemented features can reside in `docs/design_documents/implemented_designs/` or `docs/developer_guide/architecture.md`.
    *   **"Sentinel Alert Bot":** Provide a brief overview and link to `docs/user_guide/features/sentinel_alert_bot.md` and `sentinel/alert_bot/README.md`.
    *   **"Getting Started" (Prerequisites, Installation, Environment Setup, Running the Application):** Move the detailed steps to `docs/user_guide/getting_started.md`. Keep a very brief "How to Run" in the README if desired, linking to the full guide.
    *   **"For Developers" (Packaging Application):** Move this content to a new file, e.g., `docs/developer_guide/packaging.md`. The architecture image currently in this section should ideally be in or linked from `docs/developer_guide/architecture.md`.

2.  **Update Table of Contents:** Ensure the Table of Contents reflects the new, slimmer `README.md` structure and links correctly.

3.  **Add Links:** Where content is moved, ensure the `README.md` links to the new location in the `/docs` directory.

**General Instructions for Codex:**

*   Prioritize clarity and organization.
*   If a document contains multiple topics, consider splitting it appropriately into the new structure.
*   If content seems redundant, try to consolidate it into a single source of truth and link to it.
*   For files moved to `archive/`, ensure they are genuinely outdated or superseded. If unsure, it's better to keep them in a more active section initially.
*   All file operations (create, move, delete, modify) should be clearly attributable to this reorganization task.
*   The output should enable the user to easily generate a diff of all changes for a pull request.

**Example of how to handle a file:**
*   The content of `docs/ALERTBOTMANAGER.md` should be reviewed. Its primary content should form `docs/user_guide/features/sentinel_alert_bot.md`. Any highly technical design aspects might be moved to `docs/design_documents/implemented_designs/` if a specific design document for the bot integration exists or is created from files like `docs/plans/alert_bot_ts_merge.md`.

Please proceed with this reorganization.
```

# HTMX Frontend Implementation Plan

This document outlines the architecture and step-by-step plan for building a new HTMX-based frontend for the TradingAgents project.

## 1. General Architecture

The frontend will be a single-page web application served by a lightweight Python backend (FastAPI). This backend will be responsible for serving the HTML, handling user requests to start the agent process, and providing real-time status updates. The frontend and backend code will be housed in a new top-level `webapp` directory to keep it separate from the core agent logic.

### Core Components:

*   **FastAPI Backend:** A Python web server that will:
    *   Serve the main `index.html` file.
    *   Provide API endpoints for the frontend to interact with.
    *   Run the `TradingAgentsGraph` in a background thread.
    *   Maintain and serve the state of the execution process.
*   **HTMX Frontend:** The user interface, which will:
    *   Display the configuration form and start button.
    *   Show a hierarchical view of the agent execution process.
    *   Poll the backend for status updates.
    *   Display the content of selected process steps (reports, messages, errors) on the right side of the screen.
*   **Communication:** The frontend will communicate with the backend using a simple polling mechanism. The HTMX frontend will periodically request a status update from a `/status` endpoint. The backend will return a JSON object representing the current state of the execution tree. For displaying detailed content, the frontend will make specific requests to a `/content/{item_id}` endpoint.

## 2. Proposed Project Structure

To maintain separation of concerns, the new frontend code will live in a `webapp` directory.

```
C:\Users\kevin\repo\TradingAgents\
├───... (existing project files)
└───webapp/
    ├───main.py             # FastAPI application
    ├───static/
    │   └───styles.css      # CSS for styling
    └───templates/
        ├───index.html      # Main HTML file
        └───_partials/
            ├───left_panel.html   # HTMX partial for the execution tree
            └───right_panel.html  # HTMX partial for the content view
```

## 3. Backend Implementation (FastAPI)

The `webapp/main.py` file will define the FastAPI application and its endpoints.

### API Endpoints:

*   **`GET /`**: Serves the main `templates/index.html` page.
*   **`POST /start`**:
    *   Accepts a JSON payload with the run configuration (`company_symbol`, etc.).
    *   Initializes the `TradingAgentsGraph`.
    *   Starts the `graph.propagate()` method in a background thread.
    *   Returns an initial response that replaces the config form with the main progress bar.
*   **`GET /status`**:
    *   This is the main polling endpoint for HTMX.
    *   It will return an HTML partial (`_partials/left_panel.html`) rendered with the current state of the execution tree. The state will be stored in memory.
*   **`GET /content/{item_id}`**:
    *   When a user clicks an item in the left panel, HTMX will call this endpoint.
    *   It will retrieve the specific content for that `item_id` from the in-memory state.
    *   It will return an HTML partial (`_partials/right_panel.html`) with the formatted content (e.g., a formatted report, a code block for a message, or a stack trace for an error).

### State Management & Integration:

To get real-time updates from the `TradingAgentsGraph`, we will need to instrument its execution. The plan is to modify the `TradingAgentsGraph` class slightly to accept a callback function.

1.  **Modify `TradingAgentsGraph.__init__`**: Add an optional `on_step_end` callback parameter.
2.  **Callback Execution**: Inside the graph's execution logic (after each agent or tool runs), this callback will be invoked with the details of the completed step (e.g., node name, output, status).
3.  **Update Global State**: The callback function, defined in `webapp/main.py`, will update a global in-memory dictionary that represents the hierarchical execution tree. This tree will store the status, content, and relationships of all steps.

This approach avoids tight coupling and allows the web application to listen to the progress of the core agent logic.

## 4. Frontend Implementation (HTMX)

The frontend will be built using HTMX attributes directly in the HTML templates.

*   **`templates/index.html`**:
    *   Contains the basic page structure: a top bar for the overall progress, a left panel for the execution tree, and a right panel for content.
    *   Includes the HTMX library.
    *   Contains the initial configuration form. The form will have an `hx-post="/start"` attribute to trigger the process.

*   **Left Panel (`_partials/left_panel.html`)**:
    *   This partial will be the target of the status polling. The main container will have `hx-get="/status"` and `hx-trigger="load, every 5s"`.
    *   It will use a template loop (Jinja2) to render the hierarchical tree from the state object provided by the backend.
    *   Each item in the tree will be a clickable element with an `hx-get="/content/{item_id}"` attribute and an `hx-target="#right-panel"` attribute to load its content on the right side.
    *   The status of each item (pending, in-progress, completed, error) will be reflected using different CSS classes and icons:
        - **Pending**: ⏸️ (paused icon, gray color)
        - **In Progress**: ⏳ (hourglass icon, blue color)
        - **Completed**: ✅ (check mark, green color)
        - **Error**: ❌ (X mark, red color)

*   **Right Panel (`_partials/right_panel.html`)**:
    *   A simple container (`<div id="right-panel">`) that gets its content replaced by HTMX when a user clicks an item on the left.
    *   Content will be pre-formatted by the backend (e.g., using Markdown-to-HTML conversion or syntax highlighting for code/errors).

*   **Progress Bar**:
    *   The response from the initial `POST /start` call will replace the configuration form with a global progress bar.
    *   This progress bar's value will be updated as part of the `/status` polling response, by targeting its element ID with an `hx-swap-oob="true"` (Out of Band swap).

### Execution Tree Structure

The left panel should display a hierarchical tree structure as follows:

```
📈 Trading Analysis for [SYMBOL]
├── 📊 Data Collection Phase
│   ├── 📈 Market Analyst
│   │   ├── 📄 Market Analysis Report
│   │   └── 💬 Agent Messages
│   ├── 📱 Social Media Analyst
│   │   ├── 📄 Sentiment Analysis Report  
│   │   └── 💬 Agent Messages
│   ├── 📰 News Analyst
│   │   ├── 📄 News Analysis Report
│   │   └── 💬 Agent Messages
│   └── 📊 Fundamentals Analyst
│       ├── 📄 Fundamentals Report
│       └── 💬 Agent Messages
├── 🔍 Research Phase
│   ├── 🐂 Bull Researcher
│   │   ├── 📄 Bull Case Analysis
│   │   └── 💬 Agent Messages
│   ├── 🐻 Bear Researcher
│   │   ├── 📄 Bear Case Analysis
│   │   └── 💬 Agent Messages
│   └── 🔍 Research Manager
│       ├── 📄 Research Synthesis
│       └── 💬 Agent Messages
├── 📋 Planning Phase
│   └── 📋 Trade Planner
│       ├── 📄 Trading Plan
│       └── 💬 Agent Messages
├── ⚡ Execution Phase
│   └── ⚡ Trader
│       ├── 📄 Execution Report
│       └── 💬 Agent Messages
└── ⚠️ Risk Management Phase
    ├── 🚨 Aggressive Risk Analyst
    │   ├── 📄 Risk Assessment (Aggressive)
    │   └── 💬 Agent Messages
    ├── ⚖️ Neutral Risk Analyst
    │   ├── 📄 Risk Assessment (Neutral)
    │   └── 💬 Agent Messages
    ├── 🛡️ Conservative Risk Analyst
    │   ├── 📄 Risk Assessment (Conservative)
    │   └── 💬 Agent Messages
    └── ⚠️ Risk Judge
        ├── 📄 Final Risk Decision
        └── 💬 Agent Messages
```

Each agent should have:
1. **Status Icon**: Shows current execution state (pending, in-progress, completed, error)
2. **Report Sub-item**: Shows the specific report generated by that agent
3. **Messages Sub-item**: Shows messages to/from that agent during execution

The tree structure should be initialized at the start showing all agents in "pending" state, then update their status as execution progresses.

## 5. Detailed Implementation Steps

1.  **Setup Environment**:
    *   Create the `webapp` directory and the file structure outlined above.
    *   Add `fastapi`, `uvicorn`, and `python-multipart` to the `requirements.txt` file and install them.

2.  **Backend - Basic Server**:
    *   Create the initial FastAPI app in `webapp/main.py`.
    *   Implement the `GET /` endpoint to serve `templates/index.html`.
    *   Create a basic `index.html` with the two-panel layout.

3.  **Backend - State & Integration**:
    *   Define the Python data classes for the execution state (e.g., `ProcessStep`, `RunState`).
    *   Modify `tradingagents/graph/trading_graph.py` to include the `on_step_end` callback mechanism.
    *   In `webapp/main.py`, implement the callback function that builds the hierarchical state tree in memory.

4.  **Backend - Endpoints**:
    *   Implement the `/start` endpoint to receive configuration and launch the `propagate` method in a background thread, passing the callback function.
    *   Implement the `/status` endpoint to render and return the `_partials/left_panel.html` partial.
    *   Implement the `/content/{item_id}` endpoint to render and return the `_partials/right_panel.html` partial.

5.  **Frontend - HTMX**:
    *   Develop the configuration form in `index.html` with `hx-post` to start the process.
    *   Create the `_partials/left_panel.html` template with the Jinja2 loop and the `hx-get` attributes for clicking on items.
    *   Add the polling mechanism to the main container in `index.html`.
    *   Style the different states (pending, completed, error) using CSS in `static/styles.css`.

6.  **Error Handling**:
    *   When the callback receives an error, it will update the corresponding item's status to "error" and store the stack trace.
    *   The frontend will visually flag the item as an error.
    *   When clicked, the `/content/{item_id}` endpoint will return the formatted stack trace to be displayed in the right panel.

7.  **Refinement**:
    *   Add a loading indicator for HTMX requests.
    *   Refine the CSS to ensure the application is visually appealing and user-friendly.
    *   Ensure the background process is managed correctly, especially in case of errors or server shutdown.

## 6. Current Implementation Issues & Solutions

### Issues Identified:

1. **Incomplete Agent Tree Structure**: The current implementation only shows a single top-level item "Trading Analysis for [SYMBOL]" with limited sub-items, instead of the full agent hierarchy.

2. **Improper Status Tracking**: Agents don't show proper execution status (pending, in-progress, completed, error) with appropriate icons.

3. **Missing Reports and Messages**: Sub-items for individual agent reports and messages are not being created or displayed.

4. **Callback State Detection**: The `update_execution_state` callback in `webapp/main.py` is not properly detecting and organizing the execution flow of all agents.

### Solutions Implemented:

#### Backend Changes (`webapp/main.py`):

1. **Initialize Complete Tree Structure**: Pre-populate the execution tree with all agents in "pending" state at the start of execution.

2. **Improved State Detection**: Enhanced the callback function to:
   - Detect agent execution start/completion more reliably
   - Track both agent status and their generated reports/messages
   - Maintain proper phase organization (Data Collection, Research, Planning, Execution, Risk Management)

3. **Agent Sub-items**: Each agent now has sub-items for:
   - **Report**: The specific analysis/report generated by the agent
   - **Messages**: Communication to/from the agent during execution

#### Frontend Changes (`_partials/left_panel.html`):

1. **Enhanced Status Icons**: Clear visual indicators for each execution state
2. **Hierarchical Display**: Proper nesting of phases, agents, and their sub-items
3. **Clickable Content**: All items are clickable to show detailed content in the right panel

#### State Management:

The execution tree now properly reflects:
- **Phases**: Logical grouping of related agents (Data Collection, Research, etc.)
- **Agents**: Individual agents with their execution status
- **Sub-items**: Reports and messages for each agent
- **Real-time Updates**: Status changes as execution progresses

This provides users with complete visibility into the trading analysis process, allowing them to track which agents are running, completed, or encountering issues, and access detailed reports and communications from each agent.

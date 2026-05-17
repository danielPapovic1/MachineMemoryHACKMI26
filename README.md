# Machine Memory

Machine Memory helps manufacturing teams prevent unplanned downtime by turning messy maintenance records into a normalized, centralized machine intelligence layer.

It is built for legacy manufacturing environments, especially small and mid-sized Michigan manufacturers that rely on critical equipment, CSV exports, technician notes, and years of disconnected maintenance history. Machine Memory does not require replacing existing machines or technician workflows. It modernizes faster by making the data teams already have easier to trust, search, score, and act on.

**Mission:** Modernize existing operations without replacing equipment. 

## The Problem

Manufacturing downtime is expensive, and many plants still depend on legacy equipment that cannot easily be replaced. The knowledge needed to keep those machines running is often scattered across:

- CSV exports from older systems
- maintenance logs and work orders
- technician notes
- downtime records
- machine lists and factory maps
- informal memory from experienced operators

When that information stays disconnected, teams lose time finding past fixes, repeat the same troubleshooting steps, and miss early signals that a machine is becoming risky.

## The Solution

Machine Memory turns maintenance history into structured machine memory.

The system ingests messy CSV maintenance exports, normalizes records into a consistent format, matches them to known factory machines, and builds a clear operational view for each asset. It then calculates deterministic risk signals, surfaces similar past fixes, and can generate AI-enhanced maintenance reviews grounded in the uploaded history.

The result is a practical maintenance intelligence dashboard that helps teams answer:

- What machines have meaningful maintenance history?
- Which machines are showing risk signals?
- What similar issues happened before?
- What fixes were attempted?
- What downtime exposure is visible from the records?
- What should a technician or supervisor review next?

## Demo Flow

```txt
Upload CSV
-> Normalize maintenance records
-> Match machines to factory map
-> Calculate selected machine risk
-> Show signals, similar past fixes, and AI analysis
```

In the app this appears as:

```txt
Ingest Logs -> Map Machines -> Score Risk -> Machine Profile -> Maintenance Memory -> Live Signals
```

## What Is Real In The Demo

- CSV upload for maintenance-history data
- messy column normalization
- machine ID matching against a known machine registry
- accumulated maintenance history stored locally
- dashboard metrics from maintenance logs
- factory map with machine status context
- selected-machine risk signals
- similar historical maintenance events
- recent logs and alerts
- AI machine snapshot analysis
- deeper AI maintenance review using structured machine history

## AI Role

AI is layered on top of deterministic backend evidence. It helps explain patterns, summarize messy technician notes, and turn prior fixes into practical maintenance recommendations.

Machine Memory does not pretend to perfectly diagnose equipment, replace technicians, or override plant procedures. The backend first selects and structures the evidence; AI then explains that evidence in maintenance-supervisor language.

## Architecture

```txt
React / Vite frontend
        |
        v
FastAPI backend
        |
        v
CSV normalization + machine matching + rule-based risk scoring
        |
        v
JSON proof-of-concept data layer
        |
        v
Optional watsonx.ai analysis for selected-machine insight
```

### Frontend

- React 19
- Vite
- TypeScript
- Tailwind CSS
- Framer Motion

### Backend

- FastAPI
- Python
- CSV normalization pipeline
- deterministic dashboard/risk logic
- JSON data files for proof-of-concept persistence
- IBM watsonx.ai model calls for AI analysis

### Data Layer

The proof-of-concept uses JSON files in `Backend/data/`:

- `machines.json`: stable machine registry and factory map context
- `maintenance_logs.json`: accumulated normalized maintenance history
- `ai-responses.json`: saved AI outputs, separate from maintenance history
- `dashboard-metrics.json`: demo/cache values only

## Setup

### 1. Backend

```powershell
cd Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Fill in `Backend/.env` with your IBM watsonx.ai values:

```env
WATSONX_API_KEY=your_ibm_watsonx_api_key_secret
WATSONX_PROJECT_ID=your_watsonx_project_id
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-3-8b-instruct
```

Run the API:

```powershell
python -m uvicorn src.api:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend

```powershell
cd Frontend
npm install
npm run dev
```

Open the Vite URL, typically:

```txt
http://localhost:5173
```

## Demo Data

Sample CSV files are included in `csv-files/`. Uploading multiple batches demonstrates how Machine Memory grows over time:

- more machines gain history
- risk signals become more meaningful
- repeated issue patterns appear
- similar past fixes become available
- dashboard metrics update from maintenance logs

## Future Direction

Machine Memory is a hackathon proof of concept with a clear path to production:

- CMMS integration
- sensor and runtime data integration
- work-order export
- stronger semantic grouping of technician notes
- production database
- role-based access
- plant-level trend analysis
- deeper fleet-wide maintenance planning

## Why It Matters For Michigan

Michigan manufacturers operate in a practical reality: downtime is costly, skilled technician knowledge is valuable, and many factories cannot simply replace legacy equipment.

Machine Memory gives these teams a modernization path that works with existing operations. It preserves technician knowledge, centralizes maintenance history, and helps supervisors make faster, evidence-backed decisions without forcing a full equipment overhaul.

## Judging Highlights

- Practical problem with clear Michigan manufacturing relevance
- Works with messy real-world maintenance exports
- Preserves technician knowledge instead of replacing it
- Combines deterministic risk scoring with grounded AI explanation
- Demonstrates a usable end-to-end workflow
- Leaves a realistic path toward CMMS, sensor, and production database integration

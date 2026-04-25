# 📂 Guidelines: Database Migration Framework (Python)

## 🎯 Objective
Build a cross-platform (WSL/Windows) database migration engine that automates schema discovery, enforces data integrity via Pydantic contracts, and provides a rich terminal interface with granular logging.

---

## 🛠 1. Technical Stack & Environment
* **Language:** Python 3.10+
* **CLI/UI:** `Typer` (commands), `Rich` (TUI/Progress/Tables).
* **ORM/Core:** `SQLAlchemy 2.0` (Metadata & Reflection).
* **Validation:** `Pydantic v2` (Dynamic Model Factory).
* **Logging:** `Loguru` (JSON Structured Logging).
* **Config:** `Pydantic-Settings` (JIT Config via `.env` and CLI).
* **Orchestration:** `Makefile` for cross-platform task execution.

---

## 🚀 2. Core Architecture Tasks

### Task 2.1: JIT Configuration & CLI (The "Entry Point")
- [ ] Implement `config.py` using `BaseSettings` to load `.env` credentials.
- [ ] Create `main.py` with `Typer` commands: `run`, `profile`, `doctor`.
- [ ] Ensure path compatibility between WSL (`/mnt/c/`) and Windows (`C:\`) using `pathlib`.

### Task 2.2: The Profiling Engine (Metadata Discovery)
- [ ] Implement a `Profiler` class that connects to Source DB and reflects schemas.
- [ ] **Task:** Generate a summary report (JSON/HTML) containing:
    - Table names, row counts, and column types.
    - Primary keys and Foreign Key constraints.
    - Identification of "Dangerous Types" (LOBs, BLOBs, Custom Types).

### Task 2.3: Dynamic Contract Factory (Pydantic Integration)
- [ ] Create a `ContractFactory` that converts SQLAlchemy metadata into Pydantic models at runtime.
- [ ] **Feature:** Support for type-mapping overrides via a `mapping.py` or `.yaml` file.
- [ ] **Validation:** Implement a "Data Cleaner" logic within Pydantic to handle common migration issues (trimming strings, coercing dates).

### Task 2.4: Execution Engine (The "Data Streamer")
- [ ] Implement **Chunked Reading**: Use server-side cursors to fetch data in batches (e.g., 10k rows).
- [ ] Implement **Parallel Workers**: Use `concurrent.futures` to migrate multiple tables simultaneously.
- [ ] **Checkpoint System:** Store progress in a local `state.db` (SQLite). Record `last_processed_id` per table.

### Task 2.5: The "Rich" Interface (TUI)
- [ ] Create a live dashboard using `rich.progress` and `rich.table`.
- [ ] **Display:** Show a side-by-side "Source Count" vs "Target Count" updating in real-time.
- [ ] Implement color-coded status for each table: `PENDING`, `SYNCING`, `VALIDATING`, `SUCCESS`, `FAILED`.

---

## 📊 3. Logging & Observability Tasks

### Task 3.1: Structured Logging
- [ ] Implement a logger that creates one file per table: `logs/{project}/{table_name}.jsonl`.
- [ ] **Schema:** Every log entry must be a JSON line with `timestamp`, `level`, `chunk_id`, and `payload_sample` (on error).
- [ ] Implement an automated "Error Summary" at the end of the execution.

---

## 🛡 4. Quality & Performance Guidelines

* **Memory Management:** Never load a full table into RAM. Always use Generators and Iterators.
* **Bulk Priority:** For V1, prioritize `bulk_insert_mappings` or native `COPY` commands if the dialect supports it.
* **Resilience:** If the network drops, the framework must be able to resume from the last successful chunk using the SQLite state file.
* **Cross-OS:** All terminal outputs must be forced to `UTF-8`. Use `pathlib` for all file operations.

---

## 📋 5. V1 Checklist for GLM-5 Execution

1.  **Connectivity:** Connects to Oracle/Postgres/MSSQL from both WSL and PowerShell.
2.  **Contracts:** Generates Pydantic models from Source and validates 100% of rows.
3.  **Logs:** Creates `.jsonl` files for every table migrated.
4.  **UI:** Displays progress bars and a final reconciliation table.
5.  **Makefile:** `make setup`, `make migrate`, and `make doctor` are fully functional.

---

## 🛠 6. Example Makefile Template
```makefile
migrate:
	@python main.py run \
		--source-type $(src) \
		--target-type $(target) \
		--batch-size 5000 \
		--parallel 4
```

---

**Final Note to GLM-5:** *Focus on the modularity of the `drivers/` folder. Each database dialect should have its own adapter to handle syntax variations, while the `core/` logic remains engine-agnostic.*
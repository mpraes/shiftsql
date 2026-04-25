# ShiftSQL

A database migration framework with schema profiling, chunked data transfer, and checkpoint-based resumability.

## Project Structure

```
src/
├── config.py          # Pydantic Settings configuration
├── main.py            # CLI entry point (Typer)
├── core/
│   ├── profiler.py        # Database schema profiling
│   ├── execution_engine.py # Chunked migration engine
│   └── contract_factory.py # Dynamic Pydantic models
└── utils/
    └── logger.py          # Structured JSONL logging

tests/
└── unit/
    ├── test_config.py
    └── test_profiler.py

docs/
└── GUIDELINES.md
```

## Guidelines

See [docs/GUIDELINES.md](docs/GUIDELINES.md) for project development guidelines.

See [AGENTS.md](AGENTS.md) for agent operating principles.

## Features

### Database Profiler
Schema discovery and metadata extraction from source databases.
- Connect to any SQLAlchemy-supported database
- Extract table names, columns, types, primary keys, and foreign keys
- Identify potentially problematic data types (LOBs, BLOBs, CLOBs, etc.)
- Generate JSON profile reports with summary statistics

See `src/core/profiler.py` and `tests/unit/test_profiler.py`.

### Execution Engine
Chunked data transfer with parallel workers and checkpoint-based resumability.
- **CheckpointManager**: SQLite-based checkpoint storage for migration recovery
- **ChunkedReader**: Batch reading with ID-based chunking for large tables
- **DataWriter**: Bulk insert operations to target database
- Parallel processing with configurable worker count
- Progress callbacks for real-time monitoring
- Resume interrupted migrations from last checkpoint

See `src/core/execution_engine.py`.

### Contract Factory
Dynamic Pydantic model generation from SQLAlchemy metadata.
- Automatic type mapping from SQLAlchemy to Python/Pydantic types
- Built-in data cleaners for strings, numerics, and datetimes
- Runtime model creation with validators
- Model caching for performance

See `src/core/contract_factory.py`.

### CLI Interface
Typer-based command-line interface with Rich formatting.
- `shiftsql run` - Execute full migration workflow
- `shiftsql profile` - Profile source database only
- `shiftsql doctor` - System health check and diagnostics

See `src/main.py`.

### Structured Logging
JSONL-based structured logging per table.
- Separate log file per table for easy debugging
- Error tracking with summary generation
- Automatic log cleanup for old files

See `src/utils/logger.py`.

### Configuration
Pydantic Settings-based configuration with environment variable support.
- JIT configuration loading from `.env` files
- Connection string builders for source and target databases
- Configurable batch sizes and parallel workers

See `src/config.py` and `tests/unit/test_config.py`.

## Getting Started

Follow these steps to set up and run the project locally.

- **Prerequisites:** Python 3.10+ and git installed.
- **Create a virtual environment:**

  ```bash
  python3 -m venv venv
  ```

- **Activate the environment:**

  ```bash
  source venv/bin/activate
  ```

- **Install dependencies:**

  ```bash
  pip install -r requirements.txt
  ```

- **Configuration:**

  Create a `.env` file with your database credentials:

  ```bash
  SOURCE_DB_TYPE=postgresql
  SOURCE_DB_HOST=localhost
  SOURCE_DB_PORT=5432
  SOURCE_DB_NAME=source_db
  SOURCE_DB_USER=user
  SOURCE_DB_PASSWORD=password

  TARGET_DB_TYPE=postgresql
  TARGET_DB_HOST=localhost
  TARGET_DB_PORT=5432
  TARGET_DB_NAME=target_db
  TARGET_DB_USER=user
  TARGET_DB_PASSWORD=password
  ```

- **Run tests:**

  ```bash
  pytest -q
  ```

- **Run migrations:**

  ```bash
  python -m src.main run --source-type postgresql --target-type postgresql
  ```
# Makefile for ShiftSQL Database Migration Framework
# Cross-platform task execution for development and deployment

.PHONY: setup migrate profile doctor test clean logs help

# Variables
PYTHON = python3
VENV = venv
PIP = $(VENV)/bin/pip
PYTHON_EXEC = $(VENV)/bin/python

# Default target
help:
	@echo "ShiftSQL Database Migration Framework"
	@echo ""
	@echo "Available targets:"
	@echo "  setup     - Create virtual environment and install dependencies"
	@echo "  migrate   - Run database migration with default parameters"
	@echo "  profile   - Profile source database and generate report"
	@echo "  doctor    - Check system health and dependencies"
	@echo "  test      - Run unit tests"
	@echo "  clean     - Remove temporary files and caches"
	@echo "  logs      - Show recent log entries"
	@echo ""
	@echo "Example usage:"
	@echo "  make setup"
	@echo "  source $(VENV)/bin/activate"
	@echo "  make migrate SOURCE_TYPE=postgres TARGET_TYPE=sqlite"
	@echo ""

# Setup virtual environment and install dependencies
setup:
	@echo "Setting up virtual environment..."
	$(PYTHON) -m venv $(VENV)
	@echo "Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install sqlalchemy pydantic loguru typer rich
	@echo "Setup complete! Activate with: source $(VENV)/bin/activate"

# Run database migration
migrate:
	@echo "Running database migration..."
	$(PYTHON_EXEC) src/main.py run \
		--source-type $(SOURCE_TYPE) \
		--target-type $(TARGET_TYPE) \
		--batch-size $(BATCH_SIZE) \
		--parallel $(PARALLEL) \
		$(if $(TABLES),--tables $(TABLES)) \
		$(if $(PROFILE_ONLY),--profile-only) \
		$(if $(PROJECT_NAME),--project $(PROJECT_NAME))

# Profile source database
profile:
	@echo "Profiling source database..."
	$(PYTHON_EXEC) src/main.py profile \
		--source-type $(SOURCE_TYPE) \
		--host $(DB_HOST) \
		--port $(DB_PORT) \
		--database $(DB_NAME) \
		--user $(DB_USER) \
		--password $(DB_PASSWORD) \
		--output $(OUTPUT_FILE)

# System health check
doctor:
	@echo "Running system health check..."
	$(PYTHON_EXEC) src/main.py doctor

# Run unit tests
test:
	@echo "Running unit tests..."
	$(PYTHON_EXEC) -m unittest discover tests/ -v

# Clean temporary files and caches
clean:
	@echo "Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*~" -delete
	find . -type f -name "*.log" -delete
	rm -rf .coverage .pytest_cache htmlcov/ 2>/dev/null || true
	@echo "Clean complete"

# Show recent logs
logs:
	@echo "Showing recent log entries..."
	if [ -d "logs" ]; then \
		find logs/ -name "*.jsonl" -head -5 2>/dev/null | xargs cat 2>/dev/null || \
		echo "No log files found"; \
	else \
		echo "Logs directory not found"; \
	fi

# Development shortcuts
dev-setup: setup
	@echo "Development environment ready!"

# Help target (already defined above)
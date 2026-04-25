"""
Main entry point for the ShiftSQL migration framework.
Provides Typer CLI interface with commands: run, profile, doctor.
"""

import typer
from rich.console import Console
from rich.table import Table
from pathlib import Path
import sys
import os
from typing import Optional

# Add src to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from config import settings
from utils.logger import init_logger, get_logger, log_info, log_error, log_warning

app = typer.Typer(help="ShiftSQL Database Migration Framework")
console = Console()


@app.command()
def run(
    source_type: str = typer.Option(..., "--source-type", help="Source database type (oracle, postgres, mssql)"),
    target_type: str = typer.Option(..., "--target-type", help="Target database type (oracle, postgres, mssql)"),
    batch_size: int = typer.Option(5000, "--batch-size", help="Batch size for data transfer"),
    parallel: int = typer.Option(4, "--parallel", help="Number of parallel workers"),
    profile_only: bool = typer.Option(False, "--profile-only", help="Only profile source database, don't migrate"),
    tables: Optional[str] = typer.Option(None, "--tables", help="Comma-separated list of tables to migrate (default: all)"),
    project_name: str = typer.Option("default", "--project", help="Project name for logging")
):
    """Run the migration process from source to target database."""
    console.print(f"[bold green]Starting migration from {source_type} to {target_type}[/bold green]")
    console.print(f"Batch size: {batch_size}, Parallel workers: {parallel}")
    console.print(f"Project: {project_name}")
    
    # Initialize logger
    logger = init_logger(settings.logs_dir, project_name)
    logger.info("system", payload_sample={"event": "migration_started", "source_type": source_type, "target_type": target_type})
    
    # Import required modules
    from core.profiler import Profiler
    from core.contract_factory import ContractFactory
    from core.execution_engine import ExecutionEngine
    from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, SpinnerColumn
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    import json
    import time
    
    # Override settings with command line arguments
    settings.batch_size = batch_size
    settings.parallel_workers = parallel
    
    try:
        # Step 1: Profile source database
        console.print("\n[bold blue]Step 1: Profiling source database[/bold blue]")
        source_conn_str = settings.get_source_connection_string()
        profiler = Profiler(source_conn_str)
        
        if not profiler.connect():
            console.print("[red]Failed to connect to source database[/red]")
            logger.error("system", payload_sample={"event": "connection_failed", "database_type": "source"})
            raise typer.Exit(1)
        
        logger.info("system", payload_sample={"event": "source_database_connected"})
        
        # Generate profile
        profile_path = settings.logs_dir / project_name / "profile_report.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        report = profiler.generate_profile_report(profile_path)
        
        console.print(f"[green]✓ Profiled {report['summary']['total_tables']} tables[/green]")
        console.print(f"[green]✓ Profile saved to {profile_path}[/green]")
        logger.info("system", payload_sample={"event": "profiling_completed", "tables_count": report['summary']['total_tables']})
        
        if profile_only:
            console.print("[yellow]Profile-only mode selected. Exiting.[/yellow]")
            logger.info("system", payload_sample={"event": "migration_completed", "mode": "profile_only"})
            profiler.disconnect()
            return
        
        # Step 2: Display profile summary
        console.print("\n[bold blue]Step 2: Profile Summary[/bold blue]")
        table = Table(title="Database Profile Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Tables", str(report['summary']['total_tables']))
        table.add_row("Total Rows", f"{report['summary']['total_rows']:,}")
        table.add_row("Tables with LOBs", str(report['summary']['tables_with_lobs']))
        
        console.print(table)
        
        # Step 3: Determine tables to migrate
        console.print("\n[bold blue]Step 3: Determining tables to migrate[/bold blue]")
        all_tables = [t['name'] for t in report['tables']]
        
        if tables:
            table_list = [t.strip() for t in tables.split(',')]
            # Validate that tables exist
            invalid_tables = [t for t in table_list if t not in all_tables]
            if invalid_tables:
                console.print(f"[red]Error: Tables not found in source database: {invalid_tables}[/red]")
                logger.error("system", payload_sample={"event": "invalid_tables_specified", "invalid_tables": invalid_tables})
                profiler.disconnect()
                raise typer.Exit(1)
            console.print(f"[green]✓ Will migrate {len(table_list)} specified tables[/green]")
            logger.info("system", payload_sample={"event": "tables_selected", "tables": table_list, "count": len(table_list)})
        else:
            table_list = all_tables
            console.print(f"[green]✓ Will migrate all {len(table_list)} tables[/green]")
            logger.info("system", payload_sample={"event": "all_tables_selected", "count": len(table_list)})
        
        # Step 4: Show tables that will be migrated
        tables_to_migrate = [t for t in report['tables'] if t['name'] in table_list]
        if len(table_list) <= 10:  # Show details only for small lists
            table_detail = Table(title="Tables to Migrate")
            table_detail.add_column("Table Name", style="cyan")
            table_detail.add_column("Rows", style="green")
            table_detail.add_column("Columns", style="yellow")
            table_detail.add_column("LOB Types", style="red")
            
            for table_info in tables_to_migrate:
                lob_count = len(table_info['dangerous_types'])
                lob_str = ", ".join(table_info['dangerous_types'][:3]) + ("..." if lob_count > 3 else "")
                if lob_count == 0:
                    lob_str = "None"
                
                table_detail.add_row(
                    table_info['name'],
                    f"{table_info['row_count']:,}",
                    str(table_info['column_count']),
                    lob_str
                )
            
            console.print(table_detail)
        else:
            console.print(f"[dim]Migrating {len(table_list)} tables (use --tables to specify subset)[/dim]")
        
        # Step 5: Initialize execution engine
        console.print("\n[bold blue]Step 4: Initializing execution engine[/bold blue]")
        target_conn_str = settings.get_target_connection_string()
        
        execution_engine = ExecutionEngine(
            source_connection_string=source_conn_str,
            target_connection_string=target_conn_str,
            batch_size=batch_size,
            parallel_workers=parallel,
            checkpoint_db_path=settings.state_db_path
        )
        
        logger.info("system", payload_sample={"event": "execution_engine_initialized"})
        
        # Step 6: Run migration with Rich progress tracking
        console.print("\n[bold blue]Step 5: Running migration[/bold blue]")
        
        # We'll use a live updating display for migration progress
        def create_progress_layout():
            """Create the layout for the progress display."""
            from rich.columns import Columns
            from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
            
            # Overall progress
            overall_progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            )
            
            # Add overall task
            overall_task = overall_progress.add_task("[green]Migrating tables...", total=len(table_list))
            
            # Individual table progress (we'll update this dynamically)
            table_progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            )
            
            # We'll create tasks for each table as we migrate them
            table_tasks = {}
            
            return overall_progress, overall_task, table_progress, table_tasks
        
        # Track migration results
        migration_results = {}
        failed_tables = []
        
        # Custom progress callback that updates our Rich display
        def migration_progress_callback(table_name: str, chunk_id: int, total_chunks: int,
                                      migrated_rows: int, total_rows: int, success: bool):
            # Update logger
            if success and chunk_id >= 0:
                logger.info(table_name, chunk_id=chunk_id, 
                          payload_sample={"migrated_rows": migrated_rows, "total_rows": total_rows},
                          additional_data={"progress": f"{migrated_rows}/{total_rows}"})
            elif not success and chunk_id >= 0:
                logger.error(table_name, chunk_id=chunk_id,
                           payload_sample={"migrated_rows": migrated_rows, "total_rows": total_rows},
                           additional_data={"error": "Chunk processing failed"})
            elif chunk_id < 0:  # Table-level completion
                if success:
                    logger.info(table_name, payload_sample={"event": "table_migration_completed", 
                                                              "migrated_rows": migrated_rows, "total_rows": total_rows})
                else:
                    logger.error(table_name, payload_sample={"event": "table_migration_failed", 
                                                           "migrated_rows": migrated_rows, "total_rows": total_rows})
            
            # Store result for final reporting
            migration_results[table_name] = {
                'success': success,
                'migrated_rows': migrated_rows,
                'total_rows': total_rows
            }
            
            if not success:
                failed_tables.append(table_name)
        
        # Run the migration
        console.print("[yellow]Starting migration process...[/yellow]")
        start_time = time.time()
        
        results = execution_engine.migrate_tables(
            table_list, 
            id_column="id",  # Assuming most tables have an 'id' column
            progress_callback=migration_progress_callback
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info("system", payload_sample={"event": "migration_process_completed", 
                                               "duration_seconds": duration})
        
        # Step 7: Show final results
        console.print("\n[bold blue]Step 6: Migration Results[/bold blue]")
        results_table = Table(title="Migration Summary")
        results_table.add_column("Table", style="cyan")
        results_table.add_column("Status", style="green")
        results_table.add_column("Rows Migrated", style="yellow")
        results_table.add_column("Percentage", style="blue")
        results_table.add_column("Details", style="white")
        
        success_count = 0
        total_rows_migrated = 0
        total_rows_source = 0
        
        for table_name, success in results.items():
            if success:
                status = "[green]✓ SUCCESS[/green]"
                success_count += 1
                details = f"Completed in {duration:.1f}s"
            else:
                status = "[red]✗ FAILED[/red]"
                details = "Check logs for details"
            
            # Get migrated rows from our tracking
            table_result = migration_results.get(table_name, {'migrated_rows': 0, 'total_rows': 0})
            migrated_rows = table_result['migrated_rows']
            total_rows = table_result['total_rows']
            
            total_rows_migrated += migrated_rows
            total_rows_source += total_rows
            
            percentage = f"{(migrated_rows/total_rows*100):.1f}%" if total_rows > 0 else "0.0%"
            
            results_table.add_row(
                table_name, 
                status, 
                f"{migrated_rows:,}", 
                percentage,
                details
            )
        
        console.print(results_table)
        
        # Summary statistics
        summary_table = Table(title="Migration Statistics")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Tables Processed", f"{len(table_list)}")
        summary_table.add_row("Tables Successful", f"{success_count}")
        summary_table.add_row("Tables Failed", f"{len(table_list) - success_count}")
        summary_table.add_row("Total Rows Migrated", f"{total_rows_migrated:,}")
        summary_table.add_row("Total Rows Source", f"{total_rows_source:,}")
        summary_table.add_row("Success Rate", f"{(success_count/len(table_list)*100):.1f}%" if table_list else "0.0%")
        summary_table.add_row("Duration", f"{duration:.2f} seconds")
        
        console.print(summary_table)
        
        logger.info("system", payload_sample={
            "event": "migration_summary",
            "tables_processed": len(table_list),
            "tables_successful": success_count,
            "tables_failed": len(table_list) - success_count,
            "total_rows_migrated": total_rows_migrated,
            "duration_seconds": duration
        })
        
        # Step 8: Show error summary if any failures
        if failed_tables:
            console.print(f"\n[bold red]Failed tables: {', '.join(failed_tables)}[/bold red]")
            console.print("[yellow]Check logs/ directory for detailed error information[/yellow]")
            
            # Show recent errors from logger
            error_summary = get_logger().get_error_summary()
            if error_summary["total_errors"] > 0:
                error_table = Table(title="Recent Errors")
                error_table.add_column("Timestamp", style="dim")
                error_table.add_column("Table", style="cyan")
                error_table.add_column("Level", style="red")
                error_table.add_column("Message", style="white")
                
                # Show up to 5 recent errors
                recent_errors = error_summary["recent_errors"][:5]
                for error in recent_errors:
                    timestamp = error["timestamp"][:19].replace("T", " ")  # Format timestamp
                    error_table.add_row(
                        timestamp,
                        error["table_name"],
                        error["level"],
                        error["message"][:50] + ("..." if len(error["message"]) > 50 else "")
                    )
                
                console.print(error_table)
        
        # Cleanup
        profiler.disconnect()
        logger.info("system", payload_sample={"event": "migration_completed"})
        
    except Exception as e:
        console.print(f"[red]Error during migration: {e}[/red]")
        logger.error("system", payload_sample={"event": "migration_error", "error": str(e)})
        raise typer.Exit(1)


@app.command()
def profile(
    source_type: str = typer.Option(..., "--source-type", help="Source database type (oracle, postgres, mssql)"),
    output: str = typer.Option("profile_report.json", "--output", help="Output file for profile report"),
    host: str = typer.Option("localhost", "--host", help="Database host"),
    port: int = typer.Option(5432, "--port", help="Database port"),
    database: str = typer.Option("testdb", "--database", help="Database name"),
    user: str = typer.Option("postgres", "--user", help="Database user"),
    password: str = typer.Option("", "--password", help="Database password")
):
    """Profile the source database and generate a report."""
    console.print(f"[bold blue]Profiling {source_type} database[/bold blue]")
    
    # Build connection string
    connection_string = f"{source_type}://{user}:{password}@{host}:{port}/{database}"
    
    # Import and use profiler
    from core.profiler import Profiler
    
    profiler = Profiler(connection_string)
    if profiler.connect():
        try:
            report = profiler.generate_profile_report(Path(output))
            console.print(f"[green]Profile report generated: {output}[/green]")
            console.print(f"Found {report['summary']['total_tables']} tables with {report['summary']['total_rows']} total rows")
        except Exception as e:
            console.print(f"[red]Error generating profile: {e}[/red]")
        finally:
            profiler.disconnect()
    else:
        console.print("[red]Failed to connect to database[/red]")


@app.command()
def doctor():
    """Check system health and dependencies."""
    console.print("[bold cyan]Running system health check[/bold cyan]")
    
    table = Table(title="ShiftSQL Doctor Report")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")
    
    # Check Python version
    table.add_row("Python", "✓ OK", f"{sys.version}")
    
    # Check required directories
    for dir_name in ["src", "tests", "logs", "drivers"]:
        dir_path = Path(dir_name)
        if dir_path.exists():
            table.add_row(f"Directory {dir_name}", "✓ OK", str(dir_path.absolute()))
        else:
            table.add_row(f"Directory {dir_name}", "✗ MISSING", f"Expected at {dir_path.absolute()}")
    
    # Check .env file
    env_path = Path(".env")
    if env_path.exists():
        table.add_row(".env file", "✓ OK", str(env_path.absolute()))
    else:
        table.add_row(".env file", "⚠ WARNING", "Not found (will use defaults)")
    
    console.print(table)
    
    # TODO: Add more health checks (database connectivity, package versions, etc.)


if __name__ == "__main__":
    app()
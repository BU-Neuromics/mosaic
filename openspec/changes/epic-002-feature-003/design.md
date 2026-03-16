## Context

Configure SQLite database with Write-Ahead Logging (WAL) mode for improved concurrency and performance. WAL mode allows concurrent read operations to proceed without blocking writes, and vice versa, by using a separate WAL journal file instead of rollback journal.

Current state: SQLite databases are created with default journal mode (DELETE). This change adds WAL mode configuration to improve concurrency for multi-process access scenarios.

## Goals / Non-Goals

**Goals:**
- Enable WAL mode on SQLite databases via PRAGMA journal_mode=WAL
- Support concurrent read operations during write operations
- Ensure data integrity through checkpoint operations

**Non-Goals:**
- Database migration strategy for existing databases
- Replication or distributed transaction support
- Performance benchmarking or tuning

## Decisions

- Use PRAGMA journal_mode=WAL to enable WAL mode at connection time
- WAL file location defaults to same directory as database file
- Checkpoint operations managed automatically by SQLite

## Risks / Trade-offs

- WAL mode uses additional disk space for WAL file
- First connection to database performs WAL recovery if needed
- Some legacy tools may not support WAL mode

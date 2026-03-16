"""SQL trigger definitions for provenance immutability."""

PROVENANCE_TABLE = "provenance"

TRIGGER_PREVENT_PK_UPDATE = """
CREATE TRIGGER IF NOT EXISTS prevent_provenance_pk_update
BEFORE UPDATE OF entity_id ON provenance
BEGIN
    SELECT RAISE(ABORT, 'Cannot update primary key of provenance record');
END;
"""

TRIGGER_PREVENT_TIMESTAMP_UPDATE = """
CREATE TRIGGER IF NOT EXISTS prevent_provenance_timestamp_update
BEFORE UPDATE OF timestamp ON provenance
BEGIN
    SELECT RAISE(ABORT, 'Cannot update timestamp of provenance record');
END;
"""

TRIGGER_PREVENT_METADATA_UPDATE = """
CREATE TRIGGER IF NOT EXISTS prevent_provenance_metadata_update
BEFORE UPDATE OF user_context ON provenance
BEGIN
    SELECT RAISE(ABORT, 'Cannot update user_context field of provenance record');
END;
"""

TRIGGER_PREVENT_CONTENT_UPDATE = """
CREATE TRIGGER IF NOT EXISTS prevent_provenance_content_update
BEFORE UPDATE OF payload ON provenance
BEGIN
    SELECT RAISE(ABORT, 'Cannot update payload field of provenance record');
END;
"""

TRIGGER_PREVENT_DELETE = """
CREATE TRIGGER IF NOT EXISTS prevent_provenance_delete
BEFORE DELETE ON provenance
BEGIN
    SELECT RAISE(ABORT, 'Cannot delete provenance record');
END;
"""

ALL_TRIGGERS = [
    TRIGGER_PREVENT_PK_UPDATE,
    TRIGGER_PREVENT_TIMESTAMP_UPDATE,
    TRIGGER_PREVENT_METADATA_UPDATE,
    TRIGGER_PREVENT_CONTENT_UPDATE,
    TRIGGER_PREVENT_DELETE,
]


def get_trigger_sql_list():
    """Return list of all trigger SQL statements."""
    return ALL_TRIGGERS

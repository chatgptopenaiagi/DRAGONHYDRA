-- Explicit secondary research archive. Never the canonical sports/job database.
-- Version 1 is applied only to a newly created, empty, product-owned database.
CREATE TABLE dbo.dh_research_owner (
    owner_key tinyint NOT NULL PRIMARY KEY CHECK (owner_key = 1),
    product_id nvarchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    schema_version int NOT NULL CHECK (schema_version = 1),
    migration_sha256 varbinary(32) NOT NULL CHECK (DATALENGTH(migration_sha256) = 32),
    initialized_at datetime2(7) NOT NULL
);
CREATE TABLE dbo.dh_research_migrations (
    migration_name nvarchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL PRIMARY KEY,
    checksum varbinary(32) NOT NULL CHECK (DATALENGTH(checksum) = 32),
    applied_at datetime2(7) NOT NULL
);
CREATE TABLE dbo.dh_research_archives (
    scope nvarchar(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
    archive_id char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    match_id char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    forecast_run_id nvarchar(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
    home_name nvarchar(512) NOT NULL,
    away_name nvarchar(512) NOT NULL,
    competition nvarchar(512) NOT NULL,
    event_date date NOT NULL,
    source_id nvarchar(512) COLLATE Latin1_General_100_BIN2 NOT NULL,
    payload nvarchar(max) NOT NULL CHECK (ISJSON(payload) = 1),
    payload_sha256 varbinary(32) NOT NULL CHECK (DATALENGTH(payload_sha256) = 32),
    persisted_at datetime2(7) NOT NULL,
    input_count bigint NOT NULL CHECK (input_count >= 0 AND input_count <= 50000),
    synthetic bit NOT NULL CHECK (synthetic = 0),
    CONSTRAINT PK_dh_research_archives PRIMARY KEY (scope, archive_id)
);
CREATE INDEX IX_dh_research_archive_match ON dbo.dh_research_archives(scope, match_id, persisted_at DESC, archive_id);
CREATE TABLE dbo.dh_research_models (
    scope nvarchar(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
    archive_id char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    record_id nvarchar(160) COLLATE Latin1_General_100_BIN2 NOT NULL,
    model_name nvarchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    model_version nvarchar(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
    data_cutoff datetime2(7) NOT NULL,
    payload nvarchar(max) NOT NULL CHECK (ISJSON(payload) = 1),
    CONSTRAINT PK_dh_research_models PRIMARY KEY (scope, archive_id, record_id),
    CONSTRAINT FK_dh_research_models_archive FOREIGN KEY (scope, archive_id)
        REFERENCES dbo.dh_research_archives(scope, archive_id)
);
CREATE TABLE dbo.dh_research_predictions (
    scope nvarchar(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
    archive_id char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    record_id nvarchar(160) COLLATE Latin1_General_100_BIN2 NOT NULL,
    model_run_id nvarchar(160) COLLATE Latin1_General_100_BIN2 NOT NULL,
    home_probability decimal(38,28) NOT NULL CHECK (home_probability >= 0 AND home_probability <= 1),
    draw_probability decimal(38,28) NOT NULL CHECK (draw_probability >= 0 AND draw_probability <= 1),
    away_probability decimal(38,28) NOT NULL CHECK (away_probability >= 0 AND away_probability <= 1),
    decision_cutoff datetime2(7) NOT NULL,
    predicted_at datetime2(7) NOT NULL,
    payload nvarchar(max) NOT NULL CHECK (ISJSON(payload) = 1),
    CONSTRAINT PK_dh_research_predictions PRIMARY KEY (scope, archive_id, record_id),
    CONSTRAINT CK_dh_research_probability_sum CHECK
        (ABS(home_probability + draw_probability + away_probability - 1) <= 0.000000000001),
    CONSTRAINT FK_dh_research_predictions_model FOREIGN KEY (scope, archive_id, model_run_id)
        REFERENCES dbo.dh_research_models(scope, archive_id, record_id)
);
CREATE TABLE dbo.dh_research_inputs (
    scope nvarchar(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
    archive_id char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ordinal int NOT NULL CHECK (ordinal >= 0),
    evidence_id nvarchar(160) COLLATE Latin1_General_100_BIN2 NOT NULL,
    source_id nvarchar(512) COLLATE Latin1_General_100_BIN2 NOT NULL,
    source_sha256 varbinary(32) NOT NULL CHECK (DATALENGTH(source_sha256) = 32),
    usable_at datetime2(7) NOT NULL,
    payload nvarchar(max) NOT NULL CHECK (ISJSON(payload) = 1),
    CONSTRAINT PK_dh_research_inputs PRIMARY KEY (scope, archive_id, ordinal),
    CONSTRAINT FK_dh_research_inputs_archive FOREIGN KEY (scope, archive_id)
        REFERENCES dbo.dh_research_archives(scope, archive_id)
);
CREATE TABLE dbo.dh_research_notes (
    scope nvarchar(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
    note_id uniqueidentifier NOT NULL,
    match_id char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    note_text nvarchar(4000) NOT NULL,
    revision bigint NOT NULL CHECK (revision >= 1),
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    CONSTRAINT PK_dh_research_notes PRIMARY KEY (scope, note_id)
);
CREATE INDEX IX_dh_research_notes_match ON dbo.dh_research_notes(scope, match_id, updated_at, note_id);
CREATE TABLE dbo.dh_research_note_audit (
    scope nvarchar(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
    note_id uniqueidentifier NOT NULL,
    revision bigint NOT NULL,
    match_id char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    note_text nvarchar(4000) NOT NULL,
    action nvarchar(8) NOT NULL CHECK (action IN ('created', 'updated')),
    occurred_at datetime2(7) NOT NULL,
    CONSTRAINT PK_dh_research_note_audit PRIMARY KEY (scope, note_id, revision),
    CONSTRAINT FK_dh_research_note_audit_note FOREIGN KEY (scope, note_id)
        REFERENCES dbo.dh_research_notes(scope, note_id)
);
GO
CREATE TRIGGER dbo.dh_research_archives_immutable ON dbo.dh_research_archives AFTER UPDATE, DELETE AS
BEGIN SET NOCOUNT ON; THROW 51000, 'DH_RESEARCH_IMMUTABLE', 1; END;
GO
CREATE TRIGGER dbo.dh_research_models_immutable ON dbo.dh_research_models AFTER UPDATE, DELETE AS
BEGIN SET NOCOUNT ON; THROW 51000, 'DH_RESEARCH_IMMUTABLE', 1; END;
GO
CREATE TRIGGER dbo.dh_research_predictions_immutable ON dbo.dh_research_predictions AFTER UPDATE, DELETE AS
BEGIN SET NOCOUNT ON; THROW 51000, 'DH_RESEARCH_IMMUTABLE', 1; END;
GO
CREATE TRIGGER dbo.dh_research_inputs_immutable ON dbo.dh_research_inputs AFTER UPDATE, DELETE AS
BEGIN SET NOCOUNT ON; THROW 51000, 'DH_RESEARCH_IMMUTABLE', 1; END;
GO
CREATE TRIGGER dbo.dh_research_owner_immutable ON dbo.dh_research_owner AFTER UPDATE, DELETE AS
BEGIN SET NOCOUNT ON; THROW 51000, 'DH_RESEARCH_IMMUTABLE', 1; END;
GO
CREATE TRIGGER dbo.dh_research_migrations_immutable ON dbo.dh_research_migrations AFTER UPDATE, DELETE AS
BEGIN SET NOCOUNT ON; THROW 51000, 'DH_RESEARCH_IMMUTABLE', 1; END;
GO
CREATE TRIGGER dbo.dh_research_note_audit_immutable ON dbo.dh_research_note_audit AFTER UPDATE, DELETE AS
BEGIN SET NOCOUNT ON; THROW 51000, 'DH_RESEARCH_IMMUTABLE', 1; END;
GO
CREATE TRIGGER dbo.dh_research_notes_no_delete ON dbo.dh_research_notes AFTER DELETE AS
BEGIN SET NOCOUNT ON; THROW 51000, 'DH_RESEARCH_NOTE_DELETE_DISABLED', 1; END;
GO
CREATE TRIGGER dbo.dh_research_notes_audit ON dbo.dh_research_notes AFTER INSERT, UPDATE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM deleted d LEFT JOIN inserted i
        ON i.scope = d.scope AND i.note_id = d.note_id WHERE i.note_id IS NULL)
        THROW 51001, 'DH_RESEARCH_NOTE_IDENTITY_IMMUTABLE', 1;
    IF EXISTS (SELECT 1 FROM inserted i LEFT JOIN deleted d
        ON i.scope = d.scope AND i.note_id = d.note_id WHERE
        (d.note_id IS NULL AND i.revision <> 1) OR
        (d.note_id IS NOT NULL AND (i.revision <> d.revision + 1 OR i.match_id <> d.match_id
            OR i.created_at <> d.created_at OR i.updated_at < d.updated_at)))
        THROW 51002, 'DH_RESEARCH_NOTE_REVISION_INVALID', 1;
    INSERT INTO dbo.dh_research_note_audit(scope, note_id, revision, match_id, note_text, action, occurred_at)
        SELECT i.scope, i.note_id, i.revision, i.match_id, i.note_text,
            CASE WHEN d.note_id IS NULL THEN 'created' ELSE 'updated' END, i.updated_at
        FROM inserted i LEFT JOIN deleted d ON i.scope = d.scope AND i.note_id = d.note_id;
END;

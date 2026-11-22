DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users GROUP BY username HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Duplicate logins: resolve them in the database copy before retrying';
    END IF;
    IF EXISTS (
        SELECT 1 FROM users
        WHERE username IS NULL OR btrim(username) = '' OR role IS NULL
              OR lower(role) NOT IN ('admin', 'user', 'viewer')
    ) THEN
        RAISE EXCEPTION 'Invalid logins or roles: resolve them in the database copy before retrying';
    END IF;
END
$$;

UPDATE users SET role = initcap(role), areaid = CASE WHEN lower(role) = 'viewer' THEN areaid END;
ALTER TABLE users
    ALTER COLUMN username SET NOT NULL,
    ALTER COLUMN role SET NOT NULL,
    ADD CONSTRAINT users_username_unique UNIQUE (username),
    ADD CONSTRAINT users_role_check CHECK (role IN ('Admin', 'User', 'Viewer')),
    ADD CONSTRAINT users_area_check CHECK (role = 'Viewer' OR areaid IS NULL);

ALTER TABLE diagnostics
    ALTER COLUMN distance TYPE NUMERIC(14, 3),
    ADD COLUMN survey_date DATE,
    ADD COLUMN latitude DOUBLE PRECISION,
    ADD COLUMN longitude DOUBLE PRECISION,
    ADD COLUMN created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN version BIGINT NOT NULL DEFAULT 1,
    ADD CONSTRAINT diagnostics_coordinates_check CHECK (
        (latitude IS NULL AND longitude IS NULL)
        OR (latitude IS NOT NULL AND longitude IS NOT NULL
            AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)
    );

-- The legacy timestamp only represents the last recorded change.
UPDATE diagnostics SET created_at = NULL, updated_at = timestampdata AT TIME ZONE 'UTC';

CREATE TABLE diagnostic_spans (
    diagnostic_id INTEGER NOT NULL REFERENCES diagnostics ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    first_well TEXT NOT NULL,
    flow TEXT NOT NULL,
    slope TEXT NOT NULL,
    length NUMERIC(14, 3) NOT NULL CHECK (length > 0),
    last_well TEXT NOT NULL,
    PRIMARY KEY (diagnostic_id, position)
);

CREATE TABLE diagnostic_defects (
    diagnostic_id INTEGER NOT NULL REFERENCES diagnostics ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    description TEXT NOT NULL CHECK (btrim(description) <> ''),
    distance NUMERIC(14, 3) NOT NULL CHECK (distance >= 0),
    PRIMARY KEY (diagnostic_id, position)
);

CREATE TABLE diagnostic_attachments (
    id BIGSERIAL PRIMARY KEY,
    diagnostic_id INTEGER NOT NULL REFERENCES diagnostics ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('photo', 'slope')),
    stored_name TEXT NOT NULL CHECK (stored_name <> ''),
    media_type TEXT NOT NULL,
    legacy BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (diagnostic_id, kind, stored_name)
);

CREATE TABLE diagnostic_migration_issues (
    diagnostic_id INTEGER NOT NULL REFERENCES diagnostics ON DELETE CASCADE,
    field TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (diagnostic_id, field)
);

CREATE TABLE pending_file_deletions (
    stored_name TEXT PRIMARY KEY
);

CREATE TABLE login_attempts (
    client_key TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX login_attempts_expiry_idx ON login_attempts (expires_at);

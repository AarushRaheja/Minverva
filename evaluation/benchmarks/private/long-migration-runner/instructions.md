Build a small database migration runner in `migrate/runner.py`, using sqlite3 from the standard library. Do it in stages, because each stage depends on the last:

1. `Runner(conn, migrations)` takes a sqlite3 connection and a list of `(version:int, name:str, sql:str)`. `upgrade()` applies the unapplied migrations in version order and returns the list of versions applied. Applied versions are recorded in a `schema_migrations(version, name, checksum)` table, so a second call applies nothing.
2. Each migration runs in its own transaction. If one fails, its changes are rolled back, earlier migrations stay applied, and `MigrationError` is raised naming the version. Multi-statement SQL must be supported and must roll back as a unit.
3. Duplicate versions in the list raise `MigrationError` before anything runs. The checksum is the SHA-256 hex digest of the sql. If an already applied migration's sql has changed, `upgrade()` raises `MigrationError` before anything runs.
4. `status()` returns a list of `{"version", "name", "applied"}` sorted by version.

Run the visible tests with: python3 -m unittest discover -s tests/public -t tests/public
Hidden tests will also grade your work. Don't edit existing tests.

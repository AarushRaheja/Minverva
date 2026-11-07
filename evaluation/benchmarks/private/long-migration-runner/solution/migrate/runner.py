import hashlib
import sqlite3


class MigrationError(Exception):
    pass


def _checksum(sql):
    return hashlib.sha256(sql.encode()).hexdigest()


class Runner:
    def __init__(self, conn, migrations):
        self.conn = conn
        self.migrations = sorted(migrations, key=lambda m: m[0])

    def _ensure(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, name TEXT, checksum TEXT)")
        self.conn.commit()

    def _applied(self):
        self._ensure()
        return {v: c for v, c in self.conn.execute("SELECT version, checksum FROM schema_migrations")}

    def upgrade(self):
        versions = [m[0] for m in self.migrations]
        if len(set(versions)) != len(versions):
            raise MigrationError("duplicate migration versions")
        applied = self._applied()
        for version, _, sql in self.migrations:
            if version in applied and applied[version] != _checksum(sql):
                raise MigrationError(f"migration {version} changed after it was applied")
        done = []
        for version, name, sql in self.migrations:
            if version in applied:
                continue
            quoted = name.replace("\'", "\'\'")
            script = (f"BEGIN; {sql.rstrip().rstrip(';')}; INSERT INTO schema_migrations VALUES "
                      f"({int(version)}, '{quoted}', '{_checksum(sql)}'); COMMIT;")
            try:
                self.conn.executescript(script)
            except sqlite3.Error as e:
                if self.conn.in_transaction:
                    self.conn.rollback()
                raise MigrationError(f"migration {version} failed: {e}") from e
            done.append(version)
        return done

    def status(self):
        applied = self._applied()
        return [{"version": v, "name": n, "applied": v in applied} for v, n, _ in self.migrations]

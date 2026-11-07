class MigrationError(Exception):
    pass


class Runner:
    def __init__(self, conn, migrations):
        self.conn = conn
        self.migrations = migrations

    def upgrade(self):
        raise NotImplementedError

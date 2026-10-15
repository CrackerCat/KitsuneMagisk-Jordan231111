from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DatabaseVersionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="kitsune-native-sqlite-")
        cls.binary = Path(cls.temporary.name) / "database"
        source = (ROOT / "native/src/core/sqlite.cpp").read_text()
        native = source[source.index("// Keep the first online snapshot"):source.index("// Exported from Rust")]
        support = r'''
#include <sqlite3.h>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include "db_migrations.hpp"
using namespace std;
struct DbValues {
    sqlite3_stmt *statement;
    int get_int(int column) const { return sqlite3_column_int(statement, column); }
    const char *get_text(int column) const {
        auto text = sqlite3_column_text(statement, column);
        return text ? reinterpret_cast<const char *>(text) : "";
    }
};
using Callback = void (*)(void *, int, const DbValues &);
int sql_exec_impl(sqlite3 *db, string_view sql, void * = nullptr, void * = nullptr,
                  Callback callback = nullptr, void *cookie = nullptr) {
    if (const char *fail = getenv("FAIL_SQL"); fail && sql == fail) return SQLITE_IOERR;
    string text(sql);
    const char *cursor = text.c_str();
    while (*cursor) {
        sqlite3_stmt *statement = nullptr;
        int rc = sqlite3_prepare_v2(db, cursor, -1, &statement, &cursor);
        if (rc != SQLITE_OK) return rc;
        if (!statement) continue;
        while ((rc = sqlite3_step(statement)) == SQLITE_ROW) {
            if (callback) callback(cookie, 0, DbValues{statement});
        }
        sqlite3_finalize(statement);
        if (rc != SQLITE_DONE) return rc;
    }
    return SQLITE_OK;
}
static auto close_database = &sqlite3_close;
#define sqlite3_close close_database
#define DB_VERSION 12
#define DB_VERSION_STR "12"
const char *db_path;
#define MAGISKDB db_path
#define LOGE(...) fprintf(stderr, __VA_ARGS__)
#define sql_chk_log(fn, ...) if (fn(__VA_ARGS__) != SQLITE_OK) return nullptr;
bool load_sqlite() { return true; }
'''
        program = support + native + r'''
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    db_path = argv[1];
    sqlite3 *db = open_and_init_db();
    if (!db) return 1;
    sqlite3_close(db);
    return 0;
}
'''
        path = cls.binary.with_suffix(".cpp")
        path.write_text(program)
        subprocess.run(["c++", "-std=c++20", str(path),
                        "-I", str(ROOT / "native/src/core"), "-lsqlite3", "-o", str(cls.binary)],
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def database(self, path: Path, version=13):
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("""
CREATE TABLE policies(uid INT PRIMARY KEY, policy INT, until INT, logging INT, notification INT);
CREATE TABLE settings(key TEXT PRIMARY KEY, value INT);
CREATE TABLE strings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE denylist(package_name TEXT, process TEXT, PRIMARY KEY(package_name,process));
CREATE TABLE hidelist(package_name TEXT, process TEXT, PRIMARY KEY(package_name,process));
CREATE TABLE sulist(package_name TEXT, process TEXT, PRIMARY KEY(package_name,process));
CREATE TABLE hide_migration_v13(id INTEGER PRIMARY KEY, strategy TEXT,
 source_hidelist_rows INT, source_denylist_rows INT, source_sulist_rows INT,
 overlap_rows INT, migrated_rows INT, malformed_hidelist_rows INT, sulist_enabled INT);
INSERT INTO policies VALUES(2000,2,0,0,0),(10001,1,0,1,1);
INSERT INTO settings VALUES('sulist',1),('denylist',0),('zygisk',0);
INSERT INTO strings VALUES('retained','user setting');
INSERT INTO denylist VALUES('one','one'),('two','two');
INSERT INTO hidelist SELECT * FROM denylist;
INSERT INTO sulist VALUES('allowed','allowed');
INSERT INTO hide_migration_v13 VALUES(1,'union-preserve-legacy',2,1,1,1,1,0,1);
""")
            db.execute(f"PRAGMA user_version={version}")

    def dump(self, path):
        with closing(sqlite3.connect(path)) as db, db:
            self.assertEqual("ok", db.execute("PRAGMA integrity_check").fetchone()[0])
            return list(db.iterdump()), db.execute("PRAGMA user_version").fetchone()[0]

    def run_native(self, path, failure=None):
        env = dict(os.environ)
        if failure:
            env["FAIL_SQL"] = failure
        return subprocess.run([str(self.binary), str(path)], env=env,
                              capture_output=True, text=True, timeout=10)

    def test_newer_schemas_are_preserved_without_conversion(self):
        cases = [
            (13, None),
            (14, None),
            (13, "DROP TABLE hide_migration_v13"),
            (13, "UPDATE hide_migration_v13 SET migrated_rows=99"),
            (13, "UPDATE hide_migration_v13 SET strategy='unknown'"),
            (13, "ALTER TABLE policies RENAME COLUMN until TO future_expiry"),
        ]
        for version, mutation in cases:
            with self.subTest(version=version, mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "magisk.db"
                self.database(path, version)
                if mutation:
                    with closing(sqlite3.connect(path)) as db, db:
                        db.execute(mutation)
                before = path.read_bytes()
                self.assertNotEqual(0, self.run_native(path).returncode)
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(version, self.dump(path)[1])

    def test_v12_keeps_legacy_tables_and_policies(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "magisk.db"
            self.database(path, 12)
            before = path.read_bytes()
            self.assertEqual(0, self.run_native(path).returncode)
            self.assertEqual(before, path.read_bytes())

    def test_fresh_has_no_backup_and_separate_empty_lists(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "magisk.db"
            self.assertEqual(0, self.run_native(path).returncode)
            self.assertFalse(path.with_suffix(".db.hide-v1.bak").exists())
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(12, db.execute("PRAGMA user_version").fetchone()[0])
                for table in ("denylist", "hidelist", "sulist"):
                    self.assertEqual([], db.execute(f"SELECT * FROM {table}").fetchall())
                self.assertEqual(1, db.execute("SELECT COUNT(*) FROM hide_migration_v13").fetchone()[0])

    def test_legacy_union_backup_and_no_resurrection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "magisk.db"
            self.database(path, 12)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("DROP TABLE hide_migration_v13")
                db.execute("INSERT INTO hidelist VALUES('legacy.app','legacy.app')")
                db.execute("INSERT INTO hidelist VALUES(NULL,'bad')")
                db.execute("INSERT INTO hidelist VALUES('','')")
            self.assertEqual(0, self.run_native(path).returncode)
            backup = Path(str(path) + ".hide-v1.bak")
            self.assertEqual(0o600, backup.stat().st_mode & 0o777)
            original = backup.read_bytes()
            with closing(sqlite3.connect(path)) as db, db:
                self.assertIn(('legacy.app', 'legacy.app'), db.execute("SELECT * FROM denylist").fetchall())
                self.assertEqual([('allowed', 'allowed')], db.execute("SELECT * FROM sulist").fetchall())
                self.assertNotIn(('allowed', 'allowed'), db.execute("SELECT * FROM denylist").fetchall())
                db.execute("DELETE FROM denylist WHERE package_name='legacy.app'")
            self.assertEqual(0, self.run_native(path).returncode)
            self.assertEqual(original, backup.read_bytes())
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(0, db.execute("SELECT COUNT(*) FROM denylist WHERE package_name='legacy.app'").fetchone()[0])

    def test_invalid_marker_and_unsafe_backup_fail_without_union(self):
        for fault in ("marker", "symlink", "permissions", "corrupt"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "magisk.db"
                self.database(path, 12)
                with closing(sqlite3.connect(path)) as db, db:
                    if fault == "marker":
                        db.execute("UPDATE hide_migration_v13 SET migrated_rows=999")
                    else:
                        db.execute("DROP TABLE hide_migration_v13")
                backup = Path(str(path) + ".hide-v1.bak")
                if fault == "symlink": backup.symlink_to(path)
                if fault in ("permissions", "corrupt"):
                    backup.write_bytes(b"invalid database")
                    backup.chmod(0o644 if fault == "permissions" else 0o600)
                before = path.read_bytes()
                self.assertNotEqual(0, self.run_native(path).returncode)
                self.assertEqual(before, path.read_bytes())

    def test_failed_transaction_does_not_publish_partial_union(self):
        source = (ROOT / "native/src/core/db_migrations.hpp").read_text()
        reconcile = source.split('HIDE_TABLE_RECONCILE[] = R"sql(', 1)[1].split(')sql";', 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "magisk.db"
            self.database(path, 12)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("DROP TABLE hide_migration_v13")
                db.execute("INSERT INTO hidelist VALUES('new.app','new.app')")
            before = self.dump(path)
            self.assertNotEqual(0, self.run_native(path, reconcile).returncode)
            self.assertEqual(before, self.dump(path))
            self.assertEqual(0, self.run_native(path).returncode)


if __name__ == "__main__":
    unittest.main()

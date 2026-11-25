"""TOC filtering for pg_restore when the dumped schema already exists in a fresh target."""
from app.services.backups.restore import restore_list

LISTING = b''';
; Archive created at 2026-11-25 15:21:55 UTC
;
5; 2615 2200 SCHEMA - public pg_database_owner
3669; 0 0 COMMENT - SCHEMA public pg_database_owner
230; 1259 16390 TABLE public persons project2_prod
231; 1259 16391 TABLE public public_holidays project2_prod
4000; 2606 16400 CONSTRAINT public persons persons_pkey project2_prod
6; 2615 2201 SCHEMA - publicity owner
'''


def test_existing_public_schema_entries_are_removed_only():
    result = restore_list(LISTING, 'public')
    assert b'SCHEMA - public pg_database_owner' not in result
    assert b'COMMENT - SCHEMA public' not in result
    for kept in (b'TABLE public persons', b'TABLE public public_holidays', b'CONSTRAINT public persons',
                 b'SCHEMA - publicity owner', b'; Archive created'):
        assert kept in result
    assert len(result.splitlines()) == len(LISTING.splitlines()) - 2


def test_missing_schema_keeps_full_listing():
    assert restore_list(LISTING, None) == LISTING


def test_windows_line_endings_and_other_schema():
    crlf = LISTING.replace(b'\n', b'\r\n')
    result = restore_list(crlf, 'public')
    assert b'SCHEMA - public pg' not in result and result.endswith(b'\r\n')
    custom = b'7; 2615 3000 SCHEMA - project2_test_ab12 owner\n9; 1259 1 TABLE project2_test_ab12 t owner\n'
    assert restore_list(custom, 'project2_test_ab12') == b'9; 1259 1 TABLE project2_test_ab12 t owner\n'

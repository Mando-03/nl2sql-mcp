from __future__ import annotations

import pytest

from nl2sql_mcp.schema_tools.utils import is_archive_label


@pytest.mark.parametrize(
    "label,expected",
    [
        ("dbo.Orders_Archive", True),
        ("dbo.Cities_ARCHIVED", True),
        ("dbo.Invoices_Hist", True),
        ("dbo.Invoices_History", True),
        ("dbo.InvoicesBackup2", True),
        ("dbo.Backup", True),
        ("dbo.Tmp", True),
        ("dbo.Temp", True),
        ("dbo.Old", True),
        ("dbo.Snapshot_2023_06", True),
        ("dbo.Snap_20240601", True),
        ("dbo.OrdersHistory2021", True),
        ("dbo.CustomersArchive2020", True),
        ("dbo.Archive_Orders", True),
        ("dbo.History_Customers", True),
        ("dbo.ActiveCustomers", False),
        ("dbo.Orders", False),
        ("dbo.SearchLog", False),  # avoid matching partial 'arch' in 'search'
        ("dbo.BackOrder", False),  # 'back' is not 'backup/bak'
    ],
)
def test_is_archive_label(label: str, expected: bool) -> None:
    assert is_archive_label(label) is expected

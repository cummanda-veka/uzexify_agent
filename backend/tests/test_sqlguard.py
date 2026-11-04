import pytest

from uzexify.sqlguard import SqlRejected, validate_sql


def test_allows_cte_select():
    validate_sql(
        "WITH t AS (SELECT product, count(*) n FROM v_deals GROUP BY product) "
        "SELECT * FROM t ORDER BY n DESC LIMIT 5"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM deals",
        "SELECT 1; SELECT 2",
        "SELECT pg_sleep(1)",
        "WITH x AS (DELETE FROM deals RETURNING *) SELECT * FROM x",
        "SELECT * FROM pg_authid",
        "SELECT * FROM pg_catalog.pg_class",
        "SELECT * INTO t FROM deals",
    ],
)
def test_rejects(sql):
    with pytest.raises(SqlRejected):
        validate_sql(sql)

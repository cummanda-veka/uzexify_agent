import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg
from psycopg import sql

from uzexify.settings import get_settings
from uzexify.text import name_key, product_key

REGIONS = {
    "Toshkent shahri": "г. Ташкент",
    "Toshkent viloyati": "Ташкентская область",
    "Andijon viloyati": "Андижанская область",
    "Buxoro viloyati": "Бухарская область",
    "Farg‘ona viloyati": "Ферганская область",
    "Jizzax viloyati": "Джизакская область",
    "Namangan viloyati": "Наманганская область",
    "Navoiy viloyati": "Навоийская область",
    "Qashqadaryo viloyati": "Кашкадарьинская область",
    "Qoraqalpog‘iston Respublikasi": "Республика Каракалпакстан",
    "Samarqand viloyati": "Самаркандская область",
    "Sirdaryo viloyati": "Сырдарьинская область",
    "Surxondaryo viloyati": "Сурхандарьинская область",
    "Xorazm viloyati": "Хорезмская область",
}
EXPECTED = {
    "deals": 500000,
    "contracts": 6616,
    "participants": 14392,
    "brokers": 120,
    "usd_rates": 1765,
    "products": 697,
    "regions": 14,
}

# Each mapping is (database column, CSV heading, conversion).
BROKERS = [
    ("code", "Код брокера", "text"),
    ("name", "Наименование", "text"),
    ("inn", "ИНН", "text"),
    ("region_uz", "Регион", "region"),
]
PARTICIPANTS = [
    ("inn", "ИНН", "text"),
    ("name", "Наименование", "text"),
    ("region_uz", "Регион", "region"),
    ("activity", "Вид деятельности", "text"),
    ("role", "Роль", "text"),
    ("vat_payer", "Плательщик НДС", "bool"),
]
CONTRACTS = list(
    zip(
        [
            "contract_no",
            "product_name",
            "brand",
            "size",
            "grade",
            "product_type",
            "product_class",
            "tnved_code",
            "product_group",
            "product_category",
            "industry",
            "unit",
            "lot_size",
            "currency",
            "base_price",
            "deposit_pct",
            "delivery_basis",
            "region_ru",
            "warehouse_address",
            "trade_type",
            "contract_type",
            "contract_form",
            "payment_term_days",
            "delivery_term_days",
            "packaging",
            "seller_inn",
            "registered_on",
            "valid_until",
        ],
        [
            "Номер контракта",
            "Наименование продукта",
            "Марка товара",
            "Размер товара",
            "Сорт товара",
            "Тип товара",
            "Класс товара",
            "Код ТН ВЭД",
            "Группа товара",
            "Категория товара",
            "Отрасль промышленности",
            "Единица измерения",
            "Лот",
            "Валюта",
            "Базисная цена",
            "Сумма залога",
            "Базис поставки",
            "Регион",
            "Адрес склада",
            "Тип торгов",
            "Тип контракта",
            "Форма контракта",
            "Срок оплаты",
            "Срок поставки",
            "Упаковка",
            "ИНН продавца",
            "Дата регистрации",
            "Действует до",
        ],
        [
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "number",
            "text",
            "number",
            "percent",
            "text",
            "region_ru",
            "text",
            "text",
            "text",
            "text",
            "integer",
            "integer",
            "text",
            "text",
            "date",
            "date",
        ],
        strict=True,
    )
)
DEALS = list(
    zip(
        [
            "deal_no",
            "deal_date",
            "deal_time",
            "trade_type",
            "quantity_lots",
            "amount",
            "start_price",
            "contract_no",
            "product",
            "lot_size",
            "unit",
            "region_uz",
            "contract_type",
            "contract_form",
            "status",
            "seller_inn",
            "buyer_inn",
            "seller_broker",
            "buyer_broker",
            "paid_on",
            "delivered_on",
            "delivered_lots",
        ],
        [
            "Номер сделки",
            "Дата сделки",
            "Время сделки",
            "Тип торгов",
            "Количество",
            "Сумма сделки",
            "Стартовая цена",
            "Номер контракта",
            "Наименование товара",
            "Лот",
            "Единица измерения",
            "Регион",
            "Тип контракта",
            "Форма контракта",
            "Состояние сделки",
            "ИНН продавца",
            "ИНН покупателя",
            "Брокер продавца",
            "Брокер покупателя",
            "Дата оплаты",
            "Дата поставки",
            "Поставлено",
        ],
        [
            "integer",
            "date",
            "time",
            "text",
            "number",
            "number",
            "number",
            "text",
            "text",
            "number",
            "text",
            "region",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "date",
            "date",
            "number",
        ],
        strict=True,
    )
)
RATES = [("rate_date", "Дата", "date"), ("uzs_per_usd", "Курс", "number")]


def convert(value: str, kind: str):
    if not value:
        return None
    if kind in ("number", "integer", "percent"):
        if kind == "percent":
            if not value.endswith("%"):
                raise ValueError("expected percent")
            value = value[:-1]
        cleaned = value.translate(str.maketrans("", "", " \u00a0\u202f"))
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", cleaned):
            raise ValueError("invalid number")
        number = Decimal(cleaned)
        if kind == "integer":
            if number != number.to_integral_value():
                raise ValueError("expected integer")
            return int(number)
        return number
    if kind == "date":
        return datetime.strptime(value, "%d.%m.%Y").date()
    if kind == "time":
        return datetime.strptime(value, "%H:%M:%S").time()
    if kind == "bool":
        if value not in ("Да", "Нет"):
            raise ValueError("expected Да or Нет")
        return value == "Да"
    if kind == "region" and value not in REGIONS:
        raise ValueError("unknown region")
    if kind == "region_ru" and value not in REGIONS.values():
        raise ValueError("unknown region")
    return value


def load_file(conn, path, table, mapping):
    columns = [item[0] for item in mapping]
    if table in ("brokers", "participants"):
        columns.append("name_key")
    if table == "contracts":
        columns.append("region_uz")
    command = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    reverse_regions = {ru: uz for uz, ru in REGIONS.items()}
    with path.open(encoding="utf-8", newline="") as source, conn.cursor() as cur:
        reader = csv.DictReader(source)
        missing = {heading for _, heading, _ in mapping} - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns: {sorted(missing)}")
        with cur.copy(command) as copy:
            for row in reader:
                values = []
                for _, heading, kind in mapping:
                    try:
                        values.append(convert(row[heading], kind))
                    except (ValueError, InvalidOperation, TypeError) as exc:
                        raise ValueError(f"{path}:{reader.line_num}:{heading}: {exc}") from exc
                if table in ("brokers", "participants"):
                    values.append(name_key(row["Наименование"]))
                if table == "contracts":
                    values.append(reverse_regions[row["Регион"]])
                copy.write_row(values)


def setup_agent_role(conn, password):
    """Create or refresh the read-only `uzex_agent` role. Idempotent; roles live outside pg_dump."""
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'uzex_agent'").fetchone()
    if not exists:
        conn.execute("CREATE ROLE uzex_agent LOGIN")
    # set_config cannot set passwords; SQL literal quoting is provided by psycopg.
    conn.execute(sql.SQL("ALTER ROLE uzex_agent WITH LOGIN PASSWORD {}").format(sql.Literal(password)))
    db = conn.info.dbname
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO uzex_agent").format(sql.Identifier(db)))
    conn.execute("GRANT USAGE ON SCHEMA public TO uzex_agent")
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO uzex_agent")
    conn.execute("ALTER ROLE uzex_agent SET default_transaction_read_only = on")
    conn.execute("ALTER ROLE uzex_agent SET statement_timeout = '10s'")
    conn.execute("ALTER ROLE uzex_agent SET search_path = public")
    conn.execute(sql.SQL("REVOKE TEMP ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))


def grant():
    """Refresh the agent role on an existing database (e.g. one restored from a dump)."""
    settings = get_settings()
    if not settings.agent_db_password:
        raise ValueError("AGENT_DB_PASSWORD is required")
    with psycopg.connect(settings.database_url) as conn, conn.transaction():
        setup_agent_role(conn, settings.agent_db_password)
    print("uzex_agent role ready")


def ingest(data_dir):
    settings = get_settings()
    if not settings.agent_db_password:
        raise ValueError("AGENT_DB_PASSWORD is required")
    data = Path(data_dir)
    with psycopg.connect(settings.database_url) as conn:  # noqa: SIM117 - keep transaction scope explicit
        with conn.transaction():
            schema = (Path(__file__).parent / "db" / "schema.sql").read_text(encoding="utf-8")
            conn.execute(schema)  # ty: ignore[no-matching-overload] - trusted file from package
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO regions VALUES (%s, %s)", list(REGIONS.items()))
            for filename, table, mapping in [
                ("brokers.csv", "brokers", BROKERS),
                ("participants.csv", "participants", PARTICIPANTS),
                ("contracts.csv", "contracts", CONTRACTS),
                ("usd_rates.csv", "usd_rates", RATES),
            ]:
                load_file(conn, data / filename, table, mapping)
            for year in range(2022, 2027):
                load_file(conn, data / f"deals_{year}.csv", "deals", DEALS)
            conn.execute("""INSERT INTO products (product, product_name, product_category, industry, unit, n_deals, first_deal, last_deal)
                SELECT d.product, mode() WITHIN GROUP (ORDER BY c.product_name), mode() WITHIN GROUP (ORDER BY c.product_category),
                mode() WITHIN GROUP (ORDER BY c.industry), mode() WITHIN GROUP (ORDER BY d.unit), count(*), min(d.deal_date), max(d.deal_date)
                FROM deals d JOIN contracts c USING (contract_no) GROUP BY d.product""")
            with conn.cursor() as cur:
                products = cur.execute("SELECT product FROM products").fetchall()
                cur.executemany(
                    "UPDATE products SET name_key = %s WHERE product = %s",
                    [(product_key(p), p) for (p,) in products],
                )
            conn.execute("""UPDATE participants p SET n_deals_sold = COALESCE(s.n, 0), n_deals_bought = COALESCE(b.n, 0)
                FROM (SELECT inn FROM participants) x LEFT JOIN (SELECT seller_inn, count(*) n FROM deals GROUP BY seller_inn) s ON s.seller_inn=x.inn
                LEFT JOIN (SELECT buyer_inn, count(*) n FROM deals GROUP BY buyer_inn) b ON b.buyer_inn=x.inn WHERE p.inn=x.inn""")
            conn.execute("""UPDATE brokers b SET n_deals = counts.n FROM (SELECT code, count(*) n FROM
                (SELECT seller_broker AS code FROM deals UNION ALL SELECT buyer_broker FROM deals) t GROUP BY code) counts WHERE b.code=counts.code""")
            counts = {}
            for table, expected in EXPECTED.items():
                row = conn.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                ).fetchone()
                count = row[0] if row else 0
                if count != expected:
                    raise ValueError(f"{table}: expected {expected}, got {count}")
                counts[table] = count
            setup_agent_role(conn, settings.agent_db_password)
            conn.execute("ANALYZE")
    for table, count in counts.items():
        print(f"{table} {count}")

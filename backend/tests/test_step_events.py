from uzexify.agent import _result_event


def test_retried_validation_errors_are_not_reported_as_rows():
    # Pydantic AI reports argument-validation retries as list content with outcome="retried".
    errors = [{"type": "missing", "loc": ["sql"], "msg": "Field required"}]
    step = _result_event("c1", "run_sql", errors, "retried")
    assert step["ok"] is False
    assert step["call_id"] == "c1"


def test_successful_sql_reports_row_count():
    step = _result_event("c2", "run_sql", {"row_count": 5, "rows": []}, "success")
    assert step["ok"] is True
    assert step["label_ru"] == "Получено строк: 5"

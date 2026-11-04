from uzexify.agent.deps import EvidenceLog


def test_parallel_sql_calls_get_distinct_ids_before_results_arrive():
    ev = EvidenceLog()
    first, second = ev.next_sql_id(), ev.next_sql_id()  # both reserved before anything is appended
    assert first != second

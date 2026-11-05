from uzexify.bot import ChatSessions


def test_session_is_stable_until_new_chat():
    s = ChatSessions()
    first = s.get(1)
    assert s.get(1) == first
    renewed = s.reset(1)
    assert renewed != first
    assert s.get(1) == renewed


def test_chats_and_restarts_do_not_share_sessions():
    s = ChatSessions()
    assert s.get(1) != s.get(2)
    # A restarted bot (new instance) must not resume the old conversation.
    assert ChatSessions().get(1) != s.get(1)

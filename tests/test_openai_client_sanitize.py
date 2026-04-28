import tradingagents.llm_clients.openai_client as oc


def test_sanitize_dict_role_tool_to_function():
    src = {"role": "tool", "content": "hello"}
    out = oc._sanitize_messages(src)
    assert out["role"] == "function"
    assert out["content"] == "hello"


def test_sanitize_nested_list_and_dict():
    src = [
        {"role": "system", "content": "init"},
        {"role": "tool", "content": "tool output"},
        [{"role": "tool", "content": "deep"}],
    ]
    out = oc._sanitize_messages(src)
    assert isinstance(out, list)
    assert out[1]["role"] == "function"
    assert out[2][0]["role"] == "function"

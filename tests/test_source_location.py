from lecture.context import ExecutionContext, execution_scope


def test_source_location_uses_helper_file_instead_of_context_entry():
    namespace = {"__name__": "author_helpers"}
    exec(
        compile(
            'from lecture import text\ndef helper():\n    text("hello")\n',
            "author_helpers.py",
            "exec",
        ),
        namespace,
    )
    with execution_scope(ExecutionContext(source_file="entry.py")) as ctx:
        namespace["helper"]()
    location = ctx.log.to_list()[0]["source_location"]
    assert location == {"file": "author_helpers.py", "line": 3, "func": "helper"}

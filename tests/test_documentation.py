from scripts.check_docs import maintained_documents, validate_documentation


def test_maintained_documentation_is_complete_and_linked() -> None:
    assert len(maintained_documents()) >= 18
    assert validate_documentation() == []

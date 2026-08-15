import pytest
from app.agent.tools.calculator import calculator
from app.agent.tools.filesystem import read_file, PROJECT_ROOT
from app.agent.tools.time import get_time


def test_calculator_valid():
    assert calculator("25 * 4") == 100


def test_calculator_invalid_expression():
    with pytest.raises(ValueError):
        calculator("import os")


def test_calculator_syntax_error():
    with pytest.raises(Exception):
        calculator("25 +")


def test_read_file_missing():
    with pytest.raises(FileNotFoundError):
        read_file("this_file_does_not_exist.txt")


def test_read_file_traversal():
    with pytest.raises(ValueError):
        read_file("../../../../../../etc/passwd")


def test_read_file_success():
    # requirements.txt should exist at PROJECT_ROOT after step 3
    target = PROJECT_ROOT / "requirements.txt"
    assert target.exists(), "requirements.txt missing — run pip freeze first"
    content = read_file("requirements.txt")
    assert isinstance(content, str)
    assert len(content) > 0


def test_get_time_returns_iso_string():
    result = get_time()
    assert isinstance(result, str)
    from datetime import datetime
    parsed = datetime.fromisoformat(result)  # should not raise
import pytest

from helpers import ListLog


@pytest.fixture
def log():
    return ListLog()

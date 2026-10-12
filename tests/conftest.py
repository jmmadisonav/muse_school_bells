import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import ListLog  # noqa: E402


@pytest.fixture
def log():
    return ListLog()

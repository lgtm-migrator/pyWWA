"""Test cf6_parser."""
# 3rd Party
from pyiem.util import utc
import pytest

# Local
import pywwa
from pywwa.workflows import cf6_parser
from pywwa.testing import get_example_file


@pytest.mark.parametrize("database", ["iem"])
def test_processor(cursor):
    """Test basic parsing."""
    data = get_example_file("CF6.txt")
    pywwa.CTX.utcnow = utc(2020, 11, 25, 9, 20)
    prod = cf6_parser.processor(cursor, data)
    assert prod.valid == pywwa.CTX.utcnow

"""Test fake_afos_dump."""
# 3rd Party
import pytest
from pyiem.util import utc

# Local
import pywwa
from pywwa.workflows import fake_afos_dump
from pywwa.testing import get_example_file


@pytest.mark.parametrize("database", ["afos"])
def test_processor(cursor):
    """Test basic parsing."""
    data = get_example_file("CWA.txt")
    pywwa.CTX.utcnow = utc(2011, 3, 3, 6, 16)
    tp = fake_afos_dump.really_process_data(cursor, data)
    assert tp.valid == utc(2011, 3, 3, 1, 5)

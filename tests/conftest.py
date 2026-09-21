import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # UI tests need no display


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])

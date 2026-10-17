"""Typed integration configuration failures."""
from ..domain.contracts import Denied

class NotConfigured(Denied):
    pass

# finance/importers/__init__.py
from .revolut import RevolutImporter
from .seb import SEBImporter
from .swedbank import SwedbankImporter

IMPORTERS = {
    "revolut": RevolutImporter(),
    "seb": SEBImporter(),
    "swedbank": SwedbankImporter(),
}

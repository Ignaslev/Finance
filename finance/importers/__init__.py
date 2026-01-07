# finance/importers/__init__.py
from .revolut import RevolutImporter
from .seb import SEBImporter

IMPORTERS = {
    "revolut": RevolutImporter(),
    "seb": SEBImporter(),
}

from abc import ABC

from app.commons.database.infra import DB


class PayoutBankDBRepository(ABC):
    """
    Base repository containing Payout_BankDB connection resources
    """

    _database: DB

    def __init__(self, *, _database: DB):
        self._database = _database

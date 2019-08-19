import asyncio
from datetime import datetime
import uuid

import pytest
import pytest_mock
from asyncpg import DataError

from app.commons.context.app_context import AppContext
from app.commons.database.infra import DB
from app.commons.types import CurrencyType
from app.ledger.core.mx_transaction.data_types import (
    GetMxLedgerByIdInput,
    GetMxScheduledLedgerOutput,
    GetMxScheduledLedgerInput,
)
from app.ledger.core.mx_transaction.exceptions import (
    MxTransactionCreationError,
    LedgerErrorCode,
    ledger_error_message_maps,
)
from app.ledger.core.mx_transaction.processor import create_mx_transaction_impl
from app.ledger.core.mx_transaction.types import (
    MxScheduledLedgerIntervalType,
    MxLedgerType,
    MxLedgerStateType,
    MxTransactionType,
)
from app.ledger.repository.mx_ledger_repository import (
    MxLedgerRepository,
    InsertMxLedgerInput,
)
from app.ledger.repository.mx_scheduled_ledger_repository import (
    InsertMxScheduledLedgerInput,
    MxScheduledLedgerRepository,
)
from app.ledger.repository.mx_transaction_repository import MxTransactionRepository


class TestMxTransactionProcessor:
    pytestmark = [pytest.mark.asyncio]

    async def test_get_open_mx_scheduled_ledger_success(
        self,
        mocker: pytest_mock.MockFixture,
        ledger_app_context: AppContext,
        ledger_paymentdb: DB,
    ):
        ledger_repo = MxLedgerRepository(context=ledger_app_context)
        scheduled_ledger_repo = MxScheduledLedgerRepository(context=ledger_app_context)
        transaction_repo = MxTransactionRepository(context=ledger_app_context)
        ledger_id = uuid.uuid4()
        payment_account_id = str(uuid.uuid4())
        routing_key = datetime(2019, 8, 1)
        interval_type = MxScheduledLedgerIntervalType.WEEKLY

        mx_scheduled_ledger_to_insert = InsertMxScheduledLedgerInput(
            id=ledger_id,
            payment_account_id=payment_account_id,
            ledger_id=ledger_id,
            interval_type=MxScheduledLedgerIntervalType.WEEKLY.value,
            start_time=datetime(2019, 7, 29, 7),
            end_time=datetime(2019, 8, 5, 7),
        )
        ledger_to_insert = InsertMxLedgerInput(
            id=ledger_id,
            type=MxLedgerType.SCHEDULED.value,
            currency=CurrencyType.USD.value,
            state=MxLedgerStateType.OPEN.value,
            balance=2000,
            payment_account_id=payment_account_id,
        )
        await ledger_repo.insert_mx_ledger(ledger_to_insert)
        await scheduled_ledger_repo.insert_mx_scheduled_ledger(
            mx_scheduled_ledger_to_insert
        )
        mx_transaction = await create_mx_transaction_impl(
            app_context=ledger_app_context,
            req_context=mocker.Mock(),
            payment_account_id=payment_account_id,
            amount=2000,
            currency=CurrencyType.USD,
            routing_key=routing_key,
            interval_type=interval_type,
            mx_ledger_repository=ledger_repo,
            mx_scheduled_ledger_repository=scheduled_ledger_repo,
            mx_transaction_repository=transaction_repo,
            idempotency_key=str(uuid.uuid4()),
            target_type=MxTransactionType.MERCHANT_DELIVERY,
        )

        assert mx_transaction is not None
        assert mx_transaction.ledger_id == ledger_id
        assert mx_transaction.currency == CurrencyType.USD
        assert mx_transaction.routing_key == routing_key
        assert mx_transaction.amount == 2000
        assert mx_transaction.target_type == MxTransactionType.MERCHANT_DELIVERY

        get_scheduled_ledger_request = GetMxScheduledLedgerInput(
            payment_account_id=payment_account_id,
            routing_key=routing_key,
            interval_type=MxScheduledLedgerIntervalType.WEEKLY,
        )
        mx_scheduled_ledger = await scheduled_ledger_repo.get_open_mx_scheduled_ledger_for_period(
            get_scheduled_ledger_request
        )
        assert mx_scheduled_ledger is not None

        get_mx_ledger_request = GetMxLedgerByIdInput(id=ledger_id)
        mx_ledger = await ledger_repo.get_ledger_by_id(get_mx_ledger_request)
        assert mx_ledger is not None
        assert mx_ledger.balance == 4000

    async def test_get_open_mx_ledger_success(
        self,
        mocker: pytest_mock.MockFixture,
        ledger_app_context: AppContext,
        ledger_paymentdb: DB,
    ):
        ledger_repo = MxLedgerRepository(context=ledger_app_context)
        scheduled_ledger_repo = MxScheduledLedgerRepository(context=ledger_app_context)
        transaction_repo = MxTransactionRepository(context=ledger_app_context)
        ledger_id = uuid.uuid4()
        payment_account_id = str(uuid.uuid4())
        routing_key = datetime(2019, 8, 1)
        interval_type = MxScheduledLedgerIntervalType.WEEKLY

        mx_scheduled_ledger_to_insert = InsertMxScheduledLedgerInput(
            id=ledger_id,
            payment_account_id=payment_account_id,
            ledger_id=ledger_id,
            interval_type=MxScheduledLedgerIntervalType.WEEKLY.value,
            start_time=datetime(2019, 7, 29, 7),
            end_time=datetime(2019, 8, 5, 7),
        )
        ledger_to_insert = InsertMxLedgerInput(
            id=ledger_id,
            type=MxLedgerType.SCHEDULED.value,
            currency=CurrencyType.USD.value,
            state=MxLedgerStateType.PAID.value,
            balance=2000,
            payment_account_id=payment_account_id,
        )
        ledger_id_correct = uuid.uuid4()
        ledger_to_insert_correct = InsertMxLedgerInput(
            id=ledger_id_correct,
            type=MxLedgerType.SCHEDULED.value,
            currency=CurrencyType.USD.value,
            state=MxLedgerStateType.OPEN.value,
            balance=2000,
            payment_account_id=payment_account_id,
        )

        await ledger_repo.insert_mx_ledger(ledger_to_insert)
        await scheduled_ledger_repo.insert_mx_scheduled_ledger(
            mx_scheduled_ledger_to_insert
        )
        await ledger_repo.insert_mx_ledger(ledger_to_insert_correct)

        mx_transaction = await create_mx_transaction_impl(
            app_context=ledger_app_context,
            req_context=mocker.Mock(),
            payment_account_id=payment_account_id,
            amount=2000,
            currency=CurrencyType.USD,
            routing_key=routing_key,
            interval_type=interval_type,
            mx_ledger_repository=ledger_repo,
            mx_scheduled_ledger_repository=scheduled_ledger_repo,
            mx_transaction_repository=transaction_repo,
            idempotency_key=str(uuid.uuid4()),
            target_type=MxTransactionType.MERCHANT_DELIVERY,
        )
        assert mx_transaction is not None
        assert mx_transaction.ledger_id == ledger_id_correct
        assert mx_transaction.currency == CurrencyType.USD
        assert mx_transaction.routing_key == routing_key
        assert mx_transaction.amount == 2000
        assert mx_transaction.target_type == MxTransactionType.MERCHANT_DELIVERY

        get_mx_ledger_request = GetMxLedgerByIdInput(id=ledger_to_insert_correct.id)
        mx_ledger = await ledger_repo.get_ledger_by_id(get_mx_ledger_request)
        assert mx_ledger is not None
        assert mx_ledger.balance == 4000

    async def test_create_mx_ledger_success(
        self,
        mocker: pytest_mock.MockFixture,
        ledger_app_context: AppContext,
        ledger_paymentdb: DB,
    ):
        payment_account_id = str(uuid.uuid4())
        routing_key = datetime(2019, 8, 1)
        mx_ledger_repository = MxLedgerRepository(context=ledger_app_context)
        mx_scheduled_repository = MxScheduledLedgerRepository(
            context=ledger_app_context
        )
        transaction_repo = MxTransactionRepository(context=ledger_app_context)

        mx_transaction = await create_mx_transaction_impl(
            app_context=ledger_app_context,
            req_context=mocker.Mock(),
            payment_account_id=payment_account_id,
            amount=2000,
            currency=CurrencyType.USD,
            routing_key=routing_key,
            interval_type=MxScheduledLedgerIntervalType.WEEKLY,
            mx_ledger_repository=mx_ledger_repository,
            mx_scheduled_ledger_repository=mx_scheduled_repository,
            mx_transaction_repository=transaction_repo,
            idempotency_key=str(uuid.uuid4()),
            target_type=MxTransactionType.MERCHANT_DELIVERY,
        )

        assert mx_transaction is not None
        assert mx_transaction.currency == CurrencyType.USD
        assert mx_transaction.routing_key == datetime(2019, 8, 1)
        assert mx_transaction.amount == 2000
        assert mx_transaction.target_type == MxTransactionType.MERCHANT_DELIVERY

        get_scheduled_ledger_request = GetMxScheduledLedgerInput(
            payment_account_id=payment_account_id,
            routing_key=routing_key,
            interval_type=MxScheduledLedgerIntervalType.WEEKLY,
        )
        mx_scheduled_ledger = await mx_scheduled_repository.get_open_mx_scheduled_ledger_for_period(
            get_scheduled_ledger_request
        )
        assert mx_scheduled_ledger is not None
        assert mx_scheduled_ledger.ledger_id == mx_transaction.ledger_id

        get_mx_ledger_request = GetMxLedgerByIdInput(id=mx_transaction.ledger_id)
        mx_ledger = await mx_ledger_repository.get_ledger_by_id(get_mx_ledger_request)
        assert mx_ledger is not None
        assert mx_ledger.balance == 2000

    async def test_insert_txn_and_ledger_raise_data_error(
        self, mocker: pytest_mock.MockFixture, ledger_app_context: AppContext
    ):
        error = DataError()
        mocker.patch(
            "app.ledger.repository.mx_transaction_repository.MxTransactionRepository.create_ledger_and_insert_mx_transaction",
            side_effect=error,
        )
        payment_account_id = str(uuid.uuid4())
        mx_ledger_repository = MxLedgerRepository(context=ledger_app_context)
        mx_scheduled_repository = MxScheduledLedgerRepository(
            context=ledger_app_context
        )
        transaction_repo = MxTransactionRepository(context=ledger_app_context)
        with pytest.raises(MxTransactionCreationError) as e:
            await create_mx_transaction_impl(
                app_context=ledger_app_context,
                req_context=mocker.Mock(),
                payment_account_id=payment_account_id,
                amount=2000,
                currency=CurrencyType.USD,
                routing_key=datetime(2019, 8, 1),
                interval_type=MxScheduledLedgerIntervalType.WEEKLY,
                mx_ledger_repository=mx_ledger_repository,
                mx_scheduled_ledger_repository=mx_scheduled_repository,
                mx_transaction_repository=transaction_repo,
                idempotency_key=str(uuid.uuid4()),
                target_type=MxTransactionType.MERCHANT_DELIVERY,
            )
            assert e.error_code == LedgerErrorCode.MX_TXN_CREATE_ERROR
            assert (
                e.error_message
                == ledger_error_message_maps[LedgerErrorCode.MX_TXN_CREATE_ERROR.value]
            )

    async def test_insert_txn_and_ledger_raise_unique_violate_error(
        self, mocker: pytest_mock.MockFixture, ledger_app_context: AppContext
    ):
        payment_account_id = str(uuid.uuid4())
        ledger_id = uuid.uuid4()
        mx_ledger_repository = MxLedgerRepository(context=ledger_app_context)
        mx_scheduled_repository = MxScheduledLedgerRepository(
            context=ledger_app_context
        )
        transaction_repo = MxTransactionRepository(context=ledger_app_context)

        mx_scheduled_ledger_to_insert = InsertMxScheduledLedgerInput(
            id=ledger_id,
            payment_account_id=payment_account_id,
            ledger_id=ledger_id,
            interval_type=MxScheduledLedgerIntervalType.WEEKLY.value,
            start_time=datetime(2019, 7, 29, 7),
            end_time=datetime(2019, 8, 5, 7),
        )
        ledger_to_insert = InsertMxLedgerInput(
            id=ledger_id,
            type=MxLedgerType.SCHEDULED.value,
            currency=CurrencyType.USD.value,
            state=MxLedgerStateType.OPEN.value,
            balance=2000,
            payment_account_id=payment_account_id,
        )

        await mx_ledger_repository.insert_mx_ledger(ledger_to_insert)
        inserted_mx_scheduled_ledger = await mx_scheduled_repository.insert_mx_scheduled_ledger(
            mx_scheduled_ledger_to_insert
        )

        values_for_get_open_mx_scheduled_ledger_for_period = iter(
            [None, inserted_mx_scheduled_ledger]
        )

        @asyncio.coroutine
        def mock_get_open_mx_scheduled_ledger_for_period_results(*args):
            return next(values_for_get_open_mx_scheduled_ledger_for_period)

        @asyncio.coroutine
        def mock_get_open_ledger_for_payment_account(*args):
            return None

        # To trigger a UniqueViolationError in create_mx_transaction_impl, we have to insert a mx_scheduled_ledger
        # first, and mock get_open_mx_scheduled_ledger_for_period and get_open_ledger_for_payment_account as None to
        # simulate the concurrent mx_scheduled_ledger creations.
        # In the error handling of UniqueViolationError, get_open_mx_scheduled_ledger_for_period is called again, since
        # the same mx_scheduled_ledger is already created. We mock the second get_open_mx_scheduled_ledger_for_period
        # call to return the inserted_mx_scheduled_ledger.
        mocker.patch(
            "app.ledger.repository.mx_scheduled_ledger_repository.MxScheduledLedgerRepository.get_open_mx_scheduled_ledger_for_period",
            side_effect=mock_get_open_mx_scheduled_ledger_for_period_results,
        )
        mocker.patch(
            "app.ledger.repository.mx_ledger_repository.MxLedgerRepository.get_open_ledger_for_payment_account",
            side_effect=mock_get_open_ledger_for_payment_account,
        )

        mx_transaction = await create_mx_transaction_impl(
            app_context=ledger_app_context,
            req_context=mocker.Mock(),
            payment_account_id=payment_account_id,
            amount=2000,
            currency=CurrencyType.USD,
            routing_key=datetime(2019, 8, 1),
            interval_type=MxScheduledLedgerIntervalType.WEEKLY,
            mx_ledger_repository=mx_ledger_repository,
            mx_scheduled_ledger_repository=mx_scheduled_repository,
            mx_transaction_repository=transaction_repo,
            idempotency_key=str(uuid.uuid4()),
            target_type=MxTransactionType.MERCHANT_DELIVERY,
        )
        assert mx_transaction is not None
        assert mx_transaction.ledger_id == ledger_id

        get_ledger_request = GetMxLedgerByIdInput(id=ledger_id)
        retrieved_mx_ledger = await mx_ledger_repository.get_ledger_by_id(
            get_ledger_request
        )
        assert retrieved_mx_ledger is not None
        assert retrieved_mx_ledger.balance == 4000

    async def test_insert_txn_and_update_ledger_raise_data_error(
        self, mocker: pytest_mock.MockFixture, ledger_app_context: AppContext
    ):
        error = DataError()
        payment_account_id = str(uuid.uuid4())
        mock_mx_scheduled_ledger = GetMxScheduledLedgerOutput(
            id=uuid.uuid4(),
            payment_account_id=payment_account_id,
            ledger_id=uuid.uuid4(),
            interval_type=MxScheduledLedgerIntervalType.WEEKLY,
            start_time=datetime(2019, 8, 5),
            end_time=datetime(2019, 8, 12),
        )

        @asyncio.coroutine
        def mock_coro(*args):
            return mock_mx_scheduled_ledger

        mocker.patch(
            "app.ledger.repository.mx_transaction_repository.MxTransactionRepository.insert_mx_transaction_and_update_ledger",
            side_effect=error,
        )
        mocker.patch(
            "app.ledger.repository.mx_scheduled_ledger_repository.MxScheduledLedgerRepository.get_open_mx_scheduled_ledger_for_period",
            side_effect=mock_coro,
        )
        mx_ledger_repository = MxLedgerRepository(context=ledger_app_context)
        mx_scheduled_repository = MxScheduledLedgerRepository(
            context=ledger_app_context
        )
        transaction_repo = MxTransactionRepository(context=ledger_app_context)

        with pytest.raises(MxTransactionCreationError) as e:
            await create_mx_transaction_impl(
                app_context=ledger_app_context,
                req_context=mocker.Mock(),
                payment_account_id=payment_account_id,
                amount=2000,
                currency=CurrencyType.USD,
                routing_key=datetime(2019, 8, 1),
                interval_type=MxScheduledLedgerIntervalType.WEEKLY,
                mx_ledger_repository=mx_ledger_repository,
                mx_scheduled_ledger_repository=mx_scheduled_repository,
                mx_transaction_repository=transaction_repo,
                idempotency_key=str(uuid.uuid4()),
                target_type=MxTransactionType.MERCHANT_DELIVERY,
            )
            assert e.error_code == LedgerErrorCode.MX_TXN_CREATE_ERROR
            assert (
                e.error_message
                == ledger_error_message_maps[LedgerErrorCode.MX_TXN_CREATE_ERROR.value]
            )
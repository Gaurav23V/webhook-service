import uuid
from datetime import datetime, timedelta
import pytest
from unittest.mock import MagicMock

import requests

from src.workers.delivery_worker import (
    process_delivery,
    MAX_ATTEMPTS,
    BACKOFF_SCHEDULE,
)
from src.models.subscription import Subscription
from src.models.delivery_log import DeliveryLog
from src.cache.subscription_cache import cache_subscription
from src.queue.redis_conn import delivery_queue

# --- Test Data ---
TEST_URL = "http://test-target.local"
TEST_PAYLOAD = {"message": "hello"}
TEST_EVENT_TYPE = "test.event"
TEST_SIGNATURE = "sha256=test"

@pytest.fixture
def test_sub(db_session):
    """Creates a subscription and caches it for worker tests."""
    sub = Subscription(target_url=TEST_URL, secret="test_secret")
    db_session.add(sub)
    db_session.commit() # Commit here as worker runs in separate 'transaction'
    db_session.refresh(sub)
    cache_subscription(sub) # Ensure it's in cache for the worker
    return sub

def test_process_delivery_success(
    test_sub, db_session, mocker # Use mocker fixture from pytest-mock
):
    """Test successful delivery on the first attempt."""
    webhook_id = uuid.uuid4()
    subscription_id = test_sub.id

    # Mock requests.post to return a successful response
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mocker.patch("requests.post", return_value=mock_response)

    # Mock the enqueue_in method (it shouldn't be called on success)
    mock_enqueue_in = mocker.patch(
        "src.queue.redis_conn.delivery_queue.enqueue_in"
    )

    # Execute the worker function
    process_delivery(
        subscription_id=subscription_id,
        payload=TEST_PAYLOAD,
        event_type=TEST_EVENT_TYPE,
        signature=TEST_SIGNATURE,
        webhook_id=webhook_id,
        attempt=1,
    )

    # Assertions
    # 1. requests.post was called correctly
    requests.post.assert_called_once_with(
        TEST_URL,
        json=TEST_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-Event-Type": TEST_EVENT_TYPE,
            "X-Signature": TEST_SIGNATURE, # Assuming signature is passed through
        },
        timeout=mocker.ANY, # Check timeout exists, value checked elsewhere
    )

    # 2. No retry was scheduled
    mock_enqueue_in.assert_not_called()

    # 3. Success log entry was created
    log = db_session.query(DeliveryLog).filter_by(webhook_id=webhook_id).one()
    assert log.subscription_id == subscription_id
    assert log.attempt_number == 1
    assert log.outcome == "Success"
    assert log.status_code == 200
    assert log.error is None

def test_process_delivery_retry_on_failure(
    test_sub, db_session, delivery_queue, mocker # Need delivery_queue fixture
):
    """Test failure (non-2xx) leading to a retry."""
    webhook_id = uuid.uuid4()
    subscription_id = test_sub.id
    initial_attempt = 1

    # Mock requests.post to return a server error
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 503
    # Raise exception for non-2xx status codes to mimic requests behavior
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "Service Unavailable", response=mock_response
    )
    mocker.patch("requests.post", return_value=mock_response)

    # Mock the enqueue_in method to capture arguments
    mock_enqueue_in = mocker.patch(
        "src.queue.redis_conn.delivery_queue.enqueue_in"
    )

    # Execute the worker function for the first attempt
    # It should raise the exception internally but handle it for retry
    process_delivery(
        subscription_id=subscription_id,
        payload=TEST_PAYLOAD,
        event_type=TEST_EVENT_TYPE,
        signature=TEST_SIGNATURE,
        webhook_id=webhook_id,
        attempt=initial_attempt,
    )

    # Assertions
    # 1. requests.post was called
    requests.post.assert_called_once()

    # 2. Retry *was* scheduled with correct parameters
    expected_delay = timedelta(seconds=BACKOFF_SCHEDULE[initial_attempt - 1])
    mock_enqueue_in.assert_called_once_with(
        expected_delay,
        process_delivery, # The function itself
        subscription_id,
        TEST_PAYLOAD,
        TEST_EVENT_TYPE,
        TEST_SIGNATURE,
        webhook_id,
        initial_attempt + 1, # Next attempt number
    )

    # 3. "Failed Attempt" log entry was created
    log = db_session.query(DeliveryLog).filter_by(webhook_id=webhook_id).one()
    assert log.subscription_id == subscription_id
    assert log.attempt_number == initial_attempt
    assert log.outcome == "Failed Attempt"
    assert log.status_code == 503 # Status code should be logged
    assert "503" in log.error # Error details should contain status

def test_process_delivery_retry_on_timeout(
    test_sub, db_session, delivery_queue, mocker
):
    """Test failure (timeout) leading to a retry."""
    webhook_id = uuid.uuid4()
    subscription_id = test_sub.id
    initial_attempt = 2 # Simulate a later attempt

    # Mock requests.post to raise a Timeout exception
    mocker.patch(
        "requests.post",
        side_effect=requests.exceptions.Timeout("Connection timed out")
    )

    mock_enqueue_in = mocker.patch(
        "src.workers.delivery_worker.delivery_queue.enqueue_in"
    )
    
    # Mock get_subscription to avoid Redis dependency
    mocker.patch(
        "src.workers.delivery_worker.get_subscription", 
        return_value={
            "id": str(subscription_id),
            "target_url": "http://test-target.local",
            "secret": "test_secret",
            "events": []
        }
    )

    # Execute the worker function
    process_delivery(
        subscription_id=subscription_id,
        payload=TEST_PAYLOAD,
        event_type=TEST_EVENT_TYPE,
        signature=TEST_SIGNATURE,
        webhook_id=webhook_id,
        attempt=initial_attempt,
    )

    # Assertions
    # 1. requests.post was called
    requests.post.assert_called_once()

    # 2. Retry was scheduled
    expected_delay = timedelta(seconds=BACKOFF_SCHEDULE[initial_attempt - 1])
    mock_enqueue_in.assert_called_once_with(
        expected_delay,
        process_delivery,
        subscription_id,
        TEST_PAYLOAD,
        TEST_EVENT_TYPE,
        TEST_SIGNATURE,
        webhook_id,
        initial_attempt + 1,
    )

    # 3. "Failed Attempt" log entry was created for timeout
    log = db_session.query(DeliveryLog).filter_by(webhook_id=webhook_id).one()
    assert log.subscription_id == subscription_id
    assert log.attempt_number == initial_attempt
    assert log.outcome == "Failed Attempt"
    assert log.status_code is None # No status code on timeout
    assert "Connection timed out" in log.error

def test_process_delivery_retry_on_failure(
    test_sub, db_session, delivery_queue, mocker
):
    """Test failure (non-2xx) leading to a retry."""
    webhook_id = uuid.uuid4()
    subscription_id = test_sub.id
    initial_attempt = 1

    # Mock requests.post to return a server error
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 503
    mocker.patch("requests.post", return_value=mock_response)

    mock_enqueue_in = mocker.patch(
        "src.workers.delivery_worker.delivery_queue.enqueue_in"
    )

    # Mock get_subscription to avoid Redis dependency
    mocker.patch(
        "src.workers.delivery_worker.get_subscription", 
        return_value={
            "id": str(subscription_id),
            "target_url": "http://test-target.local",
            "secret": "test_secret",
            "events": []
        }
    )

    # Execute the worker function for the first attempt
    process_delivery(
        subscription_id=subscription_id,
        payload=TEST_PAYLOAD,
        event_type=TEST_EVENT_TYPE,
        signature=TEST_SIGNATURE,
        webhook_id=webhook_id,
        attempt=initial_attempt,
    )

    # Assertions
    # 1. requests.post was called
    requests.post.assert_called_once()

    # 2. Retry was scheduled
    mock_enqueue_in.assert_called_once()
    
    # Check retry args
    args = mock_enqueue_in.call_args[0]
    assert args[7] == initial_attempt + 1
    
    # 3. Log entry was created
    log = db_session.query(DeliveryLog).filter_by(webhook_id=webhook_id).one()
    assert log.subscription_id == subscription_id
    assert log.attempt_number == initial_attempt
    assert log.outcome == "Failed Attempt"
    assert log.status_code == 503
    assert "HTTP 503" in log.error
from unittest.mock import patch

from lumux.bridge_client import BridgeAuthError, BridgeConnectionError
from lumux.hue_bridge import HueBridge

KEYS = {"app_key": "key", "client_key": "ck"}


def create_user(side_effect, **kwargs):
    bridge = HueBridge("10.0.0.1", "")
    with (
        patch("lumux.hue_bridge.BridgeClient.create_user", side_effect=side_effect) as m,
        patch("lumux.hue_bridge.time.sleep"),
    ):
        return bridge, bridge.create_user("10.0.0.1", **kwargs), m


def test_create_user_polls_until_link_button_pressed():
    bridge, result, m = create_user(
        [BridgeAuthError("link button not pressed")] * 2 + [KEYS], retry_delay=0
    )

    assert result == KEYS
    assert m.call_count == 3
    assert bridge.app_key == "key"


def test_create_user_gives_up_after_max_retries():
    _, result, m = create_user(BridgeAuthError("link button not pressed"), max_retries=4)

    assert result is None
    assert m.call_count == 4


def test_create_user_stops_immediately_when_bridge_unreachable():
    _, result, m = create_user(BridgeConnectionError("no route"))

    assert result is None
    assert m.call_count == 1

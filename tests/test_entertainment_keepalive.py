"""Tests for the DTLS keepalive and reconnection of the entertainment stream."""

import time
from unittest.mock import MagicMock, patch

from lumux import entertainment
from lumux.entertainment import EntertainmentStream
from lumux.sync import SyncController


class FakeProc:
    def __init__(self):
        self.stdin = MagicMock()

    def poll(self):
        return None


def make_stream(channels=(0, 1)):
    stream = EntertainmentStream("127.0.0.1", "app", "00" * 16, "x" * 36)
    stream._channels = {ch: MagicMock() for ch in channels}
    stream._init_message_buffer()
    stream._openssl_proc = FakeProc()
    stream._connected = True
    return stream


def sent_messages(stream):
    return [c.args[0] for c in stream._openssl_proc.stdin.write.call_args_list]


def test_keepalive_resends_last_frame_when_idle():
    stream = make_stream()
    stream.send_colors_xy({0: ((0.3, 0.3), 200), 1: ((0.4, 0.4), 100)})
    first = sent_messages(stream)[0]

    with patch.object(entertainment, "KEEPALIVE_INTERVAL", 0.1):
        stream._start_keepalive()
        time.sleep(1.2)
        stream._stop_keepalive()

    messages = sent_messages(stream)
    assert len(messages) > 1
    # Same colors as the last real frame; only the sequence number differs
    assert messages[1][12:] == first[12:]
    assert messages[1][11] != first[11]


def test_keepalive_sends_black_before_first_frame():
    stream = make_stream()
    with patch.object(entertainment, "KEEPALIVE_INTERVAL", 0.1):
        stream._start_keepalive()
        time.sleep(1.2)
        stream._stop_keepalive()

    header = entertainment.HueStreamProtocol.MESSAGE_HEADER_SIZE
    messages = sent_messages(stream)
    assert messages
    size = entertainment.HueStreamProtocol.CHANNEL_DATA_SIZE
    for m in messages:
        slots = [m[header + i * size:header + (i + 1) * size] for i in range(2)]
        # Every channel is addressed and black, not just channel 0
        assert [slot[0] for slot in slots] == [0, 1]
        assert not any(b for slot in slots for b in slot[1:])


def test_keepalive_stops_with_stream():
    stream = make_stream()
    with patch.object(entertainment, "KEEPALIVE_INTERVAL", 0.1):
        stream._start_keepalive()
        stream._stop_keepalive()
        time.sleep(1.2)

    assert sent_messages(stream) == []


def test_reconnect_is_scheduled_off_the_sync_thread_and_throttled():
    stream = MagicMock()
    stream.is_connected.return_value = False
    stream.reconnect.return_value = True
    controller = SyncController(
        MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(),
        MagicMock(), entertainment_stream=stream,
    )
    controller.running = True
    controller._build_zone_channel_mapping = MagicMock()

    controller._update_lights({"top_0": ((0.3, 0.3), 100)})
    controller._update_lights({"top_0": ((0.3, 0.3), 100)})
    time.sleep(0.3)

    stream.reconnect.assert_called_once()

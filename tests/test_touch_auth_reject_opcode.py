"""TYPE_TOUCH_AUTH_REJECTED (0xAA) - new binary-protocol opcode for the explicit WS-level
"server confirmed you're unauthorized" message (see websocket_server.py's echo()/
process_request() and jaam_touch's WsClient.cpp handleAuthRejected()). The one property that
matters at the protocol level: it must not collide with any other TYPE_* opcode, or a client
could misinterpret one message type as another."""

import utils


def test_touch_auth_rejected_opcode_does_not_collide():
    type_constants = {name: value for name, value in vars(utils).items() if name.startswith("TYPE_")}
    assert type_constants["TYPE_TOUCH_AUTH_REJECTED"] == 0xAA
    assert len(type_constants) == len(set(type_constants.values())), f"duplicate opcode values among {type_constants}"

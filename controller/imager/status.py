STATUS_TOPIC = "status/imager"


def publish_status(client, payload: str, *, retain: bool = True) -> None:
    """Publish the current imager state so newly connected clients can catch up."""
    client.publish(STATUS_TOPIC, payload, retain=retain)

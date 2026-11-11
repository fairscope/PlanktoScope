import unittest

from status import STATUS_TOPIC, publish_status


class FakeClient:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload, *, retain):
        self.messages.append((topic, payload, retain))


class PublishStatusTests(unittest.TestCase):
    def test_state_messages_are_retained_for_late_subscribers(self):
        client = FakeClient()

        publish_status(client, '{"status":"Started"}')

        self.assertEqual(
            client.messages,
            [(STATUS_TOPIC, '{"status":"Started"}', True)],
        )

    def test_transient_messages_can_opt_out_of_retention(self):
        client = FakeClient()

        publish_status(client, '{"type":"progress"}', retain=False)

        self.assertEqual(
            client.messages,
            [(STATUS_TOPIC, '{"type":"progress"}', False)],
        )


if __name__ == "__main__":
    unittest.main()

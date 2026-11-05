import unittest

from ts12p8 import REPORT_SIZE, describe_report


def report(key=1, state=0):
    return b"ACK\0\0OK\0\0" + bytes((key, state)) + bytes(REPORT_SIZE - 11)


class InputClassificationTests(unittest.TestCase):
    def test_wire_index_boundaries(self):
        for key in (1, 12):
            with self.subTest(key=key):
                decoded = describe_report(report(key))
                self.assertEqual(decoded["key_candidate"], key)
                self.assertEqual(decoded["state_byte"], 0)

    def test_other_reports_are_not_classified_as_keys(self):
        malformed = {
            "short": report()[:-1],
            "long": report() + b"\0",
            "different_header": b"ERR" + report()[3:],
            "zero_index": report(key=0),
            "unsupported_index": report(key=13),
            "extra_payload": report()[:-1] + b"\x01",
        }
        for reason, data in malformed.items():
            with self.subTest(reason=reason):
                decoded = describe_report(data)
                self.assertNotIn("key_candidate", decoded)
                self.assertNotIn("state_byte", decoded)


if __name__ == "__main__":
    unittest.main()

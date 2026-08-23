import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from website.captcha import consume_challenge, issue_challenge
from website.complaint_api import router as complaint_router


class ComplaintCaptchaTests(unittest.TestCase):
    def test_challenge_is_one_use(self):
        token = issue_challenge("4821")
        self.assertTrue(consume_challenge(token, "4821"))
        self.assertFalse(consume_challenge(token, "4821"))

    def test_invalid_challenge_is_rejected_before_storage(self):
        app = FastAPI()
        app.include_router(complaint_router)
        client = TestClient(app)

        response = client.post(
            "/api/complaint/submit",
            json={
                "type": "technical",
                "content": "这是用于验证码回归测试的投诉内容。",
                "captcha_challenge": "unknown-token",
                "captcha_answer": "4821",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "验证码无效或已过期")


if __name__ == "__main__":
    unittest.main()

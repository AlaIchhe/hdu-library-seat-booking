"""Tests for hdu_library_booking.auth — generate_api_token signature generation."""

import base64

from hdu_library_booking.auth import generate_api_token


class TestGenerateApiToken:
    """Api-Token 签名生成测试。"""

    def test_returns_token_and_time(self):
        token, api_time = generate_api_token(
            seat_id="296",
            uid="12345",
            begin_time=1700000000,
            duration=3600,
        )
        assert isinstance(token, str)
        assert len(token) > 0
        assert isinstance(api_time, int)
        assert api_time > 0

    def test_token_is_base64(self):
        token, _ = generate_api_token("1", "1", 1, 1)
        # 应能被 base64 解码
        decoded = base64.b64decode(token.encode("utf-8")).decode("utf-8")
        # 解码后应为 32 字符的 hex 字符串 (MD5)
        assert len(decoded) == 32
        assert all(c in "0123456789abcdef" for c in decoded)

    def test_different_inputs_produce_different_tokens(self):
        t1, _ = generate_api_token("100", "1", 1, 1)
        t2, _ = generate_api_token("200", "1", 1, 1)
        assert t1 != t2

    def test_same_inputs_produce_same_token(self):
        args = ("296", "12345", 1700000000, 3600)
        t1, _ = generate_api_token(*args)
        t2, _ = generate_api_token(*args)
        assert t1 == t2

    def test_explicit_api_time(self):
        _token, api_time = generate_api_token("1", "1", 1, 1, api_time=9999999999)
        assert api_time == 9999999999

    def test_is_recommend_default(self):
        t1, _ = generate_api_token("1", "1", 1, 1)
        t2, _ = generate_api_token("1", "1", 1, 1, is_recommend=1)
        assert t1 == t2

    def test_token_is_deterministic(self):
        """同一组参数必须产生相同的 token（幂等性）。"""
        params = {
            "seat_id": "296",
            "uid": "12345",
            "begin_time": 1700000000,
            "duration": 32400,
            "is_recommend": 1,
            "api_time": 1700000000,
        }
        expected, _ = generate_api_token(**params)
        for _ in range(10):
            token, _ = generate_api_token(**params)
            assert token == expected, "token 应具有确定性"

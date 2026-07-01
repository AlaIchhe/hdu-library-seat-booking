"""Tests for hdu_library_booking.constants — URLS, headers, room mappings, defaults."""

from hdu_library_booking import constants as C


class TestURLS:
    def test_all_urls_are_strings(self):
        for key, url in C.URLS.items():
            assert isinstance(url, str), f"URLS[{key}] 应为字符串"
            assert url.startswith("https://"), f"URLS[{key}] 应以 https:// 开头"

    def test_required_endpoints_present(self):
        required = ["book_seat", "login", "query_seats", "query_rooms"]
        for key in required:
            assert key in C.URLS, f"缺少必要端点: {key}"


class TestDefaultHeaders:
    def test_is_dict(self):
        assert isinstance(C.DEFAULT_HEADERS, dict)

    def test_has_content_type(self):
        assert "Content-type" in C.DEFAULT_HEADERS

    def test_user_agent_contains_android(self):
        assert "Android" in C.DEFAULT_HEADERS["User-Agent"]


class TestSessionParams:
    def test_lab_json_param(self):
        assert C.DEFAULT_SESSION_PARAMS["LAB_JSON"] == "1"


class TestRoomTypeMap:
    def test_map_values(self):
        assert C.ROOM_TYPE_MAP["1"] == "自习室"
        assert C.ROOM_TYPE_MAP["2"] == "教师休息室"
        assert C.ROOM_TYPE_MAP["3"] == "阅览室"
        assert C.ROOM_TYPE_MAP["4"] == "讨论室"


class TestErrorMessages:
    def test_messages_are_non_empty(self):
        assert len(C.MSG_TIME_OUT_OF_RANGE) > 0
        assert len(C.MSG_DUPLICATE) > 0
        assert len(C.MSG_SEAT_UNAVAILABLE) > 0
        assert len(C.MSG_INVALID_REQUEST) > 0


class TestDefaults:
    def test_default_org_id(self):
        assert C.DEFAULT_ORG_ID == "104"

    def test_default_timeout_positive(self):
        assert C.DEFAULT_TIMEOUT > 0

    def test_default_max_trials_positive(self):
        assert C.DEFAULT_MAX_TRIALS > 0

    def test_default_retry_delay_positive(self):
        assert C.DEFAULT_RETRY_DELAY > 0

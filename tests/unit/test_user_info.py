"""Tests for hdu_library_booking.gateways.user_info — UID 解析。"""

from hdu_library_booking.gateways.user_info import find_user_info


class TestUserInfoFromDict:
    def test_user_info_from_dict(self):
        from hdu_library_booking.gateways.user_info import _user_info_from_dict

        result = _user_info_from_dict({"uid": "123", "name": "张三"}, hint="currentUser")
        assert result is not None
        assert result["uid"] == "123"
        assert result["name"] == "张三"

    def test_no_match_returns_none(self):
        from hdu_library_booking.gateways.user_info import _user_info_from_dict

        result = _user_info_from_dict({"foo": "bar"})
        assert result is None

    def test_score_boosts_for_relevant_hints(self):
        from hdu_library_booking.gateways.user_info import _user_info_from_dict

        r1 = _user_info_from_dict({"uid": "1"}, hint="something")
        r2 = _user_info_from_dict({"uid": "2"}, hint="currentLogin")
        assert r2["score"] > (r1["score"] if r1 else 0)


class TestFindUserInfo:
    def test_finds_uid_in_nested_structure(self):
        data = {
            "DATA": {"name": {"name": "currentUser", "value": '{"uid": "888", "name": "张三"}'}}
        }
        result = find_user_info(data)
        assert result is not None
        assert result["uid"] == "888"

    def test_no_match_returns_none(self):
        result = find_user_info({"foo": "bar"})
        assert result is None

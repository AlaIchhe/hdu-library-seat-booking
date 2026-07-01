"""Tests for hdu_library_booking.exceptions — exception hierarchy."""

import pytest

from hdu_library_booking.exceptions import (
    BookingCancelled,
    BookingError,
    BookingValidationError,
    CookieError,
    HduLibraryError,
    LoginError,
    RoomQueryError,
    SeatQueryError,
)


class TestExceptionHierarchy:
    """验证异常继承链。"""

    def test_all_inherit_from_hdu_library_error(self):
        subs = [
            LoginError,
            CookieError,
            RoomQueryError,
            SeatQueryError,
            BookingError,
            BookingValidationError,
            BookingCancelled,
        ]
        for cls in subs:
            assert issubclass(cls, HduLibraryError), f"{cls.__name__} 应继承 HduLibraryError"

    def test_all_inherit_from_exception(self):
        subs = [
            HduLibraryError,
            LoginError,
            CookieError,
            RoomQueryError,
            SeatQueryError,
            BookingError,
            BookingValidationError,
            BookingCancelled,
        ]
        for cls in subs:
            assert issubclass(cls, Exception), f"{cls.__name__} 应继承 Exception"

    def test_exception_message_retained(self):
        exc = LoginError("密码错误")
        assert str(exc) == "密码错误"
        assert "密码错误" in repr(exc)

    def test_can_catch_by_base(self):
        """应能用基类捕获所有子异常。"""
        errors = [
            LoginError("a"),
            CookieError("b"),
            RoomQueryError("c"),
            SeatQueryError("d"),
            BookingError("e"),
            BookingValidationError("f"),
            BookingCancelled("g"),
        ]
        caught = []
        for e in errors:
            try:
                raise e
            except HduLibraryError:
                caught.append(True)
        assert len(caught) == len(errors)

    def test_can_catch_individually(self):
        """应能精确捕获特定子类异常。"""
        try:
            raise BookingCancelled("用户取消")
        except BookingCancelled:
            pass  # 正确捕获
        except HduLibraryError:
            pytest.fail("BookingCancelled 应被自己的 except 子句捕获")

    def test_exception_cause_chain(self):
        """验证异常链 from exc 语义。"""

        def _raise_chained():
            try:
                raise ValueError("底层错误")
            except ValueError as exc:
                raise HduLibraryError("包装后错误") from exc

        with pytest.raises(HduLibraryError) as exc_info:
            _raise_chained()
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert "底层错误" in str(exc_info.value.__cause__)

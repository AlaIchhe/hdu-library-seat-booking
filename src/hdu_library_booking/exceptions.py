"""
公共异常层次结构。

自定义异常均可用以下分类。
"""


class HduLibraryError(Exception):
    """所有 HDU 图书馆相关异常的基类。"""

    pass


class LoginError(HduLibraryError):
    """登录失败（密码错误、账号无效、页面变更等）。"""

    pass


class CookieError(HduLibraryError):
    """Cookie 加载失败或无效。"""

    pass


class RoomQueryError(HduLibraryError):
    """房间 / 区域查询失败。"""

    pass


class SeatQueryError(HduLibraryError):
    """座位查询失败。"""

    pass


class BookingError(HduLibraryError):
    """预约提交失败。"""

    pass


class BookingValidationError(HduLibraryError):
    """预约参数校验不通过（时间范围、座位号等）。"""

    pass


class BookingCancelled(HduLibraryError):
    """用户主动取消预约任务。"""

    pass

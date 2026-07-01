"""
应用层抽象接口。

定义 Repository、Strategy、UI、Notification 的抽象契约。
所有上层依赖均面向这些接口编程，而非具体实现。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable

from hdu_library_booking.gateways.protocols import ILibraryGateway
from hdu_library_booking.types import Result, SeatPoi

from ..models.plan import BookingPlan


# ======================================================================
# IPlanRepository — 方案持久化抽象 (Repository Pattern)
# ======================================================================
class IPlanRepository(ABC):
    """方案存储的抽象接口。"""

    @abstractmethod
    def load_all(self) -> list[BookingPlan]:
        """加载全部方案。"""
        ...

    @abstractmethod
    def save_all(self, plans: list[BookingPlan]) -> None:
        """保存全部方案。"""
        ...

    @abstractmethod
    def add(self, plan: BookingPlan) -> None:
        """新增一个方案。"""
        ...

    @abstractmethod
    def remove(self, plan_id: str) -> bool:
        """删除方案，返回 True 表示删除成功。"""
        ...

    @abstractmethod
    def get(self, plan_id: str) -> BookingPlan | None:
        """按 ID 获取方案。"""
        ...


# ======================================================================
# ISeatSelectionStrategy — 座位选择策略抽象 (Strategy Pattern)
# ======================================================================
class ISeatSelectionStrategy(ABC):
    """座位选择策略接口。"""

    @abstractmethod
    def select_seat(
        self, gateway: ILibraryGateway, plan: BookingPlan, **kwargs: object
    ) -> Result[SeatPoi, str]:
        """从楼层中选出目标座位 POI 对象。

        Args:
            gateway: API 网关接口。
            plan: 预约方案。
            **kwargs: 额外参数（如随机种子、用户偏好等）。

        Returns:
            成功时包含座位 POI；失败时包含原因描述字符串。
        """
        ...

    @abstractmethod
    def describe(self, plan: BookingPlan) -> str:
        """返回策略的人类可读描述。"""
        ...


# ======================================================================
# INotificationChannel — 通知通道抽象 (Observer Pattern)
# ======================================================================
class INotificationChannel(ABC):
    """消息通知通道接口。"""

    @abstractmethod
    def send(self, title: str, body: str, success: bool = True) -> None:
        """发送一条通知。

        Parameters
        ----------
        title : str
            通知标题。
        body : str
            通知正文。
        success : bool
            是否为成功消息（影响展示样式）。
        """
        ...


# ======================================================================
# IUserInterface — 用户界面抽象
# ======================================================================
class IUserInterface(ABC):
    """用户交互界面接口。"""

    @abstractmethod
    def run(self, context: dict) -> int:
        """启动界面主循环。

        Parameters
        ----------
        context : dict
            上下文数据（配置、客户端、服务实例等）。

        Returns
        -------
        int
            退出码（0=正常）。
        """
        ...


# ======================================================================
# ITaskCancellation — 可取消任务抽象
# ======================================================================
class ITaskCancellation(ABC):
    """可取消的长时间运行任务的接口。"""

    @abstractmethod
    def is_cancelled(self) -> bool:
        """检查任务是否已被取消。"""
        ...

    @abstractmethod
    def cancel(self) -> None:
        """请求取消任务。"""
        ...


class CancellationToken(ITaskCancellation):
    """线程安全的取消令牌实现。

    基于 threading.Event，支持注册取消回调。
    向后兼容旧接口（is_cancelled / cancel）。
    """

    def __init__(self) -> None:
        import threading

        self._event = threading.Event()
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            for cb in self._callbacks:
                try:
                    cb()
                except Exception:
                    pass

    def register_callback(self, callback: Callable[[], None]) -> None:
        """注册取消回调（可选扩展）。"""
        with self._lock:
            self._callbacks.append(callback)
            if self._event.is_set():
                try:
                    callback()
                except Exception:
                    pass

    def wait(self, timeout: float | None = None) -> bool:
        """等待取消信号（可选扩展）。"""
        return self._event.wait(timeout)

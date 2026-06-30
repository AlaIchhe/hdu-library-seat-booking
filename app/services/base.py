"""
应用层抽象接口。

定义 Repository、Strategy、UI、Notification 的抽象契约。
所有上层依赖均面向这些接口编程，而非具体实现。
"""

from abc import ABC, abstractmethod

from core.infrastructure.protocols import ILibraryGateway

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
    ) -> dict[str, object] | None:
        """从楼层中选出目标座位 POI 对象。

        Args:
            gateway: API 网关接口。
            plan: 预约方案。
            **kwargs: 额外参数（如随机种子、用户偏好等）。

        Returns:
            选中的座位 POI 对象，None 表示无法选出。
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
    """简单的取消令牌实现。"""

    def __init__(self) -> None:
        self._cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

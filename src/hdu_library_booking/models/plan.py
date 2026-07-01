"""
预约方案数据模型。

BookingPlan 是应用层的核心领域对象，承载一次预约所需的全部参数。
"""

from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum


class Weekday(IntEnum):
    """星期枚举，与 Python datetime.weekday() 对齐 (周一=0)。"""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    @classmethod
    def label(cls, day: "Weekday") -> str:
        labels = {
            cls.MONDAY: "周一",
            cls.TUESDAY: "周二",
            cls.WEDNESDAY: "周三",
            cls.THURSDAY: "周四",
            cls.FRIDAY: "周五",
            cls.SATURDAY: "周六",
            cls.SUNDAY: "周日",
        }
        return labels.get(day, "?")


class PlanStatus(str, Enum):
    """方案启用状态。"""

    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass
class BookingPlan:
    """一次预约的完整参数集合。

    Attributes
    ----------
    room_type : int
        房间类型编号（1=自习室, 2=教师休息室, 3=阅览室, 4=讨论室）。
    floor_id : int
        目标楼层 ID。
    seat_num : str
        座位号。
    start_hour : int
        预约开始小时 (0-23)。
    duration_hours : int
        预约持续小时数。
    booker_name : str, optional
        预约人姓名。
    book_days : int
        天数偏移：0=今天, 1=明天, 2=后天。
    status : PlanStatus
        方案启用状态。
    weekday : Weekday, optional
        按星期切换模式下绑定的星期；None 表示适用于所有天。
    tags : list[str]
        用户自定义标签。
    plan_id : str, optional
        方案唯一标识（由 repository 生成）。
    created_at : str, optional
        ISO 格式创建时间。
    """

    room_type: int
    floor_id: int
    seat_num: str
    start_hour: int
    duration_hours: int
    booker_name: str = ""
    book_days: int = 0
    status: PlanStatus = PlanStatus.ENABLED
    weekday: Weekday | None = None
    tags: list[str] = field(default_factory=list)
    plan_id: str | None = None
    created_at: str | None = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """校验方案参数，返回错误列表（空列表表示通过）。"""
        errors = []
        if self.room_type not in (1, 2, 3, 4):
            errors.append(f"无效的房间类型：{self.room_type}")
        if self.floor_id <= 0:
            errors.append(f"无效的楼层 ID：{self.floor_id}")
        if not self.seat_num or not str(self.seat_num).strip():
            errors.append("座位号不能为空")
        if not (0 <= self.start_hour <= 23):
            errors.append(f"开始小时超出范围：{self.start_hour}")
        if self.duration_hours <= 0:
            errors.append(f"时长必须为正数：{self.duration_hours}")
        if self.book_days < 0:
            errors.append(f"天数偏移不能为负：{self.book_days}")
        return errors

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """转为可序列化的字典（plan_id 作为 key）。"""
        data = asdict(self)
        data["status"] = self.status.value
        if self.weekday is not None:
            data["weekday"] = self.weekday.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "BookingPlan":
        """从字典还原 BookingPlan。"""
        data = dict(data)  # shallow copy
        # 枚举还原
        status = data.get("status", "enabled")
        data["status"] = PlanStatus(status) if isinstance(status, str) else PlanStatus.ENABLED
        wd = data.get("weekday")
        data["weekday"] = Weekday(wd) if wd is not None else None
        # 过滤未知字段
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    # ------------------------------------------------------------------
    # Plan code (compact representation)
    # ------------------------------------------------------------------
    def to_plan_code(self) -> str:
        """编码为 roomType:floorId:seatNum:startHour:durationHours 格式。"""
        return f"{self.room_type}:{self.floor_id}:{self.seat_num}:{self.start_hour}:{self.duration_hours}"

    @classmethod
    def from_plan_code(cls, code: str) -> "BookingPlan":
        """从编码字符串反序列化。"""
        from hdu_library_booking.models.time_utils import parse_plan_code

        parsed = parse_plan_code(code)
        return cls(
            room_type=parsed["room_type"],
            floor_id=parsed["floor_id"],
            seat_num=parsed["seat_num"],
            start_hour=parsed["start_hour"],
            duration_hours=parsed["duration_hours"],
        )

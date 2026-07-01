# 修复计划：room_type 选择机制 + 关联 bug 修复

## Context

用户的核心诉求是：**room_type 应该只允许用户从 API 获取的列表中选择，而非手动输入数字**。

当前问题链：
1. TUI 虽然从 API 获取了房间列表供用户选择，但随后用脆弱的 `_extract_room_type()` 从名字反推数字编号（子字符串匹配，容易出错）
2. `book_single()` 中又用子字符串匹配将数字映射回房间名，且无匹配时**静默回退到第一个房间类型**（可能预约到错误房间）
3. `FixedSeatStrategy._fetch_floors()` 硬编码使用 `room_types[0]`
4. CLI 的 `--plan` 编码中 room_type 是数字，用户需要记住编号含义

修复策略：**在 BookingPlan 中增加 `room_query` 字段保存 API 返回的精确 query 字符串，booking 时优先用 query 直接查询，彻底消除名字↔数字的转换**。

---

## 修复项清单

### 修复 1：BookingPlan 增加 `room_query` 字段 【核心】

**文件**: `src/hdu_library_booking/models/plan.py`

- 在 `BookingPlan` dataclass 中增加可选字段 `room_query: str = ""`
- 保存 API 返回的 `query` 字符串（如 `"space_category[category_id]=10&space_category[content_id]=20"`）
- `to_dict()` / `from_dict()` 自动兼容（dataclass asdict 处理）
- `to_plan_code()` 不变（保持 5 段紧凑格式，向后兼容）
- `validate()` 不变（room_query 是可选的辅助字段）

### 修复 2：TUI 存储 room_query，移除脆弱的 _extract_room_type

**文件**: `src/hdu_library_booking/cli/terminal.py`

- `_handle_create_plan()`: 创建 plan 时传入 `room_query=selected_room["query"]`
- `_handle_create_plan()`: `room_type` 仍保存数字（用于向后兼容和 CLI 显示），但**优先使用 room_query 做匹配**
- 删除 `_extract_room_type()` 方法（不再需要）
- 新增 `_resolve_room_type_name()`: 从 API 返回的 room_types 中精确查找，给定 query 找到对应 name，再用 ROOM_TYPE_MAP 精确匹配数字
- 无匹配时**明确报错**而非默认返回 1

### 修复 3：book_single 优先使用 room_query 精确匹配

**文件**: `src/hdu_library_booking/services/booking.py` (lines 207-224)

新匹配逻辑：
```python
# 优先：如果 plan 有 room_query，直接用 query 字符串匹配
if plan.room_query:
    matched = [r for r in room_types if r.get("query") == plan.room_query]
# 回退：用 ROOM_TYPE_MAP 精确匹配名字
if not matched:
    target_name = C.ROOM_TYPE_MAP.get(str(plan.room_type), "")
    matched = [r for r in room_types if r.get("name") == target_name]
# 无匹配 → 明确报错，不再静默回退
if not matched:
    return BookingResult(plan, False, f"未找到匹配的房间类型: {target_name or plan.room_type}")
```

### 修复 4：FixedSeatStrategy._fetch_floors 使用 plan 的 room_query

**文件**: `src/hdu_library_booking/strategies/fixed.py`

- `_fetch_floors()`: 如果 `plan.room_query` 存在，直接用它获取 room_detail
- 否则回退到当前行为（room_types[0]），但增加 warning 日志

### 修复 5：on_progress 回调异常保护

**文件**: `src/hdu_library_booking/services/booking.py` (line 455-456)

```python
if on_progress:
    try:
        on_progress(result)
    except Exception as exc:
        logger.warning("on_progress_callback_failed", error=str(exc))
```

### 修复 6：load_all() 区分文件不存在 vs 解析错误

**文件**: `src/hdu_library_booking/services/yaml_plan.py` (lines 44-54)

```python
if not self._file.exists():
    self._cache = []
    return []  # 文件不存在 → 空列表（正常）

try:
    data = yaml.safe_load(...)
except yaml.YAMLError as exc:
    # YAML 解析错误 → 抛出，让调用者感知
    error_tracker.record(...)
    raise E.RoomQueryError(f"方案文件 YAML 解析失败: {self._file}") from exc
except OSError as exc:
    # 权限错误等 → 抛出
    error_tracker.record(...)
    raise
```

### 修复 7：book_at 时区安全

**文件**: `src/hdu_library_booking/services/booking.py` (lines 587-588)

```python
now = datetime.now().astimezone()
# 确保 execute_at 是 offset-aware
if execute_at.tzinfo is None:
    execute_at = execute_at.replace(tzinfo=now.tzinfo)
wait_seconds = (execute_at - now).total_seconds()
```

### 修复 8：_backoff_delay 最小延迟保证

**文件**: `src/hdu_library_booking/services/booking.py` (line 555)

```python
jitter = random.uniform(0, delay)
return max(jitter, 0.1)  # 最小 100ms 延迟
```

### 修复 9：TUI 不再允许保存无效方案

**文件**: `src/hdu_library_booking/cli/terminal.py` (lines 245-251)

```python
errors = plan.validate()
if errors:
    print("\n⚠ 方案校验失败:")
    for e in errors:
        print(f"  - {e}")
    print("请重新创建方案。")
    return  # 直接返回，不再询问"仍然保存?"
```

### 修复 10：smoke 测试改用 skip 替代 fail

**文件**: `tests/e2e/test_smoke.py` (line 124)

```python
pytest.skip(
    "所有 Cookie 认证方式均失败（无 cookie 文件/环境变量）。"
    "此测试需要真实凭据。"
)
```

---

## 新增测试

### 测试 1：BookingPlan room_query 字段

**文件**: `tests/unit/test_models.py`

- test_plan_with_room_query: 创建带 room_query 的 plan，验证序列化往返
- test_plan_without_room_query: 兼容旧数据（room_query 为空字符串）
- test_from_dict_with_room_query: 从 dict 还原含 room_query 的 plan

### 测试 2：book_single room_type 精确匹配

**文件**: `tests/integration/test_booking_service.py`

- test_book_single_room_type_matched_by_query: plan 带 room_query，精确匹配成功
- test_book_single_room_type_matched_by_name: plan 不带 room_query，用 ROOM_TYPE_MAP 精确名字匹配
- test_book_single_room_type_no_match_raises: 无匹配时返回失败结果（非回退到第一个）
- test_book_single_room_type_fallback_not_silent: 验证不会静默选择错误房间

### 测试 3：on_progress 异常不中断流程

**文件**: `tests/integration/test_booking_service.py`

- test_book_all_on_progress_exception_does_not_abort: on_progress 抛异常时 book_all 继续执行

### 测试 4：_load_all 区分文件不存在和解析错误

**文件**: `tests/unit/test_plan_repository.py`

- test_load_all_file_not_found_returns_empty: 文件不存在返回 []
- test_load_all_corrupt_yaml_raises: YAML 解析错误抛出异常

### 测试 5：_backoff_delay 最小值

**文件**: `tests/unit/test_strategies.py` 或新建 `test_booking_retry.py`

- test_backoff_delay_has_minimum: 验证延迟 >= 0.1

---

## 向后兼容策略

| 方面 | 兼容方式 |
|------|---------|
| 已有 YAML 方案文件 | `room_query` 默认空字符串，book_single 回退到 ROOM_TYPE_MAP 名字匹配 |
| CLI `--plan` 编码格式 | 不变，仍为 `roomType:floorId:seatNum:startHour:durationHours` |
| 已有单元测试 | 不需要修改 mock 数据（测试中的房间名匹配仍然有效） |
| 数据库/API 契约 | 无变化，只是客户端内部匹配逻辑更精确 |

---

## 执行顺序

1. **修复 1**: BookingPlan 加 `room_query` 字段（基础变更）
2. **测试 1**: room_query 字段测试
3. **修复 2**: TUI 使用 room_query + 移除 _extract_room_type
4. **修复 3**: book_single 优先用 room_query 匹配
5. **修复 4**: FixedSeatStrategy 使用 room_query
6. **测试 2**: book_single 匹配逻辑测试
7. **修复 5**: on_progress 异常保护
8. **测试 3**: on_progress 异常测试
9. **修复 6**: load_all 区分异常
10. **测试 4**: load_all 异常测试
11. **修复 7**: book_at 时区安全
12. **修复 8**: backoff 最小延迟
13. **测试 5**: backoff 最小值测试
14. **修复 9**: TUI 不保存无效方案
15. **修复 10**: smoke skip

---

## 验证方式

```bash
# 1. 单元测试 + 集成测试
uv run pytest tests/unit/ tests/integration/ -x -q

# 2. 类型检查
uv run mypy src/

# 3. 代码风格
uv run ruff check src/ tests/

# 4. 全部预提交检查
uv run pre-commit run --all-files
```

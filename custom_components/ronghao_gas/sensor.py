"""Sensors for Ronghao Gas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_BASE_URL,
    CONF_USER_ID,
    CONF_USERINFO_ID,
    DATA_COORDINATORS,
    DEFAULT_API_BASE_URL,
    DOMAIN,
)
from .coordinator import RonghaoGasDataUpdateCoordinator

ATTR_SOURCE = "www.rhwxsf.com"
CURRENCY_CNY = "CNY"


@dataclass(frozen=True, kw_only=True)
class RonghaoGasSensorEntityDescription(SensorEntityDescription):
    """Description for a Ronghao Gas sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ronghao Gas sensors."""
    coordinator: RonghaoGasDataUpdateCoordinator = hass.data[DOMAIN][DATA_COORDINATORS][
        entry.entry_id
    ]
    entities: list[SensorEntity] = [
        RonghaoGasSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(RonghaoGasCardSensor(coordinator, entry))
    async_add_entities(entities)


class RonghaoGasSensor(
    CoordinatorEntity[RonghaoGasDataUpdateCoordinator], SensorEntity
):
    """A Ronghao Gas sensor."""

    entity_description: RonghaoGasSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RonghaoGasDataUpdateCoordinator,
        entry: ConfigEntry,
        description: RonghaoGasSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_translation_key = description.key

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        data = self._entry.data
        return DeviceInfo(
            identifiers={(DOMAIN, str(data.get(CONF_USERINFO_ID, self._entry.entry_id)))},
            manufacturer="荣浩能源",
            model="Ronghao Gas Cloud",
            name="荣浩燃气",
            configuration_url=data.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self.entity_description.attrs_fn(self.coordinator.data or {})


def _user_info(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("user_info") or {}


def _meter(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("meter") or {}


def _sell_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in data.get("sell_list", []) if isinstance(item, dict)]


def _hand_plan(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in data.get("hand_plan", []) if isinstance(item, dict)]


def _latest(items: list[dict[str, Any]]) -> dict[str, Any]:
    return items[0] if items else {}


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round2(value: Any) -> float | None:
    number = _to_float(value)
    return round(number, 2) if number is not None else None


def _first_number(*values: Any) -> float | None:
    for value in values:
        number = _to_float(value)
        if number is not None:
            return number
    return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _compact(attrs: dict[str, Any]) -> dict[str, Any]:
    """Remove null values while keeping valid falsey values."""
    return {key: value for key, value in attrs.items() if value is not None}


def _gas_day_key(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    return text[:10]


def _gas_month_key(value: Any) -> str:
    day = _gas_day_key(value)
    return day[:7] if len(day) >= 7 else ""


def _parse_api_datetime(value: Any) -> datetime | None:
    """Parse API date/time values as Home Assistant local datetimes."""
    if isinstance(value, datetime):
        parsed = value
    elif value:
        text = str(value).strip()
        parsed = dt_util.parse_datetime(text) or dt_util.parse_datetime(
            text.replace(" ", "T")
        )
    else:
        return None

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.now().tzinfo)
    return parsed


def _format_local_datetime(value: datetime | None) -> str | None:
    """Format a datetime for exact display in entity cards."""
    if value is None:
        return None
    local = dt_util.as_local(value)
    return (
        f"{local.year}年{local.month}月{local.day}日 "
        f"{local.hour:02d}:{local.minute:02d}"
    )


def _today_sell_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    today = dt_util.now().date().isoformat()
    return [
        item
        for item in _sell_list(data)
        if str(item.get("f_delivery_date", ""))[:10] == today
    ]


def _sum_float(items: list[dict[str, Any]], key: str) -> float:
    return sum(_to_float(item.get(key)) or 0 for item in items)


def _account_balance(data: dict[str, Any]) -> float | None:
    """Return the best money balance exposed by the API."""
    info = _user_info(data)
    meter = _meter(data)
    latest_usage = _latest(_hand_plan(data))
    latest_sell = _latest(_sell_list(data))
    return _round2(
        _first_number(
            info.get("f_balance"),
            meter.get("f_balance_amount"),
            latest_usage.get("f_balance"),
            latest_sell.get("f_curbalance_amount"),
            info.get("summoney"),
        )
    )


def _updated_at(data: dict[str, Any]) -> Any:
    return data.get("updated_at")


def _refresh_attrs(data: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "更新时间": _updated_at(data),
            "数据来源": ATTR_SOURCE,
        }
    )


def _user_attrs(data: dict[str, Any]) -> dict[str, Any]:
    info = _user_info(data)
    prices = info.get("chargeprice") or []
    p1 = prices[0] if len(prices) > 0 and isinstance(prices[0], dict) else {}
    p2 = prices[1] if len(prices) > 1 and isinstance(prices[1], dict) else {}
    p3 = prices[2] if len(prices) > 2 and isinstance(prices[2], dict) else {}
    return _compact(
        {
            "账户余额_元": _account_balance(data),
            "平台账户余额_元": _round2(info.get("summoney")),
            "当前金额余额_元": _account_balance(data),
            "当前气量余额_m3": _to_float(info.get("f_balance_gas")),
            "累计用气量_m3": _to_float(info.get("sumgas")),
            "总用气量_m3": _to_float(info.get("f_total_gas")),
            "阶梯开始日期": info.get("stairbegindate"),
            "气价1名称": p1.get("f_price_name"),
            "气价1_元": _to_float(p1.get("f_price")),
            "气价1用量_m3": _to_float(p1.get("f_gas")),
            "气价2名称": p2.get("f_price_name"),
            "气价2_元": _to_float(p2.get("f_price")),
            "气价2用量_m3": _to_float(p2.get("f_gas")),
            "气价3名称": p3.get("f_price_name"),
            "气价3_元": _to_float(p3.get("f_price")),
            "气价3用量_m3": _to_float(p3.get("f_gas")),
            "recentGas": info.get("recentGas") or [],
            "priceRecord": info.get("priceRecord") or [],
            "数据时间": info.get("f_update_date") or _updated_at(data),
            "更新时间": _updated_at(data),
            "数据来源": ATTR_SOURCE,
        }
    )


def _meter_attrs(data: dict[str, Any]) -> dict[str, Any]:
    meter = _meter(data)
    valve = meter.get("f_valvestate")
    valve_state = "正常" if valve == "0" else f"异常({valve})" if valve is not None else None
    return _compact(
        {
            "表号": meter.get("f_meternumber"),
            "表底数_m3": _to_float(meter.get("f_meter_base")),
            "累计用气量_m3": _to_float(meter.get("f_total_gas")),
            "抄表次数": _to_int(meter.get("f_times")),
            "表具别名": meter.get("f_alias"),
            "表具品牌": meter.get("f_meter_brand"),
            "表具类型": meter.get("f_meter_classify"),
            "气量余额_m3": _to_float(meter.get("f_balance_gas")),
            "金额余额_元": _round2(meter.get("f_balance_amount")),
            "阀门状态": valve_state,
            "计费方式": meter.get("f_calculation"),
            "充值上限": meter.get("f_topup_ceil"),
            "插入时间": meter.get("f_insert_date"),
            "数据时间": meter.get("f_insert_date"),
            "更新时间": _updated_at(data),
            "数据来源": ATTR_SOURCE,
        }
    )


def _sell_daylist(sell_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "node": index + 1,
            "date": item.get("f_delivery_date"),
            "readingTime": item.get("f_delivery_date"),
            "usage": item.get("f_preamount"),
            "amount": item.get("f_collection"),
            "pay_mode": item.get("f_payment"),
            "pay_amount": item.get("f_curbalance_amount"),
            "f_delivery_date": item.get("f_delivery_date"),
            "f_preamount": item.get("f_preamount"),
            "f_collection": item.get("f_collection"),
            "f_curbalance_amount": item.get("f_curbalance_amount"),
            "f_curbalance_gas": item.get("f_curbalance_gas"),
            "f_balance_amount": item.get("f_balance_amount"),
            "f_payment": item.get("f_payment"),
            "f_type": item.get("f_type"),
            "f_meter_type": item.get("f_meter_type"),
            "f_user_name": item.get("f_user_name"),
            "f_address": item.get("f_address"),
        }
        for index, item in enumerate(sell_list)
    ]


def _sell_attrs(data: dict[str, Any]) -> dict[str, Any]:
    sell_list = _sell_list(data)
    latest = _latest(sell_list)
    today_sell = _today_sell_records(data)
    today_total = _sum_float(today_sell, "f_collection")
    return _compact(
        {
            "当前气量余额_m3": _to_float(latest.get("f_curbalance_gas")),
            "当前金额余额_元": _to_float(latest.get("f_curbalance_amount")),
            "今日购气总额_元": today_total,
            "今日购气次数": len(today_sell),
            "最近购气日总额_元": _latest_purchase_day_total(data),
            "最近购气日期": _gas_day_key(latest.get("f_delivery_date")),
            "今日购气记录": [
                {
                    "时间": item.get("f_delivery_date"),
                    "购气量": item.get("f_preamount"),
                    "实付金额": item.get("f_collection"),
                    "支付方式": item.get("f_payment"),
                }
                for item in today_sell
            ],
            "daylist": _sell_daylist(sell_list),
            "总记录数": len(sell_list),
            "数据时间": latest.get("f_delivery_date") or _updated_at(data),
            "更新时间": _updated_at(data),
            "数据来源": ATTR_SOURCE,
        }
    )


def _usage_daylist(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "node": index + 1,
            "date": _gas_day_key(item.get("f_input_date")),
            "readingTime": _gas_day_key(item.get("f_input_date")),
            "usage": item.get("f_oughtamount"),
            "cycleTotalVolume": item.get("f_oughtamount"),
            "amount": item.get("f_oughtfee"),
            "cycleTotalValues": item.get("f_oughtfee"),
            "f_input_date": item.get("f_input_date"),
            "f_oughtamount": item.get("f_oughtamount"),
            "f_oughtfee": item.get("f_oughtfee"),
            "f_curbalance": item.get("f_curbalance"),
            "f_balance": item.get("f_balance"),
            "f_tablebase": item.get("f_tablebase"),
            "f_last_tablebase": item.get("f_last_tablebase"),
            "f_gas1": item.get("f_gas1"),
            "f_gas2": item.get("f_gas2"),
            "f_gas3": item.get("f_gas3"),
            "f_money1": item.get("f_money1"),
            "f_money2": item.get("f_money2"),
            "f_money3": item.get("f_money3"),
            "f_price1": item.get("f_price1"),
            "f_price2": item.get("f_price2"),
            "f_price3": item.get("f_price3"),
        }
        for index, item in enumerate(plans)
    ]


def _usage_amount(item: dict[str, Any]) -> float:
    amount = _to_float(item.get("f_oughtamount"))
    if amount is not None:
        return amount
    return sum(_to_float(item.get(key)) or 0 for key in ("f_gas1", "f_gas2", "f_gas3"))


def _usage_fee(item: dict[str, Any]) -> float:
    fee = _to_float(item.get("f_oughtfee"))
    if fee is not None:
        return fee
    return sum(
        _to_float(item.get(key)) or 0 for key in ("f_money1", "f_money2", "f_money3")
    )


def _usage_datetime(item: dict[str, Any]) -> datetime | None:
    """Return the record time used by the Ronghao mini program."""
    return _parse_api_datetime(item.get("f_input_date") or item.get("f_hand_date"))


def _usage_day(item: dict[str, Any]) -> str:
    """Return the local day used by usage charts and card data."""
    used_at = _usage_datetime(item)
    return dt_util.as_local(used_at).date().isoformat() if used_at else ""


def _latest_billable_usage(plans: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the first usage row that carries an actual usage or fee value."""
    for item in plans:
        if (_to_float(item.get("f_oughtamount")) or 0) > 0:
            return item
        if (_to_float(item.get("f_oughtfee")) or 0) > 0:
            return item
    return _latest(plans)


def _month_keys(count: int) -> list[str]:
    now = dt_util.now()
    current = now.year * 12 + now.month - 1
    keys: list[str] = []
    for offset in range(count - 1, -1, -1):
        month_index = current - offset
        keys.append(f"{month_index // 12:04d}-{month_index % 12 + 1:02d}")
    return keys


def _last_12_month_usage_chart(data: dict[str, Any]) -> list[dict[str, Any]]:
    keys = _month_keys(12)
    grouped = {key: {"date": key, "usage": 0.0, "amount": 0.0, "records": 0} for key in keys}
    for item in _hand_plan(data):
        used_at = _usage_datetime(item)
        if used_at is None:
            continue
        key = used_at.strftime("%Y-%m")
        if key not in grouped:
            continue
        grouped[key]["usage"] += _usage_amount(item)
        grouped[key]["amount"] += _usage_fee(item)
        grouped[key]["records"] += 1

    return [
        {
            "date": row["date"],
            "usage": round(row["usage"], 4),
            "amount": round(row["amount"], 2),
            "records": row["records"],
        }
        for row in grouped.values()
    ]


def _last_30_day_usage_chart(data: dict[str, Any]) -> list[dict[str, Any]]:
    today = dt_util.now().date()
    keys = [(today - timedelta(days=offset)).isoformat() for offset in range(29, -1, -1)]
    grouped = {key: {"date": key, "usage": 0.0, "amount": 0.0, "records": 0} for key in keys}
    for item in _hand_plan(data):
        key = _usage_day(item)
        if key not in grouped:
            continue
        grouped[key]["usage"] += _usage_amount(item)
        grouped[key]["amount"] += _usage_fee(item)
        grouped[key]["records"] += 1

    return [
        {
            "date": row["date"],
            "usage": round(row["usage"], 4),
            "amount": round(row["amount"], 2),
            "records": row["records"],
        }
        for row in grouped.values()
    ]


def _chart_total(chart: list[dict[str, Any]]) -> float:
    return round(sum(_to_float(row.get("usage")) or 0 for row in chart), 4)


def _last_12_month_usage_value(data: dict[str, Any]) -> float:
    return _chart_total(_last_12_month_usage_chart(data))


def _last_30_day_usage_value(data: dict[str, Any]) -> float:
    return _chart_total(_last_30_day_usage_chart(data))


def _usage_chart_attrs(chart: list[dict[str, Any]], updated_at: Any) -> dict[str, Any]:
    return _compact(
        {
            "daylist": chart,
            "chart": chart,
            "总记录数": sum(_to_int(row.get("records")) or 0 for row in chart),
            "更新时间": updated_at,
            "数据来源": ATTR_SOURCE,
        }
    )


def _last_12_month_usage_attrs(data: dict[str, Any]) -> dict[str, Any]:
    return _usage_chart_attrs(_last_12_month_usage_chart(data), _updated_at(data))


def _last_30_day_usage_attrs(data: dict[str, Any]) -> dict[str, Any]:
    return _usage_chart_attrs(_last_30_day_usage_chart(data), _updated_at(data))


def _usage_attrs(data: dict[str, Any]) -> dict[str, Any]:
    plans = _hand_plan(data)
    latest = _latest_billable_usage(plans)
    current = _latest(plans)
    user_info = _user_info(data)
    fallback_total = sum(
        _to_float(latest.get(key)) or 0 for key in ("f_gas1", "f_gas2", "f_gas3")
    )
    cumulative = _to_float(user_info.get("sumgas"))
    return _compact(
        {
            "最新用气量_m3": _to_float(latest.get("f_oughtamount")),
            "最新用气金额_元": _to_float(latest.get("f_oughtfee")),
            "最新抄表时间": latest.get("f_input_date"),
            "最新表底": _to_float(latest.get("f_tablebase")),
            "气价1_元": _to_float(latest.get("f_price1")),
            "气价2_元": _to_float(latest.get("f_price2")),
            "气价3_元": _to_float(latest.get("f_price3")),
            "本次一档用量_m3": _to_float(latest.get("f_gas1")),
            "本次二档用量_m3": _to_float(latest.get("f_gas2")),
            "本次三档用量_m3": _to_float(latest.get("f_gas3")),
            "本次一档金额_元": _to_float(latest.get("f_money1")),
            "本次二档金额_元": _to_float(latest.get("f_money2")),
            "本次三档金额_元": _to_float(latest.get("f_money3")),
            "累计用气量_m3": cumulative if cumulative is not None else fallback_total,
            "阶梯开始日期": user_info.get("stairbegindate"),
            "当前气量余额_m3": _to_float(current.get("f_curbalance")),
            "当前金额余额_元": _round2(current.get("f_balance")),
            "daylist": _usage_daylist(plans),
            "总记录数": len(plans),
            "数据时间": latest.get("f_input_date") or _updated_at(data),
            "更新时间": _updated_at(data),
            "数据来源": ATTR_SOURCE,
        }
    )


def _latest_sell_amount(data: dict[str, Any]) -> float | None:
    return _round2(_latest(_sell_list(data)).get("f_collection"))


def _latest_purchase_day_total(data: dict[str, Any]) -> float | None:
    sell_list = _sell_list(data)
    latest_day = _gas_day_key(_latest(sell_list).get("f_delivery_date"))
    if not latest_day:
        return None
    return round(
        _sum_float(
            [
                item
                for item in sell_list
                if _gas_day_key(item.get("f_delivery_date")) == latest_day
            ],
            "f_collection",
        ),
        2,
    )


def _latest_usage_amount(data: dict[str, Any]) -> float | None:
    return _to_float(_latest_billable_usage(_hand_plan(data)).get("f_oughtamount"))


def _latest_usage_fee(data: dict[str, Any]) -> float | None:
    return _round2(_latest_billable_usage(_hand_plan(data)).get("f_oughtfee"))


def _latest_usage_time(data: dict[str, Any]) -> str | None:
    return _format_local_datetime(
        _usage_datetime(_latest_billable_usage(_hand_plan(data)))
    )


def _latest_refresh_time(data: dict[str, Any]) -> str | None:
    return _format_local_datetime(_parse_api_datetime(_updated_at(data)))


def _card_daylist(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return gas usage records in electricity-info-card daylist format."""
    grouped: dict[str, dict[str, Any]] = {}
    for item in _hand_plan(data):
        day = _usage_day(item)
        usage = _usage_amount(item)
        amount = _usage_fee(item)
        if not day:
            continue
        row = grouped.setdefault(
            day,
            {
                "day": day,
                "dayEleNum": 0.0,
                "dayEleCost": 0.0,
                "dayTPq": 0,
                "dayPPq": 0,
                "dayNPq": 0,
                "dayVPq": 0,
                "f_gas": 0.0,
                "e_gas": 0.0,
                "unit": UnitOfVolume.CUBIC_METERS,
                "f_input_date": item.get("f_input_date"),
                "f_hand_date": item.get("f_hand_date"),
                "f_tablebase": item.get("f_tablebase"),
                "records": 0,
            },
        )
        row["dayEleNum"] += usage
        row["dayEleCost"] += amount
        row["f_gas"] += usage
        row["e_gas"] += amount
        row["records"] += 1

    recent_days = _last_30_day_usage_chart(data)
    recent_keys = {row["date"] for row in recent_days}
    for chart_row in recent_days:
        day = chart_row["date"]
        usage = _to_float(chart_row.get("usage")) or 0
        amount = _to_float(chart_row.get("amount")) or 0
        row = grouped.setdefault(
            day,
            {
                "day": day,
                "dayTPq": 0,
                "dayPPq": 0,
                "dayNPq": 0,
                "dayVPq": 0,
                "unit": UnitOfVolume.CUBIC_METERS,
            },
        )
        row["dayEleNum"] = usage
        row["dayEleCost"] = amount
        row["f_gas"] = usage
        row["e_gas"] = amount
        row["records"] = _to_int(chart_row.get("records")) or 0

    rows: list[dict[str, Any]] = []
    for day, row in grouped.items():
        usage = _to_float(row.get("f_gas")) or 0
        amount = _to_float(row.get("e_gas")) or 0
        if day not in recent_keys and usage <= 0 and amount <= 0:
            continue
        rows.append(
            {
                **row,
                "dayEleNum": round(usage, 4),
                "dayEleCost": round(amount, 2),
                "f_gas": round(usage, 4),
                "e_gas": round(amount, 2),
            }
        )
    return sorted(rows, key=lambda row: row["day"], reverse=True)


def _card_monthlist(daylist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in daylist:
        month = _gas_month_key(item.get("day"))
        if not month:
            continue
        row = grouped.setdefault(
            month,
            {
                "month": month,
                "monthEleNum": 0.0,
                "monthEleCost": 0.0,
                "monthTPq": 0,
                "monthPPq": 0,
                "monthNPq": 0,
                "monthVPq": 0,
                "unit": UnitOfVolume.CUBIC_METERS,
            },
        )
        row["monthEleNum"] += _to_float(item.get("f_gas")) or 0
        row["monthEleCost"] += _to_float(item.get("e_gas")) or 0
    return [
        {
            **row,
            "monthEleNum": round(row["monthEleNum"], 4),
            "monthEleCost": round(row["monthEleCost"], 2),
        }
        for _, row in sorted(grouped.items(), reverse=True)
    ]


def _card_yearlist(monthlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in monthlist:
        month = str(item.get("month", ""))
        year = month[:4]
        if not year:
            continue
        row = grouped.setdefault(
            year,
            {
                "year": year,
                "yearEleNum": 0.0,
                "yearEleCost": 0.0,
                "yearTPq": 0,
                "yearPPq": 0,
                "yearNPq": 0,
                "yearVPq": 0,
                "unit": UnitOfVolume.CUBIC_METERS,
            },
        )
        row["yearEleNum"] += _to_float(item.get("monthEleNum")) or 0
        row["yearEleCost"] += _to_float(item.get("monthEleCost")) or 0
    return [
        {
            **row,
            "yearEleNum": round(row["yearEleNum"], 4),
            "yearEleCost": round(row["yearEleCost"], 2),
        }
        for _, row in sorted(grouped.items(), reverse=True)
    ]


def _card_attrs(data: dict[str, Any]) -> dict[str, Any]:
    daylist = _card_daylist(data)
    monthlist = _card_monthlist(daylist)
    yearlist = _card_yearlist(monthlist)
    latest_usage = _latest_billable_usage(_hand_plan(data))
    user_info = _user_info(data)
    meter = _meter(data)
    return _compact(
        {
            "balance": _account_balance(data),
            "date": _latest_refresh_time(data) or _updated_at(data),
            "daylist": daylist,
            "monthlist": monthlist,
            "yearlist": yearlist,
            "utility_type": "gas",
            "unit": UnitOfVolume.CUBIC_METERS,
            "total_usage": _to_float(user_info.get("sumgas") or meter.get("f_total_gas")),
            "remaining_usage": _to_float(user_info.get("f_balance_gas") or meter.get("f_balance_gas")),
            "meter_reading": _to_float(meter.get("f_meter_base") or latest_usage.get("f_tablebase")),
            "recent_12_month_usage": _last_12_month_usage_value(data),
            "recent_30_day_usage": _last_30_day_usage_value(data),
            "last_payment_amount": _latest_sell_amount(data),
            "latest_usage": _latest_usage_amount(data),
            "latest_amount": _latest_usage_fee(data),
            "latest_usage_date": _usage_day(latest_usage),
            "数据来源": ATTR_SOURCE,
        }
    )


class RonghaoGasCardSensor(
    CoordinatorEntity[RonghaoGasDataUpdateCoordinator], SensorEntity
):
    """A card-friendly aggregate sensor for electricity-info-card."""

    _attr_has_entity_name = True
    _attr_translation_key = "card_data"
    _attr_icon = "mdi:fire"
    _attr_native_unit_of_measurement = CURRENCY_CNY
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(
        self,
        coordinator: RonghaoGasDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the card data sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_card_data"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        data = self._entry.data
        return DeviceInfo(
            identifiers={(DOMAIN, str(data.get(CONF_USERINFO_ID, self._entry.entry_id)))},
            manufacturer="荣浩能源",
            model="Ronghao Gas Cloud",
            name="荣浩燃气",
            configuration_url=data.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
        )

    @property
    def native_value(self) -> Any:
        """Return the account balance."""
        return _account_balance(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return card-friendly aggregate attributes."""
        return _card_attrs(self.coordinator.data or {})


SENSOR_DESCRIPTIONS: tuple[RonghaoGasSensorEntityDescription, ...] = (
    RonghaoGasSensorEntityDescription(
        key="account_balance",
        name="账户余额",
        icon="mdi:currency-cny",
        native_unit_of_measurement=CURRENCY_CNY,
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_account_balance,
        attrs_fn=_user_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="cumulative_gas",
        name="累计用气量",
        icon="mdi:fire",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _to_float(_user_info(data).get("sumgas")),
        attrs_fn=_user_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="meter_reading",
        name="燃气表读数",
        icon="mdi:gas-station",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _to_float(_meter(data).get("f_meter_base")),
        attrs_fn=_meter_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="meter_gas_balance",
        name="气量余额",
        icon="mdi:meter-gas",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        value_fn=lambda data: _to_float(_meter(data).get("f_balance_gas")),
        attrs_fn=_meter_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="latest_purchase_amount",
        name="最近购气金额",
        icon="mdi:cart-outline",
        native_unit_of_measurement=CURRENCY_CNY,
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_latest_sell_amount,
        attrs_fn=_sell_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="latest_usage_amount",
        name="最新用气量",
        icon="mdi:fire",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        value_fn=_latest_usage_amount,
        attrs_fn=_usage_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="latest_usage_fee",
        name="最新用气金额",
        icon="mdi:currency-cny",
        native_unit_of_measurement=CURRENCY_CNY,
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_latest_usage_fee,
        attrs_fn=_usage_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="usage_last_12_months",
        name="最近12个月用气数",
        icon="mdi:chart-line",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last_12_month_usage_value,
        attrs_fn=_last_12_month_usage_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="usage_last_30_days",
        name="最近30天用气数",
        icon="mdi:chart-bar",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last_30_day_usage_value,
        attrs_fn=_last_30_day_usage_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="latest_usage_time",
        name="最近一次用气时间",
        icon="mdi:calendar-clock",
        value_fn=_latest_usage_time,
        attrs_fn=_usage_attrs,
    ),
    RonghaoGasSensorEntityDescription(
        key="latest_refresh_time",
        name="最近一次刷新时间",
        icon="mdi:update",
        value_fn=_latest_refresh_time,
        attrs_fn=_refresh_attrs,
    ),
)

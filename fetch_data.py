"""从扶摇 API 获取贵州茅台（600519.SH）2024 年报的财务指标。

用法：python fetch_data.py
API Key 优先从环境变量 HITHINK_FINANCE_API_KEY 读取，
环境变量为空时回退到同目录下的 ai-playground.txt（本地开发用）。
"""

import os
import sys
from pathlib import Path

import requests

# Windows 下管道/重定向输出时默认用 GBK，这里统一成 UTF-8 避免中文乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except OSError:
        pass

# 部分指标在接口中带有 calculate_ 前缀，匹配时兼容两种写法
INDEX_ID_PREFIXES = ("calculate_",)

API_URL = "https://fuyao.aicubes.cn/api/a-share/financials/indicators"
KEY_FILE = Path(__file__).resolve().parent / "ai-playground.txt"
API_KEY_ENV_VAR = "HITHINK_FINANCE_API_KEY"

# 需要提取的指标 index_id
TARGET_INDICATORS = [
    "operating_income_yoy_growth_ratio",
    "sale_gross_margin",
    "net_profit_cash_content",
]


def load_api_key(key_file=KEY_FILE):
    """读取 API Key，并去除首尾的换行符和空格。

    优先级：环境变量 HITHINK_FINANCE_API_KEY > 本地 key 文件（本地开发用）。
    """
    # 1) 云端 / CI：优先环境变量
    key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    if key:
        return key

    # 2) 本地：回退到 txt 文件
    try:
        key = key_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"未找到 API Key：环境变量 {API_KEY_ENV_VAR} 为空，且文件不存在：{key_file}"
        )
    except OSError as e:
        raise RuntimeError(f"读取 API Key 文件失败：{e}")

    if not key:
        raise RuntimeError(
            f"API Key 为空：环境变量 {API_KEY_ENV_VAR} 为空，文件内容也为空：{key_file}"
        )
    return key


def fetch_indicators(api_key, thscode="600519.SH", report="2024-4", timeout=15):
    """调用接口并返回解析后的 JSON；失败时抛出 RuntimeError。"""
    headers = {"X-api-key": api_key}
    params = {"thscode": thscode, "report": report}

    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"网络请求失败：{e}")

    try:
        payload = resp.json()
    except ValueError:
        raise RuntimeError(
            f"返回内容不是合法 JSON（HTTP {resp.status_code}）：{resp.text[:300]}"
        )

    if not isinstance(payload, dict):
        raise RuntimeError(f"返回数据格式异常：{payload!r}")

    # HTTP 层错误也要带上接口返回的 msg，方便排查
    if resp.status_code != 200:
        msg = payload.get("msg") or payload.get("message") or ""
        raise RuntimeError(f"HTTP {resp.status_code}" + (f"，msg={msg}" if msg else ""))

    code = payload.get("code")
    if code != 0:
        msg = payload.get("msg") or payload.get("message") or "无错误信息"
        raise RuntimeError(f"API 返回错误，code={code}，msg={msg}")

    return payload


def find_indicator_values(node, targets, found=None):
    """递归遍历嵌套结构，找到 index_id 匹配的指标并提取其 value。

    返回 {index_id: value}，同一个指标出现多次时保留第一个。
    """
    if found is None:
        found = {}

    if isinstance(node, dict):
        index_id = node.get("index_id")
        if isinstance(index_id, str):
            # 去掉 calculate_ 等可能的前缀，还原成标准指标名
            name = index_id
            for prefix in INDEX_ID_PREFIXES:
                if name.startswith(prefix):
                    name = name[len(prefix):]
                    break
            if name in targets and name not in found:
                found[name] = node.get("value")
        # 继续向下遍历（值可能藏在 data / items 等子节点中）
        for value in node.values():
            find_indicator_values(value, targets, found)
    elif isinstance(node, list):
        for item in node:
            find_indicator_values(item, targets, found)

    return found


def main():
    try:
        api_key = load_api_key()
        payload = fetch_indicators(api_key)
    except RuntimeError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 1

    values = find_indicator_values(payload, set(TARGET_INDICATORS))

    print("贵州茅台（600519.SH）2024-4 财务指标：")
    for index_id in TARGET_INDICATORS:
        if index_id in values:
            print(f"  {index_id}: {values[index_id]}")
        else:
            print(f"  {index_id}: 未在返回数据中找到")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""本地测试 MCP Server —— SSE 模式。SoulChat 添加: http://localhost:8765/sse / SSE / 无认证。"""
import hashlib
import json
import random
import time
from datetime import datetime, timezone, timedelta

from mcp.server.fastmcp import FastMCP

_CST = timezone(timedelta(hours=8))
mcp = FastMCP("TestTools", host="0.0.0.0", port=8765)


@mcp.tool()
def weather(city: str) -> str:
    """查询指定城市的天气（模拟数据）。"""
    conds = ["晴", "多云", "小雨", "阴", "阵雨"]
    temps = random.randint(5, 38)
    return json.dumps({
        "city": city,
        "temperature": temps,
        "humidity": random.randint(30, 90),
        "condition": random.choice(conds),
        "updated": datetime.now(_CST).strftime("%H:%M"),
    }, ensure_ascii=False)


@mcp.tool()
def text_stats(text: str) -> str:
    """分析文本：字数、词频、MD5。"""
    chars = len(text)
    words = len(text.split()) if text.strip() else 0
    md5 = hashlib.md5(text.encode()).hexdigest()
    return json.dumps({
        "characters": chars,
        "words": words,
        "md5": md5,
    }, ensure_ascii=False)


@mcp.tool()
def roll_dice(sides: int = 6, count: int = 1) -> str:
    """掷骰子。sides=面数，count=个数。"""
    results = [random.randint(1, sides) for _ in range(count)]
    return json.dumps({"sides": sides, "count": count, "results": results, "sum": sum(results)}, ensure_ascii=False)


@mcp.tool()
def sha256(text: str) -> str:
    """计算文本的 SHA256 哈希。"""
    return hashlib.sha256(text.encode()).hexdigest()


@mcp.tool()
def unix_time() -> str:
    """获取当前 Unix 时间戳（秒和毫秒）。"""
    now = time.time()
    return json.dumps({"seconds": int(now), "millis": int(now * 1000), "datetime": datetime.now(_CST).isoformat()}, ensure_ascii=False)


if __name__ == "__main__":
    print("MCP Test Server: http://localhost:8765/sse")
    print("Tools: weather, text_stats, roll_dice, sha256, unix_time")
    mcp.run(transport="sse")

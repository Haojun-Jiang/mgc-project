"""用于手动验证 FixAgent -> VerifyAgent 闭环的示例代码。

建议在前端 Requirement 中填写：

calculate_payable 用于计算订单应付金额。amount 表示原价，必须大于等于 0，
否则抛出 ValueError；is_member=True 时应按原价的 80% 结算，
is_member=False 时应按原价结算；最终结果使用 round(value, 2) 保留两位小数。
不得修改函数名和参数。

文件故意把会员折扣写成了 90%，便于验证完整流程：
生成测试 -> 测试失败 -> FixAgent 修复 -> VerifyAgent 重新执行并通过。
"""

from __future__ import annotations


def calculate_payable(amount: float, is_member: bool) -> float:
    """按照模块顶部的业务规则计算订单应付金额。"""
    if amount < 0:
        raise ValueError("amount must be non-negative")

    # 故意保留的单一缺陷：会员应享受 8 折，这里错误写成了 9 折。
    rate = 0.9 if is_member else 1.0
    return round(amount * rate, 2)


if __name__ == "__main__":
    print(calculate_payable(100.0, is_member=True))

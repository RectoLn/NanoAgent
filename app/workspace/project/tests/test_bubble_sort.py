"""
冒泡排序单元测试模块
测试各种数据集的排序结果与 Python 内置 sorted() 一致性
"""

import sys
import os

# 添加项目 src 目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import unittest
from bubble_sort import bubble_sort
from dataset import (
    get_random_list,
    get_ascending_list,
    get_descending_list,
    get_duplicate_list,
    get_single_element_list,
    get_empty_list
)


class TestBubbleSort(unittest.TestCase):
    """冒泡排序单元测试类"""
    
    def test_random_list(self):
        """测试随机乱序列表"""
        data = get_random_list()
        expected = sorted(data)
        result = bubble_sort(data)
        self.assertEqual(result, expected,
            f"随机乱序列表排序失败: 期望 {expected}, 得到 {result}")
    
    def test_ascending_list(self):
        """测试已正序列表（最佳情况）"""
        data = get_ascending_list()
        expected = sorted(data)
        result = bubble_sort(data)
        self.assertEqual(result, expected,
            f"正序列表排序失败: 期望 {expected}, 得到 {result}")
    
    def test_descending_list(self):
        """测试已逆序列表（最坏情况）"""
        data = get_descending_list()
        expected = sorted(data)
        result = bubble_sort(data)
        self.assertEqual(result, expected,
            f"逆序列表排序失败: 期望 {expected}, 得到 {result}")
    
    def test_duplicate_list(self):
        """测试包含重复元素的列表"""
        data = get_duplicate_list()
        expected = sorted(data)
        result = bubble_sort(data)
        self.assertEqual(result, expected,
            f"重复元素列表排序失败: 期望 {expected}, 得到 {result}")
    
    def test_single_element_list(self):
        """测试只有一个元素的列表"""
        data = get_single_element_list()
        expected = sorted(data)
        result = bubble_sort(data)
        self.assertEqual(result, expected,
            f"单元素列表排序失败: 期望 {expected}, 得到 {result}")
    
    def test_empty_list(self):
        """测试空列表"""
        data = get_empty_list()
        expected = sorted(data)
        result = bubble_sort(data)
        self.assertEqual(result, expected,
            f"空列表排序失败: 期望 {expected}, 得到 {result}")


if __name__ == '__main__':
    print("=" * 60)
    print("运行冒泡排序单元测试")
    print("=" * 60)
    
    # 使用 unittest 运行测试
    unittest.main(verbosity=2)
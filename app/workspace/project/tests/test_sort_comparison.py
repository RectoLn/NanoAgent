"""
排序算法对比单元测试模块
验证选择排序、插入排序与冒泡排序的正确性
"""

import sys
import os

# 添加项目 src 目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import unittest
from bubble_sort import bubble_sort
from sort_comparison import selection_sort, insertion_sort
from dataset import (
    get_random_list,
    get_ascending_list,
    get_descending_list,
    get_duplicate_list,
    get_single_element_list,
    get_empty_list
)


class TestSelectionSort(unittest.TestCase):
    """选择排序单元测试类"""
    
    def test_random_list(self):
        """测试随机乱序列表"""
        data = get_random_list()
        expected = sorted(data)
        result = selection_sort(data)
        self.assertEqual(result, expected,
            f"选择排序 - 随机乱序列表排序失败")
    
    def test_ascending_list(self):
        """测试已正序列表"""
        data = get_ascending_list()
        expected = sorted(data)
        result = selection_sort(data)
        self.assertEqual(result, expected,
            f"选择排序 - 正序列表排序失败")
    
    def test_descending_list(self):
        """测试已逆序列表"""
        data = get_descending_list()
        expected = sorted(data)
        result = selection_sort(data)
        self.assertEqual(result, expected,
            f"选择排序 - 逆序列表排序失败")
    
    def test_duplicate_list(self):
        """测试包含重复元素的列表"""
        data = get_duplicate_list()
        expected = sorted(data)
        result = selection_sort(data)
        self.assertEqual(result, expected,
            f"选择排序 - 重复元素列表排序失败")
    
    def test_single_element_list(self):
        """测试只有一个元素的列表"""
        data = get_single_element_list()
        expected = sorted(data)
        result = selection_sort(data)
        self.assertEqual(result, expected,
            f"选择排序 - 单元素列表排序失败")
    
    def test_empty_list(self):
        """测试空列表"""
        data = get_empty_list()
        expected = sorted(data)
        result = selection_sort(data)
        self.assertEqual(result, expected,
            f"选择排序 - 空列表排序失败")


class TestInsertionSort(unittest.TestCase):
    """插入排序单元测试类"""
    
    def test_random_list(self):
        """测试随机乱序列表"""
        data = get_random_list()
        expected = sorted(data)
        result = insertion_sort(data)
        self.assertEqual(result, expected,
            f"插入排序 - 随机乱序列表排序失败")
    
    def test_ascending_list(self):
        """测试已正序列表"""
        data = get_ascending_list()
        expected = sorted(data)
        result = insertion_sort(data)
        self.assertEqual(result, expected,
            f"插入排序 - 正序列表排序失败")
    
    def test_descending_list(self):
        """测试已逆序列表"""
        data = get_descending_list()
        expected = sorted(data)
        result = insertion_sort(data)
        self.assertEqual(result, expected,
            f"插入排序 - 逆序列表排序失败")
    
    def test_duplicate_list(self):
        """测试包含重复元素的列表"""
        data = get_duplicate_list()
        expected = sorted(data)
        result = insertion_sort(data)
        self.assertEqual(result, expected,
            f"插入排序 - 重复元素列表排序失败")
    
    def test_single_element_list(self):
        """测试只有一个元素的列表"""
        data = get_single_element_list()
        expected = sorted(data)
        result = insertion_sort(data)
        self.assertEqual(result, expected,
            f"插入排序 - 单元素列表排序失败")
    
    def test_empty_list(self):
        """测试空列表"""
        data = get_empty_list()
        expected = sorted(data)
        result = insertion_sort(data)
        self.assertEqual(result, expected,
            f"插入排序 - 空列表排序失败")


class TestSortConsistency(unittest.TestCase):
    """测试三种排序结果一致性"""
    
    def test_all_sorts_produce_same_result(self):
        """验证三种排序算法产生相同结果"""
        datasets = [
            get_random_list(),
            get_ascending_list(),
            get_descending_list(),
            get_duplicate_list(),
            get_single_element_list(),
            get_empty_list()
        ]
        
        for i, data in enumerate(datasets):
            with self.subTest(dataset_index=i):
                expected = sorted(data)
                bubble_result = bubble_sort(data)
                selection_result = selection_sort(data)
                insertion_result = insertion_sort(data)
                
                self.assertEqual(bubble_result, expected)
                self.assertEqual(selection_result, expected)
                self.assertEqual(insertion_result, expected)


if __name__ == '__main__':
    print("=" * 60)
    print("排序算法单元测试（选择排序 + 插入排序）")
    print("=" * 60)
    
    unittest.main(verbosity=2)

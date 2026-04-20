#!/usr/bin/env python3
"""
冒泡排序单元测试
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bubble_sort import bubble_sort, bubble_sort_inplace
from dataset import get_all_datasets


def test_random_list():
    """测试随机乱序列表"""
    datasets = get_all_datasets()
    random_list = datasets["random_list"]
    
    # 测试非原地排序
    sorted_result = bubble_sort(random_list)
    expected = sorted(random_list)
    
    assert sorted_result == expected, f"随机列表排序失败: {sorted_result} != {expected}"
    print("✓ 随机乱序列表测试通过")
    
    # 测试原地排序
    test_list = random_list.copy()
    bubble_sort_inplace(test_list)
    assert test_list == expected, f"随机列表原地排序失败: {test_list} != {expected}"
    print("✓ 随机乱序列表原地排序测试通过")


def test_sorted_list():
    """测试已经正序的列表"""
    datasets = get_all_datasets()
    sorted_list = datasets["sorted_list"]
    
    # 测试非原地排序
    sorted_result = bubble_sort(sorted_list)
    expected = sorted(sorted_list)
    
    assert sorted_result == expected, f"正序列表排序失败: {sorted_result} != {expected}"
    print("✓ 已经正序列表测试通过")
    
    # 测试原地排序
    test_list = sorted_list.copy()
    bubble_sort_inplace(test_list)
    assert test_list == expected, f"正序列表原地排序失败: {test_list} != {expected}"
    print("✓ 已经正序列表原地排序测试通过")


def test_reverse_sorted_list():
    """测试已经逆序的列表"""
    datasets = get_all_datasets()
    reverse_list = datasets["reverse_sorted_list"]
    
    # 测试非原地排序
    sorted_result = bubble_sort(reverse_list)
    expected = sorted(reverse_list)
    
    assert sorted_result == expected, f"逆序列表排序失败: {sorted_result} != {expected}"
    print("✓ 已经逆序列表测试通过")
    
    # 测试原地排序
    test_list = reverse_list.copy()
    bubble_sort_inplace(test_list)
    assert test_list == expected, f"逆序列表原地排序失败: {test_list} != {expected}"
    print("✓ 已经逆序列表原地排序测试通过")


def test_list_with_duplicates():
    """测试包含重复元素的列表"""
    datasets = get_all_datasets()
    dup_list = datasets["list_with_duplicates"]
    
    # 测试非原地排序
    sorted_result = bubble_sort(dup_list)
    expected = sorted(dup_list)
    
    assert sorted_result == expected, f"重复元素列表排序失败: {sorted_result} != {expected}"
    print("✓ 包含重复元素列表测试通过")
    
    # 测试原地排序
    test_list = dup_list.copy()
    bubble_sort_inplace(test_list)
    assert test_list == expected, f"重复元素列表原地排序失败: {test_list} != {expected}"
    print("✓ 包含重复元素列表原地排序测试通过")


def test_single_element_list():
    """测试只有一个元素的列表"""
    datasets = get_all_datasets()
    single_list = datasets["single_element_list"]
    
    # 测试非原地排序
    sorted_result = bubble_sort(single_list)
    expected = sorted(single_list)
    
    assert sorted_result == expected, f"单元素列表排序失败: {sorted_result} != {expected}"
    print("✓ 只有一个元素的列表测试通过")
    
    # 测试原地排序
    test_list = single_list.copy()
    bubble_sort_inplace(test_list)
    assert test_list == expected, f"单元素列表原地排序失败: {test_list} != {expected}"
    print("✓ 只有一个元素的列表原地排序测试通过")


def test_empty_list():
    """测试空列表"""
    datasets = get_all_datasets()
    empty_list = datasets["empty_list"]
    
    # 测试非原地排序
    sorted_result = bubble_sort(empty_list)
    expected = sorted(empty_list)
    
    assert sorted_result == expected, f"空列表排序失败: {sorted_result} != {expected}"
    print("✓ 空列表测试通过")
    
    # 测试原地排序
    test_list = empty_list.copy()
    bubble_sort_inplace(test_list)
    assert test_list == expected, f"空列表原地排序失败: {test_list} != {expected}"
    print("✓ 空列表原地排序测试通过")


def test_original_list_not_modified():
    """测试原列表是否被修改"""
    test_list = [5, 3, 8, 1, 2]
    original_copy = test_list.copy()
    
    # 测试非原地排序
    sorted_result = bubble_sort(test_list)
    
    # 原列表应该没有被修改
    assert test_list == original_copy, f"原列表被修改了: {test_list} != {original_copy}"
    print("✓ 原列表未被修改测试通过")


def test_edge_cases():
    """测试边界情况"""
    # 测试所有元素相同
    same_list = [7, 7, 7, 7, 7]
    sorted_result = bubble_sort(same_list)
    assert sorted_result == same_list, f"相同元素列表排序失败"
    print("✓ 所有元素相同列表测试通过")
    
    # 测试负数
    negative_list = [-5, -1, -8, -3, -2]
    sorted_result = bubble_sort(negative_list)
    assert sorted_result == sorted(negative_list), f"负数列表排序失败"
    print("✓ 负数列表测试通过")
    
    # 测试混合正负数
    mixed_list = [5, -3, 0, -1, 2]
    sorted_result = bubble_sort(mixed_list)
    assert sorted_result == sorted(mixed_list), f"混合正负数列表排序失败"
    print("✓ 混合正负数列表测试通过")


def run_all_tests():
    """运行所有测试"""
    print("开始运行冒泡排序单元测试...")
    print("=" * 60)
    
    tests = [
        test_random_list,
        test_sorted_list,
        test_reverse_sorted_list,
        test_list_with_duplicates,
        test_single_element_list,
        test_empty_list,
        test_original_list_not_modified,
        test_edge_cases
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"✗ {test_func.__name__} 失败: {e}")
        except Exception as e:
            failed += 1
            print(f"✗ {test_func.__name__} 异常: {e}")
    
    print("=" * 60)
    print(f"测试结果: 通过 {passed} 个，失败 {failed} 个")
    
    if failed == 0:
        print("🎉 所有测试通过！")
        return True
    else:
        print("❌ 有测试失败，请检查代码")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
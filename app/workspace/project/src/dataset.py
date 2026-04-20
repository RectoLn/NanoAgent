#!/usr/bin/env python3
"""
测试数据集构造模块
"""

import random


def generate_random_list(size=20, min_val=1, max_val=100):
    """
    生成随机乱序列表
    
    参数:
        size: 列表大小
        min_val: 最小值
        max_val: 最大值
        
    返回:
        随机列表
    """
    return [random.randint(min_val, max_val) for _ in range(size)]


def get_sorted_list(size=10, min_val=1, max_val=100):
    """
    生成已经正序的列表
    
    参数:
        size: 列表大小
        min_val: 最小值
        max_val: 最大值
        
    返回:
        正序列表
    """
    arr = [random.randint(min_val, max_val) for _ in range(size)]
    return sorted(arr)


def get_reverse_sorted_list(size=10, min_val=1, max_val=100):
    """
    生成已经逆序的列表
    
    参数:
        size: 列表大小
        min_val: 最小值
        max_val: 最大值
        
    返回:
        逆序列表
    """
    arr = [random.randint(min_val, max_val) for _ in range(size)]
    return sorted(arr, reverse=True)


def get_list_with_duplicates(size=15, min_val=1, max_val=20):
    """
    生成包含重复元素的列表
    
    参数:
        size: 列表大小
        min_val: 最小值
        max_val: 最大值（范围较小以确保重复）
        
    返回:
        包含重复元素的列表
    """
    return [random.randint(min_val, max_val) for _ in range(size)]


def get_single_element_list():
    """
    生成只有一个元素的列表
    
    返回:
        单元素列表
    """
    return [random.randint(1, 100)]


def get_empty_list():
    """
    生成空列表
    
    返回:
        空列表
    """
    return []


def get_all_datasets():
    """
    获取所有测试数据集
    
    返回:
        包含所有数据集的字典
    """
    # 设置随机种子以确保可重复性
    random.seed(42)
    
    datasets = {
        "random_list": generate_random_list(20),
        "sorted_list": get_sorted_list(10),
        "reverse_sorted_list": get_reverse_sorted_list(10),
        "list_with_duplicates": get_list_with_duplicates(15),
        "single_element_list": get_single_element_list(),
        "empty_list": get_empty_list()
    }
    
    return datasets


def print_datasets(datasets):
    """
    打印所有数据集
    
    参数:
        datasets: 数据集字典
    """
    print("测试数据集:")
    print("=" * 60)
    
    for name, data in datasets.items():
        print(f"{name}:")
        print(f"  长度: {len(data)}")
        print(f"  内容: {data}")
        print(f"  是否有序: {data == sorted(data)}")
        print("-" * 40)


if __name__ == "__main__":
    # 生成并打印所有数据集
    datasets = get_all_datasets()
    print_datasets(datasets)
    
    # 验证数据集特性
    print("\n数据集特性验证:")
    print("=" * 60)
    
    # 验证随机列表确实乱序
    random_list = datasets["random_list"]
    print(f"随机列表是否乱序: {random_list != sorted(random_list)}")
    
    # 验证正序列表确实有序
    sorted_list = datasets["sorted_list"]
    print(f"正序列表是否有序: {sorted_list == sorted(sorted_list)}")
    
    # 验证逆序列表确实逆序
    reverse_list = datasets["reverse_sorted_list"]
    print(f"逆序列表是否逆序: {reverse_list == sorted(reverse_list, reverse=True)}")
    
    # 验证重复元素列表确实有重复
    dup_list = datasets["list_with_duplicates"]
    has_duplicates = len(dup_list) != len(set(dup_list))
    print(f"重复元素列表是否有重复: {has_duplicates}")
    
    # 验证单元素列表
    single_list = datasets["single_element_list"]
    print(f"单元素列表长度: {len(single_list)}")
    
    # 验证空列表
    empty_list = datasets["empty_list"]
    print(f"空列表长度: {len(empty_list)}")
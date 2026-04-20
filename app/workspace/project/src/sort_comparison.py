"""
排序算法对比模块
实现选择排序、插入排序，并与冒泡排序进行性能对比
"""

import time
import sys
import os

# 添加当前目录到路径以导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bubble_sort import bubble_sort
from dataset import (
    get_random_list,
    get_ascending_list,
    get_descending_list,
    get_duplicate_list,
    get_single_element_list,
    get_empty_list
)


def selection_sort(arr):
    """
    选择排序算法实现
    
    原理：每轮从未排序部分选择最小元素放到已排序部分末尾
    
    参数:
        arr: 待排序的列表
        
    返回:
        排序后的列表
    """
    result = arr.copy()
    n = len(result)
    
    for i in range(n):
        # 假设当前索引是最小值
        min_idx = i
        # 在未排序部分查找最小元素
        for j in range(i + 1, n):
            if result[j] < result[min_idx]:
                min_idx = j
        # 将最小元素交换到已排序部分末尾
        result[i], result[min_idx] = result[min_idx], result[i]
    
    return result


def insertion_sort(arr):
    """
    插入排序算法实现
    
    原理：将元素逐个插入到已排序部分的正确位置
    
    参数:
        arr: 待排序的列表
        
    返回:
        排序后的列表
    """
    result = arr.copy()
    n = len(result)
    
    for i in range(1, n):
        key = result[i]
        j = i - 1
        # 将比 key 大的元素向后移动
        while j >= 0 and result[j] > key:
            result[j + 1] = result[j]
            j -= 1
        # 插入 key 到正确位置
        result[j + 1] = key
    
    return result


def benchmark_sort(sort_func, data, runs=100):
    """
    对排序函数进行性能计时
    
    参数:
        sort_func: 排序函数
        data: 测试数据
        runs: 运行次数
        
    返回:
        平均耗时（秒）
    """
    total_time = 0
    for _ in range(runs):
        start = time.perf_counter()
        sort_func(data)
        end = time.perf_counter()
        total_time += (end - start)
    
    return total_time / runs


def run_comparison():
    """
    运行三种排序算法的性能对比
    """
    # 定义测试数据集
    datasets = {
        "随机乱序列表": get_random_list(),
        "正序列表": get_ascending_list(),
        "逆序列表": get_descending_list(),
        "重复元素列表": get_duplicate_list(),
        "单元素列表": get_single_element_list(),
        "空列表": get_empty_list()
    }
    
    # 排序函数列表
    sort_funcs = {
        "冒泡排序": bubble_sort,
        "选择排序": selection_sort,
        "插入排序": insertion_sort
    }
    
    # 存储结果
    results = {name: {} for name in sort_funcs.keys()}
    
    print("=" * 70)
    print("排序算法性能对比测试")
    print("=" * 70)
    print(f"每种数据集运行 100 次取平均值\n")
    
    # 对每个数据集进行测试
    for dataset_name, data in datasets.items():
        print(f"\n📊 数据集: {dataset_name} (长度: {len(data)})")
        print("-" * 50)
        
        for sort_name, sort_func in sort_funcs.items():
            avg_time = benchmark_sort(sort_func, data, runs=100)
            results[sort_name][dataset_name] = avg_time
            print(f"  {sort_name:10s}: {avg_time * 1000:10.6f} ms")
    
    # 打印汇总表格
    print("\n" + "=" * 70)
    print("📈 性能对比汇总表")
    print("=" * 70)
    print(f"{'数据集':<20s} | {'冒泡排序':<12s} | {'选择排序':<12s} | {'插入排序':<12s}")
    print("-" * 70)
    
    for dataset_name in datasets.keys():
        bubble_time = results["冒泡排序"][dataset_name] * 1000
        selection_time = results["选择排序"][dataset_name] * 1000
        insertion_time = results["插入排序"][dataset_name] * 1000
        
        print(f"{dataset_name:<18s} | {bubble_time:>10.4f}ms | {selection_time:>10.4f}ms | {insertion_time:>10.4f}ms")
    
    print("-" * 70)
    print("\n✅ 性能测试完成！")
    
    return results


if __name__ == "__main__":
    run_comparison()

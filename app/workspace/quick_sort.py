#!/usr/bin/env python3
"""
快速排序算法实现
"""

def quick_sort(arr):
    """
    快速排序主函数
    """
    if len(arr) <= 1:
        return arr
    
    # 选择基准元素（这里选择最后一个元素）
    pivot = arr[-1]
    
    # 分区操作
    left = []
    right = []
    equal = []
    
    for num in arr:
        if num < pivot:
            left.append(num)
        elif num > pivot:
            right.append(num)
        else:
            equal.append(num)
    
    # 递归排序左右子数组
    return quick_sort(left) + equal + quick_sort(right)


def quick_sort_inplace(arr, low=0, high=None):
    """
    原地快速排序（节省空间）
    """
    if high is None:
        high = len(arr) - 1
    
    if low < high:
        # 分区操作，返回基准元素的正确位置
        pi = partition(arr, low, high)
        
        # 递归排序左右子数组
        quick_sort_inplace(arr, low, pi - 1)
        quick_sort_inplace(arr, pi + 1, high)
    
    return arr


def partition(arr, low, high):
    """
    分区函数，用于原地快速排序
    """
    # 选择基准元素（这里选择最后一个元素）
    pivot = arr[high]
    
    # 小于基准元素的索引
    i = low - 1
    
    for j in range(low, high):
        if arr[j] <= pivot:
            i += 1
            # 交换元素
            arr[i], arr[j] = arr[j], arr[i]
    
    # 将基准元素放到正确位置
    arr[i + 1], arr[high] = arr[high], arr[i + 1]
    return i + 1


def test_quick_sort():
    """
    测试快速排序算法
    """
    test_cases = [
        ([], []),
        ([1], [1]),
        ([5, 2, 8, 1, 9], [1, 2, 5, 8, 9]),
        ([9, 8, 7, 6, 5], [5, 6, 7, 8, 9]),
        ([3, 1, 4, 1, 5, 9, 2, 6], [1, 1, 2, 3, 4, 5, 6, 9]),
        ([64, 34, 25, 12, 22, 11, 90], [11, 12, 22, 25, 34, 64, 90]),
    ]
    
    print("测试快速排序算法...")
    print("=" * 50)
    
    # 测试普通快速排序
    print("1. 测试普通快速排序（非原地）：")
    for i, (input_arr, expected) in enumerate(test_cases):
        result = quick_sort(input_arr.copy())
        status = "✓" if result == expected else "✗"
        print(f"  测试用例 {i+1}: {status}")
        if result != expected:
            print(f"    输入: {input_arr}")
            print(f"    期望: {expected}")
            print(f"    实际: {result}")
    
    print("\n2. 测试原地快速排序：")
    for i, (input_arr, expected) in enumerate(test_cases):
        arr_copy = input_arr.copy()
        result = quick_sort_inplace(arr_copy)
        status = "✓" if result == expected else "✗"
        print(f"  测试用例 {i+1}: {status}")
        if result != expected:
            print(f"    输入: {input_arr}")
            print(f"    期望: {expected}")
            print(f"    实际: {result}")
    
    # 性能测试
    print("\n3. 性能测试：")
    import random
    import time
    
    # 生成随机数组
    random.seed(42)
    large_array = [random.randint(0, 10000) for _ in range(1000)]
    
    # 测试普通快速排序性能
    start_time = time.time()
    sorted_array1 = quick_sort(large_array.copy())
    time1 = time.time() - start_time
    
    # 测试原地快速排序性能
    start_time = time.time()
    arr_copy = large_array.copy()
    sorted_array2 = quick_sort_inplace(arr_copy)
    time2 = time.time() - start_time
    
    # 验证排序结果正确性
    is_correct = sorted_array1 == sorted(large_array) and sorted_array2 == sorted(large_array)
    
    print(f"  数组大小: 1000个随机整数")
    print(f"  普通快速排序时间: {time1:.4f}秒")
    print(f"  原地快速排序时间: {time2:.4f}秒")
    print(f"  排序结果正确: {'✓' if is_correct else '✗'}")
    
    return True


if __name__ == "__main__":
    test_quick_sort()
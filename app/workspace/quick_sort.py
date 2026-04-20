"""
快速排序（Quick Sort）实现
时间复杂度: O(n log n) 平均, O(n²) 最坏
空间复杂度: O(log n)
"""
import random

def quick_sort(arr):
    """快速排序主函数"""
    if len(arr) <= 1:
        return arr
    
    # 选择基准元素（这里使用第一个元素）
    pivot = arr[0]
    
    # 分区：小于基准的放左边，大于基准的放右边
    left = [x for x in arr[1:] if x < pivot]
    right = [x for x in arr[1:] if x >= pivot]
    
    # 递归排序左右两部分并合并
    return quick_sort(left) + [pivot] + quick_sort(right)


def quick_sort_inplace(arr, low=0, high=None):
    """原地快速排序（使用双指针法）"""
    if high is None:
        high = len(arr) - 1
    
    if low < high:
        # 分区，返回基准元素的正确位置
        pivot_idx = partition(arr, low, high)
        # 递归排序左右两部分
        quick_sort_inplace(arr, low, pivot_idx - 1)
        quick_sort_inplace(arr, pivot_idx + 1, high)
    
    return arr


def partition(arr, low, high):
    """分区操作"""
    pivot = arr[high]  # 选择最后一个元素作为基准
    i = low - 1
    
    for j in range(low, high):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    
    arr[i + 1], arr[high] = arr[high], arr[i + 1]
    return i + 1


# ====== 测试代码 ======
if __name__ == "__main__":
    print("=" * 50)
    print("快速排序算法测试")
    print("=" * 50)
    
    # 测试1: 基本功能测试
    print("\n【测试1】基本排序功能")
    test_cases = [
        ([3, 1, 4, 1, 5, 9, 2, 6], "乱序数组"),
        ([1], "单个元素"),
        ([], "空数组"),
        ([5, 4, 3, 2, 1], "逆序数组"),
        ([1, 1, 1, 1], "重复元素"),
    ]
    
    for arr, desc in test_cases:
        original = arr.copy()
        result = quick_sort(arr.copy())
        print(f"  {desc}: {original} → {result}")
        assert result == sorted(original), f"排序失败: {result}"
    print("  ✓ 所有基本测试通过")
    
    # 测试2: 原地排序测试
    print("\n【测试2】原地排序功能")
    test_arr = [3, 1, 4, 1, 5, 9, 2, 6]
    original = test_arr.copy()
    quick_sort_inplace(test_arr)
    print(f"  {original} → {test_arr}")
    assert test_arr == sorted(original), "原地排序失败"
    print("  ✓ 原地排序测试通过")
    
    # 测试3: 性能测试
    print("\n【测试3】性能测试（大数据）")
    large_arr = [random.randint(1, 10000) for _ in range(10000)]
    sorted_arr = quick_sort(large_arr.copy())
    assert sorted_arr == sorted(large_arr), "大数据排序失败"
    print(f"  ✓ 10000个随机整数排序成功")
    
    # 测试4: 完全有序数组（最坏情况）
    print("\n【测试4】完全有序数组")
    sorted_arr = list(range(1, 101))
    result = quick_sort(sorted_arr.copy())
    assert result == list(range(1, 101)), "有序数组排序失败"
    print(f"  ✓ 100个有序整数排序成功")
    
    print("\n" + "=" * 50)
    print("所有测试通过！✓")
    print("=" * 50)

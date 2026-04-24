"""
install_skill.py — ClawHub Skill 安装工具

提供 install_skill(url: str) 函数，自动化安装 ClawHub Skills。

安装流程：
1. 从 URL 提取 skill_name（slug）
2. 下载 zip: GET https://clawhub.ai/api/v1/download?slug={skill_name}
3. 解压到 workspace/skills/{skill_name}/
4. 检查 required_binaries
5. 创建 wiki/skills/{skill_name}.md
6. 更新 indexes 和 log
7. 返回安装摘要
"""

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from registry import tool
from tools.workspace import WORKSPACE_DIR


def _extract_skill_name(url: str) -> str:
    """从 ClawHub URL 提取 skill_name (slug)。"""
    parsed = urlparse(url)
    if "clawhub.ai" not in parsed.netloc:
        # 支持 slug 直接输入，如 "weather" 或 "steipete/weather"
        if "/" in url:
            return url.split("/")[-1]
        return url
    
    path_parts = parsed.path.strip("/").split("/")
    return path_parts[-1]  # 取最后一段，如 "weather"


def _download_skill_zip(skill_name: str) -> bytes:
    """下载 skill zip 文件。"""
    url = f"https://clawhub.ai/api/v1/download?slug={skill_name}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def _extract_zip(zip_content: bytes, dest_dir: Path) -> None:
    """解压 zip 到目标目录。"""
    with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
        zf.extractall(dest_dir)


def _check_binaries(binaries: list) -> list:
    """检查 binaries 是否可用，返回缺失列表。"""
    missing = []
    for binary in binaries:
        from tools.bash import bash
        result = bash(f"which {binary}")
        if result["exit_code"] != 0:
            missing.append(binary)
    return missing


def _create_wiki_doc(skill_name: str, skill_dir: Path) -> None:
    """创建 wiki/skills/{skill_name}.md（若不存在）。"""
    wiki_path = WORKSPACE_DIR / "wiki" / "skills" / f"{skill_name}.md"
    if wiki_path.exists():
        return  # 不覆盖已有经验文档
    
    # 从 SKILL.md 提取信息
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return
    
    content = skill_md.read_text()
    # 简单解析 frontmatter
    title = skill_name.replace("-", " ").title()
    tags = [skill_name]
    
    wiki_content = f"""---
title: {title}
updated: {datetime.now().strftime("%Y-%m-%d")}
avg_steps: 1
tags: {tags}
---

# 适用场景
# 最优流程
# 已知的坑
# 验证步骤
"""
    wiki_path.write_text(wiki_content)


def _update_indexes(skill_name: str) -> None:
    """更新 wiki/skills/index.md 和 wiki/index.md。"""
    # 更新 skills/index.md
    index_path = WORKSPACE_DIR / "wiki" / "skills" / "index.md"
    if index_path.exists():
        content = index_path.read_text()
        if f"[[{skill_name}]]" not in content:
            new_content = content.rstrip() + f"\n\n- [[{skill_name}]]：{skill_name} skill"
            index_path.write_text(new_content)
    
    # 更新 wiki/index.md
    wiki_index = WORKSPACE_DIR / "wiki" / "index.md"
    if wiki_index.exists():
        content = wiki_index.read_text()
        if f"skills/{skill_name}" not in content:
            new_content = content.rstrip() + f"\n- [[skills/{skill_name}]]：{skill_name} skill"
            wiki_index.write_text(new_content)


def _update_log(skill_name: str, url: str) -> None:
    """在 log.md 追加安装记录。"""
    log_path = WORKSPACE_DIR / "wiki" / "log.md"
    date = datetime.now().strftime("%Y-%m-%d")
    entry = f"{date}｜安装 {skill_name} skill（{url}）\n"
    
    if log_path.exists():
        content = log_path.read_text()
        if not content.endswith("\n"):
            content += "\n"
        content += entry
    else:
        content = entry
    
    log_path.write_text(content)


@tool(name="install_skill", description="安装 ClawHub Skill 到 workspace")
def install_skill(url: str) -> str:
    """
    安装 ClawHub Skill。
    
    Args:
        url: ClawHub Skill URL 或 slug（如 "https://clawhub.ai/steipete/weather" 或 "weather"）
    
    Returns:
        安装摘要字符串
    """
    try:
        skill_name = _extract_skill_name(url)
        skill_dir = WORKSPACE_DIR / "skills" / skill_name
        
        # 下载并解压
        zip_content = _download_skill_zip(skill_name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        _extract_zip(zip_content, skill_dir)
        
        # 检查 SKILL.md 和 required_binaries
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return f"❌ 安装失败：未找到 SKILL.md in {skill_dir}"
        
        content = skill_md.read_text()
        # 简单提取 required_binaries（假设格式固定）
        binaries = []
        lines = content.split("\n")
        for line in lines:
            if line.startswith("required_binaries:"):
                binaries_str = line.split(":", 1)[1].strip()
                binaries = json.loads(binaries_str.replace("'", '"'))
                break
        
        missing_binaries = _check_binaries(binaries)
        
        # 创建 wiki 文档
        _create_wiki_doc(skill_name, skill_dir)
        
        # 更新索引
        _update_indexes(skill_name)
        
        # 更新日志
        _update_log(skill_name, url)
        
        # 摘要
        summary = f"✅ {skill_name} skill 安装完成\n"
        summary += f"📁 安装路径: {skill_dir}\n"
        if binaries:
            summary += f"🔧 依赖: {', '.join(binaries)}\n"
            if missing_binaries:
                summary += f"⚠️ 缺失依赖: {', '.join(missing_binaries)}\n"
            else:
                summary += "✅ 所有依赖已满足\n"
        summary += "📝 已创建 wiki 文档和索引\n"
        
        return summary
        
    except Exception as e:
        return f"❌ 安装失败: {str(e)}"
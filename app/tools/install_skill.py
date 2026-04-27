"""
install_skill.py - install a Skill into app/workspace/skills.

Supported inputs:
- ClawHub URL or slug, for example: https://clawhub.ai/steipete/weather
- GitHub repository URL, for example: https://github.com/owner/repo
- GitHub tree URL, for example: https://github.com/owner/repo/tree/main/path/to/skill
"""

import io
import json
import re
import shutil
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
import yaml

from registry import tool
from tools.workspace import WORKSPACE_DIR


_GITHUB_HOSTS = {"github.com", "www.github.com"}


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip(".-_")
    return cleaned or "skill"


def _is_github_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in _GITHUB_HOSTS


def _extract_clawhub_skill_name(value: str) -> str:
    parsed = urlparse(value)
    if "clawhub.ai" not in parsed.netloc:
        return _safe_name(value.rstrip("/").split("/")[-1])

    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    return _safe_name(path_parts[-1] if path_parts else parsed.netloc)


def _parse_github_url(url: str) -> Dict[str, Optional[str]]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include owner and repo")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    branch = None
    subdir = ""

    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        branch = parts[3]
        subdir = "/".join(parts[4:])

    return {"owner": owner, "repo": repo, "branch": branch, "subdir": subdir}


def _download_url(url: str) -> bytes:
    response = requests.get(url, timeout=30, headers={"User-Agent": "NanoAgent/0.8"})
    response.raise_for_status()
    return response.content


def _download_clawhub_zip(skill_name: str) -> bytes:
    return _download_url(f"https://clawhub.ai/api/v1/download?slug={skill_name}")


def _github_default_branch(owner: str, repo: str) -> str:
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(api_url, timeout=15, headers={"User-Agent": "NanoAgent/0.8"})
    response.raise_for_status()
    return response.json().get("default_branch") or "main"


def _download_github_zip(owner: str, repo: str, branch: Optional[str]) -> Tuple[bytes, str]:
    branches = [branch] if branch else []
    if not branches:
        try:
            branches.append(_github_default_branch(owner, repo))
        except Exception:
            branches.extend(["main", "master"])

    last_error = None
    for candidate in dict.fromkeys(branches):
        try:
            url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{candidate}"
            return _download_url(url), candidate
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"failed to download GitHub repository zip: {last_error}")


def _safe_extract_zip(zip_content: bytes, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    root = dest_dir.resolve()
    with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
        for member in zf.infolist():
            target = (dest_dir / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise ValueError(f"unsafe zip member path: {member.filename}")
        zf.extractall(dest_dir)


def _first_child_dir(path: Path) -> Path:
    children = [child for child in path.iterdir() if child.is_dir()]
    return children[0] if len(children) == 1 else path


def _find_skill_source(extract_root: Path, subdir: str = "") -> Path:
    source_root = extract_root if (extract_root / "SKILL.md").exists() else _first_child_dir(extract_root)
    if subdir:
        candidate = source_root / subdir
        if not candidate.exists():
            raise FileNotFoundError(f"GitHub subdirectory not found: {subdir}")
        source_root = candidate

    if (source_root / "SKILL.md").exists():
        return source_root

    matches = list(source_root.rglob("SKILL.md"))
    if not matches:
        raise FileNotFoundError("SKILL.md not found in downloaded archive")
    if len(matches) > 1:
        names = ", ".join(str(path.parent.relative_to(source_root)) for path in matches[:5])
        raise ValueError(f"multiple SKILL.md files found; use a GitHub /tree/<branch>/<path> URL. Candidates: {names}")
    return matches[0].parent


def _copy_skill(source_dir: Path, skill_name: str) -> Path:
    dest_dir = WORKSPACE_DIR / "skills" / _safe_name(skill_name)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, dest_dir)
    return dest_dir


def _read_frontmatter(skill_md: Path) -> Dict:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1]) or {}
    return data if isinstance(data, dict) else {}


def _parse_required_binaries(skill_md: Path) -> List[str]:
    frontmatter = _read_frontmatter(skill_md)
    binaries = frontmatter.get("required_binaries", [])
    if isinstance(binaries, str):
        return [binaries]
    if isinstance(binaries, list):
        return [str(item) for item in binaries if str(item).strip()]

    for line in skill_md.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("required_binaries:"):
            raw = line.split(":", 1)[1].strip()
            try:
                parsed = json.loads(raw.replace("'", '"'))
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                return [item.strip() for item in raw.split(",") if item.strip()]
    return []


def _check_binaries(binaries: List[str]) -> List[str]:
    return [binary for binary in binaries if shutil.which(binary) is None]


@contextmanager
def _temporary_dir():
    tmp_parent = WORKSPACE_DIR / ".tmp"
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = tmp_parent / f"nanoagent_skill_{uuid.uuid4().hex}"
    tmp_dir.mkdir()
    try:
        yield str(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _create_wiki_doc(skill_name: str, skill_dir: Path) -> None:
    wiki_dir = WORKSPACE_DIR / "wiki" / "skills"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    wiki_path = wiki_dir / f"{skill_name}.md"
    if wiki_path.exists():
        return

    title = skill_name.replace("-", " ").replace("_", " ").title()
    wiki_content = f"""---
title: {title}
updated: {datetime.now().strftime("%Y-%m-%d")}
avg_steps: 1
tags: [{skill_name}]
---

# 适用场景

# 最优流程

# 已知的坑

# 验证步骤
- Installed from {skill_dir}
"""
    wiki_path.write_text(wiki_content, encoding="utf-8")


def _append_once(path: Path, marker: str, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in content:
        return
    if content and not content.endswith("\n"):
        content += "\n"
    path.write_text(content + line, encoding="utf-8")


def _update_indexes(skill_name: str) -> None:
    _append_once(
        WORKSPACE_DIR / "wiki" / "skills" / "index.md",
        f"[[{skill_name}]]",
        f"\n- [[{skill_name}]]: {skill_name} skill\n",
    )
    _append_once(
        WORKSPACE_DIR / "wiki" / "index.md",
        f"skills/{skill_name}",
        f"- [[skills/{skill_name}]]: {skill_name} skill\n",
    )


def _update_log(skill_name: str, source: str) -> None:
    log_path = WORKSPACE_DIR / "wiki" / "log.md"
    date = datetime.now().strftime("%Y-%m-%d")
    _append_once(
        log_path,
        f"Installed {skill_name} skill from {source}",
        f"{date} - Installed {skill_name} skill from {source}\n",
    )


def _install_from_github(url: str) -> Tuple[str, Path, List[str], List[str], str]:
    info = _parse_github_url(url)
    owner = info["owner"] or ""
    repo = info["repo"] or ""
    zip_content, branch = _download_github_zip(owner, repo, info["branch"])

    with _temporary_dir() as tmp:
        extract_root = Path(tmp) / "extract"
        _safe_extract_zip(zip_content, extract_root)
        source_dir = _find_skill_source(extract_root, info["subdir"] or "")
        skill_name = _safe_name(source_dir.name if source_dir.name != f"{repo}-{branch}" else repo)
        skill_dir = _copy_skill(source_dir, skill_name)

    skill_md = skill_dir / "SKILL.md"
    binaries = _parse_required_binaries(skill_md)
    missing_binaries = _check_binaries(binaries)
    return skill_name, skill_dir, binaries, missing_binaries, f"github:{owner}/{repo}@{branch}"


def _install_from_clawhub(value: str) -> Tuple[str, Path, List[str], List[str], str]:
    skill_name = _extract_clawhub_skill_name(value)
    zip_content = _download_clawhub_zip(skill_name)

    with _temporary_dir() as tmp:
        extract_root = Path(tmp) / "extract"
        _safe_extract_zip(zip_content, extract_root)
        source_dir = _find_skill_source(extract_root)
        skill_dir = _copy_skill(source_dir, skill_name)

    skill_md = skill_dir / "SKILL.md"
    binaries = _parse_required_binaries(skill_md)
    missing_binaries = _check_binaries(binaries)
    return skill_name, skill_dir, binaries, missing_binaries, f"clawhub:{value}"


@tool(name="install_skill", description="Install a Skill from ClawHub or GitHub into workspace")
def install_skill(url: str) -> str:
    """
    Install a Skill from ClawHub or GitHub.

    Args:
        url: ClawHub URL/slug or GitHub repository/tree URL.

    Returns:
        Installation summary.
    """
    if not url or not url.strip():
        return "Install failed: url is required"

    source = url.strip()
    try:
        if _is_github_url(source):
            skill_name, skill_dir, binaries, missing_binaries, source_label = _install_from_github(source)
        else:
            skill_name, skill_dir, binaries, missing_binaries, source_label = _install_from_clawhub(source)

        _create_wiki_doc(skill_name, skill_dir)
        _update_indexes(skill_name)
        _update_log(skill_name, source_label)

        summary = [
            f"Installed {skill_name} skill",
            f"Path: {skill_dir}",
            f"Source: {source_label}",
            "Updated: workspace/skills, wiki/skills document, indexes, and log",
        ]
        if binaries:
            summary.append(f"Required binaries: {', '.join(binaries)}")
            if missing_binaries:
                summary.append(f"Missing binaries: {', '.join(missing_binaries)}")
            else:
                summary.append("Dependency check passed")
        else:
            summary.append("Required binaries: none declared")
        return "\n".join(summary)
    except Exception as exc:
        return f"Install failed: {type(exc).__name__}: {exc}"

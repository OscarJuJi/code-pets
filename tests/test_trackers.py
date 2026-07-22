import json
import os
import subprocess
from datetime import datetime, timezone

from trackers import claude_tokens, files, git_local


def _utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def test_token_parser_with_corrupt_line(tmp_path):
    ts = _utc_now_iso()
    lines = [
        json.dumps({"timestamp": ts, "message": {"usage": {
            "input_tokens": 100, "output_tokens": 50,
            "cache_creation_input_tokens": 10, "cache_read_input_tokens": 999,
        }}}),
        "{{{corrupt json",
        json.dumps({"timestamp": ts, "message": {"usage": {"input_tokens": 40}}}),
        json.dumps({"type": "user"}),  # no usage block
    ]
    project = tmp_path / "projects" / "p1"
    project.mkdir(parents=True)
    (project / "s1.jsonl").write_text("\n".join(lines), encoding="utf-8")

    cache = {}
    result = claude_tokens.scan(cache, projects_dir=str(tmp_path / "projects"))
    assert result["today"] == 200  # 160 + 40; cache_read excluded
    assert len(result["series"]) == 14
    assert result["series"][-1]["tokens"] == 200

    # unchanged file -> cache hit, same totals
    result2 = claude_tokens.scan(cache, projects_dir=str(tmp_path / "projects"))
    assert result2["today"] == 200

    # deleted file -> dropped from cache and totals
    (project / "s1.jsonl").unlink()
    result3 = claude_tokens.scan(cache, projects_dir=str(tmp_path / "projects"))
    assert result3["today"] == 0
    assert cache == {}


def test_files_scan_filters_and_excludes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "b.tsx").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules" / "c.js").write_text("x", encoding="utf-8")
    (tmp_path / ".git" / "d.py").write_text("x", encoding="utf-8")

    result = files.scan(str(tmp_path))
    names = {os.path.basename(f) for f in result["files"]}
    assert names == {"a.py", "b.tsx"}
    assert result["by_language"] == {".py": 1, ".tsx": 1}


def test_git_commits_today_and_dedup(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(
            ["git", "-C", str(repo)] + list(args),
            capture_output=True, text=True, check=True,
        )

    git("init")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    git("config", "commit.gpgsign", "false")
    (repo / "f.txt").write_text("1", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "first commit")

    commits = git_local.commits_today(str(repo))
    assert len(commits) == 1
    commit_hash, subject = commits[0]
    assert subject == "first commit"

    # scanning twice returns the same commit; the credited list filters it out
    credited = [commit_hash]
    second = [c for c in git_local.commits_today(str(repo)) if c[0] not in set(credited)]
    assert second == []

    # a directory without .git reports None (not a crash)
    assert git_local.commits_today(str(tmp_path / "nope")) is None


def test_discover_repos_finds_children(tmp_path):
    (tmp_path / "a" / ".git").mkdir(parents=True)
    (tmp_path / "b").mkdir()
    repos = git_local.discover_repos(str(tmp_path))
    assert repos == [git_local.normalize(str(tmp_path / "a"))]


def test_discover_repos_key_is_case_stable(tmp_path):
    """The same repo reached through differently-cased paths yields one key."""
    (tmp_path / "a" / ".git").mkdir(parents=True)
    lower = str(tmp_path / "a").replace("E:", "e:", 1)
    upper = str(tmp_path / "a").replace("e:", "E:", 1)
    assert git_local.normalize(lower) == git_local.normalize(upper)

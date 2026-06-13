#!/usr/bin/env python3
"""delegate.py — отдать задачу агенту MiMo-Code в ИЗОЛИРОВАННОЙ копии репозитория.

Идея безопасности: mimo НЕ трогает рабочую папку проекта. Под каждую задачу
создаётся отдельный git-worktree (своя ветка + своя папка в /tmp), mimo работает
ТАМ, а нам возвращается diff на проверку. В main изменения попадают только вручную
после QA — обёртка сама в main ничего не пишет.

venv (bin/lib/include/pyvenv.cfg — всё в .gitignore) прокидывается симлинками,
поэтому в изолированной копии работает привычный ./bin/python со всеми зависимостями,
а в diff эти симлинки не попадают.

Использование:
  python3 delegate.py --task <имя> --brief "текст задачи"
  python3 delegate.py --task <имя> --brief-file brief.md
  python3 delegate.py --task <имя> --brief "..." --dry-run   # проверить конвейер без запуска mimo
  python3 delegate.py --cleanup <имя>                        # снести worktree+ветку
  python3 delegate.py --list                                 # активные worktree
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
WORKTREE_BASE = Path("/tmp/mimo_worktrees")
MIMO = shutil.which("mimo") or os.path.expanduser("~/.mimocode/bin/mimo")
# venv-папки (все в .gitignore) → прокидываем в worktree, чтобы работал ./bin/python
VENV_LINKS = ["bin", "lib", "include", "pyvenv.cfg"]


def git(args, cwd=REPO, check=True, quiet=False):
    kw = {}
    if quiet:
        kw = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = subprocess.run(["git", *args], cwd=cwd, text=True, **kw)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} → код {r.returncode}")
    return r.returncode


def wt_path(task):
    return WORKTREE_BASE / task


def branch(task):
    return f"mimo/{task}"


def branch_exists(task):
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", branch(task)],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0


def cleanup(task):
    wt = wt_path(task)
    subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                   cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "branch", "-D", branch(task)],
                   cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
    print(f"✓ Worktree и ветка для «{task}» удалены.")


def create_worktree(task, force):
    wt = wt_path(task)
    if wt.exists() or branch_exists(task):
        if not force:
            raise SystemExit(
                f"Задача «{task}» уже существует. Добавь --force чтобы пересоздать "
                f"или: python3 {Path(__file__).name} --cleanup {task}")
        cleanup(task)
    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", "-b", branch(task), str(wt), "HEAD"])
    # прокинуть venv симлинками (gitignored → в diff не попадут)
    for name in VENV_LINKS:
        src, dst = REPO / name, wt / name
        if src.exists() and not dst.exists():
            os.symlink(src, dst)
    return wt


def remove_venv_links(wt):
    """Снять venv-симлинки перед расчётом diff — иначе они шумят (.gitignore их
    не ловит: шаблон `bin/` со слешем = «папка», а симлинк git считает файлом).
    Path.unlink() убирает сам симлинк, не трогая реальный venv."""
    for name in VENV_LINKS:
        link = wt / name
        if link.is_symlink():
            link.unlink()


def show_diff(task):
    wt = wt_path(task)
    git(["add", "-A"], cwd=wt)
    print("\n" + "=" * 64)
    print(f"  РЕЗУЛЬТАТ задачи «{task}»  (ветка {branch(task)})")
    print("=" * 64)
    subprocess.run(["git", "diff", "--cached", "--stat"], cwd=wt)
    return wt


def run(task, brief, model, dry_run, force):
    if not dry_run and not Path(MIMO).exists():
        raise SystemExit(f"mimo не найден: {MIMO}")
    wt = create_worktree(task, force)
    print(f"→ Worktree: {wt}")
    print(f"→ Ветка:    {branch(task)}  (от HEAD, main не трогается)")
    print(f"→ Бриф:\n{brief}\n")

    if dry_run:
        # имитируем агента + проверяем, что venv доступен в worktree
        (wt / "_dryrun_marker.txt").write_text("plumbing ok\n")
        probe = subprocess.run(
            [str(wt / "bin" / "python"), "-c",
             "import sys, openpyxl; print('venv ok →', sys.executable)"],
            cwd=wt, text=True, capture_output=True)
        print("[dry-run] mimo НЕ запускался.")
        print("[dry-run]", (probe.stdout or probe.stderr).strip())
    else:
        print("=" * 64)
        print("  MiMo работает (модель:", model + ")...")
        print("=" * 64)
        # --dangerously-skip-permissions: автономный режим (авто-одобрение действий).
        # Безопасно — mimo заперт в изолированном worktree, main недоступен.
        subprocess.run([MIMO, "run", "--dangerously-skip-permissions",
                        "--model", model, brief], cwd=wt)

    remove_venv_links(wt)   # venv нужен только во время прогона; убрать до diff
    show_diff(task)
    name = Path(__file__).name
    print(f"""
Дальше:
  • файлы черновика:  ls -la {wt}
  • полный diff:      git -C {wt} diff --cached
  • применить в main: git -C {REPO} checkout {branch(task)} -- <файл>   (после QA!)
  • снести черновик:  python3 {name} --cleanup {task}
""")


def main():
    ap = argparse.ArgumentParser(
        description="Делегировать задачу агенту MiMo в изолированном git-worktree.")
    ap.add_argument("--task", help="короткое имя задачи (→ ветка mimo/<имя>)")
    ap.add_argument("--brief", help="текст задачи")
    ap.add_argument("--brief-file", help="файл с текстом задачи")
    ap.add_argument("--model", default="mimo/mimo-auto",
                    help="модель mimo (по умолчанию бесплатная mimo-auto)")
    ap.add_argument("--dry-run", action="store_true",
                    help="проверить весь конвейер без запуска mimo")
    ap.add_argument("--force", action="store_true",
                    help="пересоздать worktree, если задача уже есть")
    ap.add_argument("--cleanup", metavar="TASK", help="снести worktree и ветку")
    ap.add_argument("--list", action="store_true", help="показать активные worktree")
    a = ap.parse_args()

    if a.cleanup:
        cleanup(a.cleanup)
        return
    if a.list:
        subprocess.run(["git", "worktree", "list"], cwd=REPO)
        return
    if not a.task:
        ap.error("нужен --task")

    brief = Path(a.brief_file).read_text() if a.brief_file else a.brief
    if not brief:
        ap.error("нужен --brief или --brief-file")
    run(a.task, brief, a.model, a.dry_run, a.force)


if __name__ == "__main__":
    main()

import datetime
import os

branch = ''
commit_id = ''
commit_date = ''
simpai_ver = ''

def _load_git_metadata():
    global branch, commit_id, commit_date
    if branch and commit_id and commit_date:
        return
    try:
        import pygit2
        pygit2.option(pygit2.GIT_OPT_SET_OWNER_VALIDATION, 0)
        repo = pygit2.Repository(os.path.abspath(os.path.dirname(__file__)))
        commit = repo[repo.head.target]
        if not branch:
            branch = repo.head.shorthand
            if branch == "main":
                branch = "SimpAI_Studio"
        if not commit_id:
            commit_id = f'{commit.id}'[:7]
        if not commit_date:
            tz = datetime.timezone(datetime.timedelta(minutes=commit.commit_time_offset))
            commit_date = datetime.datetime.fromtimestamp(commit.commit_time, tz).strftime('%Y%m%d')
    except Exception:
        pass

def _read_simpai_log_date():
    simpai_log = os.path.abspath(f'./simpai_log.md')
    line = ''
    if os.path.exists(simpai_log):
        with open(simpai_log, "r", encoding="utf-8") as log_file:
            line = log_file.readline().strip()
            while line:
                if line.startswith("# "):
                    break
                line = log_file.readline().strip()
    if not line:
        return ''
    try:
        date = line.split(' ')[1].split('-')
        return f'{date[0]}{date[1]}{date[2]}'
    except Exception:
        return ''

def get_simpai_ver():
    global simpai_ver, commit_id
    if not simpai_ver:
        _load_git_metadata()
        date = commit_date or _read_simpai_log_date() or 'unknown'
        simpai_ver = f'v{date}'
        if commit_id:
            simpai_ver += f'.{commit_id}'
    return simpai_ver

def get_simpai_short_ver():
    ver = get_simpai_ver()
    return ver.split('.', 1)[1] if '.' in ver else ver

def get_branch():
    global branch, commit_id
    if not branch:
        _load_git_metadata()
    return branch

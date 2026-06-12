import os
import sys


root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(root)
os.chdir(root)

for legacy_arg in ('--dev', '--main'):
    while legacy_arg in sys.argv:
        sys.argv.remove(legacy_arg)
        print(f'Ignoring deprecated branch argument: {legacy_arg}')


try:
    import pygit2
    pygit2.option(pygit2.GIT_OPT_SET_OWNER_VALIDATION, 0)

    repo = pygit2.Repository(os.path.abspath(os.path.dirname(__file__)))

    remote_name = 'origin'
    branch_name = 'main'
    local_branch_ref = f'refs/heads/{branch_name}'
    remote_reference = f'refs/remotes/{remote_name}/{branch_name}'

    remote = repo.remotes[remote_name]

    remote.fetch()

    if remote_reference not in list(repo.references):
        raise RuntimeError(f'Missing remote branch: {remote_reference}')

    if local_branch_ref not in list(repo.references):
        remote_branch = repo.references[remote_reference]
        local_branch = repo.create_branch(branch_name, repo[remote_branch.target])
        local_branch.upstream = remote_branch
    else:
        local_branch = repo.lookup_branch(branch_name)

    if repo.head.shorthand != branch_name:
        print(f'Ready to checkout {branch_name}')
        repo.checkout(local_branch)

    local_branch = repo.lookup_reference(local_branch_ref)
    local_commit = repo.revparse_single(local_branch_ref)

    remote_commit = repo.revparse_single(remote_reference)

    merge_result, _ = repo.merge_analysis(remote_commit.id)
    branch_name_display = branch_name
    local_commit_short = str(local_commit.id)[:7]
    remote_commit_short = str(remote_commit.id)[:7]

    if merge_result & pygit2.GIT_MERGE_ANALYSIS_UP_TO_DATE:
        print(f'{branch_name_display}: Already up-to-date, {local_commit_short}')
    elif remote_commit.id != local_commit.id: 
        try:
            repo.reset(remote_commit.id, pygit2.GIT_RESET_HARD)
            try:
                local_branch.set_target(remote_commit.id)
                print(f'{branch_name_display}: Force Sync Remote Updates, {local_commit_short} -> {remote_commit_short}')
            except Exception as ref_error:
                try:
                    ref_name = f'refs/heads/{branch_name}'
                    repo.references.create(ref_name, remote_commit.id, True)
                    print(f'{branch_name_display}: Force Sync Remote Updates, {local_commit_short} -> {remote_commit_short}')
                except Exception as alt_error:
                    print(f'Warning: Failed to update the reference, but the file has been updated. - {str(alt_error)}')
        except Exception as reset_error:
            print(f'{branch_name_display}: Failed to Force Update - {str(reset_error)}')
    else: 
        print(f'{branch_name_display}: Update failed when {local_commit_short} <- {remote_commit_short}')
except Exception as e:
    print(f'Repo Update failed.')
    print(str(e))


if __name__ == '__main__':
    import multiprocessing as mp
    mp.set_start_method('spawn')

from launch import *

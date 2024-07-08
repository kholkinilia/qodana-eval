
def get_repo_dir_name(repo_name, commit_sha):
    return f"{repo_name.replace('/', '_')}_{commit_sha}"


def get_repo_archive_filename(repo_name, commit_sha):
    return f"{get_repo_dir_name(repo_name, commit_sha)}.zip"

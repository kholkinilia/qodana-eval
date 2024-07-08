import requests
from omegaconf import DictConfig
import os
from src.utils.paths import get_repo_archive_filename, get_repo_dir_name
import zipfile


def download_github_repo_zip(repository_name, commit_sha, output_archive_path):
    """
    Downloads a zip file of a GitHub repository at a specified commit.

    Parameters:
    repository_name (str): The name of the repository in the format 'owner/repo'.
    commit_sha (str): The SHA of the commit.
    output_archive_path (str): The output filename for the downloaded zip file.

    Returns:
    bool: True if successful, False otherwise.
    """
    url = f"https://github.com/{repository_name}/archive/{commit_sha}.zip"

    response = requests.get(url, stream=True)

    if response.status_code == 200:
        with open(output_archive_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=128):
                file.write(chunk)
        print(f"Repository '{repository_name}' at commit '{commit_sha}' has been downloaded to '{output_archive_path}'.")
        return True
    else:
        print(
            f"Failed to download repository '{repository_name}' at commit '{commit_sha}'. HTTP Status Code: {response.status_code}")
        return False


def prepare_repo(repo_name: str, commit_sha: str, cfg: DictConfig):
    """
    Prepares a GitHub repository for use by downloading and extracting it.

    Parameters:
    repo_name (str): The name of the repository in the format 'owner/repo'.
    commit_sha (str): The SHA of the commit to download.
    cfg (DictConfig): Configuration object containing operation directories.

    Returns:
    str: The name of the extracted repository directory.

    Raises:
    AssertionError: If the extracted directory does not contain exactly one repository.
    """

    # Download an archive
    archive_path = str(os.path.join(cfg.operation.dirs.repo_data, get_repo_archive_filename(repo_name, commit_sha)))
    download_github_repo_zip(repo_name, commit_sha, archive_path)

    # Extract an archive
    extract_to = str(os.path.join(cfg.operation.dirs.repo_data, get_repo_dir_name(repo_name, commit_sha)))
    with zipfile.ZipFile(archive_path, 'r') as archive:
        archive.extractall(extract_to)
    print(f"Files extracted to '{extract_to}'")

    # Check that there's only one repo there
    assert len(os.listdir(extract_to)) == 1  # There should be only the repo inside

    # Return the repo name of the project
    return os.listdir(extract_to)[0]

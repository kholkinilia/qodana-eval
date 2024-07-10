import time
import hydra
import requests.exceptions
from datasets import load_dataset
from huggingface_hub import HfApi, CommitOperationAdd
from omegaconf import DictConfig
from dotenv import load_dotenv
import os
import shutil
from tqdm.contrib.concurrent import process_map
import pandas as pd
from src.utils.repo_handling import prepare_repo, clear_repo
from src.utils.paths import get_repo_dir_name
import docker
import json
from itertools import repeat

repo_prep_func = {
    'github': prepare_repo,
    's3': None,  # TODO
}


def run_qodana(repo_name: str, commit_sha: str, cfg: DictConfig):
    json_result = {
        "exit_code": None,
        "execution_time": 0.,
        "result_archive_name": "",
        "repo_name": repo_name,
        "commit_sha": commit_sha,
    }

    # Prepare a repository
    repo_filename = repo_prep_func[cfg.data.source.type](repo_name, commit_sha, cfg)
    if not repo_filename:
        json_result["exit_code"] = cfg.exit_codes.download_failure
        return json_result
    repo_path = os.path.join(cfg.operation.dirs.repo_data, get_repo_dir_name(repo_name, commit_sha), repo_filename)

    result_path = str(os.path.join(cfg.operation.dirs.qodana_results, get_repo_dir_name(repo_name, commit_sha)))
    os.makedirs(result_path, exist_ok=True)

    # Setup a docker client
    docker_client = docker.from_env(timeout=cfg.docker.create_container_timeout)

    # Run a docker container
    volumes = {
        os.path.abspath(repo_path): {'bind': '/data/project', 'mode': 'rw'},
        os.path.abspath(result_path): {'bind': '/data/results', 'mode': 'rw'}
    }
    environment = {
        'QODANA_TOKEN': os.environ.get('QODANA_TOKEN'),
    }
    start_time = time.time()
    try:
        container = docker_client.containers.run(image=cfg.docker.qodana_image[cfg.data.language.type],
                                                 volumes=volumes,
                                                 environment=environment,
                                                 detach=True,
                                                 remove=True,
                                                 )
        container_result = container.wait(timeout=cfg.data.language[cfg.data.language.type].timeout)

        json_result["exit_code"] = container_result["StatusCode"]
    except requests.exceptions.ConnectionError as e:
        json_result["exit_code"] = cfg.exit_codes.timeout
    except requests.exceptions.ReadTimeout as e:
        json_result["exit_code"] = cfg.exit_codes.create_container_failure
    except (docker.errors.ContainerError,
            docker.errors.ImageNotFound,
            docker.errors.APIError,
            docker.errors.DockerException) as e:
        json_result["exit_code"] = cfg.exit_codes.unknown_failure
    finally:
        end_time = time.time()
        json_result["execution_time"] = end_time - start_time

    # Archive the results of a Qodana run
    result_archive_name = f"{get_repo_dir_name(repo_name, commit_sha)}.zip"
    result_archive_path = os.path.join(cfg.data.language[cfg.data.language.type].result_paths.qodana_archives,
                                       result_archive_name)
    json_result["result_archive_name"] = result_archive_name
    shutil.make_archive(result_archive_path[:-len('.zip')], 'zip', result_path)

    # Upload archive to huggingface if necessary
    if cfg.data.target.type == "huggingface" and cfg.data.target.huggingface.push_archives_dynamically:
        api = HfApi()

        api.upload_file(
            path_or_fileobj=result_archive_path,
            path_in_repo=os.path.join('qodana_archives', cfg.data.language.type, result_archive_name),
            repo_id=cfg.data.target.huggingface.repo_id,
            repo_type="dataset"
        )

        # Remove local archive if necessary
        if not cfg.data.target.huggingface.keep_local_archives:
            os.remove(result_archive_path)

    # Save json to a temporary file (to have some data saved in case execution fails)
    json_result_path = os.path.join(cfg.operation.dirs.json_results, f"{get_repo_dir_name(repo_name, commit_sha)}.json")
    with open(json_result_path, 'w') as f:
        json.dump(json_result, f)

    # Clear temporary repo data
    clear_repo(repo_name, commit_sha, cfg)

    return json_result


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    # Draw the repos names&revisions to run a script on
    repos = pd.read_json(cfg.data.language[cfg.data.language.type].repos_list_path, lines=True)

    # Create tmp dirs for operation
    os.makedirs(cfg.operation.dirs.repo_data, exist_ok=True)
    os.makedirs(cfg.operation.dirs.qodana_results, exist_ok=True)
    os.makedirs(cfg.operation.dirs.json_results, exist_ok=True)

    # Run processes
    json_results = process_map(run_qodana, repos['repo_name'].to_list(), repos['revision'].to_list(), repeat(cfg),
                               **cfg.operation.pool_config)

    # Create jsonl file with results
    jsonl_path = cfg.data.language[cfg.data.language.type].result_paths.jsonl
    with open(jsonl_path, 'w') as f:
        for json_line in json_results:
            f.write(json.dumps(json_line) + "\n")

    # Save to huggingface if necessary
    if cfg.data.target.type == "huggingface":

        dataset = load_dataset('json', data_files=jsonl_path)
        dataset['train'].push_to_hub(cfg.data.target.huggingface.repo_id, split=cfg.data.language.type)

        # Remove jsonl if required
        if not cfg.data.target.huggingface.keep_local_jsonl:
            os.remove(jsonl_path)

        # Push all archives at once
        archives_dir = cfg.data.language[cfg.data.language.type].result_paths.qodana_archives
        if not cfg.data.target.huggingface.push_archives_dynamically and os.path.exists(archives_dir):
            api = HfApi()

            target_repo_dir = os.path.join('qodana_archives', cfg.data.language.type)

            archives_to_upload = []
            for archive_name in os.listdir(archives_dir):
                archive_path = os.path.join(archives_dir, archive_name)
                if archive_path.endswith(".zip"):
                    target_path = os.path.join(target_repo_dir, archive_name)
                    archives_to_upload.append((archive_path, target_path))

            operations = [
                CommitOperationAdd(target_path, open(archive_path, "rb").read())
                for archive_path, target_path in archives_to_upload
            ]

            api.create_commit(
                repo_id=cfg.data.target.huggingface.repo_id,
                repo_type="dataset",
                operations=operations,
                commit_message="Add archive files"
            )

            if not cfg.data.target.huggingface.keep_local_archives:
                for archive_path, _ in archives_to_upload:
                    os.remove(archive_path)

        # Remove the empty repo, where archives were stored if it's indeed empty and if required
        if not cfg.data.target.huggingface.keep_local_archives and os.path.exists(archives_dir) and not any(
                os.scandir(archives_dir)):
            shutil.rmtree(archives_dir)

    # Remove tmp dir and its contents
    shutil.rmtree(cfg.operation.dirs.tmp)


if __name__ == '__main__':
    load_dotenv()
    main()

import hydra
from omegaconf import DictConfig
from dotenv import load_dotenv
import os
import shutil
from tqdm.contrib.concurrent import process_map
import pandas as pd
from src.utils.download import prepare_repo
from src.utils.paths import get_repo_dir_name
import docker
from itertools import repeat

repo_prep_func = {
    'github': prepare_repo,
    's3': None,  # TODO
}


def run_qodana(repo_name: str, commit_sha: str, cfg: DictConfig):
    # Prepare a repository
    repo_filename = repo_prep_func[cfg.data.source.type](repo_name, commit_sha, cfg)
    repo_path = os.path.join(cfg.operation.dirs.repo_data, get_repo_dir_name(repo_name, commit_sha), repo_filename)

    result_path = os.path.join(cfg.data.language[cfg.data.language.type].results_dir,
                               get_repo_dir_name(repo_name, commit_sha))
    os.makedirs(result_path, exist_ok=True)

    # Setup a docker client
    docker_client = docker.from_env()

    volumes = {
        os.path.abspath(repo_path): {'bind': '/data/project', 'mode': 'rw'},
        os.path.abspath(result_path): {'bind': '/data/results', 'mode': 'rw'}
    }
    environment = {
        'QODANA_TOKEN': os.environ.get('QODANA_TOKEN'),
    }
    try:
        container = docker_client.containers.run(image=cfg.docker.qodana_image[cfg.data.language.type],
                                                 volumes=volumes,
                                                 environment=environment,
                                                 )
    except docker.errors.ContainerError as e:
        # Error, while running a container
        # TODO: handle
        pass
    # TODO: implement timeouts
    # TODO: implement real-time clearing


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    # Draw the repos names&revisions to run a script on
    repos = pd.read_json(cfg.data.language[cfg.data.language.type].repos_list_path, lines=True)

    # Create a tmp dir for operation
    os.makedirs(cfg.operation.dirs.tmp, exist_ok=True)
    os.makedirs(cfg.operation.dirs.repo_data, exist_ok=True)

    # Run processes
    process_map(run_qodana, repos['repo_name'].to_list(), repos['revision'].to_list(), repeat(cfg),
                **cfg.operation.pool_config)

    # TODO: remove when real-time clearing is implemented
    shutil.rmtree(cfg.operation.dirs.tmp)


if __name__ == '__main__':
    load_dotenv()
    main()

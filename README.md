# Qodana-eval: a script running qodana over github repos

## How to run
1. Modify `conf/config.yaml` to your liking
2. Run `poetry install`
3. Run `poetry run python3 main.py`

## Data format
The repos path list should be a `.jsonl` file with the following fields:
* `repo_name`: a github repo name including the author or organisation (e.g. `kholkinilia/qodana-eval`)
* `revisaion`: a commit_sha of the desired version of the repo (e.g. `TODO`)
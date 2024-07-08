# Qodana-eval: a script running qodana over github repos

## How to run
1. Start a Docker daemon
2. Create a `.env` file in a repository root specifying `QODANA_TOKEN`
3. Modify `conf/config.yaml` to your liking
4. Run `poetry install`
5. Run `poetry run python3 main.py`

## Data format
The repos list should be a `.jsonl` file with the following fields:
* `repo_name`: a GitHub repo name including the author or organisation (e.g. `kholkinilia/qodana-eval`)
* `revisaion`: a commit_sha of the desired version of the repo (e.g. `cdc69a6608fbebe7ca3de6533bb619cc443b53f2`)

The results of the qodana runs would be stored in `results_dir` that you specified for your language.
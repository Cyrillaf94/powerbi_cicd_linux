"""This module provides allows to execute and log linters for pbip files
    It uses tabular editor and pbi inspector.
    The module can only run on windows machines.
    """

from distutils.dir_util import copy_tree
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import re
import sys



logging.basicConfig(level=logging.INFO,
                    format='%(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logging.addLevelName(logging.ERROR, 'ERROR')
logging.addLevelName(logging.WARNING, 'WARNING')
logging.addLevelName(logging.INFO, 'INFO')
logging.addLevelName(logging.DEBUG, 'DEBUG')


SUCCESS = True

def log_error(*args, **kwargs):
    global SUCCESS
    SUCCESS = False
    return logging.error(*args, **kwargs)

def log_exception(*args, **kwargs):
    global SUCCESS
    SUCCESS = False
    return logging.exception(*args, **kwargs)

# region test_model ####

def log_linter(func):
    """
    Decorator that logs the start and end of a linter function,
    as well as the results and score.
    """
    def wrapper(item, *args, **kwargs):
        try:
            linter_results = func(item, *args, **kwargs)
            score = float(linter_results.pop("score"))
            if score >= 8:
                logging.info(f"'{str(item)}' - Score: {score} - Good job, you're the pbi expert!"
                             f" Details {linter_results}")
            elif score >= 6:
                logging.warning(f"'{str(item)}' - Score: {score} -"
                                f" Details: {linter_results}")
            elif score < 6:
                log_error(f"'{str(item)}' - Score: {score} -"
                              f" Details: {linter_results}")
        except Exception as e:
            log_exception(f"{func.__name__} on '{item}' failed with error: {str(e)}")
    return wrapper

def handle_te_output(te_output: subprocess.CompletedProcess):
    """Fetch the json from stdout"""
    logging.debug(te_output)
    json_pattern = re.compile(r'\{.*\}', re.DOTALL)
    match = json_pattern.search(str(te_output.stdout))
    if match:
        return json.loads(match.group(0))
    else:
        logging.debug(f"stdout: {te_output.stdout}")
        logging.debug(f"stderr: {te_output.stderr}")
        raise ValueError(f"No JSON object found in the output: {te_output.stdout}")

@log_linter
def model_linter(model_root: Path) -> dict:
    """Run the TabularEditor tool on a specified directory."""
    #TODO: add possibility for a local rules file (to be done in Program.cs)
    item_path = model_root / 'definition'
    linter_path = os.path.join(os.path.dirname(__file__), 'TMDLLint')
    args = ['dotnet', 'run', '--configuration', 'Release', '--project', linter_path,
            str(item_path)]
    result = subprocess.run(args,
                            capture_output=True, text=True, check=False, timeout=120)
    results_dict = handle_te_output(result)
    return results_dict

# endregion ####

# region test_report #####

def handle_pbii_output(test_results: dict, n_visuals: int):
    results = test_results["Results"]
    log_type_mapping = {0: 'error', 1: 'warning'}
    for result in results:
        result["result_int"] = 5 if result["Actual"] is False else len(result["Actual"])
        result["severity"] = log_type_mapping.get(result["LogType"], 'info')

    n_errors = 0
    n_warnings = 0
    n_infos = 0
    penalty = 0
    for item in results:
        if item["severity"] == 'error':
            n_errors += item["result_int"]
            penalty += item["result_int"] * 2
        if item["severity"] == 'warning':
            n_warnings += item["result_int"]
            penalty += item["result_int"]
        if item["severity"] == 'info':
            n_infos += item["result_int"]

    if n_visuals == 0:
        score = 0
    else:
        score = round(max(10 - (penalty / n_visuals * 5), 0), 2)

    return {
                'objects': n_visuals,
                'errors': n_errors,
                'warnings': n_warnings,
                'infos': n_infos,
                'score': score
            }

def get_number_of_visuals(report_root: Path):
    report_file = report_root / 'report.json'
    with open(report_file, 'r', encoding='utf-8') as f:
        report_json = f.read()
    report = json.loads(report_json)
    n_visuals = 0
    for section in report.get("sections", []):
        n_visuals += len(section.get("visualContainers", []))
    return n_visuals

@log_linter
def visuals_linter(report_root: Path, rules: Path) -> None:
    """Run the PBIInspector tool on a specified directory."""
    result_dir = tempfile.mkdtemp()
    valid_root = report_root
    if not str(valid_root).islower() or not str(valid_root).endswith('.report'):
        valid_root = Path(tempfile.mkdtemp()) / '.report'
        copy_tree(str(report_root), str(valid_root), verbose = 0)
    
    # Set the linter path container for CI pipeline
    linter_path = os.path.join(os.path.dirname(__file__), 'PBI-Inspector', 'PBIXInspectorCLI') 
    command = ['dotnet', 'run',
                '--project', linter_path,
                '--configuration', 'Release',
                "-pbipreport", str(valid_root),
                "-output", result_dir,
                "-rules", str(rules), 
                "-formats", "JSON"]
    
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
    if 'Error: Could not deserialise rules file with path' in result.stdout:
        raise ValueError(f"Invalid rules file format: '{rules}'")
    logging.debug(result)
    logging.debug(' '.join(command))
    json_file = os.path.join(result_dir, os.listdir(result_dir)[0])
    with open(os.path.join(result_dir, json_file), 'r', encoding = 'utf-8-sig') as f:
        data = f.read()
    n_visuals = get_number_of_visuals(report_root)
    results_dict = handle_pbii_output(json.loads(data), n_visuals)
    return results_dict

# endregion ####

# region linter_orchestration ####

def get_item_info(path, info = 'type'):
    """
    Read the item type from the .platform file
    """
    if (path / '.platform').exists():
        with open(path / '.platform', 'r', encoding='utf-8') as f:
            platform_data = json.load(f)
            return platform_data.get('metadata', {}).get(info)
    return None

def list_platform_folders(path: Path, max_depth=3):
    """
    Returns:
     A list of all folders with a .platform file in them.
     Supports checking folders up to a given "max_depth" (forwards or backwards).
    """
    item_folders = []
    if (path / '.platform').exists():
        item_folders.append(path)
    if max_depth == 0:
        return item_folders
    if max_depth > 0:
        for item in path.iterdir():
            if item.is_dir():
                item_folders.extend(list_platform_folders(item, max_depth - 1))
    if max_depth < 0:
        item_folders.extend(list_platform_folders(path.parent, max_depth + 1))
    return item_folders

def list_items(path: Path):
    """
    Returns a dictionnary for each folder (a workspace in fabric linguo)
    Each dictionnary allows for listing of SemanticModels and Reports
    """
    item_folders = list_platform_folders(path, max_depth = 5)
    holding_folders = {folder.parent for folder in item_folders}
    items_dict = {}
    for folder in holding_folders:
        reports = [item for item in item_folders
                    if item.parent == folder and get_item_info(item, 'type') == 'Report']
        models = [item for item in item_folders
                    if item.parent == folder and get_item_info(item, 'type') == 'SemanticModel']
        items_dict[folder] = {
                'Report': reports,
                'SemanticModel': models
                    }
    return items_dict
 
def run_linter(path: Path = Path('.'),
               powerbi_inspector_rules: Path = Path(os.path.join(os.path.dirname(__file__), "pbi_inspector_rules.json"))):

    items_dict = list_items(path)
    if not items_dict:
        logging.warning(f"No items found at {path}")
        return
    
    for folder in items_dict.keys():
        logging.info(f"In '{str(folder)}', reviewing: {items_dict[folder]}")
        for item in items_dict[folder]['SemanticModel']:
            try:
                model_linter(item)
            except Exception as e:
                log_exception(e)
        for item in items_dict[folder]['Report']:
            try:
                visuals_linter(item, powerbi_inspector_rules)
            except Exception as e:
                log_exception(e)


def main():
    """You can specify a Path arg to check for a specific folder"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tempfile.tempdir = temp_dir
        if len(sys.argv) > 1:
            paths = sys.argv[1:]
        else:
            paths = ['.']
        for path in paths:
            path = Path(path)
            if not path.exists():
                log_error(f"Path {path} does not exist.")
                continue
            try:
                run_linter(path)
            except Exception as e:
                log_exception(e)


# endregion ####

if __name__ == '__main__':
    main()
    if SUCCESS:
        sys.exit(0)
    else:
        sys.exit(1)

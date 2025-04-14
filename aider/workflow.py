"""
Support for bioinformatics workflow languages and execution backends.
"""

import os
import subprocess
from enum import Enum
from pathlib import Path


class WorkflowLanguage(Enum):
    CWL = "cwl"
    NEXTFLOW = "nextflow"
    WDL = "wdl"
    SNAKEMAKE = "snakemake"
    PYTHON = "python"
    SHELL = "shell"


class WorkflowBackend(Enum):
    # CWL backends
    CWLTOOL = "cwltool"
    TOIL = "toil"
    # Nextflow backends
    NEXTFLOW_LOCAL = "nextflow-local"
    NEXTFLOW_DOCKER = "nextflow-docker"
    # WDL backends
    CROMWELL = "cromwell"
    MINIWDL = "miniwdl"
    # Snakemake backends
    SNAKEMAKE_LOCAL = "snakemake-local"
    SNAKEMAKE_CLUSTER = "snakemake-cluster"
    # Direct execution
    PYTHON_DIRECT = "python-direct"
    SHELL_DIRECT = "shell-direct"


def get_workflow_language(filename):
    """Determine workflow language from file extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".cwl":
        return WorkflowLanguage.CWL
    elif ext == ".nf":
        return WorkflowLanguage.NEXTFLOW
    elif ext == ".wdl":
        return WorkflowLanguage.WDL
    elif ext == ".smk" or filename == "Snakefile":
        return WorkflowLanguage.SNAKEMAKE
    elif ext == ".py":
        return WorkflowLanguage.PYTHON
    elif ext in [".sh", ".bash"]:
        return WorkflowLanguage.SHELL
    return None


def run_workflow(filename, backend, params=None, cwd=None, encoding="utf-8"):
    """
    Execute a workflow file using the specified backend.
    
    Args:
        filename: Path to the workflow file
        backend: WorkflowBackend enum value
        params: Dictionary of parameters to pass to the workflow
        cwd: Working directory
        encoding: File encoding
        
    Returns:
        Tuple of (return_code, output)
    """
    if params is None:
        params = {}
    
    workflow_lang = get_workflow_language(filename)
    if not workflow_lang:
        raise ValueError(f"Unsupported workflow file: {filename}")
    
    cmd = []
    
    # Build command based on backend and workflow language
    if workflow_lang == WorkflowLanguage.CWL:
        if backend == WorkflowBackend.CWLTOOL:
            cmd = ["cwltool"]
            for k, v in params.items():
                cmd.extend(["--" + k, str(v)])
            cmd.append(filename)
        elif backend == WorkflowBackend.TOIL:
            cmd = ["toil-cwl-runner"]
            for k, v in params.items():
                cmd.extend(["--" + k, str(v)])
            cmd.append(filename)
        else:
            raise ValueError(f"Backend {backend} not supported for CWL")
            
    elif workflow_lang == WorkflowLanguage.NEXTFLOW:
        if backend in [WorkflowBackend.NEXTFLOW_LOCAL, WorkflowBackend.NEXTFLOW_DOCKER]:
            cmd = ["nextflow", "run"]
            if backend == WorkflowBackend.NEXTFLOW_DOCKER:
                cmd.append("-with-docker")
            cmd.append(filename)
            for k, v in params.items():
                cmd.extend(["--" + k, str(v)])
        else:
            raise ValueError(f"Backend {backend} not supported for Nextflow")
            
    elif workflow_lang == WorkflowLanguage.WDL:
        if backend == WorkflowBackend.CROMWELL:
            cmd = ["java", "-jar", "cromwell.jar", "run", filename]
            if params:
                inputs_file = "inputs.json"
                # Would need to write params to inputs.json
                cmd.extend(["-i", inputs_file])
        elif backend == WorkflowBackend.MINIWDL:
            cmd = ["miniwdl", "run", filename]
            for k, v in params.items():
                cmd.append(f"{k}={v}")
        else:
            raise ValueError(f"Backend {backend} not supported for WDL")
            
    elif workflow_lang == WorkflowLanguage.SNAKEMAKE:
        if backend in [WorkflowBackend.SNAKEMAKE_LOCAL, WorkflowBackend.SNAKEMAKE_CLUSTER]:
            cmd = ["snakemake", "-s", filename]
            if backend == WorkflowBackend.SNAKEMAKE_CLUSTER:
                cmd.append("--cluster")
                # Would need cluster configuration
            for k, v in params.items():
                cmd.extend(["--config", f"{k}={v}"])
        else:
            raise ValueError(f"Backend {backend} not supported for Snakemake")
            
    elif workflow_lang == WorkflowLanguage.PYTHON:
        if backend == WorkflowBackend.PYTHON_DIRECT:
            cmd = ["python", filename]
            # Add parameters as command line args
            for k, v in params.items():
                cmd.extend(["--" + k, str(v)])
        else:
            raise ValueError(f"Backend {backend} not supported for Python")
            
    elif workflow_lang == WorkflowLanguage.SHELL:
        if backend == WorkflowBackend.SHELL_DIRECT:
            cmd = ["bash", filename]
            # Add parameters as environment variables
            env = os.environ.copy()
            for k, v in params.items():
                env[k] = str(v)
            # Execute with environment
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding=encoding,
                    errors="replace",
                    cwd=cwd,
                    env=env
                )
                output = []
                while True:
                    chunk = process.stdout.read(1)
                    if not chunk:
                        break
                    print(chunk, end="", flush=True)
                    output.append(chunk)
                process.wait()
                return process.returncode, "".join(output)
            except Exception as e:
                return 1, str(e)
        else:
            raise ValueError(f"Backend {backend} not supported for Shell")
    
    # Execute the command
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=encoding,
            errors="replace",
            cwd=cwd
        )
        output = []
        while True:
            chunk = process.stdout.read(1)
            if not chunk:
                break
            print(chunk, end="", flush=True)
            output.append(chunk)
        process.wait()
        return process.returncode, "".join(output)
    except Exception as e:
        return 1, str(e)


def validate_workflow(filename, workflow_lang=None):
    """
    Validate a workflow file without executing it.
    
    Args:
        filename: Path to the workflow file
        workflow_lang: Optional WorkflowLanguage enum value
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not workflow_lang:
        workflow_lang = get_workflow_language(filename)
    
    if not workflow_lang:
        return False, f"Unsupported workflow file: {filename}"
    
    cmd = []
    
    if workflow_lang == WorkflowLanguage.CWL:
        cmd = ["cwltool", "--validate", filename]
    elif workflow_lang == WorkflowLanguage.NEXTFLOW:
        cmd = ["nextflow", "validate", filename]
    elif workflow_lang == WorkflowLanguage.WDL:
        cmd = ["womtool", "validate", filename]
    elif workflow_lang == WorkflowLanguage.SNAKEMAKE:
        cmd = ["snakemake", "-s", filename, "--lint"]
    elif workflow_lang == WorkflowLanguage.PYTHON:
        cmd = ["python", "-m", "py_compile", filename]
    elif workflow_lang == WorkflowLanguage.SHELL:
        cmd = ["shellcheck", filename]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return True, ""
        else:
            return False, result.stderr or result.stdout
    except Exception as e:
        return False, str(e)

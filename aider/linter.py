import os
import re
import subprocess
import sys
import traceback
import warnings
import shlex
from dataclasses import dataclass
from pathlib import Path

from grep_ast import TreeContext, filename_to_lang
from grep_ast.tsl import get_parser  # noqa: E402

from aider.dump import dump  # noqa: F401
from aider.run_cmd import run_cmd_subprocess  # noqa: F401
# Import workflow validation functions if they exist, otherwise handle errors
try:
    from aider.workflow import WorkflowLanguage, get_workflow_language, validate_workflow
except ImportError:
    # Define dummy functions or handle the absence gracefully
    class WorkflowLanguage:
        CWL = "cwl"
        NEXTFLOW = "nextflow"
        WDL = "wdl"
        SNAKEMAKE = "snakemake"
        SHELL = "shell"
        PYTHON = "python"

    def get_workflow_language(fname):
        # Basic detection based on extension
        ext = os.path.splitext(fname)[1].lower()
        if ext == ".cwl":
            return WorkflowLanguage.CWL
        elif ext == ".nf":
            return WorkflowLanguage.NEXTFLOW
        elif ext == ".wdl":
            return WorkflowLanguage.WDL
        elif ext in (".smk", ".snakefile"):
            return WorkflowLanguage.SNAKEMAKE
        elif ext == ".sh":
            return WorkflowLanguage.SHELL
        elif ext == ".py":
            return WorkflowLanguage.PYTHON
        return None

    def validate_workflow(fname, lang):
        print(f"Warning: Workflow validation skipped for {lang} due to missing module.")
        return True, ""


# tree_sitter is throwing a FutureWarning
warnings.simplefilter("ignore", category=FutureWarning)


class Linter:
    def __init__(self, encoding="utf-8", root=None):
        self.encoding = encoding
        self.root = root

        self.languages = dict(
            python=self.py_lint,
            cwl=self.cwl_lint,
            nextflow=self.nextflow_lint,
            wdl=self.wdl_lint,
            snakemake=self.snakemake_lint,
            shell=self.shell_lint,
        )
        self.all_lint_cmd = None

    def set_linter(self, lang, cmd):
        if lang:
            self.languages[lang] = cmd
            return

        self.all_lint_cmd = cmd

    def get_rel_fname(self, fname):
        if self.root:
            try:
                return os.path.relpath(fname, self.root)
            except ValueError:
                return fname
        else:
            return fname

    def run_cmd(self, cmd, rel_fname, code, check_installed=None, install_help=""):
        """
        Run a linting command.

        :param cmd: The base command string (e.g., "flake8", "cwltool --validate").
        :param rel_fname: The relative path to the file being linted.
        :param code: The content of the file (unused in this implementation but kept for signature consistency).
        :param check_installed: Optional command to check if the linter is installed (e.g., "cwltool --version").
        :param install_help: Optional help message for installing the linter.
        :return: LintResult or None.
        """
        if check_installed:
            try:
                # Use subprocess.run with check=True to raise CalledProcessError if command fails
                subprocess.run(
                    shlex.split(check_installed),
                    capture_output=True,
                    check=True,
                    cwd=self.root,
                    encoding=self.encoding,
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                error_message = f"Linter command '{cmd.split()[0]}' not found."
                if install_help:
                    error_message += f" {install_help}"
                print(error_message)
                # Return a LintResult indicating the tool is missing
                return LintResult(text=error_message, lines=[0])

        # Append the filename to the command
        full_cmd = cmd + " " + shlex.quote(rel_fname)

        returncode = 0
        stdout = ""
        try:
            returncode, stdout = run_cmd_subprocess(
                full_cmd,
                cwd=self.root,
                encoding=self.encoding,
            )
        except OSError as err:
            print(f"Unable to execute lint command: {err}")
            return None # Return None if the command execution itself fails

        errors = stdout.strip()

        # Different tools indicate success/failure differently
        # cwltool --validate: returns 0 on success, non-zero on failure, errors on stdout
        # nextflow lint: returns 0 on success, non-zero on failure, errors on stdout
        # miniwdl lint: returns 0 on success, non-zero on failure, errors on stdout/stderr
        # snakemake --lint: returns 0 on success, non-zero on failure, errors on stdout/stderr

        if returncode == 0 and not errors: # Handle cases where success means no output
             # Check specifically for tools that might output success messages we want to ignore
             if cmd.startswith("cwltool") or cmd.startswith("nextflow") or cmd.startswith("miniwdl") or cmd.startswith("snakemake"):
                 return None # Explicitly return None for success with no errors reported

        if returncode == 0 and errors and cmd.startswith("cwltool"):
             # cwltool --validate might return 0 but print warnings/errors
             pass # Continue to process potential errors in stdout
        elif returncode == 0 and errors and cmd.startswith("nextflow"):
             # nextflow lint might return 0 but print warnings/errors
             pass # Continue to process potential errors in stdout
        elif returncode == 0 and errors and cmd.startswith("miniwdl"):
             # miniwdl lint might return 0 but print warnings/errors
             pass # Continue to process potential errors in stdout
        elif returncode == 0 and errors and cmd.startswith("snakemake"):
             # snakemake --lint might return 0 but print warnings/errors
             pass # Continue to process potential errors in stdout
        elif returncode == 0:
             return None # Generic success case

        # If we got here, there was an error (non-zero exit or errors printed)
        res = f"## Running: {full_cmd}\n\n"
        res += errors

        return self.errors_to_lint_result(rel_fname, res)

    def errors_to_lint_result(self, rel_fname, errors):
        if not errors:
            return None

        linenums = []
        # Try to find standard "filename:linenum" patterns first
        filenames_linenums = find_filenames_and_linenums(errors, [rel_fname])
        if filenames_linenums:
            filename, linenums_set = next(iter(filenames_linenums.items()))
            linenums = [num - 1 for num in sorted(list(linenums_set))] # Sort and convert to 0-based
        else:
            # Fallback: Look for generic "line X" patterns if specific format fails
            generic_matches = re.findall(r'[Ll]ine\s+(\d+)', errors)
            if generic_matches:
                linenums = [int(num) - 1 for num in generic_matches]
                linenums = sorted(list(set(linenums))) # Deduplicate and sort

        # If no line numbers found, default to line 0 to show the start of the file
        if not linenums:
            linenums = [0]

        return LintResult(text=errors, lines=linenums)

    def lint(self, fname, cmd=None):
        rel_fname = self.get_rel_fname(fname)
        try:
            code = Path(fname).read_text(encoding=self.encoding, errors="replace")
        except OSError as err:
            print(f"Unable to read {fname}: {err}")
            return None

        if cmd:
            cmd = cmd.strip()
        if not cmd:
            lang = filename_to_lang(fname)
            # Use get_workflow_language as a fallback/override if filename_to_lang fails
            if not lang:
                 lang = get_workflow_language(fname)

            if not lang:
                return None # No language detected

            if self.all_lint_cmd:
                cmd = self.all_lint_cmd
            else:
                cmd = self.languages.get(lang)

        if callable(cmd):
            lintres = cmd(fname, rel_fname, code)
        elif isinstance(cmd, str):
            lintres = self.run_cmd(cmd, rel_fname, code)
        else:
            # Fallback to basic tree-sitter linting if no specific command/method
            lintres = basic_lint(rel_fname, code)

        if not lintres or not lintres.text.strip():
            return None # No linting errors found

        res = "# Fix any errors below, if possible.\n\n"
        res += lintres.text.strip()
        res += "\n"

        # Add tree context only if line numbers were found and it's not just line 0
        if lintres.lines and lintres.lines != [0]:
             try:
                 context_str = tree_context(rel_fname, code, lintres.lines)
                 if context_str:
                     res += "\n" + context_str
             except Exception as e:
                 print(f"Error generating tree context for {rel_fname}: {e}")
                 # Optionally add a fallback message
                 res += f"\nError generating context for {rel_fname}."


        return res

    def py_lint(self, fname, rel_fname, code):
        basic_res = basic_lint(rel_fname, code)
        compile_res = lint_python_compile(fname, code)
        flake_res = self.flake8_lint(rel_fname)

        text = ""
        lines = set()
        for res in [basic_res, compile_res, flake_res]:
            if not res:
                continue
            if res.text.strip(): # Only add if there's actual error text
                if text:
                    text += "\n\n" # Add more separation between different linter outputs
                text += res.text.strip()
            lines.update(res.lines)

        if text or lines:
            return LintResult(text, sorted(list(lines)))
        return None

    def cwl_lint(self, fname, rel_fname, code):
        """Lint Common Workflow Language files using cwltool --validate"""
        return self.run_cmd(
            "cwltool --validate",
            rel_fname,
            code,
            check_installed="cwltool --version",
            install_help="Install with: pip install cwltool"
        )

    def nextflow_lint(self, fname, rel_fname, code):
        """Lint Nextflow files using 'nextflow lint'"""
        # Note: `nextflow lint` requires the file to be in the CWD or specify path relative to CWD
        # self.run_cmd handles running from self.root, so rel_fname should work.
        return self.run_cmd(
            "nextflow lint",
            rel_fname,
            code,
            check_installed="nextflow -v",
            install_help="Install Nextflow (see https://www.nextflow.io/docs/latest/getstarted.html)"
        )

    def wdl_lint(self, fname, rel_fname, code):
        """Lint Workflow Description Language files using 'miniwdl lint'"""
        return self.run_cmd(
            "miniwdl lint",
            rel_fname,
            code,
            check_installed="miniwdl --version",
            install_help="Install with: pip install miniwdl"
        )

    def snakemake_lint(self, fname, rel_fname, code):
        """Lint Snakemake files using 'snakemake --lint'"""
        # Snakemake lint needs the path relative to the CWD (self.root)
        return self.run_cmd(
            "snakemake --lint -s", # -s specifies the snakefile
            rel_fname,
            code,
            check_installed="snakemake --version",
            install_help="Install with: pip install snakemake"
        )

    def shell_lint(self, fname, rel_fname, code):
        """Lint Shell scripts using shellcheck"""
        return self.run_cmd(
            "shellcheck",
            rel_fname,
            code,
            check_installed="shellcheck --version",
            install_help="Install shellcheck (see https://github.com/koalaman/shellcheck#installing)"
        )

    def flake8_lint(self, rel_fname):
        fatal = "E9,F821,F823,F831,F406,F407,F701,F702,F704,F706"
        flake8_cmd_list = [
            sys.executable,
            "-m",
            "flake8",
            f"--select={fatal}",
            "--show-source",
            "--isolated",
            shlex.quote(rel_fname), # Ensure filename is quoted
        ]
        flake8_cmd_str = " ".join(flake8_cmd_list)

        text = f"## Running: {flake8_cmd_str}\n\n"

        try:
            result = subprocess.run(
                flake8_cmd_list, # Use list for subprocess.run
                capture_output=True,
                text=True,
                check=False,
                encoding=self.encoding,
                errors="replace",
                cwd=self.root,
            )
            errors = (result.stdout + result.stderr).strip()
        except Exception as e:
            errors = f"Error running flake8: {str(e)}"

        if not errors:
            return None

        text += errors
        return self.errors_to_lint_result(rel_fname, text)


@dataclass
class LintResult:
    text: str
    lines: list


def lint_python_compile(fname, code):
    try:
        compile(code, fname, "exec")  # USE TRACEBACK BELOW HERE
        return None
    except Exception as err:
        end_lineno = getattr(err, "end_lineno", err.lineno)
        # Ensure lineno is at least 1
        start_lineno = max(1, getattr(err, "lineno", 1))
        # Ensure end_lineno is not less than start_lineno
        end_lineno = max(start_lineno, end_lineno) if end_lineno is not None else start_lineno

        line_numbers = list(range(start_lineno - 1, end_lineno)) # 0-based index

        tb_lines = traceback.format_exception(type(err), err, err.__traceback__)
        last_file_i = 0

        target = "# USE TRACEBACK"
        target += " BELOW HERE"
        for i in range(len(tb_lines)):
            if target in tb_lines[i]:
                last_file_i = i
                break

        tb_lines = tb_lines[:1] + tb_lines[last_file_i + 1 :]

    res = "".join(tb_lines)
    return LintResult(text=res, lines=line_numbers)


def basic_lint(fname, code):
    """
    Use tree-sitter to look for syntax errors, display them with tree context.
    """
    lang = filename_to_lang(fname)
    if not lang:
        return None

    # Only support languages with available parsers for basic linting
    supported_langs = ["python", "bash", "javascript", "typescript", "tsx", "jsx", "go", "rust", "java", "c", "cpp", "c_sharp", "php", "ruby", "html", "css"]
    if lang not in supported_langs:
        return None

    try:
        parser = get_parser(lang)
    except Exception as err:
        print(f"Unable to load parser for {lang}: {err}")
        return None

    try:
        tree = parser.parse(bytes(code, "utf-8"))
        errors = traverse_tree(tree.root_node)
    except RecursionError:
        print(f"Unable to lint {fname} due to RecursionError")
        return None
    except Exception as e:
        print(f"Error during basic linting of {fname}: {e}")
        return None


    if not errors:
        return None

    # Return minimal info, context will be added later if needed
    return LintResult(text=f"Basic syntax errors detected in {fname}", lines=errors)


def tree_context(fname, code, line_nums):
    if not line_nums:
        return ""
    try:
        context = TreeContext(
            fname,
            code,
            color=False,
            line_number=True,
            child_context=False,
            last_line=False,
            margin=0,
            mark_lois=True,
            loi_pad=3,
            # header_max=30,
            show_top_of_file_parent_scope=False,
        )
        line_nums_set = set(line_nums)
        context.add_lines_of_interest(line_nums_set)
        context.add_context()
        s = "s" if len(line_nums_set) > 1 else ""
        output = f"## See relevant line{s} below marked with █.\n\n"
        output += fname + ":\n"
        output += context.format()
        return output
    except Exception as e:
        print(f"Error generating tree context for {fname}: {e}")
        return f"Error generating context for {fname}."


# Traverse the tree to find errors
def traverse_tree(node):
    errors = []
    if node is None:
        return errors
    if node.type == "ERROR" or node.is_missing:
        line_no = node.start_point[0]
        errors.append(line_no)

    for child in node.children:
        errors += traverse_tree(child)

    # Deduplicate and sort line numbers
    return sorted(list(set(errors)))


def find_filenames_and_linenums(text, fnames):
    """
    Search text for all occurrences of <filename>:<line_num> or <filename> line <line_num>
    where <filename> is one of the filenames in the list `fnames`.
    Handles variations in separators (: or space) and case for "line".
    """
    # Create a robust pattern to match filenames followed by line numbers
    # Handles separators like ':', ' line ', ' Line '
    # Ensures filename is captured correctly, even with special characters
    fname_pattern_part = "|".join(re.escape(fname) for fname in fnames)
    pattern = re.compile(
         r"\b(" + fname_pattern_part + r")"  # Capture filename
         r"(?::|\s+[Ll]ine\s+)"              # Match separator (colon or ' line ' case-insensitive)
         r"(\d+)"                            # Capture line number
    )

    matches = pattern.findall(text)
    result = {}
    for fname, linenum_str in matches:
        if fname not in result:
            result[fname] = set()
        try:
            result[fname].add(int(linenum_str))
        except ValueError:
            # Ignore if linenum can't be converted to int
            pass
    return result


def main():
    """
    Main function to parse files provided as command line arguments.
    """
    if len(sys.argv) < 2:
        print("Usage: python linter.py <file1> <file2> ...")
        sys.exit(1)

    linter = Linter(root=os.getcwd())
    for file_path in sys.argv[1:]:
        errors = linter.lint(file_path)
        if errors:
            print(errors)


if __name__ == "__main__":
    main()

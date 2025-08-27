import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from logging import warning
from pathlib import Path
from typing import List, Optional, Tuple, cast

DEFAULT_CPP_SUFFIXES = (".c", ".cc", ".cpp", ".cxx")
DEFAULT_CUDA_SUFFIXES = (".cu",)

HISTORY_FILE = os.path.expanduser("~/.config/compile_commands_generator/history.json")
DEFAULT_PLACEHOLDER_DIR = os.path.expanduser(
    "~/.config/compile_commands_generator/placeholder_DO_NOT_EDIT"
)


def generate_compile_commands(
    proj_path: str,
    cpp_args: List[str],
    cuda_args: List[str],
    cuda_inherit_cpp: bool,
    ignore_formats: List[str],
    extra_cpp_suffixes: Optional[Tuple[str, ...]] = None,
    extra_cuda_suffixes: Optional[Tuple[str, ...]] = None,
    output_dir: Optional[str] = None,
) -> int:
    """
    Generate a compile_commands.json file for a project.

    Args:
        proj_path: Path to the project directory.
        cpp_args: Compiler arguments for C/C++ files.
        cuda_args: Compiler arguments for CUDA (.cu) files.
        cuda_inherit_cpp: If True, CUDA files will also include cpp_args.
        ignore_formats: List of glob patterns to ignore.
    """
    cpp_suffixes = cast(
        Tuple[str, ...], DEFAULT_CPP_SUFFIXES + (extra_cpp_suffixes or ())
    )
    cuda_suffixes = cast(
        Tuple[str, ...], DEFAULT_CUDA_SUFFIXES + (extra_cuda_suffixes or ())
    )

    proj = Path(proj_path).resolve()
    if not proj.is_dir():
        raise ValueError(f"{proj} is not a valid directory")

    entries = []

    # Recursively walk through the project directory
    for root, dirs, files in os.walk(proj):
        for fname in files:
            path = Path(root) / fname
            relpath = str(path.relative_to(proj))

            # Skip if matches any ignore pattern
            if any(fnmatch.fnmatch(relpath, pattern) for pattern in ignore_formats):
                continue

            # Check file extension to determine file type
            if path.suffix in cpp_suffixes:
                command = ["g++"] + cpp_args + ["-c", relpath]
            elif path.suffix in cuda_suffixes:
                args = cpp_args if cuda_inherit_cpp else []
                command = ["nvcc"] + args + cuda_args + ["-c", relpath]
            else:
                continue  # Skip header and unrelated files

            entry = {
                "directory": str(proj),
                "file": relpath,
                "command": " ".join(command),
            }
            entries.append(entry)

    # Write the compile_commands.json file
    output_d = proj if output_dir is None else Path(output_dir).resolve()
    outfile = output_d / "compile_commands.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"✅ compile_commands.json generated at: {outfile}")

    return len(entries)


def detect_cuda_args() -> List[str]:
    """
    Detect CUDA environment and generate default CUDA compiler arguments.

    Returns:
        A list of CUDA arguments if detection succeeds.
        If detection fails, prints warning and returns an empty list.
    """
    cuda_path = None
    cuda_ver_major = None
    cuda_ver_minor = None
    cuda_ver_build = None
    arch_str = None

    # Detect nvcc version
    try:
        nvcc_path = subprocess.check_output(["which", "nvcc"], text=True).strip()
        nvcc_out = subprocess.check_output([nvcc_path, "--version"], text=True)
        # Look for: Cuda compilation tools, release 12.6, V12.6.20
        m = re.search(r"release\s+(\d+)\.(\d+).*V(\d+)\.(\d+)\.(\d+)", nvcc_out)
        if m:
            cuda_ver_major = int(m.group(1))
            cuda_ver_minor = int(m.group(2))
            cuda_ver_build = int(m.group(5))
            cuda_path = f"/usr/local/cuda-{cuda_ver_major}.{cuda_ver_minor}"
        else:
            warning("⚠️ Could not parse nvcc version output")
            return []
    except Exception as e:
        warning(f"⚠️ nvcc not found or failed to run: {e}")
        return []

    # Detect GPU compute capability
    try:
        sm_out = subprocess.check_output(
            [
                "nvidia-smi",
                "--id=0",
                "--query-gpu=compute_cap",
                "--format=csv,noheader",
            ],
            text=True,
        ).strip()
        # e.g. "9.0"
        major_minor = sm_out.split(".")
        if len(major_minor) == 2:
            arch_str = f"sm_{major_minor[0]}{major_minor[1]}"
        else:
            warning("⚠️ Could not parse compute capability from nvidia-smi output")
            return []
    except Exception as e:
        warning(f"⚠️ nvidia-smi not found or failed to query compute capability: {e}")
        return []

    # Assemble default args
    cuda_args = [
        f"--cuda-path={cuda_path}",
        f"--cuda-gpu-arch={arch_str}",
        f"-I{cuda_path}/include",
        "-D__CUDACC__",
        f"-D__CUDA_ARCH__={arch_str[3:]}0",  # e.g. 900
        f"-D__CUDA_ARCH_LIST__={arch_str[3:]}0",
        "-D__NV_LEGACY_LAUNCH",
        "-D__NVCC__",
        f"-D__CUDACC_VER_MAJOR__={cuda_ver_major}",
        f"-D__CUDACC_VER_MINOR__={cuda_ver_minor}",
        f"-D__CUDACC_VER_BUILD__={cuda_ver_build}",
        f"-D__CUDA_API_VER_MAJOR__={cuda_ver_major}",
        f"-D__CUDA_API_VER_MINOR__={cuda_ver_minor}",
        "-D__NVCC_DIAG_PRAGMA_SUPPORT__=1",
        "-D__CUDA_INCLUDE_COMPILER_INTERNAL_HEADERS__",
    ]

    return cuda_args


def torch_args():
    """
    Detect PyTorch environment and generate clangd fallbackFlags."""
    try:
        purelib_path = Path(
            subprocess.check_output(
                [
                    "python",
                    "-c",
                    "import sysconfig; print(sysconfig.get_paths()['purelib'])",
                ],
                text=True,
            ).strip()
        )
        torch_path = purelib_path / "torch"
        assert torch_path.exists(), "PyTorch not found in the expected path."
        args = [
            f"-I{torch_path}",
            f"-I{torch_path / 'include'}",
            f"-I{torch_path / 'include' / 'torch' / 'csrc' / 'api' / 'include'}",
            f"-I{torch_path / 'include' / 'TH'}",
            f"-I{torch_path / 'include' / 'THC'}",
        ]

        python_path = subprocess.check_output(
            [
                "python",
                "-c",
                "import sysconfig; print(sysconfig.get_paths()['include'])",
            ],
            text=True,
        ).strip()
        args.append(f"-I{python_path}")
        return args

    except Exception as e:
        warning(f"⚠️ Failed to detect PyTorch path: {e}")
        return []


def parse_cutlass(cutlass_root: str) -> List[str]:
    """
    Parse CUTLASS include paths from the given root directory.

    Args:
        cutlass_root: Path to the CUTLASS root directory.

    Returns:
        A list of include paths for CUTLASS.
    """
    root = Path(cutlass_root).resolve()

    args = [
        root / "include",
        root / "tools" / "util" / "include",
        root / "examples" / "common",
    ]

    if not all(arg.exists() for arg in args):
        warning(f"⚠️ CUTLASS root {cutlass_root} does not contain expected directories.")
        return []

    return ["-I" + str(arg) for arg in args]


def share_includes(
    cpp_args: List[str], cuda_args: List[str]
) -> Tuple[List[str], List[str]]:
    cpp_args.extend(
        include
        for include in cuda_args
        if include.startswith("-I") and include not in cpp_args
    )
    cuda_args.extend(
        include
        for include in cpp_args
        if include.startswith("-I") and include not in cuda_args
    )

    return cpp_args, cuda_args


def generate_empty_cc_file(path: Path) -> None:
    cc_name = "placeholder.cc"
    cu_name = "placeholder.cu"
    code = """// This file is automatically generated by compile_commands_generator.py for placeholder purposes. Do not edit manually.\n"""

    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

        with open(path / cu_name, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"✅ Created empty CUDA file at: {path / cu_name}")

        # with open(path / cc_name, "w", encoding="utf-8") as f:
        #     f.write(code)
        # print(f"✅ Created empty C++ file at: {path / cc_name}")


def generate(args):
    proj_path = args.root
    cpp_args = args.cpp_args
    cuda_args = detect_cuda_args() + args.cuda_args
    ignore_formats = args.ignore_formats
    extra_cpp_suffixes = tuple(args.extra_cpp_suffixes)
    extra_cuda_suffixes = tuple(args.extra_cuda_suffixes)

    if args.require_torch or args.cutlass_root:
        if args.require_torch:
            torch_includes = torch_args()
            cpp_args.extend(torch_includes)
        if args.cutlass_root:
            cutlass_includes = parse_cutlass(args.cutlass_root)
            cpp_args.extend(cutlass_includes)

        cuda_inherit_cpp = True
    else:
        cuda_inherit_cpp = args.cuda_inherit_cpp

    cpp_args, cuda_args = share_includes(cpp_args, cuda_args)

    def try_generate(proj_root: str, out_dir: str):
        entry_count = generate_compile_commands(
            proj_path=proj_root,
            cpp_args=cpp_args,
            cuda_args=cuda_args,
            cuda_inherit_cpp=cuda_inherit_cpp,
            ignore_formats=ignore_formats,
            output_dir=out_dir,
            extra_cpp_suffixes=extra_cpp_suffixes,
            extra_cuda_suffixes=extra_cuda_suffixes,
        )

        return entry_count

    entry_count = try_generate(proj_path, proj_path)

    if entry_count == 0:
        warning("⚠️ No valid source files found. Generating an empty placeholder file.")
        generate_empty_cc_file(Path(args.placeholder_dir))

        entry_count = try_generate(args.placeholder_dir, proj_path)
        if entry_count == 0:
            warning(
                "⚠️ Still no valid source files found after generating placeholder. Did you set it to ignore the placeholder files?"
            )
        else:
            print(
                "✅ Successfully generated compile_commands.json with placeholder file included."
            )


def list_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    except FileNotFoundError:
        print("No history recorded yet.")
        return
    for proj, cmd in history.items():
        print(f"[{proj}] -> {cmd}")


def load_last_command(project_root: str):
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    except FileNotFoundError:
        return None
    return history.get(os.path.abspath(project_root))


def save_last_command(project_root: str, argv: list[str]):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    except FileNotFoundError:
        history = {}

    history[os.path.abspath(project_root)] = " ".join(argv)

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def main():

    def comma_split(arg: str) -> List[str]:
        """Helper to split comma-separated arguments."""
        return [s.strip() for s in arg.split(",") if s.strip()]

    parser = argparse.ArgumentParser(
        description="Generate compile_commands.json for C++/CUDA projects."
    )
    parser.add_argument(
        "--root",
        "-r",
        type=str,
        required=True,
        help="Path to the project directory.",
    )
    parser.add_argument(
        "--cpp-args",
        "-cc",
        type=comma_split,
        default=[],
        help='Comma-separated list arguments for C/C++ files (e.g. --cpp-args="-std=c++17,-Iinclude").',
    )
    parser.add_argument(
        "--cuda-args",
        "-cu",
        type=comma_split,
        default=[],
        help='Comma-separated list arguments for CUDA files (e.g. --cuda-args="-I/usr/local/cuda/include,-D__CUDACC__").',
    )
    parser.add_argument(
        "--no-cuda-inherit-cpp",
        "-nci",
        action="store_false",
        dest="cuda_inherit_cpp",
        help="If set, CUDA files will NOT include cpp_args. Default is to inherit.",
    )
    parser.add_argument(
        "--require-torch",
        "-rt",
        action="store_true",
        help="If set, requires PyTorch to be installed and adds its include paths to the compile commands.",
    )
    parser.add_argument(
        "--cutlass-root",
        "-cr",
        type=str,
        help="If set, requires CUTLASS to be installed and adds its include paths to the compile commands.",
    )
    parser.add_argument(
        "--ignore-formats",
        "-igs",
        type=comma_split,
        default=[],
        help="Glob patterns to ignore (e.g. --ignore-formats '*.test.cpp,*/tests/*').",
    )
    parser.add_argument(
        "--placeholder-dir",
        type=str,
        default=DEFAULT_PLACEHOLDER_DIR,
        help="Directory to create a placeholder file if no valid source files are found.",
    )
    parser.add_argument(
        "--extra-cpp-suffixes",
        type=comma_split,
        default=[],
        help="Additional file suffixes to treat as C/C++ source files. We basically include (.c, .cc, .cpp, .cxx) by default.",
    )
    parser.add_argument(
        "--extra-cuda-suffixes",
        type=comma_split,
        default=[],
        help="Additional file suffixes to treat as CUDA source files. We basically include (.cu) by default.",
    )
    parser.add_argument(
        "--reuse",
        "-rs",
        action="store_true",
        help="Reuse the last command used for this project.",
    )
    parser.add_argument(
        "--list-history",
        "-lh",
        action="store_true",
        help="List all recorded project commands.",
    )

    args = parser.parse_args()

    if args.list_history:
        list_history()
        sys.exit(0)

    project_root = args.root
    if args.reuse:
        argv = load_last_command(project_root)
        if argv is None:
            print(f"No history found for project: [{project_root}].")
            sys.exit(1)
        print(f"Reusing last command for {project_root}:")
        cmd = sys.executable + " " + argv
        print(cmd)
        subprocess.call(cmd.split(), shell=False)
    else:
        save_last_command(project_root, sys.argv)
        generate(args)


if __name__ == "__main__":
    main()

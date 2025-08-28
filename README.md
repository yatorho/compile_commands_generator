# compile-commands-generator

A tiny, no-build helper to generate a `compile_commands.json` for **clangd** (and other tooling) without CMake, Make, Bazel, or any build system.

It scans your project for C/C++ and CUDA sources, builds reasonable per-file “compile” entries, and writes a ready-to-use `compile_commands.json`. It can also auto-detect your CUDA toolchain/GPU arch, and optionally add headers from **PyTorch** and **CUTLASS**.

---

## Why?

* You want clangd code completion, go-to-definition, and diagnostics **now**, but your project has no build system.
* You have a mix of `.cc/.cpp` and `.cu` files and just need the right include paths and defines in one place.
* You prefer to keep things simple and explicit.

---

## Features

* 🔍 Recursively scans your project for C/C++ (`.c .cc .cpp .cxx`) and CUDA (`.cu`) sources
* 🧠 CUDA auto-detection (if available): detects `nvcc` version, CUDA install path, **GPU compute capability** (`nvidia-smi`) and adds sensible flags/defines
* 🤝 Optional integration headers:

  * `--require-torch` adds PyTorch headers (and your Python include dir)
  * `--cutlass_root` adds CUTLASS headers (verifies typical include folders)
* 🧱 Include sharing: `-I...` flags are kept in sync between C++ and CUDA command lines
* 🚫 Ignore patterns: exclude files/folders with glob patterns (e.g. tests, vendored code)
* 🧩 Extensible suffixes: add extra source file extensions via `--extra-cpp-suffixes` and `--extra-cuda-suffixes`
* 🩹 Placeholder compilation unit for header-only projects: generates an empty source file (`.cu` by default) and a corresponding `compile_commands.json` entry with your `-I...` paths so **clangd** can index headers and provide completions even when you have no real `.cc/.cu` files.

---

## Quick Start

```bash
# From your project root
python -m compile_commands_generator \
  --root . \
  --cpp-args "-std=c++17,-Iinclude" \
  --ignore-formats "*.test.cpp,*/tests/*"

# or
compile-commands -r . --cpp-args "-Iinclude"
```

That’s it. You’ll get:

```
✅ compile_commands.json generated at: /absolute/path/to/your/project/compile_commands.json
```

Open the project in your editor (e.g. VS Code + clangd) and enjoy completions.

---

## Installation

This script is standalone—no packaging required.

```bash
git clone https://github.com/yatorho/compile_commands_generator.git

pip install .
```

**Requirements**

* Python 3.8+
* For CUDA auto-detection (optional): `nvcc` and `nvidia-smi` on PATH
* For PyTorch headers (optional): `torch` installed in your current Python env
* For CUTLASS headers (optional): a local CUTLASS checkout

> Works best on Linux/macOS (uses `which`). On Windows, use a POSIX-like shell or adapt the script accordingly.

---

## Common Usage

**C/C++ only**

```bash
compile_commands \
  --root . \
  --cpp-args "-std=c++20,-Iinclude,-DNDEBUG" \
  --ignore-formats "*.test.cpp,*/third_party/*"
```

**C++ + CUDA (auto-detect CUDA)**

```bash
compile_commands \
  --root . \
  --cpp-args "-std=c++17,-Iinclude"
# The script will try to detect nvcc, CUDA path, and GPU arch automatically.
```

**C++ + CUDA (add your own CUDA flags as well)**

```bash
compile_commands \
  --root . \
  --cpp-args "-std=c++17,-Iinclude" \
  --cuda-args "-I/usr/local/cuda/include,-DUSE_CUDA=1"
```

**CUDA files NOT inheriting C++ flags**

```bash
compile_commands \
  --root . \
  --cpp-args "-std=c++17,-Iinclude" \
  --no-cuda-inherit-cpp
```

**Add PyTorch headers**

```bash
compile_commands \
  --root . \
  --require-torch
# Adds -I<site-packages>/torch and common torch include subdirs, plus your Python include dir.
```

**Add CUTLASS headers**

```bash
compile_commands \
  --root . \
  --cutlass_root /path/to/cutlass
```

**Support additional file suffixes**

```bash
# Treat .C and .c++ as C/C++ sources, and .cuh as CUDA sources
compile_commands \
  --root . \
  --extra-cpp-suffixes ".C,.c++" \
  --extra-cuda-suffixes ".cuh"
```

## Header-only projects: how the placeholder works

clangd indexes **compilation units** (source files) and then follows the headers included via your `-I` paths. Headers by themselves aren’t compiled, so clangd won’t parse them unless they’re reachable from some source file. To support header-only repositories, this tool can generate a **placeholder** source file and add it to `compile_commands.json`. clangd then uses the flags (especially your `-I...`) from that entry to index your headers.

**Typical flow**

```bash
compile_commands \
  --root . \
  --cpp-args "-Iinclude,-Ithird_party/some_lib/include"
```

* If the scan finds no real sources, the tool creates an empty placeholder source file (`.cu` by default) under `--placeholder-dir` and emits a `compile_commands.json` entry that includes your `-I...` paths.
* This is enough for clangd to start providing LSP features for your headers.
* If you prefer a C++ compilation unit specifically, you can add your own tiny `placeholder.cc` (empty file) anywhere in the repo and re-run the tool; it will be picked up like any other source file.

> Note: The placeholder’s extension is `.cu` by default. That’s okay for indexing; clangd mainly cares about the flags and include paths. If your project is strictly C++, adding a trivial `.cc` source file is also a fine approach.


## Command History Support

To simplify workflow across multiple projects, compile-commands-generator automatically remembers the last command you used for each project root. This prevents mixing up long sets of flags and makes it easy to repeat your setup.

**Reuse the Last Command**

If you want to re-run the exact same command you previously used in the current project directory:

```bash
compile-commands --root . --reuse
```

This will look up the most recent command for the given project path and execute it again.
Useful when you just want to refresh `compile_commands.json` with the same settings.

---

**List All Recorded Commands**

You can also inspect the stored history:

```bash
compile-commands --list-history
```

This prints all recorded project paths and their corresponding last commands, for example:

```txt
[/home/user/projs/mirage] -> python -m compile_commands_generator -r . -cc=-Iinclude,-I/home/user/projs/mirage/include -rt -cr=/home/user/projs/mirage/deps/cutlass -igs=deps/*,build/*
[/home/user/projs/another_project] -> python -m compile_commands_generator -r . -cc=-Iinclude,-DNDEBUG
```

This allows you to quickly copy, review, or reuse commands across multiple projects.

---


## Ignore Patterns Examples

```bash
# Ignore tests and build outputs
--ignore-formats "*/tests/*,*.test.cpp,build/*,out/*"

# Ignore vendored third-party trees
--ignore-formats "third_party/*,external/*,vendor/*"
```

Patterns are matched against **paths relative to the project root**.

---

## CLI Reference

```
--root, -r <path>            Project root to scan (required).

--cpp-args, -cc "<a,b,c>"    Comma-separated args for C/C++ files.
                             Example: "-std=c++17,-Iinclude,-DNDEBUG"

--cuda-args, -cu "<a,b,c>"   Comma-separated args for CUDA (.cu) files.
                             Appended to auto-detected CUDA args when available.

--no-cuda-inherit-cpp, -nci  By default, CUDA files inherit cpp args (-cc).
                             Pass this flag to stop inheriting.

--require-torch, -rt         Add PyTorch include paths (torch + Python headers).

--cutlass_root, -cr <path>   Add CUTLASS include paths from the given root.

--ignore-formats, -igs "<g1,g2,...>"
                             Glob patterns to ignore during the scan.
                             Example: "*.test.cpp,*/tests/*,*/third_party/*"

--extra-cpp-suffixes "<s1,s2,...>"
                             Additional file suffixes to treat as C/C++ sources.
                             Defaults already include .c,.cc,.cpp,.cxx

--extra-cuda-suffixes "<s1,s2,...>"
                             Additional file suffixes to treat as CUDA sources.
                             Defaults already include .cu

--placeholder-dir <path>     Where to create a placeholder file when no sources
                             are found (defaults to 
                             ~/.config/compile_commands_generator/placeholder_DO_NOT_EDIT.)
      
--reuse, -rs                 Reuse the last recorded command for the given project root.
                             Useful to quickly regenerate compile_commands.json
                             with the same settings as before.
                            
--list-history, -lh          Print all recorded project roots and their last commands.
                             Allows reviewing or copying past invocations.
```

**Notes & Behaviour**

* The tool always tries to detect CUDA first. If detection fails, it prints a warning and continues.
* If you pass `--require-torch` or `--cutlass_root`, CUDA files will **automatically inherit** C/C++ args (same as default) to keep include flags aligned.
* The generated `compile_commands.json` is written to your **project root**.

---

## What gets generated?

Each source file becomes a `command` entry. Examples:

```json
{
  "directory": "/abs/path/to/project",
  "file": "src/foo.cc",
  "command": "g++ -std=c++17 -Iinclude -c src/foo.cc"
}
```

```json
{
  "directory": "/abs/path/to/project",
  "file": "kernels/bar.cu",
  "command": "nvcc -Iinclude --cuda-path=/usr/local/cuda-12.6 --cuda-gpu-arch=sm_90 -D__CUDACC__ -c kernels/bar.cu"
}
```

clangd primarily cares about the **flags** (`-I`, `-D`, language/std settings, etc.). The exact compiler binary (`g++` vs `clang++`) is less important for IDE features, but if you prefer `clang++` you can adjust the script.

---

## Troubleshooting

* **“nvcc not found or failed to run” / “nvidia-smi not found”**
  CUDA auto-detection is optional. Provide your own `--cuda-args` or install CUDA tools.

* **“Could not parse nvcc version / compute capability”**
  Your tool output is unusual. Add required CUDA flags manually via `--cuda-args`.

* **“No valid source files found”**
  The tool creates an empty **placeholder source file** (`.cu` by default) in `--placeholder-dir` and includes it in `compile_commands.json`. Be sure to pass the include directories you want indexed via `--cpp-args "-Ipath1,-Ipath2"` (and/or `--cuda-args`). This is intentional for **header-only** projects: clangd only parses headers when they’re reachable from a compilation unit that has the right `-I...` paths. If you prefer a pure C++ unit, add a tiny `placeholder.cc` and re-run the script.

* **clangd still can’t find some headers**
  Add more `-I...` via `--cpp-args` (and/or `--cuda-args`). You can also use `--require-torch` or `--cutlass_root` when relevant.

* **Windows**
  The script uses `which` and POSIX paths. Run in MSYS2/Git Bash/WSL or adapt the code for native Windows.

---


## Design Notes & Limitations

* Uses `g++` for C/C++ entries and `nvcc` for CUDA entries. clangd mostly cares about flags; if you prefer `clang++`, tweak the script.
* CUDA arch detection uses **GPU 0** via `nvidia-smi`. Multi-arch builds aren’t modeled; it emits a single `__CUDA_ARCH__` value (e.g. `900` for `sm_90`).
* Headers aren’t scanned; only compilation **units** (default `.c/.cc/.cpp/.cxx/.cu`, plus any you add) are listed.
* No attempt is made to mirror a project’s real build graph; this is intentionally a **fast, best-effort** generator for editor tooling.

---

## License

MIT (recommended). Replace with your preferred license if needed.

---


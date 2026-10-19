# Running TargetDesign-workbench in a container

The container image is the distributed stand-alone application: it starts the local web
workbench on `http://localhost:5000` and bundles the native C++20 indexed off-target
engine, so no Python installation and no third-party software installation is needed on
the host.

## Pulling the published image

The release version's single source is `[project].version` in `pyproject.toml`. Set
`VERSION` to that value before using the examples below; no second hard-coded image tag
needs to be maintained.

The images are built, smoke-tested and published by the `container` workflow
(`.github/workflows/container.yml`) on GitHub's runners, so producing or obtaining them needs no
local Docker installation. For a verification-only run, start the workflow manually with
`publish=false` and `build_full=true`. The runner builds both targets without logging in to GHCR,
smoke-tests the core web/native surface and checks that the full image imports CPU PyTorch plus
the bundled ViennaRNA, Cas-OFFinder and R/NuPoP tools:

```bash
VERSION="<version>"  # pyproject.toml [project].version
docker pull ghcr.io/lnt-666/targetdesign-workbench:$VERSION
docker pull ghcr.io/lnt-666/targetdesign-workbench:$VERSION-full
docker run --rm -p 127.0.0.1:5000:5000 ghcr.io/lnt-666/targetdesign-workbench:$VERSION
```

Image visibility is set separately from the repository. This package is public, so the images can
be pulled without an account and without a prior `docker login`.
## Requirements

- Docker Engine 24 or newer (Docker Desktop on Windows and macOS), or Podman with the
  `podman build` / `podman run` equivalents.
- About 4 GB of free disk space for the default image, more for `--target full`.
- The image is built on Ubuntu 24.04 with Python 3.12, GCC 13 and CMake 3.28: the toolchain
  this project is verified against.

## Build and run

```bash
VERSION="<version>"  # pyproject.toml [project].version
docker build -t targetdesign-workbench:$VERSION .
docker run --rm -p 127.0.0.1:5000:5000 -v targetdesign-data:/data targetdesign-workbench:$VERSION
```

Then open <http://localhost:5000>. The port is published on the loopback interface only;
add `-p 5000:5000` instead if other machines should reach it.

With Compose:

```bash
VERSION="<version>"  # pyproject.toml [project].version
TAG="$VERSION" docker compose up --build
```

`docker-compose.yml` requires `TAG` so Compose fails with a clear message instead of silently
pulling a mismatched image tag. Run data remains in `./data`.

The native engine is compiled during the build and its unit tests are executed by `ctest`,
so a successful build already reports the engine version and passes the engine test suite.

Verification status: the `core` image is built, smoke-tested and published by
`.github/workflows/container.yml` on a GitHub runner, as
`ghcr.io/lnt-666/targetdesign-workbench:0.1.0` and `:latest`, together with
`ghcr.io/lnt-666/targetdesign-workbench:0.1.0-full` for the optional adapters. The package is
public, so anyone can pull the images without an account (verified anonymously on 2026-10-08:
`tags/list` answers 200 and all three tags resolve). The engine build and its `ctest` suite were
also checked on a Linux host with GCC 13.3 and CMake 3.28 (1/1 test passed,
`offtarget-engine 0.1.0 index-format=1`), and the web workbench answered HTTP 200 on `/`,
`/static/styles.css` and `/static/app.js`. Both targets are built and published by the same
workflow, `.github/workflows/container.yml`. Container builds are intentionally delegated to
GitHub runners; local Docker or Podman is not a verification requirement.

## Operating-system coverage

`.github/workflows/portability.yml` builds the same tree on `ubuntu-latest`, `macos-latest`
and `windows-latest`, and records per platform that the native engine configures and passes
its `ctest` suite with that operating system's own toolchain (GCC, Clang, MSVC), that every
shipped module compiles with every hard import declared, that `run_tests.py` passes, that the
batch CLI reads `sample_data/`, and that the local web workbench answers HTTP 200 - the same
assertion the container workflow makes on Linux. macOS is additionally cross-built for
x86_64, so Apple Silicon and Intel are both covered. The workflow needs no machine of any of
the three kinds: run it from Actions -> portability, or push a `v*` tag to attach the record
to a release.

The desktop GUI is the one surface a runner cannot exercise, because it has no display: the
Tk windows and the "open output directory" / "open log" buttons need a desktop session. The
platform mapping those buttons use is covered on every runner instead, by
`tests/test_open_path.py`.

## Data

Genomes, annotation files, built indexes and exported runs are read from and written to the
volume mounted at `/data` (the `TARGETDESIGN_DATA` environment variable). Keeping them
outside the image means a rebuilt image never discards a genome index.

## Trying it without a genome

The image also ships the small synthetic data set under `sample_data/`
(`sample_data/README.md` documents it). The web top bar has a **Load sample data** button
(`GET /api/sample`) that fills the Designer with a small target over the bundled 5 Mb genome,
and a **Help** link to the bundled English help pages rendered at `/help` and `/help/tutorial`.
Neither needs a download or any host installation.

## Image targets

| Target | Contents | Command |
| --- | --- | --- |
| `core` (default) | engine + web workbench + core Python stack (numpy, h5py, biopython, pyfaidx, openpyxl, pandas, scipy, scikit-learn, matplotlib) | `docker build -t tdb:$VERSION .` |
| `full` | `core` plus ViennaRNA, Cas-OFFinder, R + NuPoP (crispAI adapter) and a CPU PyTorch build | `docker build --target full -t tdb:$VERSION-full .` |

## What is not inside the image

- **Model weights.** Third-party deep-learning weights are not redistributed with the
  software; `docs/MODELS.md` documents how to obtain them and where to place them. Runs that
  use published rule sets need no weights.
- **Third-party trees.** The optional crispAI adapter is governed by upstream licences, so
  `external_tools/` is not shipped; `tools/build_crispai_env.sh` documents the setup, which
  the `full` target already installs the non-pip prerequisites for.
- **Genomes and indexes.** Download or mount them yourself; a genome FASTA is the only
  input a first run needs.

## Command-line access to the same container

```bash
docker run --rm -v targetdesign-data:/data targetdesign-workbench:$VERSION \
  python tools/batch_run.py --spec example/batch/example_batch.json
```

## Licence

MIT; see `LICENSE`.

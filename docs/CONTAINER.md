# Running TargetDesign-workbench in a container

The container image is the distributed stand-alone application: it starts the local web
workbench on `http://localhost:5000` and bundles the native C++20 indexed off-target
engine, so no Python installation and no third-party software installation is needed on
the host.

## Pulling the published image

The images are built, smoke-tested and published by the `container` workflow
(`.github/workflows/container.yml`) on GitHub's runners, so producing or obtaining them needs no
local Docker installation:

```bash
docker pull ghcr.io/lnt-666/targetdesign-workbench:latest       # default image
docker pull ghcr.io/lnt-666/targetdesign-workbench:0.1.0-full   # with the optional adapters
docker run --rm -p 127.0.0.1:5000:5000 ghcr.io/lnt-666/targetdesign-workbench:latest
```

Image visibility follows the repository: while the repository is private the packages are private
too, so they must be switched to public (GitHub -> the package page -> Package settings -> Change
visibility) before someone without repository access can pull them.
## Requirements

- Docker Engine 24 or newer (Docker Desktop on Windows and macOS), or Podman with the
  `podman build` / `podman run` equivalents.
- About 4 GB of free disk space for the default image, more for `--target full`.
- The image is built on Ubuntu 24.04 with Python 3.12, GCC 13 and CMake 3.28: the toolchain
  this project is verified against.

## Build and run

```bash
docker build -t targetdesign-workbench:0.1.0 .
docker run --rm -p 127.0.0.1:5000:5000 -v targetdesign-data:/data targetdesign-workbench:0.1.0
```

Then open <http://localhost:5000>. The port is published on the loopback interface only;
add `-p 5000:5000` instead if other machines should reach it.

With Compose:

```bash
docker compose up --build
```

`docker-compose.yml` uses the same defaults and keeps run data in `./data`.

The native engine is compiled during the build and its unit tests are executed by `ctest`,
so a successful build already reports the engine version and passes the engine test suite.

Verification status: the engine build and its `ctest` suite were checked on a Linux host
with GCC 13.3 and CMake 3.28 (1/1 test passed, `offtarget-engine 0.1.0 index-format=1`), and the
web workbench was started on the same host and answered HTTP 200 on `/`, `/static/styles.css`
and `/static/app.js`. The image itself has not been built yet, because neither this
workstation nor the lab server has Docker or Podman installed.

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
| `core` (default) | engine + web workbench + core Python stack (numpy, h5py, biopython, pyfaidx, openpyxl, pandas, scipy, scikit-learn, matplotlib) | `docker build -t tdb:0.1.0 .` |
| `full` | `core` plus ViennaRNA, Cas-OFFinder, R + NuPoP (crispAI adapter) and a CPU PyTorch build | `docker build --target full -t tdb:0.1.0-full .` |

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
docker run --rm -v targetdesign-data:/data targetdesign-workbench:0.1.0 \
  python tools/batch_run.py --spec example/batch/example_batch.json
```

## Licence

MIT; see `LICENSE`.

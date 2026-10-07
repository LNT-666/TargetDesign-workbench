# syntax=docker/dockerfile:1
#
# TargetDesign-workbench - stand-alone application container image.
#
#   docker build -t targetdesign-workbench:0.1.0 .                     # default (core) image
#   docker build --target full -t targetdesign-workbench:0.1.0-full .  # core + optional adapters
#
#   docker run --rm -p 127.0.0.1:5000:5000 -v targetdesign-data:/data targetdesign-workbench:0.1.0
#
# then open http://localhost:5000 . The container starts the local web workbench
# (webapp/app.py, Python standard library only) together with the native C++20
# indexed off-target engine. No registration, no login and no outbound network
# access are required for a run.
#
# The toolchain is the one this project was verified against on the lab server:
# Ubuntu 24.04, GCC 13.3, CMake 3.28, Python 3.12 (the engine builds clean and its
# ctest suite passes; the web workbench answers HTTP 200 on /).

# --------------------------------------------------------- native engine build
FROM ubuntu:24.04 AS engine-build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY native/ ./native/
RUN cmake -S native -B native/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DOFFTARGET_BUILD_TESTS=ON \
 && cmake --build native/build -j"$(nproc)" \
 && ctest --test-dir native/build --output-on-failure

# ------------------------------------------------------------- python runtime
FROM ubuntu:24.04 AS python-runtime
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl python3 python3-venv python3-pip \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv \
 && python -m pip install --upgrade pip
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install -r requirements.txt \
 && python -m pip install "pandas>=1.3" "scipy>=1.10" "scikit-learn>=1.0" "matplotlib>=3.5"
COPY . .
COPY --from=engine-build /src/native/bin/offtarget-engine /app/native/bin/offtarget-engine
RUN chmod +x /app/native/bin/offtarget-engine \
 && /app/native/bin/offtarget-engine --version \
 && python -m compileall -q webapp shared tools

# ------------------------------------------------- optional adapters (--target full)
# ViennaRNA (Cas13 RNA folding), Cas-OFFinder and R + NuPoP (crispAI adapter) are
# not pip-installable on every platform, and a CPU PyTorch build is needed by the
# deep-learning scoring ports. Model weights are not redistributed: see
# docs/MODELS.md for how to obtain them.
FROM python-runtime AS full
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV MAMBA_ROOT_PREFIX=/opt/mamba \
    CRISPAI_CASOFFINDER_DIR=/usr/local/bin
RUN apt-get update \
 && apt-get install -y --no-install-recommends bzip2 build-essential ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fL -o /usr/local/bin/micromamba \
      https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64 \
 && chmod +x /usr/local/bin/micromamba \
 && micromamba install -y -n base -c conda-forge -c bioconda \
      cas-offinder viennarna r-base bioconductor-nupop \
 && micromamba clean --all --yes \
 && ln -sf /opt/mamba/bin/cas-offinder /usr/local/bin/cas-offinder \
 && python -m pip install "torch>=2.0" --index-url https://download.pytorch.org/whl/cpu

# ------------------------------------------------- default image (last stage)
FROM python-runtime AS core
ENV TARGETDESIGN_DATA=/data
VOLUME ["/data"]
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD curl -fsS http://127.0.0.1:5000/ > /dev/null || exit 1
ENTRYPOINT ["python", "webapp/app.py", "--host", "0.0.0.0", "--port", "5000"]
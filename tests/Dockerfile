# Verifier image. Runs in its own container and sees only the paths declared in `artifacts`. It
# builds the agent's module from the collected sources and runs it twice, so it needs the Go
# toolchain as well as pytest.

FROM public.ecr.aws/docker/library/golang:1.23-bookworm@sha256:167053a2bb901972bf2c1611f8f52c44d5fe7e762e5cab213708d82c421614db AS go

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    GOROOT=/usr/local/go \
    PATH=/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=go /usr/local/go /usr/local/go

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

RUN useradd --create-home --uid 10001 --shell /bin/bash runner

# Warm the build user's standard library cache with the stub, so the agent's build compiles its
# own code only. The stub binary is discarded.
COPY --chown=10001:10001 skeleton /home/runner/warm
RUN su runner -s /bin/bash -c 'cd /home/runner/warm && GOCACHE=/home/runner/gocache GOFLAGS=-mod=mod GOPROXY=off GOTOOLCHAIN=local CGO_ENABLED=0 go build -o /tmp/warm . && rm -f /tmp/warm' \
    && rm -rf /home/runner/warm

# Artifact landing directories must exist before Harbor uploads the declared artifacts.
RUN mkdir -p /app/payroll /app/data /app/out

# The held-back month. Root-only and never present in any container the agent can reach.
COPY holdout /opt/holdout
RUN chmod 700 /opt/holdout && chmod 600 /opt/holdout/*

# Separate mode does not upload tests/ into the image, so the image has to own /tests itself.
COPY . /tests/

WORKDIR /app
